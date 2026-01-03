from datetime import datetime, time
from typing import Optional, List
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
