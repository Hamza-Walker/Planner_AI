import asyncio
import logging
import os
import signal
import time
import math
import random
from collections import deque
from dataclasses import asdict
from datetime import datetime
from typing import Optional, List
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from codecarbon import EmissionsTracker

from api.backend import BackendAPI
from energy.policy import EnergyPolicy
from energy.price_signal import EnergyStatus, fetch_energy_status
from storage import db
from storage.durable_queue import DurableQueue

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# CodeCarbon tracker configuration
PROMETHEUS_PUSH_URL = os.getenv("PROMETHEUS_PUSH_URL", "")
tracker = EmissionsTracker(
    project_name="planner-ai-backend",
    save_to_prometheus=bool(PROMETHEUS_PUSH_URL),
    prometheus_url=PROMETHEUS_PUSH_URL or "http://localhost:9091",
    log_level="error"
)
load_dotenv()
app = FastAPI(title="Planner AI", version="0.9.0")

# CORS middleware for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for dev/minikube environment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

backend = BackendAPI()

# In-memory store for recent tasks and schedules (last 50)
recent_tasks: deque = deque(maxlen=50)
recent_schedules: dict = {}  # date_str -> schedule

# Durable queue instance (initialized in startup)
durable_queue: Optional[DurableQueue] = None

# Feature flag for durable queue (can be disabled via env var)
USE_DURABLE_QUEUE = os.getenv("USE_DURABLE_QUEUE", "true").lower() in {"1", "true", "yes"}
STALE_RECOVERY_INTERVAL_S = float(os.getenv("STALE_RECOVERY_INTERVAL_S", "60"))


class NotesIn(BaseModel):
    notes: str


ENERGY_STATUS_URL = os.getenv("ENERGY_STATUS_URL", "").strip()
ENERGY_PRICE_THRESHOLD_EUR = float(os.getenv("ENERGY_PRICE_THRESHOLD_EUR", "0.70"))
ENERGY_FAIL_OPEN = os.getenv("ENERGY_FAIL_OPEN", "true").lower() in {"1", "true", "yes"}
QUEUE_POLL_INTERVAL_S = float(os.getenv("QUEUE_POLL_INTERVAL_S", "5"))

policy = EnergyPolicy(
    price_threshold_eur=ENERGY_PRICE_THRESHOLD_EUR,
    fail_open=ENERGY_FAIL_OPEN,
)

# Legacy in-memory queue (used when USE_DURABLE_QUEUE=false)
notes_queue: asyncio.Queue[str] = asyncio.Queue()


def _serialize_status(status: Optional[EnergyStatus]) -> Optional[dict]:
    return asdict(status) if status is not None else None


async def _get_energy_status() -> Optional[EnergyStatus]:
    if not ENERGY_STATUS_URL:
        return None
    return await asyncio.to_thread(fetch_energy_status, ENERGY_STATUS_URL, 1.0)


async def _process_notes(notes: str, llm_tier: str) -> dict:
    # Note: backend.submit_notes accepts llm_tier as a keyword argument, 
    # but we need to pass it correctly via asyncio.to_thread
    return await asyncio.to_thread(backend.submit_notes, notes, llm_tier=llm_tier)


def _handle_shutdown(signum, frame):
    """Handle SIGTERM/SIGINT to stop CodeCarbon and push final metrics."""
    logger.info("Shutdown signal received, stopping CodeCarbon tracker")
    try:
        tracker.stop()
        time.sleep(5)  # Allow HTTP push to complete
        logger.info("CodeCarbon metrics pushed successfully")
    except Exception as e:
        logger.error(f"Error stopping CodeCarbon tracker: {e}")


