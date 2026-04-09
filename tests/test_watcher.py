# tests/test_watcher.py
from backend.watcher import is_meeting_running, MEETING_PROCESSES

def test_meeting_processes_list_not_empty():
    assert len(MEETING_PROCESSES) > 0
    assert "zoom" in MEETING_PROCESSES

def test_is_meeting_running_returns_bool():
    result = is_meeting_running()
    assert isinstance(result, bool)
