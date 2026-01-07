from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from planner_ai.models import ScheduledTask

logger = logging.getLogger(__name__)

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
except Exception:  # pragma: no cover
    build = None
    Credentials = None


class CalendarIntegration:
    def __init__(
        self, credentials: Optional[Credentials] = None, calendar_id: str = "primary"
    ):
        self.credentials = credentials
        self.calendar_id = calendar_id

    async def get_events(self, time_min: datetime, time_max: datetime) -> list[dict]:
        """
        Fetch existing events in a time range.

        Args:
            time_min: Start time (inclusive)
            time_max: End time (exclusive)

        Returns:
            List of event dictionaries
        """
        if build is None or self.credentials is None:
            logger.warning("Google Calendar API not available or credentials missing")
            return []

        try:
            service = build("calendar", "v3", credentials=self.credentials)

            # Call the Calendar API
            events_result = (
                service.events()
                .list(
                    calendarId=self.calendar_id,
                    timeMin=time_min.isoformat() + "Z",
                    timeMax=time_max.isoformat() + "Z",
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            return events_result.get("items", [])

        except Exception as e:
            logger.error(f"Failed to fetch calendar events: {e}")
            return []

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

        try:
            service = build("calendar", "v3", credentials=self.credentials)
        except Exception as e:
            logger.error(f"Failed to build Google Calendar service: {e}")
            return scheduled_tasks

        updated: list[ScheduledTask] = []
        
        # 1. Fetch Calendar Timezone
        # We need this to ensure that "13:00" means "13:00 in the user's calendar",
        # not "13:00 UTC" (which might be 8am or 9am for them).
        calendar_tz = "UTC"
        try:
             calendar_tz = self._get_calendar_timezone(service)
        except Exception:
             pass

        for task in scheduled_tasks:
            try:
                event_body = self._to_event(task, timezone=calendar_tz)

                if task.calendar_event_id:
                    try:
                        event = (
                            service.events()
                            .update(
                                calendarId=self.calendar_id,
                                eventId=task.calendar_event_id,
                                body=event_body,
                            )
                            .execute()
                        )
                        updated.append(
                            task.model_copy(
                                update={"calendar_event_id": event.get("id")}
                            )
                        )
                    except Exception as e:
                        # If update fails (e.g., event deleted), try insert?
                        # For now, just log and keep task as is, but maybe clear ID?
                        logger.warning(
                            f"Failed to update event {task.calendar_event_id}: {e}"
                        )
                        updated.append(task)
                else:
                    event = (
                        service.events()
                        .insert(
                            calendarId=self.calendar_id,
                            body=event_body,
                        )
                        .execute()
                    )
                    updated.append(
                        task.model_copy(update={"calendar_event_id": event.get("id")})
                    )
            except Exception as e:
                logger.error(f"Failed to sync task {task.title}: {e}")
                # Keep task unchanged on failure
                updated.append(task)

        return updated

    def _to_event(self, task: ScheduledTask, timezone: str = "UTC") -> dict:
        """
        Convert ScheduledTask to Google Calendar event resource.
        """
        description = task.description or ""
        if task.category:
            description = f"[{task.category}] {description}".strip()

        # Format as naive ISO string (YYYY-MM-DDTHH:MM:SS)
        # We strip tzinfo if present to ensure we send a "floating" time
        # paired with the explicit timeZone field.
        start_naive = task.start_time.replace(tzinfo=None).isoformat()
        end_naive = task.end_time.replace(tzinfo=None).isoformat()

        return {
            "summary": task.title,
            "description": description,
            "start": {
                "dateTime": start_naive,
                "timeZone": timezone
            },
            "end": {
                "dateTime": end_naive,
                "timeZone": timezone
            },
        }

    def _get_calendar_timezone(self, service) -> str:
        """
        Fetch the timezone of the target calendar.
        Defaults to 'UTC' if fetching fails.
        """
        try:
            calendar = service.calendars().get(calendarId=self.calendar_id).execute()
            return calendar.get("timeZone", "UTC")
        except Exception as e:
            logger.warning(f"Failed to fetch calendar timezone: {e}")
            return "UTC"

    async def update_event(self, event_id: str, patch_data: dict) -> dict:
        """
        Update an existing event with patch semantics.
        """
        if build is None or self.credentials is None:
            raise RuntimeError("Google Calendar API not available")

        # Running blocking call in executor if needed, but for now direct is ok 
        # as this is usually called from async loop wrapper or simple endpoint.
        # Actually Google client is blocking.
        
        service = build("calendar", "v3", credentials=self.credentials)
        updated_event = service.events().patch(
            calendarId=self.calendar_id,
            eventId=event_id,
            body=patch_data
        ).execute()
        return updated_event
