#!/usr/bin/env bash
# One-time: give the Pi passwordless SSH to the buildbox (run from repo root on the dev box).
set -euo pipefail
PI="${1:-rpi3}"; BB="${2:-192.168.0.224}"
# 1) ensure the Pi has a key
ssh "$PI" 'test -f ~/.ssh/id_ed25519 || ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519'
PI_PUB=$(ssh "$PI" 'cat ~/.ssh/id_ed25519.pub')
# 2) authorize the Pi's key on the buildbox (dev box can already reach the buildbox)
ssh "$BB" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && grep -qxF '$PI_PUB' ~/.ssh/authorized_keys 2>/dev/null || echo '$PI_PUB' >> ~/.ssh/authorized_keys"
# 2b) set the correct remote user in the Pi's SSH config so bare-IP connections use codeagent
BB_USER=$(ssh "$BB" 'whoami')
ssh "$PI" "touch ~/.ssh/config && chmod 600 ~/.ssh/config && grep -q 'Host $BB' ~/.ssh/config 2>/dev/null || printf 'Host $BB\n    User $BB_USER\n' >> ~/.ssh/config"
# 3) make the Pi trust the buildbox host key
ssh "$PI" "ssh-keyscan -H $BB >> ~/.ssh/known_hosts 2>/dev/null; true"
# 4) verify
ssh "$PI" "ssh -o BatchMode=yes $BB 'echo pi-to-buildbox-OK; hostname'"
