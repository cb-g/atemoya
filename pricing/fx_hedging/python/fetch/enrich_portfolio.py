#!/usr/bin/env python3
"""
Enrich a simple ticker+quantity portfolio with prices and currencies from yfinance.

Input:  CSV with ticker,quantity columns
Output: Full portfolio.csv with ticker,quantity,price_usd,currency,pct_exposure

The FX exposure currency is determined by the company's country of domicile,
not the exchange it trades on. ASML trades in USD on NASDAQ but is a Dutch
company with EUR-denominated revenues — its FX exposure is EUR.

Usage:
    python enrich_portfolio.py pricing/fx_hedging/data/portfolio.csv
    python enrich_portfolio.py pricing/fx_hedging/data/portfolio.csv --home-currency EUR
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[4]))

import csv
import yfinance as yf


# Map country of domicile → FX exposure currency
COUNTRY_TO_CURRENCY = {
    'Netherlands': 'EUR', 'Germany': 'EUR', 'France': 'EUR',
    'Italy': 'EUR', 'Spain': 'EUR', 'Belgium': 'EUR',
    'Ireland': 'EUR', 'Finland': 'EUR', 'Austria': 'EUR',
    'Portugal': 'EUR', 'Greece': 'EUR', 'Luxembourg': 'EUR',
    'United Kingdom': 'GBP',
    'Japan': 'JPY',
    'Switzerland': 'CHF',
    'Australia': 'AUD',
    'Canada': 'CAD',
    'China': 'CNY', 'Hong Kong': 'CNY',
    'South Korea': 'KRW',
    'Taiwan': 'TWD',
    'India': 'INR',
    'Brazil': 'BRL',
    'Sweden': 'SEK',
    'Norway': 'NOK',
    'Denmark': 'DKK',
    'United States': 'USD',
}

# Direct crypto tickers → crypto "currency" for hedging
CRYPTO_TICKERS = {
    'BTC-USD': 'BTC', 'ETH-USD': 'ETH', 'SOL-USD': 'SOL',
    'XRP-USD': 'XRP', 'ADA-USD': 'ADA', 'LINK-USD': 'LINK',
}

# Stocks with significant crypto exposure (BTC treasury / mining)
CRYPTO_PROXY_STOCKS = {
    'MSTR': 'BTC', 'MARA': 'BTC', 'RIOT': 'BTC', 'CLSK': 'BTC',
    'COIN': 'BTC',  # exchange — broad crypto, approximate as BTC
    'IBIT': 'BTC', 'FBTC': 'BTC', 'GBTC': 'BTC',  # BTC ETFs
    'ETHA': 'ETH', 'ETHE': 'ETH',  # ETH ETFs
}


def enrich_portfolio(input_file: str, home_currency: str = 'USD'):
    """Read ticker+quantity, fetch prices/currencies, write full CSV."""
    positions = []

    with open(input_file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row['ticker'].strip()
            quantity = float(row['quantity'])
            if ticker:
                positions.append({'ticker': ticker, 'quantity': quantity})

    if not positions:
        print("No positions found", file=sys.stderr)
        sys.exit(1)

    print(f"Enriching {len(positions)} positions (home currency: {home_currency})...")

    enriched = []
    for pos in positions:
        ticker = pos['ticker']
        qty = pos['quantity']

        try:
            info = yf.Ticker(ticker).info
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            if price is None:
                price = 0

            trading_currency = info.get('currency', 'USD')
            country = info.get('country', '')

            # Check for crypto exposure: direct crypto or proxy stocks
            if ticker in CRYPTO_TICKERS:
                exchange_currency = CRYPTO_TICKERS[ticker]
            elif ticker in CRYPTO_PROXY_STOCKS:
                exchange_currency = CRYPTO_PROXY_STOCKS[ticker]
            else:
                exchange_currency = COUNTRY_TO_CURRENCY.get(country, trading_currency)

            # Handle GBp (pence) → GBP
            if trading_currency == 'GBp':
                price = price / 100.0
                trading_currency = 'GBP'

            # Convert to USD if traded in foreign currency
            if trading_currency != 'USD':
                fx_pair = f"{trading_currency}USD=X"
                try:
                    fx_info = yf.Ticker(fx_pair).info
                    fx_rate = fx_info.get('regularMarketPrice', 1.0)
                    if fx_rate is None:
                        fx_rate = 1.0
                except Exception:
                    fx_rate = 1.0
                price_usd = price * fx_rate
            else:
                price_usd = price

            print(f"  {ticker:8s} ${price_usd:>10,.2f}  {exchange_currency}  ({country})")

            enriched.append({
                'ticker': ticker,
                'quantity': qty,
                'price_usd': round(price_usd, 2),
                'currency': exchange_currency,
                'pct_exposure': 1.0,
            })

        except Exception as e:
            print(f"  {ticker:8s} ERROR: {e}", file=sys.stderr)
            enriched.append({
                'ticker': ticker,
                'quantity': qty,
                'price_usd': 0.0,
                'currency': 'USD',
                'pct_exposure': 1.0,
            })

    # Filter out positions with zero price (not found)
    failed = [e for e in enriched if e['price_usd'] == 0]
    if failed:
        tickers = ', '.join(e['ticker'] for e in failed)
        print(f"\n  Warning: no price data for {tickers} — these will be excluded")
        enriched = [e for e in enriched if e['price_usd'] > 0]

    # Filter out home-currency positions (no FX exposure)
    home_positions = [e for e in enriched if e['currency'] == home_currency]
    fx_positions = [e for e in enriched if e['currency'] != home_currency]

    if home_positions:
        tickers = ', '.join(e['ticker'] for e in home_positions)
        home_val = sum(e['price_usd'] * e['quantity'] for e in home_positions)
        print(f"\n  {home_currency}-denominated (no FX exposure): {tickers} (${home_val:,.0f})")

    # Write enriched CSV (only FX-exposed positions)
    output = fx_positions if fx_positions else enriched
    with open(input_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['ticker', 'quantity', 'price_usd', 'currency', 'pct_exposure'])
        writer.writeheader()
        writer.writerows(output)

    total = sum(e['price_usd'] * e['quantity'] for e in output)
    print(f"\nFX-exposed portfolio value: ${total:,.2f}")
    print(f"Written to: {input_file}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Enrich portfolio with prices and FX currencies")
    parser.add_argument("portfolio", help="Path to portfolio CSV (ticker,quantity)")
    parser.add_argument("--home-currency", default="USD",
                        help="Home currency — positions in this currency are excluded (default: USD)")
    args = parser.parse_args()
    enrich_portfolio(args.portfolio, args.home_currency)
