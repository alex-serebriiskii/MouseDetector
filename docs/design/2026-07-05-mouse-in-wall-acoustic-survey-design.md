# Mouse-in-Wall Acoustic Survey — Design

**Date:** 2026-07-05
**Status:** Approved design, ready for implementation planning
**Author:** Claude Code + alex

## 1. Goal

Localize the wall (or wall-spot) with the most rodent activity inside it. A mouse is
audible at night through the walls; rather than tracing its routes live, attach a single
USB microphone to a different spot each night, record the whole night identically, score
each night's mouse activity, and **rank spots across nights**.

Success = a trustworthy leaderboard of spots ranked by mouse-activity score, with enough
evidence per night to confirm the detections are really the mouse.

## 2. Method and governing constraint

One mic, moved to one spot per night ("move-nightly, compare"). Because scores from
different nights are compared directly, **cross-night comparability is the governing
constraint**: sample rate, format, recording length, mic gain, device, and detection
parameters are held fixed across all nights so that a higher score means more activity,
not a different setup.

A single night is only suggestive. A spot needs **≥2–3 nights** before its ranking is
trustworthy, because mouse behavior varies night to night.

## 3. Verified environment facts

These were probed directly on 2026-07-05 and are the ground truth the design is built on.

### Raspberry Pi (recorder)
- Reachable at `rpi3.local` (mDNS) and LAN IP **`192.168.0.5`** (DHCP).
- Pi 3, 64-bit Debian, kernel 6.12 aarch64, quad Cortex-A53, **905 MB RAM (~740 MB free)**,
  **~11 GB disk free**.
- USB mic: `card 2: Microphone [UAC 1.0 Microphone]`, capture device `hw:2,0`.
  - **Fixed hardware params: `S16_LE`, 48000 Hz, 1 channel (mono).** No other rates/formats.
  - ⚠️ ALSA card numbers can reorder across reboots — reference the device by **persistent
    name** `hw:CARD=Microphone,DEV=0`, not `hw:2,0`. Verify the name at build time.
- Tools present: `arecord`, `python3`. **Missing: `ffmpeg`, `sox`, `flac`** (not needed
  for v1 — raw WAV only).

### buildbox (analysis home) — `192.168.0.224`
- Always-on Linux (Ubuntu 24.04, externally-managed / PEP 668, `ensurepip` missing), **4 cores, 31 GB RAM, 122 GB free disk**, `rsync` present, Python 3.12, system `pip 24.0`.
- Analyzer runs from a dedicated **venv** at `~/mouse-survey/venv` (`python3-venv` installed; `python3 -m venv` + `pip install numpy scipy` → numpy 2.5.1 / scipy 1.18.0, on 2026-07-05). Isolated, no `--break-system-packages`, no system-package changes. Invoke via `~/mouse-survey/venv/bin/python -m mousedetector.analyze`; system `python3` intentionally has no numpy.

### Network
- Pi (`192.168.0.5`) and buildbox (`192.168.0.224`) are on the **same `/24` LAN**.
- buildbox → Pi: ping OK, SSH port 22 open. **buildbox does not yet trust the Pi's host
  key / have an authorized key** — one-time trust setup required for the push path.

### Connection method (this harness → Pi/buildbox)
- SSH multiplexing (`ControlMaster`) **does not work** on this Windows/MSYS2 `ssh` build:
  the master starts but cannot carry sessions (`Connection reset by peer`). Confirmed by test.
- Each fresh non-multiplexed connect is **~0.5 s** and reliable over mDNS.
- **Consequence (architectural, not connection-level):** connect rarely. Run recording
  autonomously on the Pi and connect only to start / health-check / fetch. Do heavy
  analysis off-Pi. This principle shaped the whole architecture.
- A host alias `rpi3` → `rpi3.local` (User `rpi3`) was added to `~/.ssh/config`.
- FYI: `~/.ssh/config` contains a duplicated `192.168.254.46` block (left untouched).

## 4. Architecture

Pipeline (settled):

```
record-night <label>  →  48 kHz mono WAV on Pi
        │ (rename-on-done, then rsync — completed files only)
        ▼
buildbox ~/mouse-survey/incoming/
        │ analyze <wav>
        ▼
results/<wav>.json  +  append ranking.csv  +  evidence pack (top-N event clips)
        │ report
        ▼
leaderboard: spot → nights, mean events/hr, rank
```

**Target orchestration (Arch A — Pi pushes):** the nightly `record-night <label>` command
records, then on completion rsyncs the WAV+sidecar to buildbox and triggers `analyze` over
SSH. Results are ready by morning. Needs one-time Pi→buildbox SSH trust.

**Bring-up orchestration (Arch C — assisted):** build and validate the whole pipeline
manually first — Pi records, then the operator/session pulls to buildbox and runs `analyze`
on demand. This is how we get a real end-to-end result and tune the detector before wiring
the auto-push. No Pi→buildbox trust needed for bring-up.

### 4.1 Deployment / code-delivery model

