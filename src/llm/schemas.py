from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

class ExtractedTask(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    estimated_duration_min: int = Field(default=30, gt=0)
    deadline: Optional[datetime] = None

class TaskExtractionResult(BaseModel):
    tasks: List[ExtractedTask] = Field(default_factory=list)

class ClassifiedTask(BaseModel):
    title: str
    description: Optional[str] = None
    estimated_duration_min: int = Field(default=30, gt=0)
    deadline: Optional[datetime] = None

    category: str = Field(default="other")
    priority: int = Field(default=3, ge=1, le=5)

class TaskClassificationResult(BaseModel):
    tasks: List[ClassifiedTask] = Field(default_factory=list)
