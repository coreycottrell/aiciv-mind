#!/usr/bin/env bash
# Nightly dream cycle — runs at 2 AM via cron
# Also callable manually: bash tools/run_dream_cycle.sh [--quick] [--no-hub]
set -euo pipefail

cd /home/corey/projects/AI-CIV/aiciv-mind

# Source environment
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Activate venv if present
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

# Run the dream cycle, passing through any flags (e.g. --quick, --no-hub)
exec python3 tools/dream_cycle.py "$@" 2>&1 | tee -a data/dream_cycle.log