Code is authored, committed, and pushed **from the Windows dev box** (which holds the repo
clone and full editing tools). It is deployed to the Pi and buildbox as plain files over
**`scp`** — **neither device needs git or a repo clone**. Verified tooling: the Pi has
`scp` + `rsync` but **no `git`** (and doesn't need it); the buildbox has `git` + `rsync`.
`rsync` is unavailable on the Windows dev box, so dev-box→device deploys use `scp`, while
the Pi→buildbox *audio* transfer uses `rsync` (present on both Linux hosts). The GitHub repo
plus the dev box are the source of truth; the Pi stays a minimal recorder.

## 5. Component specifications

Each component is independently testable with a clear interface.

### 5.1 Recorder (Pi) — `record-night`
- **Interface:** `record-night <spot-label> [hours=8]`
- **Behavior:**
  - Capture `hw:CARD=Microphone,DEV=0` at `S16_LE / 48000 / mono` for `hours*3600` seconds
    via `arecord`.
  - **Detached execution** (nohup or systemd) so an SSH disconnect cannot kill the
    recording. Write a logfile and a pidfile; expose a `status` check.
  - Record to a temp path (e.g. `*.wav.partial`); **atomically rename** to the final
    `*.wav` only on successful completion, so partial files are never transferred/analyzed.
  - Output: `~/recordings/<YYYY-MM-DD>_<label>_<HHMM>.wav` plus a JSON sidecar
    `{label, start_iso, duration_s, sample_rate, channels, format, device, host}`.
  - **Fixed mic gain:** set capture gain via `amixer` and disable any AGC at setup; the
    same gain is used every night (comparability). The chosen value is recorded in the spec
    of the build, not changed thereafter.
  - (Arch A only) on completion: `rsync` WAV+sidecar to buildbox `~/mouse-survey/incoming/`,
    then `ssh buildbox analyze <file>`.

### 5.2 Transfer
- Direct `rsync` Pi→buildbox over the shared LAN. Transfers only completed `*.wav` (+ sidecar).
- Idempotent; safe to re-run.

### 5.3 Analyzer (buildbox) — `analyze`
- **Interface:** `analyze <wavfile>` → writes `results/<wavfile>.json`, appends `ranking.csv`,
  writes an evidence pack.
- **Algorithm (band-pass + transient events):**
  1. Load WAV (numpy/scipy).
  2. **Band-pass** to the mouse band — initial `~2–12 kHz` (Butterworth), tunable. HVAC hum,
     traffic, and structural rumble sit mostly below this band.
  3. Compute a short-frame in-band **energy/RMS envelope** (frame ~20–50 ms, with hop).
  4. Estimate a **per-night noise floor** from the frame-energy distribution (median), and a
     spread (MAD).
  5. **Detect events:** contiguous runs of frames exceeding `median + k·MAD` (k tunable,
     ~5), with a **minimum event duration** (e.g. 20 ms) and **gap-merging** (merge events
     separated by < ~50 ms) to reject isolated clicks and fragmentation.
  6. The per-night threshold being derived from that night's own noise floor makes the score
     **self-calibrating** to each night's background — the key to fair cross-night comparison.
- **Score (v1, approved):** primary = **events per hour** (duration-normalized); secondary =
  **total active seconds** (and active fraction). Emit all in the result JSON.
- **Evidence pack:** for the top-N (~20) loudest events, save start/end timestamps and extract
  short clips (event ± ~0.5 s) as WAV, so detections can be spot-listened and confirmed to be
  the mouse (not pipes/creaks/insects).

### 5.4 Report — `report`
- Aggregate `ranking.csv` by spot label: nights recorded, mean events/hr, mean active-time,
  rank. Multiple nights per spot are averaged. CLI printout + CSV.

## 6. One-time setup / build steps

1. **buildbox:** create a Python venv, install numpy/scipy; create
   `~/mouse-survey/{incoming,results,evidence}`; deploy `analyze` + `report`.
2. **Pi:** deploy `record-night`; resolve and verify the persistent device name
   `hw:CARD=Microphone,DEV=0`; set + freeze mic gain via `amixer`, disable AGC; verify
   detached execution + logging.
3. **Trust (Arch A):** passwordless SSH Pi→buildbox + accept buildbox host key.
4. **Sanity check:** record a short test clip, eyeball level and spectrum, confirm the mic
   captures real signal before trusting a full night.

## 7. Testing strategy

- **Analyzer unit tests** on synthetic WAVs:
  - Silence → 0 events.
  - Injected transient bursts at known times/frequencies (in-band) → all detected at the
    right times.
  - Low-frequency broadband noise (below the band) → rejected (≈0 events).
  - Varying noise floors → event counts stay stable (self-calibration works).
- **End-to-end validation** on one real overnight recording: run the full pipeline, manually
  verify the evidence pack, then tune band + threshold (k) from observed behavior.

## 8. Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Non-mouse transients (pipes, creaks, insects) counted as activity | Evidence pack for manual verification; tune band/threshold; ML/template matching is the later upgrade |
| Mouse behavior varies night-to-night | Require ≥2–3 nights per spot before trusting a ranking; report shows n_nights |
| ALSA card number reorders across reboots | Reference device by persistent name `hw:CARD=Microphone,DEV=0`; verify at build |
| Mic gain/AGC drift breaks comparability | Fix gain via `amixer`, disable AGC, never change it |
| Pi IP is DHCP (push path fragility) | Optional DHCP reservation for `192.168.0.5` to harden Arch A |
| Disk fill | ~2.6 GB/night → ~45 nights on buildbox; retention: keep raw N nights, keep derived features/results indefinitely |
| SSH multiplexing unavailable on this harness | Architecture already connects rarely; not a blocker |

## 9. Out of scope for v1 (YAGNI)

Real-time alerting, web dashboard, single-placement direction-finding, multi-mic
triangulation, and ML/DNN classification are all deferred. v1 is: labeled fixed-length
overnight recording → band-pass transient scoring → cross-night ranking.

## 10. Open items to resolve during implementation

- Exact band edges and threshold `k` (tune on first real night's audio).
- nohup vs systemd for detached recording (start with nohup + pidfile; systemd if we want
  it survivable across reboots).
- Whether to store the ranking as CSV or SQLite (start CSV; revisit if queries grow).
