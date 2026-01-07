import asyncio
import logging
import os
import signal
import time
import math
import random
from collections import deque
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Optional, List
from dotenv import load_dotenv
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from fastapi import Response
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from codecarbon import EmissionsTracker
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
from google_auth_oauthlib.flow import Flow
from api.backend import BackendAPI
from energy.policy import EnergyPolicy
from energy.price_signal import EnergyStatus, fetch_energy_status
from storage import db
from storage.durable_queue import DurableQueue
from storage.google_auth import GoogleAuthStore
from integration.calendar_integration import CalendarIntegration
from planner_ai.models import ScheduledTask

# Logging configuration
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# CodeCarbon tracker configuration
PROMETHEUS_PUSH_URL = os.getenv("PROMETHEUS_PUSH_URL", "")
tracker = EmissionsTracker(
    project_name="planner-ai-backend",
    save_to_prometheus=bool(PROMETHEUS_PUSH_URL),
    prometheus_url=PROMETHEUS_PUSH_URL or "http://localhost:9091",
    log_level="error",
)
load_dotenv()

# Google Auth Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
)
# Scopes must match what we requested in Google Console
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# Hardcoded single user ID
DEFAULT_USER_ID = "default"

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

# Durable queue instance (initialized in startup)
durable_queue: Optional[DurableQueue] = None

# Google Auth Store instance
google_auth_store: Optional[GoogleAuthStore] = None

# Feature flag for durable queue (can be disabled via env var)
USE_DURABLE_QUEUE = os.getenv("USE_DURABLE_QUEUE", "true").lower() in {
    "1",
    "true",
    "yes",
}
STALE_RECOVERY_INTERVAL_S = float(os.getenv("STALE_RECOVERY_INTERVAL_S", "60"))


class NotesIn(BaseModel):
    notes: str


class MoveRequestIn(BaseModel):
    task_id: str
    new_start: str  # ISO string
    new_end: str    # ISO string
    source: str     # 'planner' or 'google'


class CreateTaskIn(BaseModel):
    title: str
    description: Optional[str] = ""
    start_time: str # ISO
    end_time: str   # ISO
    priority: int = 3
    category: str = "work"


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

# In-memory storage for recent tasks (for display purposes)
recent_tasks: deque = deque(maxlen=100)

# In-memory storage for recent schedules (keyed by date string)
recent_schedules: dict = {}


def _serialize_status(status: Optional[EnergyStatus]) -> Optional[dict]:
    return asdict(status) if status is not None else None


async def _get_energy_status() -> Optional[EnergyStatus]:
    if not ENERGY_STATUS_URL:
        return None
    return await asyncio.to_thread(fetch_energy_status, ENERGY_STATUS_URL, 1.0)

