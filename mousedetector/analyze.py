import argparse
import json
import os
import sys
from mousedetector.audio import load_wav, save_wav
from mousedetector.detect import bandpass, frame_energy, detect_events
from mousedetector.score import score_events
from mousedetector.ranking import append_result

DEFAULT_LOW, DEFAULT_HIGH, DEFAULT_K, DEFAULT_TOP_N, PAD_S = 2000.0, 12000.0, 5.0, 20, 0.5

def parse_recording_name(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    parts = stem.split("_")
    if len(parts) >= 3:
        return parts[0], "_".join(parts[1:-1])
    return stem, stem

def _meta(wav_path):
    side = wav_path + ".json"
    if os.path.exists(side):
        with open(side) as f:
            return json.load(f)
    return None

def analyze_file(wav_path, ranking_csv, results_dir, evidence_dir,
                 low_hz=DEFAULT_LOW, high_hz=DEFAULT_HIGH, k=DEFAULT_K, top_n=DEFAULT_TOP_N):
    samples, sr = load_wav(wav_path)
    duration_s = len(samples) / sr
    energies, times = frame_energy(bandpass(samples, sr, low_hz, high_hz), sr)
    events = detect_events(energies, times, k=k)
    score = score_events(events, duration_s)

    meta = _meta(wav_path)
    if meta and meta.get("label"):
        date, label = meta.get("date"), meta.get("label")
    else:
        date, label = parse_recording_name(wav_path)

    stem = os.path.splitext(os.path.basename(wav_path))[0]
    os.makedirs(results_dir, exist_ok=True)
    result = {"wav": os.path.basename(wav_path), "date": date, "label": label,
              "duration_s": duration_s, "sample_rate": sr,
              "band_hz": [low_hz, high_hz], "k": k, **score}
    with open(os.path.join(results_dir, stem + ".json"), "w") as f:
        json.dump(result, f, indent=2)

    append_result(ranking_csv, date, label, duration_s,
                  score["events"], score["events_per_hour"], score["active_s"])

    top = sorted(events, key=lambda e: e.peak, reverse=True)[:top_n]
    clip_dir = os.path.join(evidence_dir, stem)
    os.makedirs(clip_dir, exist_ok=True)
    for idx, ev in enumerate(sorted(top, key=lambda e: e.start_s), 1):
        a = max(0, int((ev.start_s - PAD_S) * sr))
        b = min(len(samples), int((ev.end_s + PAD_S) * sr))
        save_wav(os.path.join(clip_dir, f"event_{idx:02d}_{ev.start_s:.1f}s.wav"), samples[a:b], sr)
    return result

def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("wav")
    base = os.path.expanduser("~/mouse-survey")
    p.add_argument("--ranking", default=os.path.join(base, "ranking.csv"))
    p.add_argument("--results", default=os.path.join(base, "results"))
    p.add_argument("--evidence", default=os.path.join(base, "evidence"))
    p.add_argument("--low", type=float, default=DEFAULT_LOW)
    p.add_argument("--high", type=float, default=DEFAULT_HIGH)
    p.add_argument("--k", type=float, default=DEFAULT_K)
    a = p.parse_args(argv)
    print(json.dumps(analyze_file(a.wav, a.ranking, a.results, a.evidence, a.low, a.high, a.k), indent=2))

if __name__ == "__main__":
    main()
