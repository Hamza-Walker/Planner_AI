from datetime import datetime, time
from typing import Optional, List, Tuple
from pydantic import BaseModel, Field


class Task(BaseModel):
    id: Optional[str] = None
    title: str
    description: Optional[str] = None

    category: Optional[str] = Field(
        default=None,
        description="work | personal | health | learning | other"
    )

    priority: Optional[int] = Field(
        default=3,
        ge=1,
        le=5,
        description="1 = highest, 5 = lowest"
    )

    estimated_duration_min: int = Field(
        default=30,
        gt=0
    )

    deadline: Optional[datetime] = None


class ScheduledTask(Task):
    start_time: datetime
    end_time: datetime
    calendar_event_id: Optional[str] = None


class UserPreferences(BaseModel):
    """User preferences for scheduling and energy-aware behavior."""
    
    focus_start: time = Field(
        default_factory=lambda: time(9, 0),
        description="Start of daily focus window"
    )
    focus_end: time = Field(
        default_factory=lambda: time(17, 0),
        description="End of daily focus window"
    )
    energy_profile: str = Field(
        default="balanced",
        description="low | balanced | high - affects model selection"
    )
    preferred_task_duration_min: int = Field(
        default=30,
        gt=0,
        description="Default task duration in minutes"
    )


class DailyRoutine(BaseModel):
    """User's daily routine with blocked time slots."""
    
    blocked_slots: List[Tuple[time, time]] = Field(
        default_factory=list,
        description="List of (start_time, end_time) tuples for blocked periods"
    )
    lunch_start: time = Field(
        default_factory=lambda: time(12, 0),
        description="Start of lunch break"
    )
    lunch_end: time = Field(
        default_factory=lambda: time(13, 0),
        description="End of lunch break"
    )
