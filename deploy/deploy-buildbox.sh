#!/usr/bin/env bash
# Deploy the analyzer package to the buildbox via scp (run from repo root on the dev box).
set -euo pipefail
BB="${1:-192.168.0.224}"
ssh "$BB" 'mkdir -p ~/mouse-survey/code/mousedetector'
scp mousedetector/__init__.py mousedetector/audio.py mousedetector/detect.py \
    mousedetector/score.py mousedetector/ranking.py mousedetector/report.py \
    mousedetector/analyze.py "$BB:mouse-survey/code/mousedetector/"
echo "deployed analyzer to $BB"
