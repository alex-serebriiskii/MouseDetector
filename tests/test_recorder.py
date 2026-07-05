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
