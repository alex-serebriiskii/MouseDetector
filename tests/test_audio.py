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
