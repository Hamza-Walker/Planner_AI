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
          - Place fixed-time tasks first.
          - Sort flexible tasks by priority/deadline.
          - Place flexible tasks in remaining slots.
        """
        if not tasks:
            return []

        prefs: UserPreferences = self.preferences_store.load()
        routine: DailyRoutine = self.routine_store.load()

        base_day = (day or datetime.utcnow()).date()
        window = self._focus_window(base_day, prefs.focus_start, prefs.focus_end)

        scheduled: list[ScheduledTask] = []
        occupied_ranges: list[tuple[datetime, datetime]] = []

        # 1. Separate Fixed vs Flexible
        fixed_tasks = []
        flexible_tasks = []
        for t in tasks:
            # Ensure it's a Task model
            task_model = t if isinstance(t, Task) else Task(**t)
            if task_model.fixed_time:
                fixed_tasks.append(task_model)
            else:
                flexible_tasks.append(task_model)

        # 2. Schedule Fixed Tasks
        for t in fixed_tasks:
            try:
                # Parse HH:MM
                h, m = map(int, t.fixed_time.split(':'))
                start_dt = datetime.combine(base_day, time(h, m))
                
                dur_min = int(t.estimated_duration_min or 30)
                end_dt = start_dt + timedelta(minutes=dur_min)
                
                scheduled.append(
                    ScheduledTask(
                        **t.model_dump(),
                        start_time=start_dt,
                        end_time=end_dt,
                    )
                )
                occupied_ranges.append((start_dt, end_dt))
            except ValueError:
                # Fallback to flexible if time parse fails
                flexible_tasks.append(t)

        # 3. Schedule Flexible Tasks
        ordered = self._order_tasks(flexible_tasks)
        cursor = window.start

        for t in ordered:
            dur_min = int(t.estimated_duration_min or 30)
            if dur_min <= 0:
                dur_min = 30

            start = self._next_available_start(cursor, dur_min, window, routine, occupied_ranges)
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
            occupied_ranges.append((start, end))

        # Sort by start time
        scheduled.sort(key=lambda x: x.start_time)
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
        occupied_ranges: list[tuple[datetime, datetime]] = None
    ) -> Optional[datetime]:
        """
        Find the next start time that fits into the window and does not overlap blocked slots.
        """
        candidate = max(cursor, window.start)
        occupied_ranges = occupied_ranges or []

        while True:
            end = candidate + timedelta(minutes=dur_min)
            if end > window.end:
                return None

            # Check routine blocks
            if self._overlaps_blocked(candidate, end, routine, candidate.date()):
                candidate = candidate + timedelta(minutes=15)
                continue
            
            # Check occupied ranges (fixed tasks or previously scheduled)
            overlap = False
            for o_start, o_end in occupied_ranges:
                if candidate < o_end and end > o_start:
                    overlap = True
                    # Jump to end of this block to save iterations
                    candidate = max(candidate + timedelta(minutes=15), o_end)
                    break
            
            if overlap:
                continue

            return candidate
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
