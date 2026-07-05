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
