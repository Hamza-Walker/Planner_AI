import asyncio
import logging
import os
import signal
import time
from collections import deque
from dataclasses import asdict
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from codecarbon import EmissionsTracker
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

from api.backend import BackendAPI
from energy.policy import EnergyPolicy
from energy.price_signal import EnergyStatus, fetch_energy_status

# Load environment variables from .env as early as possible,
# so os.getenv() reads the correct values during module initialization.
load_dotenv()

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

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

# -----------------------------
# Prometheus application metrics
# -----------------------------
REQUESTS_TOTAL = Counter(
    "planner_requests_total",
    "Total number of HTTP requests",
    ["endpoint", "status"],
)

REQUEST_LATENCY_SECONDS = Histogram(
    "planner_request_latency_seconds",
    "Request latency in seconds",
    ["endpoint"],
)

TASKS_EXTRACTED_TOTAL = Counter(
    "planner_tasks_extracted_total",
    "Total number of extracted tasks",
)

TASKS_SCHEDULED_TOTAL = Counter(
    "planner_tasks_scheduled_total",
    "Total number of scheduled tasks",
)

LLM_TIER_TOTAL = Counter(
    "planner_llm_tier_total",
    "Number of times a given LLM tier was used",
    ["tier"],
)

QUEUE_DEPTH = Gauge(
    "planner_queue_depth",
    "Current notes queue size",
)

# In-memory stores for recent tasks and schedules (best-effort, non-persistent).
# - recent_tasks holds up to last 50 tasks across calls
# - recent_schedules maps date_str -> schedule list
recent_tasks: deque = deque(maxlen=50)
recent_schedules: dict[str, list] = {}  # date_str -> schedule (list of blocks)

# Energy / carbon-aware processing settings
ENERGY_STATUS_URL = os.getenv("ENERGY_STATUS_URL", "").strip()
ENERGY_PRICE_THRESHOLD_EUR = float(os.getenv("ENERGY_PRICE_THRESHOLD_EUR", "0.70"))
ENERGY_FAIL_OPEN = os.getenv("ENERGY_FAIL_OPEN", "true").lower() in {"1", "true", "yes"}
QUEUE_POLL_INTERVAL_S = float(os.getenv("QUEUE_POLL_INTERVAL_S", "5"))

policy = EnergyPolicy(
    price_threshold_eur=ENERGY_PRICE_THRESHOLD_EUR,
    fail_open=ENERGY_FAIL_OPEN,
)

# Queue for deferred processing (when energy policy says "do not process now")
notes_queue: asyncio.Queue[str] = asyncio.Queue()


class NotesIn(BaseModel):
    notes: str


def _serialize_status(status: Optional[EnergyStatus]) -> Optional[dict]:
    """Convert EnergyStatus dataclass to JSON-serializable dict."""
    return asdict(status) if status is not None else None


async def _get_energy_status() -> Optional[EnergyStatus]:
    """
    Fetch current energy price/status from an external endpoint (if configured).
    Returns None if ENERGY_STATUS_URL is not set.
    """
    if not ENERGY_STATUS_URL:
        return None
    return await asyncio.to_thread(fetch_energy_status, ENERGY_STATUS_URL, 1.0)


async def _process_notes(notes: str, llm_tier: str) -> dict:
    """Run backend pipeline in a thread (FastAPI async-friendly)."""
    return await asyncio.to_thread(backend.submit_notes, notes, llm_tier)


# CodeCarbon tracker configuration
# NOTE: We initialize this after load_dotenv() so PROMETHEUS_PUSH_URL is correct.
PROMETHEUS_PUSH_URL = os.getenv("PROMETHEUS_PUSH_URL", "http://pushgateway:9091")
tracker = EmissionsTracker(
    project_name="planner-ai-backend",
    save_to_prometheus=True,
    prometheus_url=PROMETHEUS_PUSH_URL,
    log_level="error",
)


def _handle_shutdown(signum, frame) -> None:
    """
    Handle SIGTERM/SIGINT to stop CodeCarbon and push final metrics.
    This is best-effort; failures should not crash shutdown.
    """
    logger.info("Shutdown signal received, stopping CodeCarbon tracker")
    try:
        tracker.stop()
        time.sleep(5)  # allow HTTP push to complete
        logger.info("CodeCarbon metrics pushed successfully")
    except Exception as e:
        logger.error(f"Error stopping CodeCarbon tracker: {e}")


