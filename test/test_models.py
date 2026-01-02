from datetime import datetime
from planner_ai.models import Task, ScheduledTask, UserPreferences, DailyRoutine

def test_task_defaults():
    t = Task(title="Test")
    assert t.estimated_duration_min == 30

def test_scheduled_task():
    st = ScheduledTask(
        title="X",
        start_time=datetime(2026,1,1,9,0),
        end_time=datetime(2026,1,1,9,30),
    )
    assert st.start_time < st.end_time

def test_preferences():
    p = UserPreferences()
    assert p.energy_profile in {"low","balanced","high"}

def test_routine():
    r = DailyRoutine()
    assert isinstance(r.blocked_slots, list)