# ============================================================================
# Google OAuth2 Endpoints - MOVED TO BOTTOM
# ============================================================================



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
    global durable_queue, google_auth_store

    # Initialize DB connection
    await db.init_db_pool()
    await db.init_schema()

    # Initialize Durable Queue
    if USE_DURABLE_QUEUE:
        durable_queue = DurableQueue()
        # Start background workers...
        asyncio.create_task(_durable_queue_worker())
        asyncio.create_task(_stale_recovery_worker())
    else:
        # Start legacy in-memory worker
        asyncio.create_task(_queue_worker())

    # Initialize Google Auth Store
    google_auth_store = GoogleAuthStore()

    # Start CodeCarbon tracking if not already started
    try:
        tracker.start()
        logger.info("CodeCarbon tracker started")
    except Exception as e:
        logger.error(f"Failed to start CodeCarbon tracker: {e}")


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
                logger.debug(
                    f"Energy conditions not favorable, waiting... ({pending_count} items pending)"
                )
                await asyncio.sleep(QUEUE_POLL_INTERVAL_S)
                continue

            # Dequeue and process
            item = await durable_queue.dequeue()
            if item is None:
                await asyncio.sleep(QUEUE_POLL_INTERVAL_S)
                continue

            llm_tier = policy.llm_tier(status)
            logger.info(
                f"Processing queued item {item.id} (attempt {item.attempts}, tier: {llm_tier})"
            )

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
                    # Convert schedule list to format expected by frontend
                    schedule_list = result["schedule"]
                    slots = []
                    for s in schedule_list:
                        # Extract start/end times as HH:MM strings
                        start_time = s.get("start_time", "")
                        end_time = s.get("end_time", "")
                        # Handle datetime objects or ISO strings
                        if hasattr(start_time, 'strftime'):
                            start_time = start_time.strftime("%H:%M")
                        elif isinstance(start_time, str) and "T" in start_time:
                            start_time = start_time.split("T")[1][:5]
                        if hasattr(end_time, 'strftime'):
                            end_time = end_time.strftime("%H:%M")
                        elif isinstance(end_time, str) and "T" in end_time:
                            end_time = end_time.split("T")[1][:5]
                        slots.append({
                            "start_time": start_time,
                            "end_time": end_time,
                            "task": {
                                "title": s.get("title", "Task"),
                                "category": s.get("category", "work"),
                                "priority": s.get("priority", 3),
                                "estimated_duration": s.get("estimated_duration_min", 30),
                            }
                        })
                    recent_schedules[date_str] = {"slots": slots}
                    logger.info(f"Stored schedule with {len(slots)} slots for {date_str}")

                
                # Sync to Google Calendar if possible
                if "schedule" in result and result["schedule"] and google_auth_store:
                    try:
                        credentials = await google_auth_store.get_credentials(DEFAULT_USER_ID)
                        if credentials:
                            logger.info("Syncing schedule to Google Calendar...")
                            
                            # Convert JSON result back to ScheduledTask objects
                            task_objects = []
                            # result["schedule"] is a list of task dicts
                            for item in result["schedule"]:
                                try:
                                    s_time = item.get("start_time")
                                    e_time = item.get("end_time")
                                    
                                    # Handle string to datetime conversion
                                    if isinstance(s_time, str):
                                        s_time = datetime.fromisoformat(s_time)
                                    if isinstance(e_time, str):
                                        e_time = datetime.fromisoformat(e_time)

                                    t = ScheduledTask(
                                        title=item.get("title", "Untitled"),
                                        description=item.get("description"),
                                        category=item.get("category"),
                                        priority=item.get("priority", 3),
                                        estimated_duration_min=item.get("estimated_duration_min", 30),
                                        start_time=s_time,
                                        end_time=e_time
                                    )
                                    task_objects.append(t)
                                except Exception as e:
                                    logger.warning(f"Skipping task for sync due to parse error: {e}")
                                
                            cal_integration = CalendarIntegration(credentials=credentials)
                            # Run sync in thread as it uses blocking Http requests
                            synced_tasks = await asyncio.to_thread(cal_integration.sync, task_objects)
                            logger.info(f"Synced {len(synced_tasks)} tasks to Google Calendar")
                            
                    except Exception as e:
                        logger.error(f"Failed to auto-sync to calendar: {e}")

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
                    logger.error(
                        f"Item {item.id} moved to dead letter queue after max retries"
                    )

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
                # Convert schedule list to format expected by frontend
                schedule_list = result["schedule"]
                slots = []
                for s in schedule_list:
                    start_time = s.get("start_time", "")
                    end_time = s.get("end_time", "")
                    # Handle datetime objects or ISO strings
                    if hasattr(start_time, 'strftime'):
                        start_time = start_time.strftime("%H:%M")
                    elif isinstance(start_time, str) and "T" in start_time:
                        start_time = start_time.split("T")[1][:5]
                    if hasattr(end_time, 'strftime'):
                        end_time = end_time.strftime("%H:%M")
                    elif isinstance(end_time, str) and "T" in end_time:
                        end_time = end_time.split("T")[1][:5]
                    slots.append({
                        "start_time": start_time,
                        "end_time": end_time,
                        "task": {
                            "title": s.get("title", "Task"),
                            "category": s.get("category", "work"),
                            "priority": s.get("priority", 3),
                            "estimated_duration": s.get("estimated_duration_min", 30),
                        }
                    })
                recent_schedules[date_str] = {"slots": slots}

        except Exception:

            logger.exception("Failed to process queued notes")
        finally:
            notes_queue.task_done()



# ============================================================================
# Google OAuth Endpoints
# ============================================================================


