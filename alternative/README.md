# Alt Data - Alternative Data Signal Aggregation

Umbrella module that aggregates alternative data signals from six sub-modules into a unified dashboard. Each sub-module fetches data from a distinct source, analyzes it for actionable signals, and produces watchlist-compatible alerts that can feed into the portfolio tracker notification system.

## Overview

- Six independent sub-modules covering insider trading, options flow, short interest, Google Trends, SEC filings, and NLP sentiment
- Every sub-module produces alerts in a common JSON format compatible with the watchlist notification pipeline
- Parent-level visualization combines all sources into a single 6-panel dashboard
- Each sub-module can be run independently or orchestrated together

## Sub-Modules

### Insider Trading (`insider_trading/`)

Fetches SEC Form 4 filings via EDGAR API, parses XML transactions, and classifies insider activity. Detects cluster buying (multiple insiders purchasing within a window), executive open-market purchases, and large transactions. Calculates buy/sell sentiment scores.

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run alternative/insider_trading/python/fetch_form4.py AAPL NVDA"
docker compose exec -w /app atemoya /bin/bash -c "uv run alternative/insider_trading/python/analyze_insider.py"
```

**Native:**
```bash
uv run alternative/insider_trading/python/fetch_form4.py AAPL NVDA
uv run alternative/insider_trading/python/analyze_insider.py
```

### Options Flow (`options_flow/`)

Fetches options chain data via yfinance, calculates volume/OI ratios, premium breakdowns, and put/call ratios. Scores unusual activity (0-100) based on premium size, volume vs open interest, DTE urgency, delta, and raw volume. Detects bullish/bearish flow sentiment.

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run alternative/options_flow/python/fetch_flow.py AAPL NVDA"
docker compose exec -w /app atemoya /bin/bash -c "uv run alternative/options_flow/python/analyze_flow.py"
```

**Native:**
```bash
uv run alternative/options_flow/python/fetch_flow.py AAPL NVDA
uv run alternative/options_flow/python/analyze_flow.py
```

### Short Interest (`short_interest/`)

Fetches short interest metrics via yfinance: shares short, short % of float, days to cover, and month-over-month changes. Calculates a squeeze potential score (0-100) based on SI%, DTC, SI trend, float size, and market cap. Detects high short interest, increasing/decreasing SI, and squeeze candidates.

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run alternative/short_interest/python/fetch_short_interest.py AAPL GME AMC"
docker compose exec -w /app atemoya /bin/bash -c "uv run alternative/short_interest/python/analyze_shorts.py"
```

**Native:**
```bash
uv run alternative/short_interest/python/fetch_short_interest.py AAPL GME AMC
uv run alternative/short_interest/python/analyze_shorts.py
```

### Google Trends (`google_trends/`)

Fetches Google Trends interest-over-time data using pytrends for brand, product, stock, and negative sentiment keywords. Calculates attention scores (0-100) from brand momentum, retail attention percentiles, and rising query activity. Detects brand search surges, elevated retail attention, and negative sentiment spikes.

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run alternative/google_trends/python/fetch_trends.py --all"
docker compose exec -w /app atemoya /bin/bash -c "uv run alternative/google_trends/python/analyze_trends.py"
```

**Native:**
```bash
uv run alternative/google_trends/python/fetch_trends.py --all
uv run alternative/google_trends/python/analyze_trends.py
```

### SEC Filings (`sec_filings/`)

Fetches recent SEC filings via EDGAR API (8-K, 10-K, 10-Q, 13D/G, DEF 14A, S-1). Parses 8-K items to identify material events: earnings releases (Item 2.02), acquisitions (Item 2.01), executive changes (Item 5.02), material agreements (Item 1.01), and Reg FD disclosures (Item 7.01). Detects activist 13D positions.

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run alternative/sec_filings/python/fetch_filings.py AAPL NVDA --days 30"
docker compose exec -w /app atemoya /bin/bash -c "uv run alternative/sec_filings/python/analyze_filings.py"
```

**Native:**
```bash
uv run alternative/sec_filings/python/fetch_filings.py AAPL NVDA --days 30
uv run alternative/sec_filings/python/analyze_filings.py
```

### NLP Sentiment (`nlp_sentiment/`)

Narrative drift detection and sentiment analysis for SEC filings, earnings transcripts, and Discord chat data. Uses FinBERT for financial sentiment scoring, emoji/keyword-based signals for social media, and commitment/hedging language detection. Includes a full pipeline for document embedding and ranking. See `nlp_sentiment/README.md` for detailed Discord integration instructions.

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run alternative/nlp_sentiment/python/pipeline.py AAPL NVDA --quarters 12"
```

