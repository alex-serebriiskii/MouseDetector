# Mouse-in-Wall Acoustic Survey Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pipeline that records each night's wall audio on a Raspberry Pi, scores rodent activity offline on the buildbox, and ranks wall-spots so the most-active wall can be identified.

**Architecture:** A "dumb recorder, smart analyzer" split. The Pi runs a stdlib-only recorder (`arecord`) that captures a labeled, fixed-length overnight WAV. The audio moves to the always-on buildbox, where a Python (numpy/scipy) analyzer band-passes to the mouse frequency band, detects transient events against a per-night noise floor, scores each night, and appends to a cumulative ranking. Bring-up is manual (operator drives each stage); the final phase wires the Pi to auto-push and trigger analysis.

**Tech Stack:** Python 3 (numpy, scipy, stdlib `wave`), ALSA `arecord`, `rsync`/`scp` over SSH, pytest. Source of truth: this repo (GitHub `MouseDetector`, SSH remote).

## Global Constraints

- **Audio capture is fixed** (comparability): device `hw:CARD=Microphone,DEV=0`, format `S16_LE`, `48000` Hz, `1` channel (mono). Never vary these across nights.
- **Mic gain is frozen** at setup via `amixer` (AGC disabled) and never changed — it is the comparability lever.
- **Cross-night comparability is the governing requirement:** every night uses identical capture settings and the same fixed length; scores are compared directly.
- **Deploy model:** code is authored/committed/pushed from the Windows dev box and copied to devices via `scp`. The Pi has **no git** and **no numpy/scipy** — recorder code is stdlib-only. numpy/scipy live only in the buildbox venv (`~/mouse-survey/venv`) and the local dev venv; run the analyzer/report as `~/mouse-survey/venv/bin/python -m mousedetector.<mod>`.
- **Detached recording:** the overnight recording must survive an SSH disconnect (launched via `nohup`, pidfile written).
- **Detection defaults (tunable):** band `2000–12000` Hz, threshold `k=5.0` (median + k·MAD), frame `30` ms, hop `15` ms, min event duration `20` ms, merge gap `50` ms, evidence top-N `20`, evidence pad `0.5` s.
- **Score:** primary metric is **events per hour** (duration-normalized); secondary is **total active seconds**.
- **Ranking trust:** a spot needs ≥2–3 nights before its rank is trustworthy; the report shows `n_nights`.
- **Git:** remote is SSH (`git@github.com:alex-serebriiskii/MouseDetector.git`). Every commit message ends with the trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Test loop:** all pure-Python modules are TDD'd locally on Windows in `.venv` via `python -m pytest`. Pi/buildbox tasks are integration-tested over SSH with exact commands.

## File Structure

```
mousedetector/            # Python package (empty __init__ to avoid import chains)
  __init__.py
  audio.py                # WAV load/save (wave + numpy)              [buildbox + dev]
  detect.py               # bandpass, frame_energy, detect_events     [buildbox + dev]
  score.py                # score_events                              [buildbox + dev]
  ranking.py              # append_result, aggregate                 [buildbox + dev]
  report.py               # leaderboard CLI                          [buildbox + dev]
  analyze.py              # analyze_file + CLI (wires the pipeline)   [buildbox + dev]
  recorder.py             # pure recorder logic (stdlib)             [Pi + dev]
  record_night_worker.py  # Pi worker: arecord -> finalize -> push   [Pi]
bin/
  record-night            # Pi launcher (bash): nohup the worker      [Pi]
tests/
  __init__.py
  synth.py                # synthetic-signal helper for tests
  test_audio.py test_detect.py test_score.py test_ranking.py
  test_report.py test_analyze.py test_recorder.py
deploy/
  deploy-pi.sh            # scp recorder files + launcher to the Pi
  deploy-buildbox.sh      # scp the package to the buildbox
pyproject.toml            # pytest config (pythonpath=["."])
requirements.txt          # numpy, scipy, pytest
.gitignore
docs/design/2026-07-05-mouse-in-wall-acoustic-survey-design.md   # spec (exists)
docs/plans/2026-07-05-mouse-in-wall-acoustic-survey.md           # this plan
```

**Phases:** Task 1 (scaffold) → Tasks 2–7 (analyzer, pure-Python TDD) → Tasks 8–10 (recorder + Pi hardware) → Task 11 (buildbox + manual end-to-end, Arch C) → Task 12 (auto-push, Arch A) → Task 13 (README + deploy scripts).

---

### Task 1: Project scaffold + local dev venv

**Files:**
- Create: `mousedetector/__init__.py` (empty), `tests/__init__.py` (empty)
- Create: `pyproject.toml`, `requirements.txt`, `.gitignore`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: an importable `mousedetector` package and a working `python -m pytest` loop.

- [ ] **Step 1: Create the .gitignore**

Create `.gitignore`:
```
.venv/
__pycache__/
*.pyc
recordings/
results/
evidence/
incoming/
*.wav
*.wav.json
*.wav.partial
ranking.csv
```

- [ ] **Step 2: Create packaging files**

Create `requirements.txt`:
```
numpy>=1.26
scipy>=1.11
pytest>=7.4
```

Create `pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

Create empty `mousedetector/__init__.py` and empty `tests/__init__.py` (0 bytes each).

- [ ] **Step 3: Create the local venv and install deps**

Run (PowerShell, from repo root):
```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```
Expected: pip installs numpy, scipy, pytest without error.

- [ ] **Step 4: Write the smoke test**

Create `tests/test_smoke.py`:
```python
def test_package_imports():
    import mousedetector
    assert mousedetector is not None
