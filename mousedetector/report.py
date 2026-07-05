import os
import sys
from mousedetector.ranking import aggregate

def format_leaderboard(rows):
    lines = [f"{'rank':>4}  {'label':<20}  {'nights':>6}  {'events/hr':>9}  {'active_s':>8}"]
    for d in rows:
        lines.append(f"{d['rank']:>4}  {d['label']:<20}  {d['n_nights']:>6}  "
                     f"{d['mean_events_per_hour']:>9.2f}  {d['mean_active_s']:>8.1f}")
    return "\n".join(lines)

def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    csv_path = argv[0] if argv else os.path.expanduser("~/mouse-survey/ranking.csv")
    print(format_leaderboard(aggregate(csv_path)))

if __name__ == "__main__":
    main()