@app.get("/auth/google/login")
async def google_login():
    """Initiates the OAuth2 flow - redirects to Google."""
    if not Flow:
        raise HTTPException(status_code=501, detail="Google Auth not configured")

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google credentials not configured")

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=[
            "openid",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/userinfo.email",
        ],
        redirect_uri=GOOGLE_REDIRECT_URI,
    )

    authorization_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true"
    )

    # Redirect the browser directly to Google's OAuth page
    return Response(
        status_code=307,
        headers={"Location": authorization_url}
    )


@app.get("/auth/google/callback")
async def google_callback(code: str, error: Optional[str] = None):
    """Handles the OAuth2 callback."""
    if error:
        logger.error(f"OAuth error: {error}")
        return Response(
            status_code=307,
            headers={"Location": "http://localhost:3000/calendar?error=" + error},
        )

    if not Flow:
        return Response(
            status_code=307,
            headers={
                "Location": "http://localhost:3000/calendar?error=configuration_error"
            },
        )

    try:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=[
                "openid",
                "https://www.googleapis.com/auth/calendar.events",
                "https://www.googleapis.com/auth/calendar.readonly",
                "https://www.googleapis.com/auth/userinfo.email",
            ],
            redirect_uri=GOOGLE_REDIRECT_URI,
        )

        flow.fetch_token(code=code)

        credentials = flow.credentials

        # Get user email
        try:
            session = flow.authorized_session()
            user_info = session.get("https://www.googleapis.com/userinfo/v2/me").json()
            email = user_info.get("email")
        except Exception as e:
            logger.error(f"Failed to fetch user email: {e}")
            email = None

        if google_auth_store:
            # We assume credentials are google.oauth2.credentials.Credentials for this flow
            # Type ignore because Flow can theoretically return other types, but in this context it's OAuth2
            await google_auth_store.save_credentials(
                DEFAULT_USER_ID,
                credentials,
                str(email) if email else None,  # type: ignore
            )

        return Response(
            status_code=307,
            headers={"Location": "http://localhost:3000/calendar?success=true"},
        )

    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        return Response(
            status_code=307,
            headers={"Location": f"http://localhost:3000/calendar?error={str(e)}"},
        )


@app.get("/auth/google/status")
async def google_status() -> dict:
    """Check if user is connected."""
    if not google_auth_store:
        return {"connected": False, "error": "Auth store not initialized"}

    try:
        email = await google_auth_store.get_email(DEFAULT_USER_ID)
        creds = await google_auth_store.get_credentials(DEFAULT_USER_ID)
        return {"connected": creds is not None, "email": email}
    except Exception as e:
        logger.error(f"Error checking status: {e}")
        return {"connected": False, "error": str(e)}


@app.post("/auth/google/disconnect")
async def google_disconnect() -> dict:
    """Revoke and delete stored credentials."""
    if not google_auth_store:
        raise HTTPException(status_code=500, detail="Auth store not initialized")

    try:
        await google_auth_store.delete_credentials(DEFAULT_USER_ID)
        return {"status": "disconnected"}
    except Exception as e:
        logger.error(f"Error disconnecting: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/notes")
