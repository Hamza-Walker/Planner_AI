from datetime import datetime, time
from planner_ai.models import Task, UserPreferences, DailyRoutine
from scheduling.scheduler import Scheduler
from storage.preferences_store import PreferencesStore
from storage.routine_store import RoutineStore

def test_uc4(tmp_path):
    prefs = PreferencesStore(path=str(tmp_path/"prefs.json"))
    prefs.save(UserPreferences(focus_start=time(9,0), focus_end=time(12,0)))
    routine = RoutineStore(path=str(tmp_path/"routine.json"))
    routine.save(DailyRoutine())
    scheduler = Scheduler(prefs, routine)
    tasks = [Task(title="A", estimated_duration_min=30)]
    out = scheduler.schedule(tasks, day=datetime(2026,1,1))
    assert out