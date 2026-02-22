#!/usr/bin/env python3
"""
Fetch Google Trends data for ticker keywords.

Uses pytrends library to access Google Trends data with rate limiting
and caching to avoid being blocked.

Usage:
    python fetch_trends.py AAPL NVDA TSLA
    python fetch_trends.py --all  # Fetch all tickers in keyword_map.json
"""

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from pytrends.request import TrendReq

import numpy as np


def to_python_types(obj):
    """Convert numpy types to Python native types for JSON serialization."""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: to_python_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_python_types(i) for i in obj]
    return obj


# Rate limiting settings
REQUEST_DELAY = 3.0  # Seconds between requests
MAX_KEYWORDS_PER_REQUEST = 5  # Google Trends limit


def load_keyword_map(filepath: Path) -> dict:
    """Load ticker-to-keyword mapping."""
    with open(filepath) as f:
        return json.load(f)


class TrendsClient:
    """Google Trends client with rate limiting."""

    def __init__(self, delay: float = REQUEST_DELAY):
        self.pytrends = TrendReq(hl='en-US', tz=360)
        self.delay = delay
        self.last_request = 0

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request = time.time()

    def get_interest_over_time(self, keywords: list[str], timeframe: str = 'today 3-m') -> dict:
        """
        Get search interest over time for keywords.

        Args:
            keywords: List of search terms (max 5)
            timeframe: Time range (e.g., 'today 3-m', 'today 12-m', 'now 7-d')

        Returns:
            Dict with date index and interest values per keyword
        """
        if len(keywords) > MAX_KEYWORDS_PER_REQUEST:
            keywords = keywords[:MAX_KEYWORDS_PER_REQUEST]

        self._rate_limit()

        try:
            self.pytrends.build_payload(keywords, timeframe=timeframe, geo='US')
            df = self.pytrends.interest_over_time()

            if df.empty:
                return {"error": "No data returned", "keywords": keywords}

            # Convert to serializable format
            result = {
                "timeframe": timeframe,
                "keywords": keywords,
                "dates": [d.isoformat() for d in df.index],
                "data": {}
            }

            for kw in keywords:
                if kw in df.columns:
                    values = df[kw].tolist()
                    result["data"][kw] = {
                        "values": values,
                        "current": values[-1] if values else 0,
                        "mean": float(np.mean(values)) if values else 0,
                        "max": max(values) if values else 0,
                        "min": min(values) if values else 0,
                    }

            return result

        except Exception as e:
            return {"error": str(e), "keywords": keywords}

    def get_related_queries(self, keyword: str) -> dict:
        """Get related queries for a keyword."""
        self._rate_limit()

        try:
            self.pytrends.build_payload([keyword], timeframe='today 3-m', geo='US')
            related = self.pytrends.related_queries()

            result = {
                "keyword": keyword,
                "rising": [],
                "top": []
            }

            if keyword in related:
                rising_df = related[keyword].get('rising')
                top_df = related[keyword].get('top')

                if rising_df is not None and not rising_df.empty:
                    result["rising"] = [
                        {"query": row["query"], "value": str(row["value"])}
                        for _, row in rising_df.head(10).iterrows()
                    ]

                if top_df is not None and not top_df.empty:
                    result["top"] = [
                        {"query": row["query"], "value": int(row["value"])}
                        for _, row in top_df.head(10).iterrows()
                    ]

            return result

        except Exception as e:
            return {"error": str(e), "keyword": keyword}

    def get_realtime_trending(self) -> list:
        """Get current trending searches in the US."""
        self._rate_limit()

        try:
            df = self.pytrends.trending_searches(pn='united_states')
            return df[0].tolist()[:20]
        except Exception as e:
            return [f"Error: {e}"]


def fetch_ticker_trends(client: TrendsClient, ticker: str, keywords_config: dict) -> dict:
    """Fetch all trend data for a single ticker."""
    result = {
        "ticker": ticker,
        "timestamp": datetime.now().isoformat(),
        "trends": {},
        "related": {},
        "signals": {}
    }

    # Fetch brand trends
    brand_keywords = keywords_config.get("brand", [])
    if brand_keywords:
        print(f"    Fetching brand trends: {brand_keywords}")
        brand_data = client.get_interest_over_time(brand_keywords, 'today 3-m')
        result["trends"]["brand"] = brand_data

        # Also get related queries for primary brand
        if brand_keywords:
            related = client.get_related_queries(brand_keywords[0])
            result["related"]["brand"] = related

    # Fetch product trends
    product_keywords = keywords_config.get("products", [])
    if product_keywords:
        print(f"    Fetching product trends: {product_keywords[:5]}")
        product_data = client.get_interest_over_time(product_keywords[:5], 'today 3-m')
        result["trends"]["products"] = product_data

    # Fetch stock-specific trends
    stock_keywords = keywords_config.get("stock", [])
    if stock_keywords:
        print(f"    Fetching stock trends: {stock_keywords}")
        stock_data = client.get_interest_over_time(stock_keywords, 'today 3-m')
        result["trends"]["stock"] = stock_data

    # Fetch negative sentiment trends
    negative_keywords = keywords_config.get("negative", [])
    if negative_keywords:
        print(f"    Fetching negative trends: {negative_keywords[:5]}")
        negative_data = client.get_interest_over_time(negative_keywords[:5], 'today 3-m')
        result["trends"]["negative"] = negative_data

    return result


