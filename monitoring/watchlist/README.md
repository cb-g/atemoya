# Watchlist - Portfolio Tracker with Thesis Scoring and Price Alerts

Tracks portfolio positions with weighted bull/bear thesis arguments, price level alerts, P&L monitoring, and push notifications via ntfy.sh. The OCaml engine scores conviction from thesis weights and checks positions against buy targets, sell targets, and stop losses.

## Overview

- Manages positions (long, short, watching) with cost basis, price levels, and thesis arguments weighted 1-10
- Calculates thesis conviction score (strong bull through strong bear) from aggregated bull/bear weights
- Generates prioritized alerts: stop loss triggers (urgent), target hits (high), approaching levels (normal), and P&L milestones (info)
- State diffing detects new/resolved alerts, significant price moves, and thesis conviction changes between runs
- Push notifications via ntfy.sh with priority-mapped urgency levels and emoji tags
- Shell script orchestrates the full pipeline for cron scheduling (fetch, analyze, diff, notify)

## Architecture

```
watchlist/
├── ocaml/
│   ├── bin/main.ml              # CLI: loads portfolio + prices, runs analysis, outputs alerts
│   ├── lib/
│   │   ├── types.ml             # Position, thesis, alert, and analysis types
│   │   ├── analysis.ml          # Thesis scoring, price alert checks, P&L calculation
│   │   └── io.ml                # JSON parsing, terminal output with ANSI colors, save
│   └── test/
│       └── test_watchlist.ml
├── python/
│   ├── fetch/
│   │   ├── fetch_prices.py      # Fetches current prices for portfolio positions
│   │   └── fetch_watchlist.py   # Fetches extended data: RSI, OBV divergence, volume surges
│   ├── manage.py                # CLI to add/remove/update positions and thesis arguments
│   ├── notify.py                # ntfy.sh notification client with priority mapping
│   ├── state_diff.py            # Compares analysis runs to detect new/resolved alerts
│   └── viz/
│       └── plot_watchlist.py    # 4-panel dashboard: P&L, thesis scores, alerts, price targets
├── data/
│   ├── portfolio.json           # Portfolio positions with thesis arguments
│   ├── watchlist.json           # Watchlist ticker configuration
│   ├── prices.json              # Fetched market prices
│   ├── ticker_data.json         # Extended ticker data (RSI, OBV, volume)
│   └── state.json               # Previous run state for diffing
├── output/
│   ├── analysis.json            # Full analysis output from OCaml engine
│   ├── alerts.json              # Triggered alerts
│   ├── diff.json                # State diff between runs
│   ├── watchlist_dashboard.png  # Dashboard visualization
│   └── watchlist_dashboard.svg
└── run_watchlist.sh             # Full pipeline script for cron
```

## Quickstart

### 1. Build

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune build monitoring/watchlist"
```

**Native:**
```bash
eval $(opam env) && dune build monitoring/watchlist
```

### 2. Manage Portfolio

Add, update, and annotate positions using the management CLI.

**Docker:**
```bash
# List positions
docker compose exec -w /app atemoya /bin/bash -c "uv run monitoring/watchlist/python/manage.py list"

# Add a position
docker compose exec -w /app atemoya /bin/bash -c "uv run monitoring/watchlist/python/manage.py add AAPL --type long --shares 100 --cost 150"

# Add thesis arguments
docker compose exec -w /app atemoya /bin/bash -c "uv run monitoring/watchlist/python/manage.py thesis AAPL --bull 'Services growing 20% YoY' --weight 8"

# Set price levels
docker compose exec -w /app atemoya /bin/bash -c "uv run monitoring/watchlist/python/manage.py update AAPL --stop-loss 130 --sell-target 200"

# Add a catalyst
docker compose exec -w /app atemoya /bin/bash -c "uv run monitoring/watchlist/python/manage.py catalyst AAPL 'Q1 Earnings Jan 30'"
```

**Native:**
```bash
# List positions
uv run monitoring/watchlist/python/manage.py list

# Add a position
uv run monitoring/watchlist/python/manage.py add AAPL --type long --shares 100 --cost 150

# Add thesis arguments
uv run monitoring/watchlist/python/manage.py thesis AAPL --bull 'Services growing 20% YoY' --weight 8

# Set price levels
uv run monitoring/watchlist/python/manage.py update AAPL --stop-loss 130 --sell-target 200

# Add a catalyst
uv run monitoring/watchlist/python/manage.py catalyst AAPL 'Q1 Earnings Jan 30'
```

### 3. Fetch Prices

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run monitoring/watchlist/python/fetch/fetch_prices.py"
```

**Native:**
```bash
uv run monitoring/watchlist/python/fetch/fetch_prices.py
```

### 4. Run Analysis

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune exec watchlist -- --portfolio monitoring/watchlist/data/portfolio.json --prices monitoring/watchlist/data/prices.json --output monitoring/watchlist/output/analysis.json"
```

**Native:**
```bash
eval $(opam env) && dune exec watchlist -- --portfolio monitoring/watchlist/data/portfolio.json --prices monitoring/watchlist/data/prices.json --output monitoring/watchlist/output/analysis.json
```

### 5. Visualize

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run monitoring/watchlist/python/viz/plot_watchlist.py --input monitoring/watchlist/output/analysis.json"
```

**Native:**
```bash
uv run monitoring/watchlist/python/viz/plot_watchlist.py --input monitoring/watchlist/output/analysis.json
```

### Full Pipeline (with notifications)

The shell script runs the complete workflow: fetch prices, run OCaml analysis, diff against previous state, and optionally send push notifications.

```bash
# Analysis only
./monitoring/watchlist/run_watchlist.sh

# Analysis + notifications
./monitoring/watchlist/run_watchlist.sh --notify

# Cron-friendly silent mode
./monitoring/watchlist/run_watchlist.sh --notify --quiet
```

Requires `NTFY_TOPIC` environment variable for notifications. Set in `.env` or export directly.

## Output

- `output/analysis.json` -- per-position analysis: thesis scores, P&L, market data, and triggered alerts
- `output/diff.json` -- new alerts, resolved alerts, price changes, and conviction changes since last run
- `output/alerts.json` -- all triggered alerts with priority levels
- `output/watchlist_dashboard.png` -- 4-panel dashboard: P&L overview, thesis conviction, active alerts, price targets vs current
- `output/watchlist_dashboard.svg` -- vector version of the dashboard

## Testing

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "eval \$(opam env) && dune runtest monitoring/watchlist"
```

**Native:**
```bash
eval $(opam env) && dune runtest monitoring/watchlist
```
