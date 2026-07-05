def score_events(events, duration_s):
    n = len(events)
    active_s = float(sum(ev.end_s - ev.start_s for ev in events))
    hours = duration_s / 3600.0
    return {
        "events": n,
        "events_per_hour": (n / hours) if hours > 0 else 0.0,
        "active_s": active_s,
        "active_fraction": (active_s / duration_s) if duration_s > 0 else 0.0,
    }
