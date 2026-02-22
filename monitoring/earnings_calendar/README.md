# Earnings Calendar

Track upcoming earnings dates for portfolio holdings and generate pre-earnings alerts.

## Features

- Fetch upcoming earnings dates from yfinance
- Configurable alert window (default 14 days) with priority levels
- Pre/post-market timing detection (BMO/AMC)
- Historical EPS surprise tracking (last 4 quarters per ticker)
- Read tickers from watchlist `portfolio.json` or CLI `--tickers`
- Parallel fetching with ThreadPoolExecutor
- ntfy.sh notification integration via `--notify` flag

## Directory Structure

```
monitoring/earnings_calendar/
├── python/
│   ├── fetch/
│   │   └── fetch_earnings_calendar.py  # Fetch earnings dates + history
│   └── viz/
│       └── plot_earnings_calendar.py   # 2-panel dashboard
├── data/
│   └── earnings_calendar.json          # Fetched data (gitignored)
├── output/
│   └── earnings_calendar.svg           # Showcase dashboard
└── README.md
```

## Usage

### 1. Fetch Earnings Data

**Docker (recommended):**
```bash
# From CLI tickers
docker compose exec -w /app atemoya /bin/bash -c \
  "uv run python monitoring/earnings_calendar/python/fetch/fetch_earnings_calendar.py \
   --tickers AAPL,NVDA,TSLA,AMZN,GOOGL"

# From watchlist portfolio
docker compose exec -w /app atemoya /bin/bash -c \
  "uv run python monitoring/earnings_calendar/python/fetch/fetch_earnings_calendar.py \
   --portfolio monitoring/watchlist/data/portfolio.json"

# Custom alert window
docker compose exec -w /app atemoya /bin/bash -c \
  "uv run python monitoring/earnings_calendar/python/fetch/fetch_earnings_calendar.py \
   --tickers AAPL,NVDA --days-ahead 7"
```

**Native:**
```bash
uv run python monitoring/earnings_calendar/python/fetch/fetch_earnings_calendar.py \
  --tickers AAPL,NVDA,TSLA
```

### 2. Visualize

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c \
  "uv run python monitoring/earnings_calendar/python/viz/plot_earnings_calendar.py \
   --input monitoring/earnings_calendar/data/earnings_calendar.json"
```

**Native:**
```bash
uv run python monitoring/earnings_calendar/python/viz/plot_earnings_calendar.py \
  --input monitoring/earnings_calendar/data/earnings_calendar.json
```

### 3. Notifications

Generate alerts JSON for ntfy.sh integration:
```bash
docker compose exec -w /app atemoya /bin/bash -c \
  "uv run python monitoring/earnings_calendar/python/fetch/fetch_earnings_calendar.py \
   --tickers AAPL,NVDA --notify"
```

Or pipe to watchlist notification system:
```bash
docker compose exec -w /app atemoya /bin/bash -c \
  "uv run python monitoring/watchlist/python/notify.py \
   --alerts monitoring/earnings_calendar/data/earnings_calendar.json --topic my-alerts"
```

## Output

<img src="output/earnings_calendar.svg" width="800">

## CLI Options

### fetch_earnings_calendar.py

| Flag | Default | Description |
|------|---------|-------------|
| `--tickers, -t` | — | Comma-separated ticker symbols |
| `--portfolio, -p` | — | Path to watchlist portfolio.json |
| `--output, -o` | `data/earnings_calendar.json` | Output JSON path |
| `--days-ahead, -d` | `14` | Alert window in days |
| `--notify` | `false` | Print alerts JSON for ntfy.sh |
| `--workers, -w` | `4` | Parallel fetch workers |

### plot_earnings_calendar.py

| Flag | Default | Description |
|------|---------|-------------|
| `--input, -i` | — | Input JSON (required) |
| `--output-dir, -o` | `output/` | Output directory |
