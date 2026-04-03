#!/usr/bin/env bash
# safe_update.sh — Identity-safe git pull with backup + verification + rollback.
#
# NEVER run `git pull` directly. This script:
#   1. Backs up identity-critical directories (data/, skills/, scratchpads/, manifests/, self/)
#   2. Runs git pull
#   3. Verifies critical files still exist
#   4. Rolls back on failure
#
# Usage: tools/safe_update.sh [branch]
#   branch: git branch to pull (default: current branch)
#
# Source: BUILD-ROADMAP P2-6 (Aether Flux2 pattern — #3 GRAB)

set -euo pipefail

MIND_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$MIND_ROOT/data/backup/pre-update-$(date +%Y%m%d-%H%M%S)"
BRANCH="${1:-}"

# Directories to back up before pull
CRITICAL_DIRS=(
    "data"
    "skills"
    "scratchpads"
    "manifests"
    "self"
)

# Files that MUST exist after pull (relative to MIND_ROOT)
CRITICAL_FILES=(
    "manifests/primary.yaml"
    "src/aiciv_mind/mind.py"
    "src/aiciv_mind/memory.py"
    "src/aiciv_mind/manifest.py"
    "main.py"
)

log() { echo "[safe_update] $*"; }
die() { echo "[safe_update] FATAL: $*" >&2; exit 1; }

cd "$MIND_ROOT"

# --- Step 1: Pre-update backup ---
log "Backing up identity-critical dirs to $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

for dir in "${CRITICAL_DIRS[@]}"; do
    if [ -d "$MIND_ROOT/$dir" ]; then
        cp -a "$MIND_ROOT/$dir" "$BACKUP_DIR/$dir"
        log "  backed up $dir/ ($(find "$BACKUP_DIR/$dir" -type f | wc -l) files)"
    fi
done

# Snapshot current HEAD
git rev-parse HEAD > "$BACKUP_DIR/HEAD_BEFORE"
log "  HEAD before pull: $(cat "$BACKUP_DIR/HEAD_BEFORE")"

# --- Step 2: Git pull ---
log "Running git pull..."
if [ -n "$BRANCH" ]; then
    git pull origin "$BRANCH" 2>&1 | tee "$BACKUP_DIR/pull_output.log"
else
    git pull 2>&1 | tee "$BACKUP_DIR/pull_output.log"
fi

PULL_STATUS=${PIPESTATUS[0]}
if [ "$PULL_STATUS" -ne 0 ]; then
    log "WARNING: git pull exited with status $PULL_STATUS"
fi

git rev-parse HEAD > "$BACKUP_DIR/HEAD_AFTER"
log "  HEAD after pull: $(cat "$BACKUP_DIR/HEAD_AFTER")"

# --- Step 3: Post-update verification ---
log "Verifying critical files..."
MISSING=()
for f in "${CRITICAL_FILES[@]}"; do
    if [ ! -f "$MIND_ROOT/$f" ]; then
        MISSING+=("$f")
        log "  MISSING: $f"
    fi
done

# Check identity dirs still have content
for dir in "${CRITICAL_DIRS[@]}"; do
    if [ -d "$BACKUP_DIR/$dir" ] && [ ! -d "$MIND_ROOT/$dir" ]; then
        MISSING+=("$dir/")
        log "  MISSING DIR: $dir/ (was present before pull)"
    fi
done

# --- Step 4: Rollback if critical files missing ---
if [ ${#MISSING[@]} -gt 0 ]; then
    log "CRITICAL: ${#MISSING[@]} files/dirs missing after pull!"
    log "Rolling back identity-critical directories..."

    for dir in "${CRITICAL_DIRS[@]}"; do
        if [ -d "$BACKUP_DIR/$dir" ]; then
            # Restore backup over whatever git pull left
            rm -rf "$MIND_ROOT/$dir"
            cp -a "$BACKUP_DIR/$dir" "$MIND_ROOT/$dir"
            log "  restored $dir/ from backup"
        fi
    done

    log "Rollback complete. Code may be updated but identity data is safe."
    log "Review the pull manually: git diff $(cat "$BACKUP_DIR/HEAD_BEFORE")..$(cat "$BACKUP_DIR/HEAD_AFTER")"
    exit 1
fi

log "All critical files verified. Update successful."
log "Backup preserved at: $BACKUP_DIR"

# --- Cleanup old backups (keep last 5) ---
BACKUP_PARENT="$MIND_ROOT/data/backup"
if [ -d "$BACKUP_PARENT" ]; then
    BACKUP_COUNT=$(find "$BACKUP_PARENT" -maxdepth 1 -name "pre-update-*" -type d | wc -l)
    if [ "$BACKUP_COUNT" -gt 5 ]; then
        log "Pruning old backups (keeping 5 most recent)..."
        find "$BACKUP_PARENT" -maxdepth 1 -name "pre-update-*" -type d | sort | head -n -5 | xargs rm -rf
    fi
fi