@app.on_event("startup")
async def startup() -> None:
    """FastAPI startup hook: start CodeCarbon and a background queue worker."""
    tracker.start()
    logger.info("CodeCarbon tracker started")

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    # Start the background queue worker
    asyncio.create_task(_queue_worker())


async def _queue_worker() -> None:
    """
    Background worker that processes queued notes when energy policy allows it.
    This is an in-memory queue; notes are dropped on failure (minimal strategy).
    """
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
            logger.exception("Failed to process queued notes")
        finally:
            notes_queue.task_done()


@app.post("/notes")
async def submit_notes(payload: NotesIn) -> dict:
    """
    Main endpoint: accepts freeform notes.
    If energy policy allows processing now -> process immediately.
    Otherwise -> enqueue notes for later processing.
    """
    status = await _get_energy_status()
    llm_tier = policy.llm_tier(status)

    start = time.time()
    LLM_TIER_TOTAL.labels(tier=llm_tier).inc()

    if policy.should_process_now(status):
        result = await _process_notes(payload.notes, llm_tier=llm_tier)

        # Normalize expected output keys from backend
        tasks_out = result.get("tasks", [])
        schedule_out = result.get("schedule", [])
        processed = result.get("tasks_processed", 0)

        TASKS_EXTRACTED_TOTAL.inc(len(tasks_out))
        TASKS_SCHEDULED_TOTAL.inc(len(schedule_out))
        REQUESTS_TOTAL.labels(endpoint="/notes", status="processed").inc()
        QUEUE_DEPTH.set(notes_queue.qsize())
        REQUEST_LATENCY_SECONDS.labels(endpoint="/notes").observe(time.time() - start)

        # Store tasks and schedule for later retrieval
        for task in tasks_out:
            task["created_at"] = datetime.now().isoformat()
            recent_tasks.appendleft(task)

        if schedule_out:
            date_str = datetime.now().strftime("%Y-%m-%d")
            recent_schedules[date_str] = schedule_out

        # Always return a stable response schema to the client
        return {
            "status": "processed",
            "llm_tier": llm_tier,
            "energy": _serialize_status(status),
            "tasks": tasks_out,
            "schedule": schedule_out,
            "tasks_processed": processed,
        }

    await notes_queue.put(payload.notes)
    REQUESTS_TOTAL.labels(endpoint="/notes", status="queued").inc()
    QUEUE_DEPTH.set(notes_queue.qsize())
    REQUEST_LATENCY_SECONDS.labels(endpoint="/notes").observe(time.time() - start)

    return {
        "status": "queued",
        "llm_tier": llm_tier,
        "queue_size": notes_queue.qsize(),
        "energy": _serialize_status(status),
    }


@app.get("/queue")
async def queue_status() -> dict:
    """Returns queue size + whether policy would process now."""
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
    schedule = recent_schedules.get(date, [])
    return {
        "date": date,
        "schedule": schedule,
    }


@app.get("/schedule")
async def get_today_schedule() -> dict:
    """Get today's schedule."""
    today = datetime.now().strftime("%Y-%m-%d")
    schedule = recent_schedules.get(today, [])
    return {
        "date": today,
        "schedule": schedule,
    }


@app.get("/metrics")
async def metrics() -> Response:
    """
    Prometheus scrape endpoint.
    """
    QUEUE_DEPTH.set(notes_queue.qsize())
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.get("/metrics/carbon")
async def get_carbon_metrics() -> dict:
    """
    Get carbon emissions metrics from CodeCarbon.

    NOTE: This uses private tracker attributes for convenience (best-effort).
    In production, prefer an official exporter or persisted metrics.
    """
    try:
        emissions = tracker._emissions if hasattr(tracker, "_emissions") else 0.0
        energy = tracker._total_energy.kWh if hasattr(tracker, "_total_energy") else 0.0
        duration = tracker._total_duration if hasattr(tracker, "_total_duration") else 0.0

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