@app.on_event("startup")
async def startup() -> None:
    global durable_queue
    
    # Start CodeCarbon emissions tracking
    tracker.start()
    logger.info("CodeCarbon tracker started")
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)
    
    # Initialize database and durable queue if enabled
    if USE_DURABLE_QUEUE:
        try:
            logger.info("Initializing PostgreSQL connection pool...")
            await db.init_db_pool()
            
            logger.info("Initializing database schema...")
            await db.init_schema()
            
            durable_queue = DurableQueue()
            logger.info("Durable queue initialized successfully")
            
            # Start the durable queue worker
            asyncio.create_task(_durable_queue_worker())
            
            # Start the stale item recovery task
            asyncio.create_task(_stale_recovery_worker())
        except Exception as e:
            logger.error(f"Failed to initialize durable queue: {e}")
            logger.warning("Falling back to in-memory queue")
            durable_queue = None
            asyncio.create_task(_queue_worker())
    else:
        logger.info("Durable queue disabled, using in-memory queue")
        asyncio.create_task(_queue_worker())


@app.on_event("shutdown")
async def shutdown() -> None:
    """Graceful shutdown - close database connections."""
    logger.info("Shutting down...")
    
    if USE_DURABLE_QUEUE:
        try:
            await db.close_db_pool()
            logger.info("Database pool closed")
        except Exception as e:
            logger.error(f"Error closing database pool: {e}")


async def _durable_queue_worker() -> None:
    """Background worker that processes items from the durable queue."""
    logger.info("Durable queue worker started")
    
    while True:
        try:
            # Check if there are pending items
            if durable_queue is None:
                await asyncio.sleep(QUEUE_POLL_INTERVAL_S)
                continue
            
            pending_count = await durable_queue.get_pending_count()
            if pending_count == 0:
                await asyncio.sleep(QUEUE_POLL_INTERVAL_S)
                continue
            
            # Check energy status
            status = await _get_energy_status()
            if not policy.should_process_now(status):
                logger.debug(f"Energy conditions not favorable, waiting... ({pending_count} items pending)")
                await asyncio.sleep(QUEUE_POLL_INTERVAL_S)
                continue
            
            # Dequeue and process
            item = await durable_queue.dequeue()
            if item is None:
                await asyncio.sleep(QUEUE_POLL_INTERVAL_S)
                continue
            
            llm_tier = policy.llm_tier(status)
            logger.info(f"Processing queued item {item.id} (attempt {item.attempts}, tier: {llm_tier})")
            
            try:
                result = await _process_notes(item.notes, llm_tier=llm_tier)
                
                # Store tasks and schedule
                if "tasks" in result and result["tasks"]:
                    for task in result["tasks"]:
                        task["created_at"] = datetime.now().isoformat()
                        task["queue_item_id"] = item.id
                        recent_tasks.appendleft(task)
                if "schedule" in result and result["schedule"]:
                    date_str = datetime.now().strftime("%Y-%m-%d")
                    recent_schedules[date_str] = result["schedule"]
                
                # Mark as completed
                await durable_queue.complete(
                    item_id=item.id,
                    result=result,
                    energy_price_eur=status.electricity_price_eur if status else None,
                    solar_available=status.solar_available if status else None,
                    llm_tier=llm_tier,
                )
                logger.info(f"Successfully processed queued item {item.id}")
                
            except Exception as e:
                logger.exception(f"Failed to process queued item {item.id}: {e}")
                new_status = await durable_queue.fail(item.id, str(e))
                if new_status == "dead":
                    logger.error(f"Item {item.id} moved to dead letter queue after max retries")
                    
        except Exception as e:
            logger.exception(f"Error in durable queue worker: {e}")
            await asyncio.sleep(QUEUE_POLL_INTERVAL_S)


async def _stale_recovery_worker() -> None:
    """Periodically recover items stuck in processing state."""
    logger.info("Stale recovery worker started")
    
    while True:
        await asyncio.sleep(STALE_RECOVERY_INTERVAL_S)
        
        if durable_queue is None:
            continue
        
        try:
            recovered = await durable_queue.recover_stale(timeout_minutes=5)
            if recovered > 0:
                logger.warning(f"Recovered {recovered} stale items")
        except Exception as e:
            logger.error(f"Error in stale recovery worker: {e}")