```

- [ ] **Step 5: Run the smoke test**

Run: `.venv\Scripts\python.exe -m pytest tests/test_smoke.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add .gitignore requirements.txt pyproject.toml mousedetector/__init__.py tests/__init__.py tests/test_smoke.py
git commit -m "chore: scaffold mousedetector package and pytest loop" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Audio I/O (`audio.py`)

**Files:**
- Create: `mousedetector/audio.py`, `tests/synth.py`
- Test: `tests/test_audio.py`

**Interfaces:**
- Consumes: numpy.
- Produces:
  - `load_wav(path: str) -> tuple[np.ndarray, int]` — returns (float32 mono samples in [-1,1], sample_rate). Takes channel 0 if multi-channel; raises `ValueError` if not 16-bit.
  - `save_wav(path: str, samples: np.ndarray, sample_rate: int) -> None` — writes 16-bit mono PCM, clipping to [-1,1].
  - `tests/synth.py::tone_bursts(sample_rate, duration_s, bursts, noise_amp=0.0, seed=0) -> np.ndarray` where `bursts` is a list of `(start_s, freq_hz, dur_s, amp)`.

- [ ] **Step 1: Write the failing test**

Create `tests/synth.py`:
```python
import numpy as np

def tone_bursts(sample_rate, duration_s, bursts, noise_amp=0.0, seed=0):
    n = int(duration_s * sample_rate)
    sig = np.zeros(n, dtype=np.float32)
    for (start_s, freq, dur_s, amp) in bursts:
        i0 = int(start_s * sample_rate)
        i1 = min(n, int((start_s + dur_s) * sample_rate))
        seg = np.arange(i1 - i0) / sample_rate
        sig[i0:i1] += (amp * np.sin(2 * np.pi * freq * seg)).astype(np.float32)
    if noise_amp > 0:
        rng = np.random.default_rng(seed)
        sig += (noise_amp * rng.standard_normal(n)).astype(np.float32)
    return sig
```

Create `tests/test_audio.py`:
```python
import numpy as np
from mousedetector.audio import load_wav, save_wav
from tests.synth import tone_bursts

def test_save_then_load_roundtrip(tmp_path):
    sr = 48000
    sig = tone_bursts(sr, 0.5, [(0.1, 5000, 0.2, 0.5)])
    p = str(tmp_path / "x.wav")
    save_wav(p, sig, sr)
    back, back_sr = load_wav(p)
    assert back_sr == sr
    assert abs(len(back) - len(sig)) <= 1
    assert np.max(np.abs(back - sig[:len(back)])) < 1e-3

def test_load_rejects_non_16bit(tmp_path):
    import wave
    p = str(tmp_path / "bad.wav")
    with wave.open(p, "wb") as w:
        w.setnchannels(1); w.setsampwidth(1); w.setframerate(48000)
        w.writeframes(b"\x00\x01\x02")
    import pytest
    with pytest.raises(ValueError):
        load_wav(p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_audio.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mousedetector.audio'`.

- [ ] **Step 3: Write minimal implementation**

Create `mousedetector/audio.py`:
```python
import wave
import numpy as np

def load_wav(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        raw = w.readframes(n)
    if sw != 2:
        raise ValueError(f"expected 16-bit PCM, got sampwidth={sw}")
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch)[:, 0]
    return data, sr

def save_wav(path, samples, sample_rate):
    samples = np.asarray(samples, dtype=np.float32)
    ints = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(ints.tobytes())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_audio.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add mousedetector/audio.py tests/synth.py tests/test_audio.py
git commit -m "feat: WAV load/save and synthetic-signal test helper" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Detection (`detect.py`)

**Files:**
- Create: `mousedetector/detect.py`
- Test: `tests/test_detect.py`

**Interfaces:**
- Consumes: numpy, scipy, `tests/synth.py`.
- Produces:
  - `bandpass(samples, sample_rate, low_hz=2000.0, high_hz=12000.0, order=4) -> np.ndarray`
  - `frame_energy(samples, sample_rate, frame_ms=30.0, hop_ms=15.0) -> tuple[np.ndarray, np.ndarray]` (energies, center-times)
  - `@dataclass Event(start_s: float, end_s: float, peak: float)`
  - `detect_events(energies, times, k=5.0, min_dur_s=0.02, merge_gap_s=0.05) -> list[Event]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_detect.py`:
```python
import numpy as np
from mousedetector.detect import bandpass, frame_energy, detect_events
from tests.synth import tone_bursts

SR = 48000

def _events(sig, k=5.0):
    filt = bandpass(sig, SR)
    e, t = frame_energy(filt, SR)
    return detect_events(e, t, k=k)

def test_detects_inband_bursts_and_times():
    sig = tone_bursts(SR, 4.0, [(1.0, 5000, 0.15, 0.5), (3.0, 7000, 0.15, 0.5)], noise_amp=0.01)
    evs = _events(sig)
    assert len(evs) == 2
    starts = sorted(ev.start_s for ev in evs)
    assert abs(starts[0] - 1.0) < 0.1
    assert abs(starts[1] - 3.0) < 0.1

