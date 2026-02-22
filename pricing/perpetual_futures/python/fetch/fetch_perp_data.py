#!/usr/bin/env python3
"""
Fetch perpetual futures market data from cryptocurrency exchanges.

Fetches spot price, mark price, funding rate, and other metrics
for perpetual futures contracts.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import urllib.request
import urllib.error

# Add project root to path for data_fetcher
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))


def fetch_binance_perp(symbol: str = "BTCUSDT") -> dict:
    """
    Fetch perpetual futures data from Binance.

    Binance API:
    - /fapi/v1/premiumIndex - funding rate and mark price
    - /fapi/v1/ticker/price - futures price
    - /api/v3/ticker/price - spot price
    """
    base_url = "https://fapi.binance.com"
    spot_url = "https://api.binance.com"

    try:
        # Get funding rate and mark price
        premium_url = f"{base_url}/fapi/v1/premiumIndex?symbol={symbol}"
        with urllib.request.urlopen(premium_url, timeout=10) as response:
            premium_data = json.loads(response.read().decode())

        # Get spot price (use base symbol without USDT suffix for spot)
        base_symbol = symbol.replace("USDT", "")
        spot_symbol = f"{base_symbol}USDT"
        spot_api_url = f"{spot_url}/api/v3/ticker/price?symbol={spot_symbol}"
        with urllib.request.urlopen(spot_api_url, timeout=10) as response:
            spot_data = json.loads(response.read().decode())

        # Get 24h stats for volume and open interest
        stats_url = f"{base_url}/fapi/v1/ticker/24hr?symbol={symbol}"
        with urllib.request.urlopen(stats_url, timeout=10) as response:
            stats_data = json.loads(response.read().decode())

        return {
            "exchange": "Binance",
            "symbol": symbol,
            "spot": float(spot_data["price"]),
            "mark_price": float(premium_data["markPrice"]),
            "index_price": float(premium_data["indexPrice"]),
            "funding_rate": float(premium_data["lastFundingRate"]),
            "funding_interval_hours": 8,
            "next_funding_time": premium_data.get("nextFundingTime"),
            "open_interest": float(stats_data.get("openInterest", 0)),
            "volume_24h": float(stats_data.get("quoteVolume", 0)),
            "timestamp": datetime.now().isoformat(),
        }

    except urllib.error.URLError as e:
        print(f"Error fetching from Binance: {e}")
        return None
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error parsing Binance response: {e}")
        return None


def fetch_deribit_perp(currency: str = "BTC") -> dict:
    """
    Fetch perpetual futures data from Deribit.

    Deribit API:
    - /public/get_index_price - index price
    - /public/ticker - perpetual contract data
    """
    base_url = "https://www.deribit.com/api/v2"
    instrument = f"{currency}-PERPETUAL"

    try:
        # Get ticker data (includes funding, mark price, etc.)
        ticker_url = f"{base_url}/public/ticker?instrument_name={instrument}"
        with urllib.request.urlopen(ticker_url, timeout=10) as response:
            ticker_resp = json.loads(response.read().decode())
            ticker_data = ticker_resp.get("result", {})

        # Get index price
        index_url = f"{base_url}/public/get_index_price?index_name={currency.lower()}_usd"
        with urllib.request.urlopen(index_url, timeout=10) as response:
            index_resp = json.loads(response.read().decode())
            index_data = index_resp.get("result", {})

        return {
            "exchange": "Deribit",
            "symbol": instrument,
            "spot": float(index_data.get("index_price", 0)),
            "mark_price": float(ticker_data.get("mark_price", 0)),
            "index_price": float(ticker_data.get("index_price", 0)),
            "funding_rate": float(ticker_data.get("current_funding", 0)),
            "funding_interval_hours": 8,
            "open_interest": float(ticker_data.get("open_interest", 0)),
            "volume_24h": float(ticker_data.get("stats", {}).get("volume_usd", 0)),
            "timestamp": datetime.now().isoformat(),
        }

    except urllib.error.URLError as e:
        print(f"Error fetching from Deribit: {e}")
        return None
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error parsing Deribit response: {e}")
        return None


def fetch_bybit_perp(symbol: str = "BTCUSDT") -> dict:
    """
    Fetch perpetual futures data from Bybit.

    Bybit API v5:
    - /v5/market/tickers - market data including funding
    """
    base_url = "https://api.bybit.com"

    try:
        # Get ticker data
        ticker_url = f"{base_url}/v5/market/tickers?category=linear&symbol={symbol}"
        with urllib.request.urlopen(ticker_url, timeout=10) as response:
            resp = json.loads(response.read().decode())
            ticker_list = resp.get("result", {}).get("list", [])
            if not ticker_list:
                return None
            ticker_data = ticker_list[0]

        return {
            "exchange": "Bybit",
            "symbol": symbol,
            "spot": float(ticker_data.get("indexPrice", 0)),
            "mark_price": float(ticker_data.get("markPrice", 0)),
            "index_price": float(ticker_data.get("indexPrice", 0)),
            "funding_rate": float(ticker_data.get("fundingRate", 0)),
            "funding_interval_hours": 8,
            "open_interest": float(ticker_data.get("openInterest", 0)),
            "volume_24h": float(ticker_data.get("turnover24h", 0)),
            "timestamp": datetime.now().isoformat(),
        }

    except urllib.error.URLError as e:
        print(f"Error fetching from Bybit: {e}")
        return None
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error parsing Bybit response: {e}")
        return None


def fetch_perp_data(
    symbol: str = "BTCUSDT",
    exchange: str = "binance"
) -> Optional[dict]:
    """
    Fetch perpetual futures data from specified exchange.

    Args:
        symbol: Trading pair symbol (e.g., BTCUSDT, ETHUSDT)
        exchange: Exchange name (binance, deribit, bybit)

    Returns:
        Dictionary with market data or None if fetch fails
    """
    exchange_lower = exchange.lower()

    if exchange_lower == "binance":
        return fetch_binance_perp(symbol)
    elif exchange_lower == "deribit":
        # Deribit uses currency name, not symbol
        currency = symbol.replace("USDT", "").replace("USD", "")
        return fetch_deribit_perp(currency)
    elif exchange_lower == "bybit":
        return fetch_bybit_perp(symbol)
    else:
        print(f"Unknown exchange: {exchange}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Fetch perpetual futures market data from crypto exchanges"
    )
    parser.add_argument(
        "--symbol", "-s",
        default="BTCUSDT",
        help="Trading pair symbol (default: BTCUSDT)"
    )
    parser.add_argument(
        "--exchange", "-e",
        default="binance",
        choices=["binance", "deribit", "bybit"],
        help="Exchange to fetch from (default: binance)"
    )
    parser.add_argument(
        "--output", "-o",
        default="pricing/perpetual_futures/data/market_data.json",
        help="Output file path"
    )

    args = parser.parse_args()

    print(f"Fetching {args.symbol} perpetual data from {args.exchange}...")
    data = fetch_perp_data(args.symbol, args.exchange)

    if data is None:
        print("Failed to fetch data")
        sys.exit(1)

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nData written to {output_path}")
    print(f"\nMarket Data Summary:")
    print(f"  Exchange:      {data['exchange']}")
    print(f"  Symbol:        {data['symbol']}")
    print(f"  Spot/Index:    ${data['index_price']:,.2f}")
    print(f"  Mark Price:    ${data['mark_price']:,.2f}")
    print(f"  Funding Rate:  {data['funding_rate']*100:.4f}% (per {data['funding_interval_hours']}h)")

    # Annualize funding rate
    periods_per_year = 365 * 24 / data['funding_interval_hours']
    annual_funding = data['funding_rate'] * periods_per_year
    print(f"  Annual Funding: {annual_funding*100:.2f}%")

    basis = data['mark_price'] - data['index_price']
    basis_pct = basis / data['index_price'] * 100
    print(f"  Basis:         ${basis:,.2f} ({basis_pct:.4f}%)")


if __name__ == "__main__":
    main()
