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
