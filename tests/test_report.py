from mousedetector.report import format_leaderboard

def test_format_leaderboard_order_and_content():
    rows = [
        {"rank": 1, "label": "kitchen", "n_nights": 2, "mean_events_per_hour": 15.0, "mean_active_s": 50.0},
        {"rank": 2, "label": "bedroom", "n_nights": 1, "mean_events_per_hour": 2.5, "mean_active_s": 8.0},
    ]
    text = format_leaderboard(rows)
    lines = text.splitlines()
    assert len(lines) == 3            # header + 2 rows
    assert "kitchen" in lines[1] and lines[1].strip().startswith("1")
    assert "bedroom" in lines[2] and lines[2].strip().startswith("2")