async def _queue_worker() -> None:
    """Legacy in-memory queue worker (used when USE_DURABLE_QUEUE=false)."""
    logger.info("In-memory queue worker started")
    
    while True:
        if notes_queue.empty():
            await asyncio.sleep(QUEUE_POLL_INTERVAL_S)
            continue

        status = await _get_energy_status()
        if not policy.should_process_now(status):
            await asyncio.sleep(QUEUE_POLL_INTERVAL_S)
            continue

        notes = await notes_queue.get()
        try:
            result = await _process_notes(notes, llm_tier=policy.llm_tier(status))
            
            # Store tasks and schedule
            if "tasks" in result and result["tasks"]:
                for task in result["tasks"]:
                    task["created_at"] = datetime.now().isoformat()
                    recent_tasks.appendleft(task)
            if "schedule" in result and result["schedule"]:
                date_str = datetime.now().strftime("%Y-%m-%d")
                recent_schedules[date_str] = result["schedule"]
                
        except Exception:
            logger.exception("Failed to process queued notes")
        finally:
            notes_queue.task_done()


@app.post("/notes")
async def submit_notes(payload: NotesIn) -> dict:
    logger.info(f"Received notes submission: {payload.notes[:50]}...")
    status = await _get_energy_status()
    llm_tier = policy.llm_tier(status)

    if policy.should_process_now(status):
        logger.info(f"Processing notes immediately (Tier: {llm_tier})")
        try:
            result = await _process_notes(payload.notes, llm_tier=llm_tier)
            logger.info(f"Notes processed successfully. Tasks found: {len(result.get('tasks', []))}")
        except Exception as e:
            logger.error(f"Error processing notes: {e}")
            raise
        
        # Store tasks and schedule for later retrieval
        if "tasks" in result and result["tasks"]:
            for task in result["tasks"]:
                task["created_at"] = datetime.now().isoformat()
                recent_tasks.appendleft(task)
        if "schedule" in result and result["schedule"]:
            date_str = datetime.now().strftime("%Y-%m-%d")
            recent_schedules[date_str] = result["schedule"]
        
        # Force update of carbon metrics
        if hasattr(tracker, 'flush'):
            tracker.flush()

        return {
            "status": "processed",
            "llm_tier": llm_tier,
            "energy": _serialize_status(status),
            **result,
        }

    # Queue the notes for later processing
    if USE_DURABLE_QUEUE and durable_queue is not None:
        # Use durable PostgreSQL-backed queue
        item_id = await durable_queue.enqueue(
            notes=payload.notes,
            energy_price_eur=status.electricity_price_eur if status else None,
            solar_available=status.solar_available if status else None,
            llm_tier=llm_tier,
        )
        pending_count = await durable_queue.get_pending_count()
        
        return {
            "status": "queued",
            "queue_item_id": item_id,
            "llm_tier": llm_tier,
            "queue_size": pending_count,
            "queue_type": "durable",
            "energy": _serialize_status(status),
        }
    else:
        # Fallback to in-memory queue
        await notes_queue.put(payload.notes)
        return {
            "status": "queued",
            "llm_tier": llm_tier,
            "queue_size": notes_queue.qsize(),
            "queue_type": "in-memory",
            "energy": _serialize_status(status),
        }