def analyze_trends(trends_data: dict) -> dict:
    """Analyze trend data and generate signals."""
    signals = {}

    # Analyze brand trends
    brand_trends = trends_data.get("trends", {}).get("brand", {})
    if brand_trends and "data" in brand_trends:
        for keyword, data in brand_trends["data"].items():
            values = data.get("values", [])
            if len(values) >= 7:
                current = values[-1]
                week_ago = values[-7] if len(values) >= 7 else values[0]
                month_ago = values[-30] if len(values) >= 30 else values[0]

                # Calculate changes
                change_7d = ((current - week_ago) / week_ago * 100) if week_ago > 0 else 0
                change_30d = ((current - month_ago) / month_ago * 100) if month_ago > 0 else 0

                signals["brand_momentum"] = {
                    "keyword": keyword,
                    "current": current,
                    "change_7d_pct": round(change_7d, 1),
                    "change_30d_pct": round(change_30d, 1),
                    "surge": change_7d > 25,  # >25% increase in 7 days
                }
                break  # Only analyze primary brand

    # Analyze stock interest
    stock_trends = trends_data.get("trends", {}).get("stock", {})
    if stock_trends and "data" in stock_trends:
        stock_values = []
        for keyword, data in stock_trends["data"].items():
            if "stock" in keyword.lower():
                stock_values = data.get("values", [])
                break

        if stock_values:
            current = stock_values[-1]
            mean_val = np.mean(stock_values)
            percentile = (sum(1 for v in stock_values if v <= current) / len(stock_values)) * 100

            signals["retail_attention"] = {
                "current": current,
                "mean": round(mean_val, 1),
                "percentile": round(percentile, 1),
                "elevated": current > mean_val * 1.5,
            }

    # Analyze negative sentiment
    negative_trends = trends_data.get("trends", {}).get("negative", {})
    if negative_trends and "data" in negative_trends:
        max_negative = 0
        spike_keyword = None
        for keyword, data in negative_trends["data"].items():
            current = data.get("current", 0)
            mean_val = data.get("mean", 1)
            if current > max_negative:
                max_negative = current
                spike_keyword = keyword
                neg_elevated = current > mean_val * 2  # 2x normal = spike

        if spike_keyword:
            signals["negative_sentiment"] = {
                "keyword": spike_keyword,
                "current": max_negative,
                "spike": neg_elevated if 'neg_elevated' in dir() else False,
            }

    # Analyze related rising queries
    related = trends_data.get("related", {}).get("brand", {})
    rising = related.get("rising", [])
    if rising:
        signals["rising_queries"] = [q["query"] for q in rising[:5]]

    return signals


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch Google Trends data for tickers")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols to fetch")
    parser.add_argument("--all", action="store_true", help="Fetch all tickers in keyword_map.json")
    parser.add_argument("--keyword-map", type=Path,
                        default=Path(__file__).parent.parent / "data" / "keyword_map.json")
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).parent.parent / "data" / "trends_raw")

    args = parser.parse_args()

    # Load keyword mapping
    keyword_map = load_keyword_map(args.keyword_map)

    # Determine tickers to fetch
    if args.all:
        tickers = [t for t in keyword_map.keys() if not t.startswith("_")]
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        print("Error: Specify tickers or use --all", file=sys.stderr)
        sys.exit(1)

    # Filter to tickers we have keywords for
    tickers = [t for t in tickers if t in keyword_map]

    if not tickers:
        print("No valid tickers found in keyword map")
        sys.exit(1)

    print(f"Fetching Google Trends for {len(tickers)} ticker(s)...")

    # Initialize client
    client = TrendsClient()

    # Fetch trends for each ticker
    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_results = []

    for ticker in tickers:
        print(f"\n{ticker}:")
        keywords_config = keyword_map[ticker]

        try:
            trends_data = fetch_ticker_trends(client, ticker, keywords_config)
            trends_data["signals"] = analyze_trends(trends_data)

            # Save individual ticker data (convert numpy types)
            trends_data = to_python_types(trends_data)
            output_file = args.output_dir / f"trends_{ticker}.json"
            with open(output_file, "w") as f:
                json.dump(trends_data, f, indent=2)

            all_results.append(trends_data)

            # Print summary
            signals = trends_data.get("signals", {})
            if signals.get("brand_momentum", {}).get("surge"):
                print(f"    SIGNAL: Brand surge detected (+{signals['brand_momentum']['change_7d_pct']}% 7d)")
            if signals.get("retail_attention", {}).get("elevated"):
                print(f"    SIGNAL: Elevated retail attention (percentile: {signals['retail_attention']['percentile']})")
            if signals.get("negative_sentiment", {}).get("spike"):
                print(f"    SIGNAL: Negative sentiment spike ({signals['negative_sentiment']['keyword']})")

        except Exception as e:
            print(f"    ERROR: {e}")

    # Save combined results
    combined_output = args.output_dir.parent / "trends_combined.json"
    combined = {
        "fetch_time": datetime.now().isoformat(),
        "ticker_count": len(all_results),
        "tickers": all_results
    }
    with open(combined_output, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"\nResults saved to {args.output_dir}")
    print(f"Combined results: {combined_output}")


if __name__ == "__main__":
    main()
