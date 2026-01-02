from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time
from typing import Optional

from planner_ai.models import Task, ScheduledTask, UserPreferences, DailyRoutine
from storage.preferences_store import PreferencesStore
from storage.routine_store import RoutineStore


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime


class Scheduler:
    def __init__(
        self,
        preferences_store: Optional[PreferencesStore] = None,
        routine_store: Optional[RoutineStore] = None,
    ):
        self.preferences_store = preferences_store or PreferencesStore()
        self.routine_store = routine_store or RoutineStore()

    def schedule(self, tasks: list[Task], day: Optional[datetime] = None) -> list[ScheduledTask]:
        """
        Schedule tasks into time slots (UC4).
        Greedy approach:
          - Sort by priority (asc), then deadline (asc), then duration (desc).
          - Place into the focus window for the chosen day.
        """
        if not tasks:
            return []

        prefs: UserPreferences = self.preferences_store.load()
        routine: DailyRoutine = self.routine_store.load()

        base_day = (day or datetime.utcnow()).date()
        window = self._focus_window(base_day, prefs.focus_start, prefs.focus_end)

        ordered = self._order_tasks(tasks)
        scheduled: list[ScheduledTask] = []

        cursor = window.start

        for t in ordered:
            dur_min = int(t.estimated_duration_min or 30)
            if dur_min <= 0:
                dur_min = 30

            start = self._next_available_start(cursor, dur_min, window, routine)
            if start is None:
                break

            end = start + timedelta(minutes=dur_min)
            cursor = end

            scheduled.append(
                ScheduledTask(
                    **t.model_dump(),
                    start_time=start,
                    end_time=end,
                )
            )

        return scheduled

    def _order_tasks(self, tasks: list[Task]) -> list[Task]:
        def sort_key(t: Task):
            pr = t.priority if t.priority is not None else 3
            dl = t.deadline or datetime.max
            dur = t.estimated_duration_min or 30
            return (pr, dl, -dur)

        normalized = [t if isinstance(t, Task) else Task(**t) for t in tasks]
        return sorted(normalized, key=sort_key)

    def _focus_window(self, day, start_t: time, end_t: time) -> TimeWindow:
        start_dt = datetime.combine(day, start_t)
        end_dt = datetime.combine(day, end_t)
        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(hours=8)
        return TimeWindow(start=start_dt, end=end_dt)

    def _next_available_start(
        self,
        cursor: datetime,
        dur_min: int,
        window: TimeWindow,
        routine: DailyRoutine,
    ) -> Optional[datetime]:
        """
        Find the next start time that fits into the window and does not overlap blocked slots.
        """
        candidate = max(cursor, window.start)

        while True:
            end = candidate + timedelta(minutes=dur_min)
            if end > window.end:
                return None

            if not self._overlaps_blocked(candidate, end, routine, candidate.date()):
                return candidate

            # Move forward in small increments to escape blocked slots
            candidate = candidate + timedelta(minutes=15)

    def _overlaps_blocked(self, start: datetime, end: datetime, routine: DailyRoutine, day) -> bool:
        """
        Check overlap with blocked slots in routine.
        blocked_slots are stored as list of (time, time).
        """
        try:
            for slot in routine.blocked_slots:
                t1, t2 = slot
                b_start = datetime.combine(day, t1)
                b_end = datetime.combine(day, t2)
                if b_end <= b_start:
                    continue

                # Overlap test
                if start < b_end and end > b_start:
                    return True
            return False
        except Exception:
            return False