@app.get("/queue")
async def queue_status() -> dict:
    """Get queue status and energy information."""
    status = await _get_energy_status()
    
    if USE_DURABLE_QUEUE and durable_queue is not None:
        try:
            stats = await durable_queue.get_stats()
            return {
                "queue_type": "durable",
                "queue_size": stats["by_status"].get("pending", {}).get("count", 0),
                "processing": stats["by_status"].get("processing", {}).get("count", 0),
                "completed": stats["by_status"].get("completed", {}).get("count", 0),
                "failed": stats["by_status"].get("failed", {}).get("count", 0),
                "dead": stats["by_status"].get("dead", {}).get("count", 0),
                "total": stats["total"],
                "process_now": policy.should_process_now(status),
                "llm_tier": policy.llm_tier(status),
                "energy": _serialize_status(status),
            }
        except Exception as e:
            logger.error(f"Error getting queue stats: {e}")
            return {
                "queue_type": "durable",
                "error": str(e),
                "process_now": policy.should_process_now(status),
                "llm_tier": policy.llm_tier(status),
                "energy": _serialize_status(status),
            }
    else:
        return {
            "queue_type": "in-memory",
            "queue_size": notes_queue.qsize(),
            "process_now": policy.should_process_now(status),
            "llm_tier": policy.llm_tier(status),
            "energy": _serialize_status(status),
        }


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint for container orchestration."""
    health = {
        "status": "healthy",
        "profile": os.getenv("DEPLOYMENT_PROFILE", "unknown"),
        "queue_type": "durable" if USE_DURABLE_QUEUE and durable_queue else "in-memory",
    }
    
    if USE_DURABLE_QUEUE and durable_queue is not None:
        try:
            db_health = await db.health_check()
            health["database"] = db_health
            health["queue_size"] = await durable_queue.get_pending_count()
            if db_health["status"] != "healthy":
                health["status"] = "degraded"
        except Exception as e:
            health["status"] = "degraded"
            health["database"] = {"status": "error", "error": str(e)}
            health["queue_size"] = 0
    else:
        health["queue_size"] = notes_queue.qsize()
    
    return health


@app.get("/tasks")
async def get_tasks(limit: int = 20) -> dict:
    """Get recent extracted tasks."""
    tasks_list = list(recent_tasks)[:limit]
    return {
        "tasks": tasks_list,
        "total": len(recent_tasks),
    }


@app.get("/schedule/{date}")
async def get_schedule(date: str) -> dict:
    """Get schedule for a specific date (YYYY-MM-DD)."""
    schedule = recent_schedules.get(date, {})
    return {
        "date": date,
        "schedule": schedule,
    }


@app.get("/schedule")
async def get_today_schedule() -> dict:
    """Get today's schedule."""
    today = datetime.now().strftime("%Y-%m-%d")
    schedule = recent_schedules.get(today, {})
    return {
        "date": today,
        "schedule": schedule,
    }


@app.get("/metrics/carbon")
async def get_carbon_metrics() -> dict:
    """Get carbon emissions metrics from CodeCarbon."""
    try:
        # Get current emissions data from tracker
        emissions_raw = tracker._emissions if hasattr(tracker, '_emissions') else 0.0
        # Ensure emissions is a float (extract value if it's an object)
        emissions = float(emissions_raw) if not isinstance(emissions_raw, (int, float)) and hasattr(emissions_raw, "__float__") else float(emissions_raw) if isinstance(emissions_raw, (int, float, str)) else 0.0
            
        energy = tracker._total_energy.kWh if hasattr(tracker, '_total_energy') else 0.0
        duration = tracker._total_duration if hasattr(tracker, '_total_duration') else 0.0
        
        return {
            "emissions_kg": emissions,
            "emissions_g": emissions * 1000,
            "energy_kwh": energy,
            "duration_seconds": duration,
            "project_name": "planner-ai-backend",
        }
    except Exception as e:
        logger.warning(f"Could not retrieve carbon metrics: {e}")
        return {
            "emissions_kg": 0.0,
            "emissions_g": 0.0,
            "energy_kwh": 0.0,
            "duration_seconds": 0.0,
            "project_name": "planner-ai-backend",
            "error": str(e),
        }


# ============================================================================
# Queue Management Endpoints (Durable Queue Only)
# ============================================================================

