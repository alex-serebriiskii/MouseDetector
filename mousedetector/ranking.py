import csv
import os
from collections import defaultdict

FIELDS = ["date", "label", "duration_s", "events", "events_per_hour", "active_s"]

def append_result(csv_path, date, label, duration_s, events, events_per_hour, active_s):
    new = not os.path.exists(csv_path)
    parent = os.path.dirname(csv_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(csv_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({
            "date": date, "label": label, "duration_s": f"{duration_s:.1f}",
            "events": events, "events_per_hour": f"{events_per_hour:.3f}",
            "active_s": f"{active_s:.1f}",
        })

def aggregate(csv_path):
    groups = defaultdict(list)
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            groups[r["label"]].append(r)
    out = []
    for label, rs in groups.items():
        n = len(rs)
        out.append({
            "label": label,
            "n_nights": n,
            "mean_events_per_hour": sum(float(r["events_per_hour"]) for r in rs) / n,
            "mean_active_s": sum(float(r["active_s"]) for r in rs) / n,
        })
    out.sort(key=lambda d: d["mean_events_per_hour"], reverse=True)
    for i, d in enumerate(out, 1):
        d["rank"] = i
    return out
