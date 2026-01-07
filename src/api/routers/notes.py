import asyncio
import logging
import time
import os
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from prometheus_client import Counter, Histogram, Gauge

from api.backend import BackendAPI
from api import state
from api.dependencies import get_durable_queue, get_google_auth_store, get_energy_policy
from api.metrics import (
    REQUESTS_TOTAL,
    REQUEST_LATENCY_SECONDS,
    TASKS_EXTRACTED_TOTAL,
    TASKS_SCHEDULED_TOTAL,
    LLM_TIER_TOTAL,
    QUEUE_DEPTH,
)
from energy.policy import EnergyPolicy
from energy.price_signal import EnergyStatus, fetch_energy_status
from storage.durable_queue import DurableQueue
from storage.google_auth import GoogleAuthStore
from integration.calendar_integration import CalendarIntegration
from planner_ai.models import ScheduledTask

router = APIRouter()
logger = logging.getLogger(__name__)
backend = BackendAPI()

# Config
ENERGY_STATUS_URL = os.getenv("ENERGY_STATUS_URL", "").strip()
DEFAULT_USER_ID = "default"
USE_DURABLE_QUEUE = os.getenv("USE_DURABLE_QUEUE", "true").lower() in {
    "1",
    "true",
    "yes",
}


class NotesIn(BaseModel):
    notes: str


def _serialize_status(status: Optional[EnergyStatus]) -> Optional[dict]:
    from dataclasses import asdict

    return asdict(status) if status is not None else None


async def _get_energy_status() -> Optional[EnergyStatus]:
    if not ENERGY_STATUS_URL:
        return None
    return await asyncio.to_thread(fetch_energy_status, ENERGY_STATUS_URL, 1.0)


async def _process_notes(notes: str, llm_tier: str) -> dict:
    # Note: backend.submit_notes accepts llm_tier as a keyword argument,
    # but we need to pass it correctly via asyncio.to_thread
    return await asyncio.to_thread(backend.submit_notes, notes, llm_tier=llm_tier)


@router.post("/notes")
async def submit_notes(
    payload: NotesIn,
    durable_queue: Optional[DurableQueue] = Depends(get_durable_queue),
    google_auth_store: Optional[GoogleAuthStore] = Depends(get_google_auth_store),
    policy: EnergyPolicy = Depends(get_energy_policy),
) -> dict:
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
                state.recent_tasks.appendleft(task)

        if schedule_out:
            date_str = datetime.now().strftime("%Y-%m-%d")
            # Convert schedule list to format expected by frontend
            slots = []
            for s in schedule_out:
                start_time = s.get("start_time", "")
                end_time = s.get("end_time", "")
                # Handle datetime objects or ISO strings
                if hasattr(start_time, "strftime"):
                    start_time = start_time.strftime("%H:%M")
                elif isinstance(start_time, str) and "T" in start_time:
                    start_time = start_time.split("T")[1][:5]
                if hasattr(end_time, "strftime"):
                    end_time = end_time.strftime("%H:%M")
                elif isinstance(end_time, str) and "T" in end_time:
                    end_time = end_time.split("T")[1][:5]
                slots.append(
                    {
                        "start_time": start_time,
                        "end_time": end_time,
                        "task": {
                            "title": s.get("title", "Task"),
                            "category": s.get("category", "work"),
                            "priority": s.get("priority", 3),
                            "estimated_duration": s.get("estimated_duration_min", 30),
                        },
                    }
                )
            state.recent_schedules[date_str] = {"slots": slots}
            logger.info(f"Stored schedule with {len(slots)} slots for {date_str}")

            # Sync to Google Calendar if possible
            if schedule_out and google_auth_store:
                try:
                    credentials = await google_auth_store.get_credentials(
                        DEFAULT_USER_ID
                    )
                    if credentials:
                        logger.info(
                            "Syncing schedule to Google Calendar (Immediate Mode)..."
                        )

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
                                    estimated_duration_min=item.get(
                                        "estimated_duration_min", 30
                                    ),
                                    start_time=s_time,
                                    end_time=e_time,
                                )
                                task_objects.append(t)
                            except Exception as e:
                                logger.warning(
                                    f"Skipping task for sync due to parse error: {e}"
                                )

                        cal_integration = CalendarIntegration(credentials=credentials)
                        synced_tasks = await asyncio.to_thread(
                            cal_integration.sync, task_objects
                        )
                        logger.info(
                            f"Synced {len(synced_tasks)} tasks to Google Calendar"
                        )
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
                QUEUE_DEPTH.set(state.notes_queue.qsize())
        except Exception:
            pass

        # Force update of carbon metrics (best-effort)
        try:
            if hasattr(state.tracker, "flush"):
                state.tracker.flush()
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
    await state.notes_queue.put(payload.notes)

    # Prometheus counters (best-effort)
    try:
        REQUESTS_TOTAL.labels(endpoint="/notes", status="queued").inc()
        REQUEST_LATENCY_SECONDS.labels(endpoint="/notes").observe(time.time() - start)
        QUEUE_DEPTH.set(state.notes_queue.qsize())
    except Exception:
        pass

    return {
        "status": "queued",
        "llm_tier": llm_tier,
        "queue_size": state.notes_queue.qsize(),
        "queue_type": "in-memory",
        "energy": _serialize_status(status),
    }
