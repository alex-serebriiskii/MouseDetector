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
