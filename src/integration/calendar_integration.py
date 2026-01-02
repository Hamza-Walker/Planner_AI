from __future__ import annotations

from typing import Optional

from planner_ai.models import ScheduledTask

try:
    from googleapiclient.discovery import build
except Exception:  # pragma: no cover
    build = None


class CalendarIntegration:
    def __init__(self, credentials=None, calendar_id: str = "primary"):
        self.credentials = credentials
        self.calendar_id = calendar_id

    def sync(self, scheduled_tasks: list[ScheduledTask]) -> list[ScheduledTask]:
        """
        Sync scheduled tasks to Google Calendar (UC5).
        - If calendar_event_id exists: update event
        - Otherwise: create event and store returned id
        Safe no-op if Google client is unavailable or credentials are missing.
        """
        if not scheduled_tasks:
            return []

        if build is None or self.credentials is None:
            return scheduled_tasks

        service = build("calendar", "v3", credentials=self.credentials)

        updated: list[ScheduledTask] = []
        for task in scheduled_tasks:
            try:
                event_body = self._to_event(task)

                if task.calendar_event_id:
                    event = (
                        service.events()
                        .update(
                            calendarId=self.calendar_id,
                            eventId=task.calendar_event_id,
                            body=event_body,
                        )
                        .execute()
                    )
                    updated.append(task.model_copy(update={"calendar_event_id": event.get("id")}))
                else:
                    event = (
                        service.events()
                        .insert(
                            calendarId=self.calendar_id,
                            body=event_body,
                        )
                        .execute()
                    )
                    updated.append(task.model_copy(update={"calendar_event_id": event.get("id")}))
            except Exception:
                # Keep task unchanged on failure
                updated.append(task)

        return updated

    def _to_event(self, task: ScheduledTask) -> dict:
        """
        Convert ScheduledTask to Google Calendar event resource.
        """
        description = task.description or ""
        if task.category:
            description = f"[{task.category}] {description}".strip()

        return {
            "summary": task.title,
            "description": description,
            "start": {"dateTime": task.start_time.isoformat()},
            "end": {"dateTime": task.end_time.isoformat()},
        }