async def submit_notes(payload: NotesIn) -> dict:
    start = time.time()
    logger.info(f"Received notes submission: {payload.notes[:50]}...")

    status = await _get_energy_status()
    llm_tier = policy.llm_tier(status)

    # Count which LLM tier was selected for this request (best-effort)
    try:
        LLM_TIER_TOTAL.labels(tier=llm_tier).inc()
    except Exception:
        pass

    if policy.should_process_now(status):
        logger.info(f"Processing notes immediately (Tier: {llm_tier})")

        try:
            result = await _process_notes(payload.notes, llm_tier=llm_tier)
            logger.info(
                f"Notes processed successfully. Tasks found: {len(result.get('tasks', []))}"
            )
        except Exception as e:
            logger.error(f"Error processing notes: {e}")
            # Optionally count failures separately later; for now we keep behavior identical.
            raise

        # Store tasks and schedule for later retrieval
        tasks_out = result.get("tasks", []) or []
        schedule_out = result.get("schedule", []) or []

        if tasks_out:
            for task in tasks_out:
                task["created_at"] = datetime.now().isoformat()
                recent_tasks.appendleft(task)

        if schedule_out:
            date_str = datetime.now().strftime("%Y-%m-%d")
            # Convert schedule list to format expected by frontend
            slots = []
            for s in schedule_out:
                start_time = s.get("start_time", "")
                end_time = s.get("end_time", "")
                # Handle datetime objects or ISO strings
                if hasattr(start_time, 'strftime'):
                    start_time = start_time.strftime("%H:%M")
                elif isinstance(start_time, str) and "T" in start_time:
                    start_time = start_time.split("T")[1][:5]
                if hasattr(end_time, 'strftime'):
                    end_time = end_time.strftime("%H:%M")
                elif isinstance(end_time, str) and "T" in end_time:
                    end_time = end_time.split("T")[1][:5]
                slots.append({
                    "start_time": start_time,
                    "end_time": end_time,
                    "task": {
                        "title": s.get("title", "Task"),
                        "category": s.get("category", "work"),
                        "priority": s.get("priority", 3),
                        "estimated_duration": s.get("estimated_duration_min", 30),
                    }
                })
            recent_schedules[date_str] = {"slots": slots}
            logger.info(f"Stored schedule with {len(slots)} slots for {date_str}")

            # Sync to Google Calendar if possible
            if schedule_out and google_auth_store:
                try:
                    credentials = await google_auth_store.get_credentials(DEFAULT_USER_ID)
                    if credentials:
                        logger.info("Syncing schedule to Google Calendar (Immediate Mode)...")
                        
                        task_objects = []
                        for item in schedule_out:
                            try:
                                s_time = item.get("start_time")
                                e_time = item.get("end_time")
                                
                                # Handle string to datetime conversion
                                if isinstance(s_time, str):
                                    s_time = datetime.fromisoformat(s_time)
                                if isinstance(e_time, str):
                                    e_time = datetime.fromisoformat(e_time)

                                t = ScheduledTask(
                                    title=item.get("title", "Untitled"),
                                    description=item.get("description"),
                                    category=item.get("category"),
                                    priority=item.get("priority", 3),
                                    estimated_duration_min=item.get("estimated_duration_min", 30),
                                    start_time=s_time,
                                    end_time=e_time
                                )
                                task_objects.append(t)
                            except Exception as e:
                                logger.warning(f"Skipping task for sync due to parse error: {e}")
                        
                        cal_integration = CalendarIntegration(credentials=credentials)
                        synced_tasks = await asyncio.to_thread(cal_integration.sync, task_objects)
                        logger.info(f"Synced {len(synced_tasks)} tasks to Google Calendar")
                except Exception as e:
                    logger.error(f"Failed to auto-sync to calendar: {e}")

        # Prometheus counters (best-effort)

        try:
            REQUESTS_TOTAL.labels(endpoint="/notes", status="processed").inc()
            REQUEST_LATENCY_SECONDS.labels(endpoint="/notes").observe(
                time.time() - start
            )
            TASKS_EXTRACTED_TOTAL.inc(len(tasks_out))
            TASKS_SCHEDULED_TOTAL.inc(len(schedule_out))

            # Queue depth gauge (durable vs in-memory)
            if USE_DURABLE_QUEUE and durable_queue is not None:
                QUEUE_DEPTH.set(await durable_queue.get_pending_count())
            else:
                QUEUE_DEPTH.set(notes_queue.qsize())
        except Exception:
            pass

        # Force update of carbon metrics (best-effort)
        try:
            if hasattr(tracker, "flush"):
                tracker.flush()
        except Exception:
            pass

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

        # Prometheus counters (best-effort)
        try:
            REQUESTS_TOTAL.labels(endpoint="/notes", status="queued").inc()
            REQUEST_LATENCY_SECONDS.labels(endpoint="/notes").observe(
                time.time() - start
            )
            QUEUE_DEPTH.set(pending_count)
        except Exception:
            pass

        return {
            "status": "queued",
            "queue_item_id": item_id,
            "llm_tier": llm_tier,
            "queue_size": pending_count,
            "queue_type": "durable",
            "energy": _serialize_status(status),
        }

    # Fallback to in-memory queue
    await notes_queue.put(payload.notes)

    # Prometheus counters (best-effort)
    try:
        REQUESTS_TOTAL.labels(endpoint="/notes", status="queued").inc()
        REQUEST_LATENCY_SECONDS.labels(endpoint="/notes").observe(time.time() - start)
        QUEUE_DEPTH.set(notes_queue.qsize())
    except Exception:
        pass

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