**Native:**
```bash
uv run alternative/nlp_sentiment/python/pipeline.py AAPL NVDA --quarters 12
```

## Architecture

```
alt_data/
├── google_trends/
│   ├── data/                    # Keyword maps and fetched trends
│   ├── output/                  # Alerts JSON
│   └── python/
│       ├── fetch_trends.py      # Google Trends fetcher with rate limiting
│       └── analyze_trends.py    # Attention scoring and alert generation
├── insider_trading/
│   ├── data/                    # Fetched Form 4 transactions
│   ├── output/                  # Alerts JSON
│   └── python/
│       ├── fetch_form4.py       # SEC EDGAR Form 4 fetcher and XML parser
│       └── analyze_insider.py   # Cluster buying, exec buys, sentiment analysis
├── nlp_sentiment/
│   ├── data/                    # Documents, embeddings, Discord exports
│   ├── output/                  # Pipeline results, signals, snippets
│   ├── python/
│   │   ├── fetch/               # SEC MDA, transcripts, Discord import, FinBERT
│   │   ├── detect/              # Commitment, delta, hedging language detection
│   │   ├── embed/               # Document embedding
│   │   ├── surface/             # Signal ranking
│   │   └── pipeline.py          # Full NLP pipeline orchestrator
│   └── README.md                # Detailed documentation including Discord setup
├── options_flow/
│   ├── data/                    # Fetched options chain data
│   ├── output/                  # Alerts JSON
│   └── python/
│       ├── fetch_flow.py        # Options chain fetcher with unusual scoring
│       └── analyze_flow.py      # Bullish/bearish flow, large premium detection
├── sec_filings/
│   ├── data/                    # Fetched EDGAR filings
│   ├── output/                  # Alerts JSON
│   └── python/
│       ├── fetch_filings.py     # SEC EDGAR filing fetcher with 8-K item parsing
│       └── analyze_filings.py   # Material event detection, activist positions
├── short_interest/
│   ├── data/                    # Fetched short interest data
│   ├── output/                  # Alerts JSON
│   └── python/
│       ├── fetch_short_interest.py  # Short interest and squeeze score calculator
│       └── analyze_shorts.py        # SI alerts and squeeze candidate detection
├── python/
│   └── viz/
│       └── plot_alt_data.py     # Combined 6-panel dashboard across all sources
└── output/
    ├── alt_data_dashboard.png   # Combined dashboard
    └── alt_data_dashboard.svg
```

## Visualize Combined Dashboard

After running one or more sub-modules, generate the combined 6-panel dashboard:

**Docker:**
```bash
docker compose exec -w /app atemoya /bin/bash -c "uv run alternative/python/viz/plot_alt_data.py"
```

**Native:**
```bash
uv run alternative/python/viz/plot_alt_data.py
```

## Output

- `output/alt_data_dashboard.png` -- 6-panel dashboard: insider trading, options flow, short interest, Google Trends, SEC filings, NLP sentiment
- `output/alt_data_dashboard.svg` -- vector version of the dashboard
- Each sub-module also produces its own `output/*_alerts.json` and `output/*_watchlist_alerts.json` for integration with the watchlist notification pipeline

## Alert Format

All sub-modules produce alerts in a common format compatible with the watchlist notification system:

```json
{
  "symbol": "AAPL",
  "type": "insider_cluster_buy",
  "message": "Insider Alert: Cluster buying - 3 insiders purchased ($1,500,000)",
  "priority": 5,
  "priority_name": "urgent",
  "value": 1500000,
  "timestamp": "2026-02-20T10:30:00"
}
```

Priority levels: 1 (min) through 5 (urgent). Alerts can be piped to the watchlist `notify.py` for push notifications via ntfy.sh.
