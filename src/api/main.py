import asyncio
import logging
import os
import signal
import time
from collections import deque
from dataclasses import asdict
from datetime import datetime
from typing import Optional, List
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from codecarbon import EmissionsTracker

from api.backend import BackendAPI
from energy.policy import EnergyPolicy
from energy.price_signal import EnergyStatus, fetch_energy_status

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# CodeCarbon tracker configuration
PROMETHEUS_PUSH_URL = os.getenv("PROMETHEUS_PUSH_URL", "http://pushgateway:9091")
tracker = EmissionsTracker(
    project_name="planner-ai-backend",
    save_to_prometheus=True,
    prometheus_url=PROMETHEUS_PUSH_URL,
    log_level="error"
)
load_dotenv()
app = FastAPI(title="Planner AI", version="0.8.0")

# CORS middleware for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

backend = BackendAPI()

# In-memory store for recent tasks and schedules (last 50)
recent_tasks: deque = deque(maxlen=50)
recent_schedules: dict = {}  # date_str -> schedule


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

notes_queue: asyncio.Queue[str] = asyncio.Queue()


def _serialize_status(status: Optional[EnergyStatus]) -> Optional[dict]:
    return asdict(status) if status is not None else None


async def _get_energy_status() -> Optional[EnergyStatus]:
    if not ENERGY_STATUS_URL:
        return None
    return await asyncio.to_thread(fetch_energy_status, ENERGY_STATUS_URL, 1.0)


async def _process_notes(notes: str, llm_tier: str) -> dict:
    return await asyncio.to_thread(backend.submit_notes, notes, llm_tier)


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
    # Start CodeCarbon emissions tracking
    tracker.start()
    logger.info("CodeCarbon tracker started")
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)
    
    # Start the background queue worker
    asyncio.create_task(_queue_worker())


async def _queue_worker() -> None:
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
            await _process_notes(notes, llm_tier=policy.llm_tier(status))
        except Exception:
            # Minimal persistence strategy for now: drop on failure (can be replaced by a durable queue).
            logger.exception("Failed to process queued notes")
        finally:
            notes_queue.task_done()


@app.post("/notes")
async def submit_notes(payload: NotesIn) -> dict:
    status = await _get_energy_status()
    llm_tier = policy.llm_tier(status)

    if policy.should_process_now(status):
        result = await _process_notes(payload.notes, llm_tier=llm_tier)
        
        # Store tasks and schedule for later retrieval
        if "tasks" in result and result["tasks"]:
            for task in result["tasks"]:
                task["created_at"] = datetime.now().isoformat()
                recent_tasks.appendleft(task)
        if "schedule" in result and result["schedule"]:
            date_str = datetime.now().strftime("%Y-%m-%d")
            recent_schedules[date_str] = result["schedule"]
        
        return {
            "status": "processed",
            "llm_tier": llm_tier,
            "energy": _serialize_status(status),
            **result,
        }

    await notes_queue.put(payload.notes)
    return {
        "status": "queued",
        "llm_tier": llm_tier,
        "queue_size": notes_queue.qsize(),
        "energy": _serialize_status(status),
    }


@app.get("/queue")
async def queue_status() -> dict:
    status = await _get_energy_status()
    return {
        "queue_size": notes_queue.qsize(),
        "process_now": policy.should_process_now(status),
        "llm_tier": policy.llm_tier(status),
        "energy": _serialize_status(status),
    }


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint for container orchestration."""
    return {
        "status": "healthy",
        "profile": os.getenv("DEPLOYMENT_PROFILE", "unknown"),
        "queue_size": notes_queue.qsize(),
    }


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
        emissions = tracker._emissions if hasattr(tracker, '_emissions') else 0.0
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