@app.get("/metrics")
async def metrics() -> Response:
    """
    Prometheus scrape endpoint.
    """
    try:
        if USE_DURABLE_QUEUE and durable_queue is not None:
            QUEUE_DEPTH.set(await durable_queue.get_pending_count())
        else:
            QUEUE_DEPTH.set(notes_queue.qsize())
    except Exception:
        pass

    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


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
async def get_schedule(start_date: Optional[str] = None, end_date: Optional[str] = None) -> dict:
    """
    Get schedule for a date range.
    Defaults to today if no dates provided.
    Merges internally scheduled tasks with Google Calendar events if connected.
    """
    if not start_date:
        start_date = datetime.now().strftime("%Y-%m-%d")
    if not end_date:
        end_date = start_date

    # Parse dates
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    all_slots = []

    # 1. Get local/LLM-generated schedule
    # Iterate through days in range
    current = start_dt
    while current <= end_dt:
        d_str = current.strftime("%Y-%m-%d")
        stored_data = recent_schedules.get(d_str, {"slots": []})
        
        # Add date context to slots if missing and flatten
        day_slots = stored_data.get("slots", [])
        for slot in day_slots:
            # Check if start_time is just HH:MM
            st = slot.get("start_time")
            et = slot.get("end_time")
            
            # Create full ISO string
            if st and len(st) == 5:
                slot["start_iso"] = f"{d_str}T{st}:00"
            if et and len(et) == 5:
                slot["end_iso"] = f"{d_str}T{et}:00"
                
            slot["source"] = "planner"
            # Ensure task has an ID for frontend drag-and-drop
            if "task" in slot:
                if "id" not in slot["task"]:
                    slot["task"]["id"] = slot["task"].get("title", f"local-{d_str}-{st}")

            all_slots.append(slot)
            
        current = current + timedelta(days=1)
    
    # 2. Fetch from Google Calendar if connected
    if google_auth_store:
        try:
            creds = await google_auth_store.get_credentials(DEFAULT_USER_ID)
            if creds:
                integration = CalendarIntegration(creds)
                
                # Fetch range
                events = await integration.get_events(start_dt, end_dt)
                
                # Transform Google Events to Frontend Slots
                for e in events:
                    if e.get("status") == "cancelled":
                        continue
                        
                    start = e.get("start", {})
                    end = e.get("end", {})
                    
                    start_raw = start.get("dateTime") or start.get("date")
                    end_raw = end.get("dateTime") or end.get("date")
                    
                    if not start_raw: 
                        continue

                    # For all-day events (YYYY-MM-DD), make them valid ranges
                    if len(start_raw) == 10:
                        start_iso = f"{start_raw}T00:00:00"
                    else:
                        start_iso = start_raw
                        
                    if end_raw and len(end_raw) == 10:
                        end_iso = f"{end_raw}T23:59:59"
                    elif end_raw:
                        end_iso = end_raw
                    else:
                        end_iso = start_iso # Fallback

                    # Determine HH:MM for legacy support (optional)
                    start_hhmm = start_iso.split("T")[1][:5] if "T" in start_iso else "00:00"
                    end_hhmm = end_iso.split("T")[1][:5] if "T" in end_iso else "23:59"

                    # Avoid duplicates with local scheduler
                    # (Simple check could be improved)
                    is_duplicate = any(
                        s.get("start_iso") == start_iso and 
                        s["task"]["title"] == e.get("summary") 
                        for s in all_slots
                    )
                    
                    if not is_duplicate:
                        all_slots.append({
                            "start_time": start_hhmm,
                            "end_time": end_hhmm,
                            "start_iso": start_iso,
                            "end_iso": end_iso,
                            "source": "google",
                            "task": {
                                "id": e.get("id"),
                                "title": e.get("summary", "(No Title)"),
                                "category": "work", # default
                                "priority": 3,
                                "estimated_duration": 60,
                                "description": e.get("description", "")
                            }
                        })
                        
        except Exception as err:
             logger.error(f"Error merging Google Calendar events: {err}")

    # Return structure
    return {
        "range": {
            "start": start_date,
            "end": end_date
        },
        "slots": all_slots
    }