def test_rejects_low_frequency_tone():
    sig = tone_bursts(SR, 4.0, [(0.0, 300, 4.0, 0.5)], noise_amp=0.01)
    assert len(_events(sig)) == 0

def test_silence_yields_no_events():
    sig = tone_bursts(SR, 4.0, [], noise_amp=0.001)
    assert len(_events(sig)) == 0

def test_self_calibrates_to_noise_floor():
    sig = tone_bursts(SR, 4.0, [(1.0, 5000, 0.15, 0.5), (3.0, 7000, 0.15, 0.5)], noise_amp=0.05)
    assert len(_events(sig)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_detect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mousedetector.detect'`.

- [ ] **Step 3: Write minimal implementation**

Create `mousedetector/detect.py`:
```python
from dataclasses import dataclass
import numpy as np
from scipy.signal import butter, sosfiltfilt

def bandpass(samples, sample_rate, low_hz=2000.0, high_hz=12000.0, order=4):
    nyq = sample_rate / 2.0
    high = min(high_hz, nyq * 0.99)
    sos = butter(order, [low_hz / nyq, high / nyq], btype="band", output="sos")
    return sosfiltfilt(sos, np.asarray(samples, dtype=float))

def frame_energy(samples, sample_rate, frame_ms=30.0, hop_ms=15.0):
    samples = np.asarray(samples, dtype=float)
    flen = max(1, int(frame_ms / 1000.0 * sample_rate))
    hop = max(1, int(hop_ms / 1000.0 * sample_rate))
    if len(samples) < flen:
        return np.array([]), np.array([])
    starts = np.arange(0, len(samples) - flen + 1, hop)
    energies = np.array([np.sqrt(np.mean(samples[s:s + flen] ** 2)) for s in starts])
    times = (starts + flen / 2.0) / sample_rate
    return energies, times

@dataclass
class Event:
    start_s: float
    end_s: float
    peak: float

def _runs(mask):
    runs, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i - 1)); start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    return runs

def detect_events(energies, times, k=5.0, min_dur_s=0.02, merge_gap_s=0.05):
    energies = np.asarray(energies, dtype=float)
    if energies.size == 0:
        return []
    med = float(np.median(energies))
    mad = float(np.median(np.abs(energies - med))) + 1e-12
    thr = med + k * mad
    raw = [Event(float(times[s]), float(times[e]), float(energies[s:e + 1].max()))
           for s, e in _runs(energies > thr)]
    merged = []
    for ev in raw:
        if merged and ev.start_s - merged[-1].end_s < merge_gap_s:
            merged[-1] = Event(merged[-1].start_s, ev.end_s, max(merged[-1].peak, ev.peak))
        else:
            merged.append(ev)
    return [ev for ev in merged if (ev.end_s - ev.start_s) >= min_dur_s]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_detect.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add mousedetector/detect.py tests/test_detect.py
git commit -m "feat: band-pass + noise-floor-relative transient event detection" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Scoring (`score.py`)

**Files:**
- Create: `mousedetector/score.py`
- Test: `tests/test_score.py`

**Interfaces:**
- Consumes: `detect.Event`.
- Produces: `score_events(events, duration_s) -> dict` with keys `events` (int), `events_per_hour` (float), `active_s` (float), `active_fraction` (float).

- [ ] **Step 1: Write the failing test**

Create `tests/test_score.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_score.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mousedetector.score'`.

- [ ] **Step 3: Write minimal implementation**

Create `mousedetector/score.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_score.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add mousedetector/score.py tests/test_score.py
git commit -m "feat: per-night activity scoring (events/hour + active time)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Ranking store (`ranking.py`)

**Files:**
- Create: `mousedetector/ranking.py`
- Test: `tests/test_ranking.py`

**Interfaces:**
- Consumes: stdlib `csv`.
- Produces:
  - `append_result(csv_path, date, label, duration_s, events, events_per_hour, active_s) -> None` (writes header once).
  - `aggregate(csv_path) -> list[dict]` — one dict per label: `label`, `n_nights`, `mean_events_per_hour`, `mean_active_s`, `rank` (1 = highest events/hour), sorted by `mean_events_per_hour` descending.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ranking.py`:
```python
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
    assert kitchen["rank"] == 1 and agg[1]["rank"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ranking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mousedetector.ranking'`.

- [ ] **Step 3: Write minimal implementation**

Create `mousedetector/ranking.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ranking.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add mousedetector/ranking.py tests/test_ranking.py
git commit -m "feat: cumulative per-spot ranking store (CSV append + aggregate)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Report (`report.py`)

**Files:**
- Create: `mousedetector/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `ranking.aggregate`.
- Produces:
  - `format_leaderboard(rows: list[dict]) -> str` — a text table; first line is the header, one line per row in `rows` order.
  - `main(argv=None)` — CLI: `python -m mousedetector.report [ranking.csv]` (defaults to `~/mouse-survey/ranking.csv`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_report.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mousedetector.report'`.

- [ ] **Step 3: Write minimal implementation**

Create `mousedetector/report.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_report.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add mousedetector/report.py tests/test_report.py
git commit -m "feat: leaderboard report CLI" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Analyzer wiring (`analyze.py`)

**Files:**
- Create: `mousedetector/analyze.py`
- Test: `tests/test_analyze.py`

**Interfaces:**
- Consumes: `audio.load_wav`, `audio.save_wav`, `detect.*`, `score.score_events`, `ranking.append_result`.
- Produces:
  - `parse_recording_name(path) -> tuple[str, str]` — `(date, label)` from `<YYYY-MM-DD>_<label>_<HHMM>.wav`.
  - `analyze_file(wav_path, ranking_csv, results_dir, evidence_dir, low_hz=2000.0, high_hz=12000.0, k=5.0, top_n=20) -> dict` — writes `results_dir/<stem>.json`, appends to `ranking_csv`, writes up to `top_n` evidence clips under `evidence_dir/<stem>/`, and returns the result dict. Reads a sidecar `<wav_path>.json` for `date`/`label` if present, else parses the filename.
  - `main(argv=None)` — CLI: `python -m mousedetector.analyze <wav> [--ranking P] [--results D] [--evidence D] [--low HZ] [--high HZ] [--k K]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_analyze.py`:
```python
import json
import os
from mousedetector.audio import save_wav
from mousedetector.analyze import analyze_file, parse_recording_name
from tests.synth import tone_bursts

def test_parse_recording_name():
    assert parse_recording_name("2026-07-05_kitchen-north_2204.wav") == ("2026-07-05", "kitchen-north")

def test_analyze_file_end_to_end(tmp_path):
    sr = 48000
    sig = tone_bursts(sr, 4.0, [(1.0, 5000, 0.15, 0.5), (3.0, 7000, 0.15, 0.5)], noise_amp=0.01)
    wav = str(tmp_path / "2026-07-05_kitchen_2204.wav")
    save_wav(wav, sig, sr)
    ranking = str(tmp_path / "ranking.csv")
    results = str(tmp_path / "results")
    evidence = str(tmp_path / "evidence")
    res = analyze_file(wav, ranking, results, evidence)
    assert res["label"] == "kitchen" and res["date"] == "2026-07-05"
    assert res["events"] == 2
    assert os.path.exists(os.path.join(results, "2026-07-05_kitchen_2204.json"))
    assert os.path.exists(ranking)
    clips = os.listdir(os.path.join(evidence, "2026-07-05_kitchen_2204"))
    assert len(clips) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_analyze.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mousedetector.analyze'`.

- [ ] **Step 3: Write minimal implementation**

Create `mousedetector/analyze.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_analyze.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest -v`
Expected: PASS (all tests from Tasks 1–7).

- [ ] **Step 6: Commit**

```bash
git add mousedetector/analyze.py tests/test_analyze.py
git commit -m "feat: analyzer wiring (detect -> score -> results/ranking/evidence)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Recorder logic (`recorder.py`)

**Files:**
- Create: `mousedetector/recorder.py`
- Test: `tests/test_recorder.py`

**Interfaces:**
- Consumes: stdlib only (`re`, `datetime` in callers).
- Produces:
  - `sanitize_label(label: str) -> str` — safe token (`[A-Za-z0-9._-]`, spaces→`-`, empty→`"unlabeled"`).
  - `filename_for(label, start_dt) -> str` — `"<YYYY-MM-DD>_<label>_<HHMM>.wav"`.
  - `sidecar_for(label, start_dt, duration_s, device, sample_rate, channels, fmt, host) -> dict`.
  - `arecord_cmd(device, sample_rate, channels, fmt, duration_s, out_path) -> list[str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_recorder.py`:
```python
from datetime import datetime
from mousedetector.recorder import sanitize_label, filename_for, sidecar_for, arecord_cmd

def test_sanitize_label():
    assert sanitize_label("Kitchen North Wall!") == "Kitchen-North-Wall"
    assert sanitize_label("   ") == "unlabeled"

def test_filename_for():
    assert filename_for("kitchen north", datetime(2026, 7, 5, 22, 4)) == "2026-07-05_kitchen-north_2204.wav"

def test_arecord_cmd():
    assert arecord_cmd("hw:CARD=Microphone,DEV=0", 48000, 1, "S16_LE", 28800, "/tmp/x.wav.partial") == [
        "arecord", "-D", "hw:CARD=Microphone,DEV=0", "-f", "S16_LE",
        "-r", "48000", "-c", "1", "-d", "28800", "/tmp/x.wav.partial"]

def test_sidecar_for():
    sc = sidecar_for("kitchen north", datetime(2026, 7, 5, 22, 4), 28800,
                     "hw:CARD=Microphone,DEV=0", 48000, 1, "S16_LE", "rpi3")
    assert sc["label"] == "kitchen-north"
    assert sc["date"] == "2026-07-05"
    assert sc["sample_rate"] == 48000 and sc["channels"] == 1 and sc["format"] == "S16_LE"
    assert sc["host"] == "rpi3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_recorder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mousedetector.recorder'`.

- [ ] **Step 3: Write minimal implementation**

Create `mousedetector/recorder.py`:
```python
import re

def sanitize_label(label):
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", label.strip()).strip("-")
    return s or "unlabeled"

def filename_for(label, start_dt):
    return f"{start_dt:%Y-%m-%d}_{sanitize_label(label)}_{start_dt:%H%M}.wav"

def sidecar_for(label, start_dt, duration_s, device, sample_rate, channels, fmt, host):
    return {
        "label": sanitize_label(label),
        "date": f"{start_dt:%Y-%m-%d}",
        "start_iso": start_dt.isoformat(timespec="seconds"),
        "duration_s": int(duration_s),
        "device": device,
        "sample_rate": int(sample_rate),
        "channels": int(channels),
        "format": fmt,
        "host": host,
    }

def arecord_cmd(device, sample_rate, channels, fmt, duration_s, out_path):
    return ["arecord", "-D", device, "-f", fmt, "-r", str(int(sample_rate)),
            "-c", str(int(channels)), "-d", str(int(duration_s)), out_path]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_recorder.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add mousedetector/recorder.py tests/test_recorder.py
git commit -m "feat: recorder pure logic (filename, sidecar, arecord command)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Pi worker + launcher, deploy, short-capture integration test

**Files:**
- Create: `mousedetector/record_night_worker.py`, `bin/record-night`, `deploy/deploy-pi.sh`

**Interfaces:**
- Consumes: `recorder.py` (deployed alongside), `arecord` on the Pi.
- Produces: on the Pi, `record-night <spot-label> [hours=8]` records a labeled fixed-length WAV under `~/recordings/` with a `.json` sidecar. The worker also supports `--push` (wired/tested in Task 12).

- [ ] **Step 1: Write the worker**

Create `mousedetector/record_night_worker.py`:
```python
#!/usr/bin/env python3
import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import recorder  # loose module on the Pi; mousedetector/recorder.py in the repo

def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True)
    p.add_argument("--seconds", type=int, required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--device", default="hw:CARD=Microphone,DEV=0")
    p.add_argument("--sample-rate", type=int, default=48000)
    p.add_argument("--push", action="store_true")
    p.add_argument("--dest-host", default="192.168.0.224")
    p.add_argument("--dest-dir", default="mouse-survey/incoming")
    p.add_argument("--code-dir", default="mouse-survey/code")
    a = p.parse_args(argv)

    os.makedirs(a.outdir, exist_ok=True)
    start = datetime.now()
    fname = recorder.filename_for(a.label, start)
    final = os.path.join(a.outdir, fname)
    partial = final + ".partial"
    cmd = recorder.arecord_cmd(a.device, a.sample_rate, 1, "S16_LE", a.seconds, partial)
    print(f"[record-night] {start.isoformat(timespec='seconds')} recording {a.seconds}s -> {final}", flush=True)
    rc = subprocess.call(cmd)
    if rc != 0:
        print(f"[record-night] arecord failed rc={rc}", file=sys.stderr)
        return rc
    with open(final + ".json", "w") as f:
        json.dump(recorder.sidecar_for(a.label, start, a.seconds, a.device,
                                       a.sample_rate, 1, "S16_LE", socket.gethostname()), f, indent=2)
    os.replace(partial, final)
    print(f"[record-night] done -> {final}", flush=True)

    if a.push:
        subprocess.check_call(["rsync", "-av", final, final + ".json",
                               f"{a.dest_host}:{a.dest_dir}/"])
        subprocess.check_call(["ssh", a.dest_host,
                               f"cd ~/{a.code_dir} && ~/mouse-survey/venv/bin/python -m mousedetector.analyze ~/{a.dest_dir}/{fname}"])
        print(f"[record-night] pushed + analyzed on {a.dest_host}", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Write the launcher (bring-up default: no push)**

Create `bin/record-night`:
```bash
#!/usr/bin/env bash
set -euo pipefail
LABEL="${1:?usage: record-night <spot-label> [hours=8]}"
HOURS="${2:-8}"
SECS="$(python3 -c 'import sys; print(int(float(sys.argv[1]) * 3600))' "$HOURS")"
OUTDIR="$HOME/recordings"; mkdir -p "$OUTDIR"
LOG="$OUTDIR/record-night.log"
nohup python3 "$HOME/mousedetector/record_night_worker.py" \
  --label "$LABEL" --seconds "$SECS" --outdir "$OUTDIR" \
  --device "hw:CARD=Microphone,DEV=0" --sample-rate 48000 \
  >> "$LOG" 2>&1 &
echo $! > "$OUTDIR/record-night.pid"
echo "record-night started (pid $(cat "$OUTDIR/record-night.pid")) label=$LABEL hours=$HOURS -> $OUTDIR (log: $LOG)"
```

- [ ] **Step 3: Write the Pi deploy script**

Create `deploy/deploy-pi.sh`:
```bash
#!/usr/bin/env bash
# Deploy recorder to the Pi via scp (run from repo root on the dev box).
set -euo pipefail
PI="${1:-rpi3}"
ssh "$PI" 'mkdir -p ~/mousedetector ~/bin ~/recordings'
scp mousedetector/recorder.py mousedetector/record_night_worker.py "$PI:mousedetector/"
scp bin/record-night "$PI:bin/record-night"
ssh "$PI" 'chmod +x ~/bin/record-night ~/mousedetector/record_night_worker.py'
echo "deployed recorder to $PI"
```

- [ ] **Step 4: Deploy to the Pi**

Run (Git Bash on the dev box, from repo root):
```
bash deploy/deploy-pi.sh rpi3
```
Expected: `deployed recorder to rpi3`.

- [ ] **Step 5: Integration test — a 5-second real capture**

Run:
```
ssh rpi3 'python3 ~/mousedetector/record_night_worker.py --label test-spot --seconds 5 --outdir ~/recordings'
ssh rpi3 'ls -la ~/recordings/*test-spot*.wav ~/recordings/*test-spot*.json'
ssh rpi3 'python3 - <<PY
import wave, glob
f = sorted(glob.glob("/home/rpi3/recordings/*test-spot*.wav"))[-1]
w = wave.open(f, "rb")
print("rate", w.getframerate(), "ch", w.getnchannels(), "width", w.getsampwidth(), "frames", w.getnframes())
assert w.getframerate() == 48000 and w.getnchannels() == 1 and w.getsampwidth() == 2
assert w.getnframes() > 48000 * 4   # at least ~4s captured
print("OK")
PY'
```
Expected: a `.wav` + `.json` exist, params are `48000/1/2`, and it prints `OK`. No leftover `.partial` file.

- [ ] **Step 6: Commit**

```bash
git add mousedetector/record_night_worker.py bin/record-night deploy/deploy-pi.sh
git commit -m "feat: Pi record-night worker + launcher + deploy script" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Freeze mic gain + capture sanity check (Pi hardware)

**Files:** none (operational configuration on the Pi; commands recorded in README in Task 13).

**Interfaces:**
- Consumes: `amixer`, `record-night` from Task 9.
- Produces: a fixed, documented mic gain and a verified non-silent, non-clipping capture.

- [ ] **Step 1: Discover the mic's mixer controls**

Run:
```
ssh rpi3 'CARD=$(arecord -l | sed -n "s/^card \([0-9]\+\): Microphone.*/\1/p"); echo "card=$CARD"; amixer -c "$CARD" scontrols'
```
Expected: prints the card number and the capture control name(s) (commonly `Mic` or `Capture`). Note the control name for the next step.

- [ ] **Step 2: Set and freeze the capture gain (disable AGC if present)**

Run (replace `<CARD>` and `<CONTROL>` with values from Step 1; start at ~70%):
```
ssh rpi3 'amixer -c <CARD> sset "<CONTROL>" 70% cap; amixer -c <CARD> sget "<CONTROL>"'
```
Expected: the control shows the set percentage and `[on]` capture. Record the exact card/control/percent — this is the frozen gain used every night.

- [ ] **Step 3: Capture a 10-second sanity clip and pull it to the dev box**

Run:
```
ssh rpi3 'python3 ~/mousedetector/record_night_worker.py --label gain-check --seconds 10 --outdir ~/recordings'
scp "rpi3:$(ssh rpi3 'ls -t ~/recordings/*gain-check*.wav | head -1')" /tmp/gain-check.wav
```
Expected: `/tmp/gain-check.wav` exists on the dev box.

- [ ] **Step 4: Verify level with the analyzer's loader**

Run (PowerShell, from repo root):
```
.venv\Scripts\python.exe -c "from mousedetector.audio import load_wav; import numpy as np; s,sr=load_wav(r'/tmp/gain-check.wav'); import numpy; print('rms', float(np.sqrt(np.mean(s**2))), 'peak', float(np.max(np.abs(s))))"
```
Expected: `peak` is well below `1.0` (not clipping) and `rms` is clearly above the noise ambient floor (not silent). If clipping, lower the gain in Step 2 and repeat; if near-silent, raise it. Lock the final value.

- [ ] **Step 5: Commit (documentation placeholder resolved in Task 13)**

No code change in this task; the frozen gain values are captured in the README in Task 13.

---

### Task 11: buildbox setup + deploy + manual end-to-end (Arch C)

**Files:**
- Create: `deploy/deploy-buildbox.sh`

**Interfaces:**
- Consumes: `analyze.py`/`report.py` package, `rsync`.
- Produces: a buildbox that can run `~/mouse-survey/venv/bin/python -m mousedetector.analyze` and `~/mouse-survey/venv/bin/python -m mousedetector.report`, and a validated manual pipeline (record → transfer → analyze → rank → report).

- [ ] **Step 1: Analyzer venv on the buildbox (already created 2026-07-05)**

The buildbox is Ubuntu 24.04 / externally-managed (PEP 668). With `python3-venv` installed, the analyzer runs from a dedicated venv at `~/mouse-survey/venv` — isolated, no `--break-system-packages`, no system-package changes. Provisioned during planning:
```
ssh 192.168.0.224 'python3 -m venv ~/mouse-survey/venv && ~/mouse-survey/venv/bin/pip install numpy scipy'
```
Verify (should already pass):
```
ssh 192.168.0.224 '~/mouse-survey/venv/bin/python -c "import numpy,scipy; from scipy.signal import butter,sosfiltfilt; print(numpy.__version__, scipy.__version__, \"ok\")"'
```
Expected: prints e.g. `2.5.1 1.18.0 ok`. Every analyzer/report command below uses `~/mouse-survey/venv/bin/python` — the system `python3` deliberately has no numpy. Reprovisioning a fresh box: `sudo apt install python3-venv`, then rerun the one-liner above.

- [ ] **Step 2: Create the buildbox directory layout (already created 2026-07-05)**

Idempotent; run again if needed:
```
ssh 192.168.0.224 'mkdir -p ~/mouse-survey/{incoming,results,evidence,code}'
```
Expected: no error. (`incoming/`, `results/`, `evidence/`, `code/` already exist.)

- [ ] **Step 3: Write the buildbox deploy script**

Create `deploy/deploy-buildbox.sh`:
```bash
#!/usr/bin/env bash
# Deploy the analyzer package to the buildbox via scp (run from repo root on the dev box).
set -euo pipefail
BB="${1:-192.168.0.224}"
ssh "$BB" 'mkdir -p ~/mouse-survey/code/mousedetector'
scp mousedetector/__init__.py mousedetector/audio.py mousedetector/detect.py \
    mousedetector/score.py mousedetector/ranking.py mousedetector/report.py \
    mousedetector/analyze.py "$BB:mouse-survey/code/mousedetector/"
echo "deployed analyzer to $BB"
```

- [ ] **Step 4: Deploy the analyzer**

Run (Git Bash, from repo root):
```
bash deploy/deploy-buildbox.sh 192.168.0.224
```
Expected: `deployed analyzer to 192.168.0.224`.

- [ ] **Step 5: Smoke-test the analyzer on the buildbox with a synthetic WAV**

Run:
```
ssh 192.168.0.224 'cd ~/mouse-survey/code && ~/mouse-survey/venv/bin/python - <<PY
import numpy as np, wave
sr=48000; n=int(4*sr); t=np.arange(n)/sr
sig=np.zeros(n,dtype=np.float32)
for s,f in [(1.0,5000),(3.0,7000)]:
    i0=int(s*sr); i1=i0+int(0.15*sr); seg=np.arange(i1-i0)/sr
    sig[i0:i1]+= (0.5*np.sin(2*np.pi*f*seg)).astype(np.float32)
ints=(np.clip(sig,-1,1)*32767).astype("<i2")
w=wave.open("/home/codeagent/mouse-survey/incoming/2026-07-05_smoke_2204.wav","wb")
w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(ints.tobytes()); w.close()
print("wrote synthetic wav")
PY
~/mouse-survey/venv/bin/python -m mousedetector.analyze ~/mouse-survey/incoming/2026-07-05_smoke_2204.wav'
```
Expected: prints a result JSON with `"label": "smoke"` and `"events": 2`.

- [ ] **Step 6: Manual end-to-end (Arch C): record on Pi → transfer via dev box → analyze → report**

Run (Git Bash on the dev box; Arch C routes the file through the dev box since Pi→buildbox trust is not set up until Task 12):
```
# 1) record a short real clip on the Pi (foreground, ~10s)
ssh rpi3 'python3 ~/mousedetector/record_night_worker.py --label e2e-test --seconds 10 --outdir ~/recordings'
# 2) pull the newest e2e-test wav + sidecar to the dev box, then push to the buildbox
WAV=$(ssh rpi3 'ls -t ~/recordings/*e2e-test*.wav | head -1'); BASE=$(basename "$WAV")
scp "rpi3:$WAV" "rpi3:$WAV.json" /tmp/
scp "/tmp/$BASE" "/tmp/$BASE.json" 192.168.0.224:mouse-survey/incoming/
# 3) analyze on the buildbox, then print the leaderboard
ssh 192.168.0.224 "cd ~/mouse-survey/code && ~/mouse-survey/venv/bin/python -m mousedetector.analyze ~/mouse-survey/incoming/$BASE"
ssh 192.168.0.224 'cd ~/mouse-survey/code && ~/mouse-survey/venv/bin/python -m mousedetector.report'
```
Expected: analyze prints a result JSON for label `e2e-test`; report prints a leaderboard containing `e2e-test`.

- [ ] **Step 7: Commit**

```bash
git add deploy/deploy-buildbox.sh
git commit -m "feat: buildbox deploy script + validated manual pipeline (Arch C)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Auto-push wiring (Arch A) — Pi pushes and triggers analysis

**Files:**
- Modify: `bin/record-night` (add `--push` to the launched worker)
- Create: `deploy/setup-pi-trust.sh`

**Interfaces:**
- Consumes: the `--push` path already implemented in `record_night_worker.py` (Task 9).
- Produces: `record-night <label> [hours]` records, then automatically rsyncs to the buildbox and triggers `analyze`; the ranking is updated with no operator step.

- [ ] **Step 1: Set up Pi → buildbox SSH trust**

Create `deploy/setup-pi-trust.sh`:
```bash
#!/usr/bin/env bash
# One-time: give the Pi passwordless SSH to the buildbox (run from repo root on the dev box).
set -euo pipefail
PI="${1:-rpi3}"; BB="${2:-192.168.0.224}"
# 1) ensure the Pi has a key
ssh "$PI" 'test -f ~/.ssh/id_ed25519 || ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519'
PI_PUB=$(ssh "$PI" 'cat ~/.ssh/id_ed25519.pub')
# 2) authorize the Pi's key on the buildbox (dev box can already reach the buildbox)
ssh "$BB" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && grep -qxF '$PI_PUB' ~/.ssh/authorized_keys 2>/dev/null || echo '$PI_PUB' >> ~/.ssh/authorized_keys"
# 3) make the Pi trust the buildbox host key
ssh "$PI" "ssh-keyscan -H $BB >> ~/.ssh/known_hosts 2>/dev/null; true"
# 4) verify
ssh "$PI" "ssh -o BatchMode=yes $BB 'echo pi-to-buildbox-OK; hostname'"
```

- [ ] **Step 2: Run the trust setup**

Run (Git Bash, from repo root):
```
bash deploy/setup-pi-trust.sh rpi3 192.168.0.224
```
Expected: prints `pi-to-buildbox-OK` and the buildbox hostname.

- [ ] **Step 3: Flip the launcher to push by default**

In `bin/record-night`, add the push flags to the worker invocation. Change:
```bash
  --device "hw:CARD=Microphone,DEV=0" --sample-rate 48000 \
```
to:
```bash
  --device "hw:CARD=Microphone,DEV=0" --sample-rate 48000 --push \
  --dest-host 192.168.0.224 --dest-dir mouse-survey/incoming --code-dir mouse-survey/code \
```

- [ ] **Step 4: Redeploy the launcher**

Run:
```
scp bin/record-night rpi3:bin/record-night && ssh rpi3 'chmod +x ~/bin/record-night'
```
Expected: no error.

- [ ] **Step 5: Integration test — full auto path (foreground, exercises `--push`)**

Run the worker directly with `--push` (foreground, so it completes synchronously — the launcher wraps this exact call in `nohup`; avoid a bare `sleep`, which the Bash tool blocks):
```
ssh rpi3 'python3 ~/mousedetector/record_night_worker.py --label arch-a-test --seconds 12 --outdir ~/recordings --push --dest-host 192.168.0.224 --dest-dir mouse-survey/incoming --code-dir mouse-survey/code'
ssh 192.168.0.224 'ls -t ~/mouse-survey/incoming/*arch-a-test*.wav | head -1; cd ~/mouse-survey/code && ~/mouse-survey/venv/bin/python -m mousedetector.report'
```
Expected: the worker prints `pushed + analyzed on 192.168.0.224`; the recording appears in the buildbox `incoming/`; the leaderboard includes `arch-a-test` (the Pi transferred and triggered analysis with no operator step).

- [ ] **Step 6: Commit**

```bash
git add bin/record-night deploy/setup-pi-trust.sh
git commit -m "feat: Arch A auto-push (Pi rsync + remote analyze trigger) + trust setup" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: README + operator runbook

**Files:**
- Modify: `README.md`

**Interfaces:** none (documentation).

- [ ] **Step 1: Write the README**

Replace `README.md` with the following runbook. Fill `<CARD>`, `<CONTROL>`, `<PERCENT>` with the frozen mic-gain values recorded in Task 10:

```markdown
# MouseDetector

Localize the most rodent-active wall by recording each night with a USB mic on a
Raspberry Pi and scoring activity offline on the buildbox. See the design spec in
`docs/design/` and the implementation plan in `docs/plans/`.

## Topology
- **Pi** `rpi3` (192.168.0.5): USB mic `hw:CARD=Microphone,DEV=0`, records via `~/bin/record-night`.
- **buildbox** (192.168.0.224): runs the analyzer/report under `~/mouse-survey/`.
- **dev box** (Windows): source of truth; deploys via `deploy/deploy-pi.sh` and `deploy/deploy-buildbox.sh`.

## Nightly workflow
1. Attach the mic to the wall/spot you want to test.
2. Start the recording (records 8 h by default, auto-pushes to the buildbox, analysis runs by morning):
   ```
   ssh rpi3 '~/bin/record-night <wall-label>'      # e.g. kitchen-north
   ```
3. In the morning, read the leaderboard:
   ```
   ssh 192.168.0.224 'cd ~/mouse-survey/code && ~/mouse-survey/venv/bin/python -m mousedetector.report'
   ```
4. Spot-check detections by listening to the evidence clips on the buildbox:
   `~/mouse-survey/evidence/<recording-stem>/event_*.wav`.

**Use ≥2–3 nights per spot** before trusting its rank — mouse behavior varies night to night.

## Frozen capture settings (do not change — comparability depends on it)
- Format: `S16_LE`, 48000 Hz, mono. Device: `hw:CARD=Microphone,DEV=0`.
- Mic gain: card `<CARD>`, control `<CONTROL>`, set to `<PERCENT>` via
  `amixer -c <CARD> sset "<CONTROL>" <PERCENT> cap`.

## Detection tuning
Defaults live in `mousedetector/analyze.py`: band 2000–12000 Hz, `k=5.0`. Override per run:
```
~/mouse-survey/venv/bin/python -m mousedetector.analyze <wav> --low 2500 --high 10000 --k 6
```

## Redeploy after code changes (from the dev box)
```
bash deploy/deploy-pi.sh rpi3
bash deploy/deploy-buildbox.sh 192.168.0.224
```
```

- [ ] **Step 2: Verify the documented commands run**

Run each command block quoted in the README exactly as written (report command, redeploy scripts) and confirm they succeed.
Expected: all documented commands succeed.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: operator runbook for the mouse-in-wall survey" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes for the implementer

- **Where tests run:** Tasks 2–8 are pure Python — run them in the local Windows `.venv` (fast). Tasks 9–13 touch real hardware/hosts — run them over SSH exactly as written.
- **Line endings:** the repo is on Windows; git may warn `LF will be replaced by CRLF`. This is benign. Shell/Python scripts deployed to Linux use `\n` in the repo; if a deployed `bin/record-night` fails with `bad interpreter`, run `ssh rpi3 'sed -i "s/\r$//" ~/bin/record-night'`.
- **Tuning:** the detection defaults are first guesses. After the first real overnight recording, listen to the evidence pack and adjust the band (`--low/--high`) and `--k`; the defaults live in `analyze.py` and can be overridden per-run on the CLI.
- **Do not** vary capture settings or mic gain between nights — it breaks cross-night comparability, the whole point of the survey.
- **Buildbox interpreter:** always run the analyzer/report with `~/mouse-survey/venv/bin/python` (e.g. `~/mouse-survey/venv/bin/python -m mousedetector.report`). The system `python3` deliberately has no numpy/scipy, so it will `ModuleNotFoundError` — that is expected, not a bug.
