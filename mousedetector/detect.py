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
