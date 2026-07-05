import os
import mousedetector.record_night_worker as worker


def test_partial_removed_on_arecord_failure(tmp_path, monkeypatch):
    def fake_call(cmd):
        out_path = cmd[-1]            # arecord_cmd's last arg is the output (partial) path
        with open(out_path, "wb") as f:
            f.write(b"\x00" * 1024)  # simulate a partial WAV written before failure
        return 1                      # non-zero => failure

    monkeypatch.setattr(worker.subprocess, "call", fake_call)
    rc = worker.main(["--label", "t", "--seconds", "1", "--outdir", str(tmp_path)])
    assert rc == 1
    leftovers = [p for p in os.listdir(tmp_path) if p.endswith(".partial") or p.endswith(".wav")]
    assert leftovers == [], f"unexpected leftovers: {leftovers}"


def test_partial_not_created_still_returns_failure(tmp_path, monkeypatch):
    """arecord fails without writing anything — no OSError should propagate."""
    def fake_call(cmd):
        return 2  # fail without creating the partial file

    monkeypatch.setattr(worker.subprocess, "call", fake_call)
    rc = worker.main(["--label", "t", "--seconds", "1", "--outdir", str(tmp_path)])
    assert rc == 2
    leftovers = [p for p in os.listdir(tmp_path) if p.endswith(".partial") or p.endswith(".wav")]
    assert leftovers == [], f"unexpected leftovers: {leftovers}"
