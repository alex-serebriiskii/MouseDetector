#!/usr/bin/env bash
# Deploy recorder to the Pi via scp (run from repo root on the dev box).
set -euo pipefail
PI="${1:-rpi3}"
ssh "$PI" 'mkdir -p ~/mousedetector ~/bin ~/recordings'
scp mousedetector/recorder.py mousedetector/record_night_worker.py "$PI:mousedetector/"
scp bin/record-night "$PI:bin/record-night"
ssh "$PI" 'chmod +x ~/bin/record-night ~/mousedetector/record_night_worker.py'
echo "deployed recorder to $PI"
