from __future__ import annotations

from datetime import datetime, time
from typing import Literal, Optional, List, Dict

from pydantic import BaseModel, Field, field_validator


class Task(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    category: str = "general"

    priority: int = Field(3, ge=1, le=5)
    estimated_duration_min: int = Field(30, ge=1)

    deadline: Optional[datetime] = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        v2 = v.strip()
        if not v2:
            raise ValueError("title must not be blank")
        return v2


class ScheduledTask(Task):
    # Optional kvôli testom / robustnosti (UC5 vytvára ScheduledTask priamo)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    calendar_event_id: Optional[str] = None


class DailyRoutine(BaseModel):
    """
    Keep as list of dicts to stay JSON-friendly and match existing stores/tests.
    Example item: {"start":"09:00","end":"10:00","reason":"meeting"}
    """
    blocked_slots: List[Dict[str, str]] = Field(default_factory=list)

    # (voliteľné) zachováme upstream "lunch" ako extra feature, neškodí testom
    lunch_start: time = Field(default_factory=lambda: time(12, 0))
    lunch_end: time = Field(default_factory=lambda: time(13, 0))


EnergyProfile = Literal["low", "balanced", "high"]


class UserPreferences(BaseModel):
    timezone: str = "Europe/Bratislava"
    energy_profile: EnergyProfile = "balanced"

    # testy očakávajú, že toto vieš nastaviť cez UserPreferences(focus_start=..., focus_end=...)
    focus_start: time = Field(default_factory=lambda: time(9, 0))
    focus_end: time = Field(default_factory=lambda: time(12, 0))

    # necháme tvoje meno poľa, aby ti sedeli existujúce časti projektu
    default_duration_min: int = Field(30, gt=0)

    routine: DailyRoutine = Field(default_factory=DailyRoutine)

    # (voliteľné) alias z upstreamu – užitočné, ale nič nerozbije
    @property
    def preferred_task_duration_min(self) -> int:
        return self.default_duration_min
