#!/usr/bin/env bash
#
# Watchlist Cron Script
#
# Run the full watchlist workflow and optionally send notifications.
# Works from both inside Docker (cron) and from the host.
#
# Usage:
#   ./run_watchlist.sh                    # Run analysis only
#   ./run_watchlist.sh --notify           # Run analysis and send alerts
#   ./run_watchlist.sh --notify --quiet   # Silent mode for cron
#
# From host:
#   ./monitoring/watchlist/run_watchlist.sh --notify
#
# Cron (inside Docker container via /app/crontab):
#   0 9-16 * * 1-5 /app/monitoring/watchlist/run_watchlist.sh --notify --quiet
#
# Environment variables (set in .env, passed to Docker via env_file):
#   NTFY_TOPIC   - ntfy.sh topic for notifications (required if --notify)
#   NTFY_SERVER  - ntfy.sh server (default: https://ntfy.sh)
#

set -e

# Detect execution environment:
#   docker  — inside the atemoya Docker container (/app/pyproject.toml exists)
#   native  — local tools available (uv required; opam optional)
#   host    — run commands via docker compose exec
if [ -f /.dockerenv ] && [ -f /app/pyproject.toml ]; then
    RUN_MODE="docker"
elif command -v uv >/dev/null 2>&1; then
    RUN_MODE="native"
else
    RUN_MODE="host"
fi

# Check if OCaml is available (for analysis step)
HAS_OCAML=false
if command -v dune >/dev/null 2>&1 && eval $(opam env 2>/dev/null) && command -v dune >/dev/null 2>&1; then
    HAS_OCAML=true
fi

# Find project root
if [ "$RUN_MODE" = "docker" ]; then
    PROJECT_ROOT="/app"
else
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

cd "$PROJECT_ROOT"

# Load .env if present (native/host modes)
if [ "$RUN_MODE" != "docker" ] && [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Run a command — directly if in docker/native, via docker compose if on host
run_cmd() {
    if [ "$RUN_MODE" = "host" ]; then
        docker compose -f "$PROJECT_ROOT/docker-compose.yml" \
            exec -w /app -T atemoya \
            /bin/bash -c "eval \$(opam env) && $*"
    else
        eval "$@"
    fi
}

# Files (paths relative to project root, used inside Docker or via mount)
WATCHLIST_DIR="monitoring/watchlist"
PORTFOLIO_FILE="$WATCHLIST_DIR/data/portfolio.json"
PRICES_FILE="$WATCHLIST_DIR/data/prices.json"
ANALYSIS_FILE="$WATCHLIST_DIR/output/analysis.json"
STATE_FILE="$WATCHLIST_DIR/data/state.json"
DIFF_FILE="$WATCHLIST_DIR/output/diff.json"

# Parse arguments
NOTIFY=false
QUIET=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --notify|-n)
            NOTIFY=true
            shift
            ;;
        --quiet|-q)
            QUIET=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--notify] [--quiet]"
            echo ""
            echo "Options:"
            echo "  --notify, -n   Send notifications via ntfy.sh"
            echo "  --quiet, -q    Suppress output (for cron)"
            echo ""
            echo "Environment:"
            echo "  NTFY_TOPIC     ntfy.sh topic (required for --notify)"
            echo "  NTFY_SERVER    ntfy.sh server (default: https://ntfy.sh)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Helper function for logging
log() {
    if [[ "$QUIET" != "true" ]]; then
        echo "$@"
    fi
}

# Check prerequisites
if [ "$RUN_MODE" = "host" ]; then
    if ! docker compose -f "$PROJECT_ROOT/docker-compose.yml" ps --format '{{.State}}' 2>/dev/null | grep -q running; then
        echo "Error: Docker container not running. Run: docker compose up -d" >&2
        exit 1
    fi
else
    if [[ ! -f "$PROJECT_ROOT/$PORTFOLIO_FILE" ]]; then
        EXAMPLE_FILE="$WATCHLIST_DIR/data/portfolio.example.json"
        if [[ -f "$PROJECT_ROOT/$EXAMPLE_FILE" ]]; then
            log "No portfolio.json found, copying from portfolio.example.json"
            cp "$PROJECT_ROOT/$EXAMPLE_FILE" "$PROJECT_ROOT/$PORTFOLIO_FILE"
        else
            echo "Error: Portfolio file not found: $PORTFOLIO_FILE" >&2
            exit 1
        fi
    fi
fi

# Ensure output directory exists
run_cmd "mkdir -p $WATCHLIST_DIR/output"

# Step 1: Fetch prices
log "Fetching market prices..."
if [[ "$QUIET" == "true" ]]; then
    run_cmd "uv run python $WATCHLIST_DIR/python/fetch/fetch_prices.py --portfolio $PORTFOLIO_FILE --output $PRICES_FILE" 2>/dev/null
else
    run_cmd "uv run python $WATCHLIST_DIR/python/fetch/fetch_prices.py --portfolio $PORTFOLIO_FILE --output $PRICES_FILE"
fi

# Step 2: Run analysis (OCaml if available, Python fallback otherwise)
log "Running portfolio analysis..."
QUIET_FLAG=""
if [[ "$QUIET" == "true" ]]; then
    QUIET_FLAG="--quiet"
fi
if [ "$HAS_OCAML" = true ] || [ "$RUN_MODE" = "host" ]; then
    run_cmd "eval \$(opam env) && dune exec watchlist -- --portfolio $PORTFOLIO_FILE --prices $PRICES_FILE --output $ANALYSIS_FILE $QUIET_FLAG"
else
    uv run python -m monitoring.watchlist.python.analysis.cli --portfolio "$PORTFOLIO_FILE" --prices "$PRICES_FILE" --output "$ANALYSIS_FILE" $QUIET_FLAG
fi

# Step 3: Detect changes
log "Detecting changes..."
DIFF_OUTPUT=$(run_cmd "uv run python $WATCHLIST_DIR/python/state_diff.py --current $ANALYSIS_FILE --state $STATE_FILE --output $DIFF_FILE --update-state")

if [[ "$QUIET" != "true" ]]; then
    echo "$DIFF_OUTPUT"
fi

# Step 4: Send notifications if requested
if [[ "$NOTIFY" == "true" ]]; then
    if [[ -z "$NTFY_TOPIC" ]]; then
        echo "Error: NTFY_TOPIC environment variable required for --notify" >&2
        echo "  Set in .env or export NTFY_TOPIC=your-topic" >&2
        exit 1
    fi

    # Check if there are new alerts
    NEW_ALERTS=$(run_cmd "python3 -c \"import json; d=json.load(open('$DIFF_FILE')); print(d.get('summary',{}).get('new_alerts',0))\"" 2>/dev/null || echo "0")

    if [[ "$NEW_ALERTS" -gt 0 ]]; then
        log "Sending $NEW_ALERTS notification(s)..."
        run_cmd "uv run python $WATCHLIST_DIR/python/notify.py --alerts $ANALYSIS_FILE --topic $NTFY_TOPIC"
    else
        log "No new alerts to send."
    fi
fi

log "Done."