@app.get("/metrics/carbon")
async def get_carbon_metrics() -> dict:
    """Get carbon emissions metrics from CodeCarbon."""
    try:
        emissions = 0.0
        energy = 0.0
        duration = 0.0

        # Get energy consumption (available while tracking)
        if hasattr(tracker, "_total_energy") and tracker._total_energy is not None:
            if hasattr(tracker._total_energy, "kWh"):
                energy = float(tracker._total_energy.kWh)

        # Calculate duration using monotonic time (CodeCarbon uses time.monotonic for _start_time)
        if hasattr(tracker, "_start_time") and tracker._start_time is not None:
            import time as time_module

            duration = time_module.monotonic() - tracker._start_time

        # Estimate emissions from energy
        # Use average carbon intensity of ~0.4 kg CO2/kWh (global average)
        # This is a reasonable estimate when real-time data isn't available
        if energy > 0:
            emissions = energy * 0.4

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
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true",
        )

    try:
        items = await durable_queue.get_recent_items(limit=limit, status=status)
        return {
            "items": [
                {
                    "id": item.id,
                    "notes": item.notes[:100] + "..."
                    if len(item.notes) > 100
                    else item.notes,
                    "status": item.status,
                    "attempts": item.attempts,
                    "max_attempts": item.max_attempts,
                    "last_error": item.last_error,
                    "created_at": item.created_at.isoformat()
                    if item.created_at
                    else None,
                    "completed_at": item.completed_at.isoformat()
                    if item.completed_at
                    else None,
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
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true",
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
            "processing_started_at": item.processing_started_at.isoformat()
            if item.processing_started_at
            else None,
            "completed_at": item.completed_at.isoformat()
            if item.completed_at
            else None,
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
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true",
        )

    try:
        items = await durable_queue.get_dead_letter_items(limit=limit)
        return {
            "items": [
                {
                    "id": item.id,
                    "notes": item.notes[:100] + "..."
                    if len(item.notes) > 100
                    else item.notes,
                    "attempts": item.attempts,
                    "last_error": item.last_error,
                    "created_at": item.created_at.isoformat()
                    if item.created_at
                    else None,
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
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true",
        )

    try:
        success = await durable_queue.retry_dead_item(item_id)
        if not success:
            raise HTTPException(
                status_code=400, detail="Item not found or not in dead status"
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
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true",
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


@app.post("/schedule/move")
async def move_task_schedule(payload: MoveRequestIn):
    """
    Handle drag-and-drop 'move' events.
    For 'planner' tasks: updates recent_schedules (best effort).
    For 'google' tasks: updates Google Calendar event.
    """
    logger.info(f"Move request: {payload}")
    
    # 1. Google Calendar Move
    if payload.source == "google" and google_auth_store:
        creds = await google_auth_store.get_credentials(DEFAULT_USER_ID)
        if creds:
            integration = CalendarIntegration(creds)
            # We need to construct a partial event update
            # Start/End in Google format
            # Basic implementation: just assume DateTime
            event_patch = {
                "start": {"dateTime": payload.new_start},
                "end": {"dateTime": payload.new_end}
            }
            try:
                # We need the update_event method in integration
                updated = await integration.update_event(payload.task_id, event_patch)
                return {"status": "success", "updated": True}
            except Exception as e:
                logger.error(f"Failed to move Google event: {e}")
                raise HTTPException(status_code=500, detail="Failed to update Google Calendar")

    # 2. Local Planner Move
    elif payload.source == "planner":
        try:
            new_dt = datetime.fromisoformat(payload.new_start)
            new_date_key = new_dt.strftime("%Y-%m-%d")
            new_hhmm = new_dt.strftime("%H:%M")
            new_end_dt = datetime.fromisoformat(payload.new_end)
            new_end_hhmm = new_end_dt.strftime("%H:%M")
        except ValueError:
             raise HTTPException(status_code=400, detail="Invalid ISO format")

        target_id = payload.task_id
        logger.info(f"Looking for local task with ID/Title: {target_id}")

        found = False
        task_data = None
        
        # Scan (inefficient but okay for small memory store)
        for d_key, data in recent_schedules.items():
            slots = data.get("slots", [])
            for i, slot in enumerate(slots):
                t_ctx = slot.get("task", {})
                # Comparison: Check ID first, then Title
                # Note: get_schedule now ensures 'id' exists equal to title for local tasks
                if t_ctx.get("id") == target_id or t_ctx.get("title") == target_id:
                     task_data = slot
                     # Remove from old location
                     del slots[i]
                     found = True
                     break
            if found:
                break
        
        if found and task_data:
            # Add to new date
            if new_date_key not in recent_schedules:
                recent_schedules[new_date_key] = {"slots": []}
            
            # Update times
            task_data["start_time"] = new_hhmm
            task_data["end_time"] = new_end_hhmm
            task_data["start_iso"] = payload.new_start
            task_data["end_iso"] = payload.new_end
            
            recent_schedules[new_date_key]["slots"].append(task_data)
            # Re-sort?
            recent_schedules[new_date_key]["slots"].sort(key=lambda x: x["start_time"])
            
            return {"status": "success", "moved": True}
        
        return {"status": "warning", "message": "Task not found locally (persistence limited)"}

    return {"status": "ignored"}


@app.delete("/tasks/queue")
async def clear_queue_items():
    """Clear all items from the dashboard list (recent_tasks)."""
    recent_tasks.clear()
    return {"status": "cleared"}


@app.post("/tasks/create")
async def create_manual_task(payload: CreateTaskIn):
    """
    Manually create a scheduled task.
    """
    try:
        start_dt = datetime.fromisoformat(payload.start_time)
        end_dt = datetime.fromisoformat(payload.end_time)
        
        date_key = start_dt.strftime("%Y-%m-%d")
        
        # Determine duration
        duration_min = int((end_dt - start_dt).total_seconds() / 60)
        
        new_task = {
            "start_time": start_dt.strftime("%H:%M"),
            "end_time": end_dt.strftime("%H:%M"),
            "start_iso": payload.start_time,
            "end_iso": payload.end_time,
            "source": "planner",
            "task": {
                "id": payload.title, # Simple ID
                "title": payload.title,
                "description": payload.description,
                "category": payload.category,
                "priority": payload.priority,
                "estimated_duration": duration_min,
                # "fixed_time": start_dt.strftime("%H:%M") 
            }
        }

        if date_key not in recent_schedules:
            recent_schedules[date_key] = {"slots": []}
            
        recent_schedules[date_key]["slots"].append(new_task)
        recent_schedules[date_key]["slots"].sort(key=lambda x: x["start_time"])
        
        # Also add to recent tasks list
        recent_tasks.appendleft({
            "title": payload.title,
            "category": payload.category,
            "priority": payload.priority,
            "estimated_duration_min": duration_min,
            "created_at": datetime.now().isoformat()
        })

        # Sync to Google Calendar if connected
        if google_auth_store:
            creds = await google_auth_store.get_credentials(DEFAULT_USER_ID)
            if creds:
                try:
                    integration = CalendarIntegration(creds)
                    # Convert raw dict to ScheduledTask model for the sync method
                    task_obj = ScheduledTask(
                        title=payload.title,
                        description=payload.description or "",
                        category=payload.category,
                        priority=payload.priority,
                        estimated_duration_min=duration_min,
                        start_time=start_dt,
                        end_time=end_dt
                    )
                    synced_tasks = await asyncio.to_thread(integration.sync, [task_obj])
                    logger.info(f"Manual task synced to Google Calendar: {len(synced_tasks)}")
                except Exception as e:
                    logger.warning(f"Failed to sync manual task to Google Calendar: {e}")
        
        return {"status": "created", "task": new_task}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid format: {e}")
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/queue/items/{item_id}")
async def delete_queue_item(item_id: str):
    """Permanently remove a queue item."""
    if not USE_DURABLE_QUEUE or durable_queue is None:
        raise HTTPException(status_code=400, detail="Durable Queue not enabled")
    
    deleted = await durable_queue.delete_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Item not found or could not be deleted")
    
    return {"status": "deleted", "id": item_id}

