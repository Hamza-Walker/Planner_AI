import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from api import state
from api.dependencies import get_google_auth_store
from integration.calendar_integration import CalendarIntegration
from storage.google_auth import GoogleAuthStore
from planner_ai.models import ScheduledTask

router = APIRouter()
logger = logging.getLogger(__name__)

# Constants
DEFAULT_USER_ID = "default"


class MoveRequestIn(BaseModel):
    task_id: str
    new_start: str  # ISO string
    new_end: str  # ISO string
    source: str  # 'planner' or 'google'


class CreateTaskIn(BaseModel):
    title: str
    description: Optional[str] = ""
    start_time: str  # ISO
    end_time: str  # ISO
    priority: int = 3
    category: str = "work"


@router.get("/tasks")
async def get_tasks(limit: int = 20) -> dict:
    """Get recent extracted tasks."""
    tasks_list = list(state.recent_tasks)[:limit]
    return {
        "tasks": tasks_list,
        "total": len(state.recent_tasks),
    }


@router.delete("/tasks/queue")
async def clear_queue_items():
    """Clear all items from the dashboard list (recent_tasks)."""
    state.recent_tasks.clear()
    return {"status": "cleared"}


@router.get("/schedule/{date}")
async def get_schedule_by_date(date: str) -> dict:
    """Get schedule for a specific date (YYYY-MM-DD)."""
    schedule = state.recent_schedules.get(date, {})
    return {
        "date": date,
        "schedule": schedule,
    }


@router.get("/schedule")
async def get_schedule(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    google_auth_store: Optional[GoogleAuthStore] = Depends(get_google_auth_store),
) -> dict:
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
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(
            hour=0, minute=0, second=0
        )
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid date format. Use YYYY-MM-DD"
        )

    all_slots = []

    # 1. Get local/LLM-generated schedule
    # Iterate through days in range
    current = start_dt
    while current <= end_dt:
        d_str = current.strftime("%Y-%m-%d")
        stored_data = state.recent_schedules.get(d_str, {"slots": []})

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
                    slot["task"]["id"] = slot["task"].get(
                        "title", f"local-{d_str}-{st}"
                    )

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
                        end_iso = start_iso  # Fallback

                    # Determine HH:MM for legacy support (optional)
                    start_hhmm = (
                        start_iso.split("T")[1][:5] if "T" in start_iso else "00:00"
                    )
                    end_hhmm = end_iso.split("T")[1][:5] if "T" in end_iso else "23:59"

                    # Avoid duplicates with local scheduler
                    # (Simple check could be improved)
                    is_duplicate = any(
                        s.get("start_iso") == start_iso
                        and s["task"]["title"] == e.get("summary")
                        for s in all_slots
                    )

                    if not is_duplicate:
                        all_slots.append(
                            {
                                "start_time": start_hhmm,
                                "end_time": end_hhmm,
                                "start_iso": start_iso,
                                "end_iso": end_iso,
                                "source": "google",
                                "task": {
                                    "id": e.get("id"),
                                    "title": e.get("summary", "(No Title)"),
                                    "category": "work",  # default
                                    "priority": 3,
                                    "estimated_duration": 60,
                                    "description": e.get("description", ""),
                                },
                            }
                        )

        except Exception as err:
            logger.error(f"Error merging Google Calendar events: {err}")

    # Return structure
    return {"range": {"start": start_date, "end": end_date}, "slots": all_slots}


@router.post("/schedule/move")
async def move_task_schedule(
    payload: MoveRequestIn,
    google_auth_store: Optional[GoogleAuthStore] = Depends(get_google_auth_store),
):
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
                "end": {"dateTime": payload.new_end},
            }
            try:
                # We need the update_event method in integration
                updated = await integration.update_event(payload.task_id, event_patch)
                return {"status": "success", "updated": True}
            except Exception as e:
                logger.error(f"Failed to move Google event: {e}")
                raise HTTPException(
                    status_code=500, detail="Failed to update Google Calendar"
                )

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
        for d_key, data in state.recent_schedules.items():
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
            if new_date_key not in state.recent_schedules:
                state.recent_schedules[new_date_key] = {"slots": []}

            # Update times
            task_data["start_time"] = new_hhmm
            task_data["end_time"] = new_end_hhmm
            task_data["start_iso"] = payload.new_start
            task_data["end_iso"] = payload.new_end

            state.recent_schedules[new_date_key]["slots"].append(task_data)
            # Re-sort?
            state.recent_schedules[new_date_key]["slots"].sort(
                key=lambda x: x["start_time"]
            )

            return {"status": "success", "moved": True}

        return {
            "status": "warning",
            "message": "Task not found locally (persistence limited)",
        }

    return {"status": "ignored"}


@router.post("/tasks/create")
async def create_manual_task(
    payload: CreateTaskIn,
    google_auth_store: Optional[GoogleAuthStore] = Depends(get_google_auth_store),
):
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
                "id": payload.title,  # Simple ID
                "title": payload.title,
                "description": payload.description,
                "category": payload.category,
                "priority": payload.priority,
                "estimated_duration": duration_min,
                # "fixed_time": start_dt.strftime("%H:%M")
            },
        }

        if date_key not in state.recent_schedules:
            state.recent_schedules[date_key] = {"slots": []}

        state.recent_schedules[date_key]["slots"].append(new_task)
        state.recent_schedules[date_key]["slots"].sort(key=lambda x: x["start_time"])

        # Also add to recent tasks list
        state.recent_tasks.appendleft(
            {
                "title": payload.title,
                "category": payload.category,
                "priority": payload.priority,
                "estimated_duration_min": duration_min,
                "created_at": datetime.now().isoformat(),
            }
        )

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
                        end_time=end_dt,
                    )
                    synced_tasks = await asyncio.to_thread(integration.sync, [task_obj])
                    logger.info(
                        f"Manual task synced to Google Calendar: {len(synced_tasks)}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to sync manual task to Google Calendar: {e}"
                    )

        return {"status": "created", "task": new_task}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid format: {e}")
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        raise HTTPException(status_code=500, detail=str(e))