@app.get("/queue/items")
async def get_queue_items(limit: int = 20, status: Optional[str] = None) -> dict:
    """
    Get recent queue items.
    
    Args:
        limit: Maximum number of items to return (default 20)
        status: Filter by status (pending, processing, completed, failed, dead)
    """
    if not USE_DURABLE_QUEUE or durable_queue is None:
        raise HTTPException(
            status_code=400,
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true"
        )
    
    try:
        items = await durable_queue.get_recent_items(limit=limit, status=status)
        return {
            "items": [
                {
                    "id": item.id,
                    "notes": item.notes[:100] + "..." if len(item.notes) > 100 else item.notes,
                    "status": item.status,
                    "attempts": item.attempts,
                    "max_attempts": item.max_attempts,
                    "last_error": item.last_error,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "completed_at": item.completed_at.isoformat() if item.completed_at else None,
                    "submitted_llm_tier": item.submitted_llm_tier,
                    "processed_llm_tier": item.processed_llm_tier,
                }
                for item in items
            ],
            "count": len(items),
        }
    except Exception as e:
        logger.error(f"Error getting queue items: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/queue/items/{item_id}")
async def get_queue_item(item_id: str) -> dict:
    """Get details of a specific queue item."""
    if not USE_DURABLE_QUEUE or durable_queue is None:
        raise HTTPException(
            status_code=400,
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true"
        )
    
    try:
        item = await durable_queue.get_item(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Queue item not found")
        
        return {
            "id": item.id,
            "notes": item.notes,
            "status": item.status,
            "attempts": item.attempts,
            "max_attempts": item.max_attempts,
            "last_error": item.last_error,
            "submitted_energy_price_eur": item.submitted_energy_price_eur,
            "submitted_solar_available": item.submitted_solar_available,
            "submitted_llm_tier": item.submitted_llm_tier,
            "processed_energy_price_eur": item.processed_energy_price_eur,
            "processed_solar_available": item.processed_solar_available,
            "processed_llm_tier": item.processed_llm_tier,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "processing_started_at": item.processing_started_at.isoformat() if item.processing_started_at else None,
            "completed_at": item.completed_at.isoformat() if item.completed_at else None,
            "worker_id": item.worker_id,
            "result": item.result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting queue item: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/queue/dead")
async def get_dead_letter_items(limit: int = 50) -> dict:
    """Get items in the dead letter queue (failed after max retries)."""
    if not USE_DURABLE_QUEUE or durable_queue is None:
        raise HTTPException(
            status_code=400,
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true"
        )
    
    try:
        items = await durable_queue.get_dead_letter_items(limit=limit)
        return {
            "items": [
                {
                    "id": item.id,
                    "notes": item.notes[:100] + "..." if len(item.notes) > 100 else item.notes,
                    "attempts": item.attempts,
                    "last_error": item.last_error,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in items
            ],
            "count": len(items),
        }
    except Exception as e:
        logger.error(f"Error getting dead letter items: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/queue/items/{item_id}/retry")
async def retry_dead_item(item_id: str) -> dict:
    """Retry a dead letter item (reset to pending status)."""
    if not USE_DURABLE_QUEUE or durable_queue is None:
        raise HTTPException(
            status_code=400,
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true"
        )
    
    try:
        success = await durable_queue.retry_dead_item(item_id)
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Item not found or not in dead status"
            )
        
        return {
            "status": "success",
            "message": f"Item {item_id} has been reset to pending",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying dead item: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/queue/purge")
async def purge_completed_items(older_than_hours: int = 24) -> dict:
    """Purge completed items older than the specified hours."""
    if not USE_DURABLE_QUEUE or durable_queue is None:
        raise HTTPException(
            status_code=400,
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true"
        )
    
    try:
        count = await durable_queue.purge_completed(older_than_hours=older_than_hours)
        return {
            "status": "success",
            "purged_count": count,
            "older_than_hours": older_than_hours,
        }
    except Exception as e:
        logger.error(f"Error purging completed items: {e}")
        raise HTTPException(status_code=500, detail=str(e))
