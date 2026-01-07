import asyncio
import logging
import time
import os
from typing import Optional
from datetime import datetime

from api import state
from api.routers.notes import _process_notes, _serialize_status, _get_energy_status
from integration.calendar_integration import CalendarIntegration
from planner_ai.models import ScheduledTask

# Re-use policy from state or create a local reference if preferred,
# but best to use the one in dependencies or state.
# Since workers run in background, dependency injection isn't as straightforward.
# We'll use the global instances in state.py (which are populated on startup).
from api.state import (
    durable_queue,
    google_auth_store,
    notes_queue,
    recent_tasks,
    recent_schedules,
)
from energy.policy import EnergyPolicy

logger = logging.getLogger(__name__)

# Config
ENERGY_PRICE_THRESHOLD_EUR = float(os.getenv("ENERGY_PRICE_THRESHOLD_EUR", "0.70"))
ENERGY_FAIL_OPEN = os.getenv("ENERGY_FAIL_OPEN", "true").lower() in {"1", "true", "yes"}
QUEUE_POLL_INTERVAL_S = float(os.getenv("QUEUE_POLL_INTERVAL_S", "5"))
STALE_RECOVERY_INTERVAL_S = float(os.getenv("STALE_RECOVERY_INTERVAL_S", "60"))
DEFAULT_USER_ID = "default"

policy = EnergyPolicy(
    price_threshold_eur=ENERGY_PRICE_THRESHOLD_EUR,
    fail_open=ENERGY_FAIL_OPEN,
)


async def _durable_queue_worker() -> None:
    """Background worker that processes items from the durable queue."""
    logger.info("Durable queue worker started")

    while True:
        try:
            # Check if there are pending items
            # Access global state via the imported module variables
            if state.durable_queue is None:
                await asyncio.sleep(QUEUE_POLL_INTERVAL_S)
                continue

            pending_count = await state.durable_queue.get_pending_count()
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
            item = await state.durable_queue.dequeue()
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
                        state.recent_tasks.appendleft(task)
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
                                    "estimated_duration": s.get(
                                        "estimated_duration_min", 30
                                    ),
                                },
                            }
                        )
                    state.recent_schedules[date_str] = {"slots": slots}
                    logger.info(
                        f"Stored schedule with {len(slots)} slots for {date_str}"
                    )

                # Sync to Google Calendar if possible
                if (
                    "schedule" in result
                    and result["schedule"]
                    and state.google_auth_store
                ):
                    try:
                        credentials = await state.google_auth_store.get_credentials(
                            DEFAULT_USER_ID
                        )
                        if credentials:
                            logger.info("Syncing schedule to Google Calendar...")

                            # Convert JSON result back to ScheduledTask objects
                            task_objects = []
                            # result["schedule"] is a list of task dicts
                            for task_item in result["schedule"]:
                                try:
                                    s_time = task_item.get("start_time")
                                    e_time = task_item.get("end_time")

                                    # Handle string to datetime conversion
                                    if isinstance(s_time, str):
                                        s_time = datetime.fromisoformat(s_time)
                                    if isinstance(e_time, str):
                                        e_time = datetime.fromisoformat(e_time)

                                    t = ScheduledTask(
                                        title=task_item.get("title", "Untitled"),
                                        description=task_item.get("description"),
                                        category=task_item.get("category"),
                                        priority=task_item.get("priority", 3),
                                        estimated_duration_min=task_item.get(
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

                            cal_integration = CalendarIntegration(
                                credentials=credentials
                            )
                            # Run sync in thread as it uses blocking Http requests
                            synced_tasks = await asyncio.to_thread(
                                cal_integration.sync, task_objects
                            )
                            logger.info(
                                f"Synced {len(synced_tasks)} tasks to Google Calendar"
                            )

                    except Exception as e:
                        logger.error(f"Failed to auto-sync to calendar: {e}")

                # Mark as completed
                await state.durable_queue.complete(
                    item_id=item.id,
                    result=result,
                    energy_price_eur=status.electricity_price_eur if status else None,
                    solar_available=status.solar_available if status else None,
                    llm_tier=llm_tier,
                )
                logger.info(f"Successfully processed queued item {item.id}")

            except Exception as e:
                logger.exception(f"Failed to process queued item {item.id}: {e}")
                new_status = await state.durable_queue.fail(item.id, str(e))
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

        if state.durable_queue is None:
            continue

        try:
            recovered = await state.durable_queue.recover_stale(timeout_minutes=5)
            if recovered > 0:
                logger.warning(f"Recovered {recovered} stale items")
        except Exception as e:
            logger.error(f"Error in stale recovery worker: {e}")


async def _queue_worker() -> None:
    """Legacy in-memory queue worker (used when USE_DURABLE_QUEUE=false)."""
    logger.info("In-memory queue worker started")

    while True:
        if state.notes_queue.empty():
            await asyncio.sleep(QUEUE_POLL_INTERVAL_S)
            continue

        status = await _get_energy_status()
        if not policy.should_process_now(status):
            await asyncio.sleep(QUEUE_POLL_INTERVAL_S)
            continue

        notes = await state.notes_queue.get()
        try:
            result = await _process_notes(notes, llm_tier=policy.llm_tier(status))

            # Store tasks and schedule
            if "tasks" in result and result["tasks"]:
                for task in result["tasks"]:
                    task["created_at"] = datetime.now().isoformat()
                    state.recent_tasks.appendleft(task)
            if "schedule" in result and result["schedule"]:
                date_str = datetime.now().strftime("%Y-%m-%d")
                # Convert schedule list to format expected by frontend
                schedule_list = result["schedule"]
                slots = []
                for s in schedule_list:
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
                                "estimated_duration": s.get(
                                    "estimated_duration_min", 30
                                ),
                            },
                        }
                    )
                state.recent_schedules[date_str] = {"slots": slots}

        except Exception:
            logger.exception("Failed to process queued notes")
        finally:
            state.notes_queue.task_done()
