from datetime import datetime
from planner_ai.models import ScheduledTask
from integration.calendar_integration import CalendarIntegration

def test_uc5_noop():
    cal = CalendarIntegration(credentials=None)
    tasks = [ScheduledTask(title="X", start_time=datetime(2026,1,1,9,0), end_time=datetime(2026,1,1,9,30))]
    out = cal.sync(tasks)
    assert out[0].calendar_event_id is None