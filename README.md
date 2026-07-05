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
- Mic gain: card `2`, control `Mic`, set to `70%` via
  ```
  amixer -c 2 sset "Mic" 70% cap
  ```
  This gain is **persisted across reboots** via `sudo alsactl store` (the Pi's `alsa-restore` service restores it at boot), ensuring the frozen value (70% = −17.00 dB, capture on) stays frozen for cross-night comparability. The mic has no AGC control.

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
