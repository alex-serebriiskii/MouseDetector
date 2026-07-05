from mousedetector.detect import Event
from mousedetector.score import score_events

def test_score_basic():
    evs = [Event(1.0, 1.5, 0.9), Event(10.0, 10.5, 0.8)]  # 2 events, 1.0s active
    s = score_events(evs, duration_s=3600.0)
    assert s["events"] == 2
    assert abs(s["events_per_hour"] - 2.0) < 1e-9
    assert abs(s["active_s"] - 1.0) < 1e-9
    assert abs(s["active_fraction"] - (1.0 / 3600.0)) < 1e-9

def test_score_empty():
    s = score_events([], duration_s=3600.0)
    assert s["events"] == 0 and s["events_per_hour"] == 0.0 and s["active_s"] == 0.0
