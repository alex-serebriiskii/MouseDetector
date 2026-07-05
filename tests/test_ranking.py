from mousedetector.ranking import append_result, aggregate

def test_append_and_aggregate(tmp_path):
    csv_path = str(tmp_path / "ranking.csv")
    append_result(csv_path, "2026-07-05", "kitchen", 28800, 100, 12.5, 40.0)
    append_result(csv_path, "2026-07-06", "kitchen", 28800, 140, 17.5, 60.0)
    append_result(csv_path, "2026-07-07", "bedroom", 28800, 20, 2.5, 8.0)
    agg = aggregate(csv_path)
    assert [d["label"] for d in agg] == ["kitchen", "bedroom"]   # sorted by events/hr desc
    kitchen = agg[0]
    assert kitchen["n_nights"] == 2
    assert abs(kitchen["mean_events_per_hour"] - 15.0) < 1e-9
    assert abs(kitchen["mean_active_s"] - 50.0) < 1e-9
    assert kitchen["rank"] == 1 and agg[1]["rank"] == 2
