from datetime import time
from storage.preferences_store import PreferencesStore
from planner_ai.models import UserPreferences

def test_preferences_roundtrip(tmp_path):
    store = PreferencesStore(path=str(tmp_path / "prefs.json"))
    prefs = UserPreferences(focus_start=time(8,0), focus_end=time(11,0))
    store.save(prefs)
    loaded = store.load()
    assert loaded.focus_start.hour == 8
    assert loaded.focus_end.hour == 11

def test_preferences_corrupted_file(tmp_path):
    p = tmp_path / "prefs.json"
    p.write_text("{not valid json")
    store = PreferencesStore(path=str(p))
    prefs = store.load()
    assert isinstance(prefs, UserPreferences)