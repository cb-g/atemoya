#!/usr/bin/env bash
#
# Daily Skew Surface Collector
#
# Collects vol surface snapshots and computes real skew metrics.
# Runs inside the Docker container via cron.
#
# Usage:
#   ./pricing/skew_trading/cron_collect.sh                    # Default tickers (SPY)
#   ./pricing/skew_trading/cron_collect.sh SPY,AAPL,TSLA     # Explicit ticker list
#   ./pricing/skew_trading/cron_collect.sh --quiet            # Suppress stdout (for cron)
#
# Cron setup:
#   Docker (inside container):
#     echo "15 21 * * 1-5 cd /app && ./pricing/skew_trading/cron_collect.sh --quiet" >> /app/crontab
#     crontab /app/crontab
#
#   Host (from project root):
#     (crontab -l 2>/dev/null; echo "15 21 * * 1-5 cd $(pwd) && ./pricing/skew_trading/cron_collect.sh --quiet") | crontab -
#
# Environment variables:
#   SKEW_TICKERS   Override default ticker list (comma-separated)
#

set -e

# Find script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

LOG_DIR="$SCRIPT_DIR/log"
LOG_FILE="$LOG_DIR/cron_collect.log"

# Defaults
DEFAULT_TICKERS="SPY"

# Parse arguments
TICKERS=""
QUIET=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --quiet|-q)
            QUIET=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [TICKERS] [--quiet]"
            echo "  TICKERS: comma-separated ticker list (default: $DEFAULT_TICKERS)"
            echo "  --quiet: suppress stdout (for cron)"
            exit 0
            ;;
        *)
            TICKERS="$1"
            shift
            ;;
    esac
done

# Resolve tickers: argument > env var > default
TICKERS="${TICKERS:-${SKEW_TICKERS:-$DEFAULT_TICKERS}}"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Ensure PATH includes uv and opam binaries (cron runs with minimal env)
# Works both inside Docker (/home/atemoya/...) and on host ($HOME/...)
export PATH="$HOME/.local/bin:$HOME/.opam/atemoya-build/bin:/home/atemoya/.local/bin:/home/atemoya/.opam/atemoya-build/bin:$PATH"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg" >> "$LOG_FILE"
    if [[ "$QUIET" != "true" ]]; then
        echo "$msg"
    fi
}

log "=== Daily Skew Collection: $TICKERS ==="

cd "$PROJECT_ROOT"

# Step 1: Run collector
log "Running collect_snapshot.py --tickers $TICKERS"

OUTPUT=$(uv run pricing/skew_trading/python/fetch/collect_snapshot.py --tickers "$TICKERS" 2>&1) || {
    log "ERROR: Collection failed"
    log "$OUTPUT"
    exit 1
}

log "$OUTPUT"

# Step 2: Regenerate timeseries CSVs so downstream OCaml reads latest data
IFS=',' read -ra TICKER_ARRAY <<< "$TICKERS"
for T in "${TICKER_ARRAY[@]}"; do
    log "Updating timeseries for $T"
    TS_OUTPUT=$(uv run pricing/skew_trading/python/fetch/compute_skew_timeseries.py --ticker "$T" 2>&1) || {
        log "WARNING: Timeseries update failed for $T"
        log "$TS_OUTPUT"
    }
    log "$TS_OUTPUT"
done

log "=== Collection complete ==="
