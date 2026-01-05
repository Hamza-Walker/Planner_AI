import pytest
from planner_ai.models import Task

def test_task_invalid_duration():
    with pytest.raises(Exception):
        Task(title="Bad", estimated_duration_min=-5)

def test_task_empty_title():
    with pytest.raises(Exception):
        Task(title="")