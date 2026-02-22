# Unified Data Fetcher Library

This library provides a unified interface for fetching market data from multiple providers.

## Providers

- **yfinance** (default): Free, no API key required. Provides OHLCV, fundamental data, options, dividends.
- **ibkr**: Interactive Brokers. Provides real-time OHLCV and options data. Requires account and gateway.

## Usage

```python
from lib.python.data_fetcher import fetch_ohlcv, fetch_dividends, get_available_providers

# Check available providers
print(get_available_providers())  # ['yfinance'] or ['yfinance', 'ibkr']

# Fetch OHLCV data (uses IBKR if available, falls back to yfinance)
ohlcv = fetch_ohlcv("AAPL", period="3mo", interval="1d")

# Fetch dividend data
div_data = fetch_dividends("AAPL")
```

## Configuration

Set `DATA_PROVIDER` environment variable to change default provider:
- `DATA_PROVIDER=yfinance` (default)
- `DATA_PROVIDER=ibkr`

For IBKR, also set:
- `IBKR_MODE=tws` or `portal`
- `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID` (for TWS mode)
- `IBKR_GATEWAY_URL`, `IBKR_ACCOUNT_ID` (for portal mode)

## Data Types

| Function | Data Type | IBKR Support | yfinance Support |
|----------|-----------|--------------|------------------|
| `fetch_ohlcv()` | Price data | ✓ | ✓ |
| `fetch_multiple_ohlcv()` | Batch price data | ✓ | ✓ |
| `fetch_ticker_info()` | Basic ticker info | ✓ | ✓ |
| `fetch_option_chain()` | Options data | ✓ | ✓ |
| `fetch_crypto_price()` | Crypto prices | - | ✓ |
| `fetch_financial_statements()` | Financials | - | ✓ |
| `fetch_extended_info()` | Valuation metrics | - | ✓ |
| `fetch_dividends()` | Dividend history | - | ✓ |

## Fetcher Migration Status

### Migrated to data_fetcher (IBKR/yfinance fallback):
- `pricing/regime_downside/python/fetch/fetch_benchmark.py`
- `pricing/regime_downside/python/fetch/fetch_assets.py`
- `pricing/pairs_trading/python/fetch/fetch_pairs.py`
- `pricing/volatility_arbitrage/python/fetch/fetch_historical.py`
- `pricing/skew_trading/python/fetch/fetch_underlying.py`
- `pricing/options_hedging/python/fetch/fetch_underlying.py`
- `pricing/tail_risk_forecast/python/fetch/fetch_intraday.py`
- `monitoring/watchlist/python/fetch_prices.py`
- `monitoring/watchlist/python/fetch_watchlist.py`

### yfinance-only (fundamental data required):
- `valuation/dcf_deterministic/python/fetch_financials.py` - Industry-specific financials (banks, insurance, O&G)
- `valuation/garp_peg/python/fetch/fetch_garp_data.py` - Analyst estimates, EPS, growth rates
- `valuation/dividend_income/python/fetch/fetch_dividend_data.py` - Full dividend history with streak analysis
- `valuation/growth_analysis/python/fetch/fetch_growth_data.py` - Growth metrics
- `valuation/relative_valuation/python/fetch/fetch_peer_data.py` - Peer valuations
- Other valuation and fundamental analysis fetchers

**Note**: Fundamental data (financial statements, analyst estimates, valuation multiples) is only available through yfinance. IBKR is primarily useful for real-time price and options data.
