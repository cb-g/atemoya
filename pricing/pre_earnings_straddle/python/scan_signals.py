#!/usr/bin/env python3
"""
Pre-earnings straddle signal scanner — ranks tickers by earnings IV setup.

Reads *_iv_snapshots.csv files and identifies:
- IV inflation: how much IV has risen as earnings approach
- Straddle value: is the straddle cheap or expensive vs implied move
- Days to earnings: urgency of the signal

Key signals:
- Low implied move + near earnings: straddle is cheap → buy straddle
- High implied move + far from earnings: straddle is expensive → sell straddle
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
SEGMENT_DIR = Path(__file__).resolve().parents[2] / "liquidity" / "data"

# Optional macro regime context (enriches output when available)
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
try:
    from lib.python.context import load_macro_regime
except ImportError:
    load_macro_regime = lambda: None
try:
    from lib.python.context import load_ticker_sentiment
except ImportError:
    load_ticker_sentiment = lambda t: None

import re


def price_to_segment(price: float) -> str:
    """Compute segment label from a spot price."""
    if price <= 0:
        return "unknown"
    bucket = int(price // 10) * 10
    if bucket >= 200:
        return "above $200"
    low = bucket + 1 if bucket > 0 else 1
    high = bucket + 10
    return f"${low}-${high}"


def load_segment_map(segment_dir: Path) -> dict[str, str]:
    """Build ticker -> segment label map from liquid_options_*_USD.txt files."""
    segment_map = {}
    for f in sorted(segment_dir.glob("liquid_options_*_USD.txt")):
        name = f.stem.replace("liquid_options_", "").replace("_USD", "")
        m = re.match(r"(\d+)_to_(\d+)", name)
        if m:
            label = f"${m.group(1)}-${m.group(2)}"
        elif name.startswith("above_"):
            label = f"above ${name.split('_')[1]}"
        else:
            label = name
        tickers = [t.strip() for t in f.read_text().splitlines() if t.strip()]
        for t in tickers:
            segment_map[t] = label
    return segment_map


def load_histories(data_dir: Path) -> dict[str, pd.DataFrame]:
    """Load IV snapshot CSVs from both yfinance and thetadata sources."""
    histories = {}
    ticker_dfs: dict[str, list[pd.DataFrame]] = {}
    for pattern in ("*_iv_snapshots_yfinance.csv", "*_iv_snapshots_thetadata.csv"):
        for f in sorted(data_dir.glob(pattern)):
            ticker = f.stem.replace("_iv_snapshots_yfinance", "").replace("_iv_snapshots_thetadata", "")
            try:
                df = pd.read_csv(f)
                if not df.empty:
                    ticker_dfs.setdefault(ticker, []).append(df)
            except Exception:
                continue

    for ticker, dfs in ticker_dfs.items():
        merged = pd.concat(dfs, ignore_index=True)
        merged = merged.drop_duplicates(subset=["date"], keep="first")
        merged = merged.sort_values("date").reset_index(drop=True)
        if len(merged) >= 1:
            histories[ticker] = merged

    return histories


def classify_signal(row: pd.Series) -> tuple[str, str]:
    """Classify earnings straddle signal."""
    days = row["days_to_earnings"]
    implied_move_pct = row["implied_move"] * 100
    straddle_pct = (row["straddle_cost"] / row["spot"]) * 100

    # IV inflation: straddle cost as % of spot vs implied move
    ratio = straddle_pct / implied_move_pct if implied_move_pct > 0 else 1.0

    if days <= 3:
        if ratio < 0.8:
            return "BUY STRADDLE", f"{days}d to earnings, straddle cheap ({straddle_pct:.1f}% vs {implied_move_pct:.1f}% implied)"
        elif ratio > 1.5:
            return "SELL STRADDLE", f"{days}d to earnings, straddle expensive ({straddle_pct:.1f}% vs {implied_move_pct:.1f}% implied)"
        else:
            return "EARNINGS IMMINENT", f"{days}d to earnings, straddle={straddle_pct:.1f}%, implied move={implied_move_pct:.1f}%"
    elif days <= 7:
        if ratio < 0.8:
            return "LEAN BUY STRADDLE", f"{days}d to earnings, straddle below implied"
        elif ratio > 1.5:
            return "LEAN SELL STRADDLE", f"{days}d to earnings, straddle above implied"
        else:
            return "WATCH", f"{days}d to earnings, straddle={straddle_pct:.1f}%"
    else:
        return "WATCH", f"{days}d to earnings, IV={row['avg_iv']*100:.0f}%"


def scan(data_dir: Path, segment_map: dict[str, str] | None = None) -> pd.DataFrame:
    """Run the full scan and return a ranked DataFrame."""
    histories = load_histories(data_dir)
    if not histories:
        return pd.DataFrame()

    rows = []
    regime = load_macro_regime()
    for ticker, df in histories.items():
        latest = df.iloc[-1]

        if latest["days_to_earnings"] <= 0:
            continue

        signal, description = classify_signal(latest)

        # IV change if we have history
        iv_change = np.nan
        if len(df) >= 2:
            iv_change = (latest["avg_iv"] - df.iloc[0]["avg_iv"]) / df.iloc[0]["avg_iv"]

        row = {
            "ticker": ticker,
            "snapshots": len(df),
            "signal": signal,
            "description": description,
            "days_to_earnings": int(latest["days_to_earnings"]),
            "earnings_date": latest["earnings_date"],
            "avg_iv": latest["avg_iv"],
            "implied_move": latest["implied_move"],
            "straddle_cost": latest["straddle_cost"],
            "spot": latest["spot"],
            "straddle_pct": (latest["straddle_cost"] / latest["spot"]) * 100,
            "iv_change_pct": iv_change * 100 if not np.isnan(iv_change) else np.nan,
        }
        if segment_map is not None:
            seg = segment_map.get(ticker)
            if seg is None:
                seg = price_to_segment(latest["spot"])
            row["segment"] = seg
        if regime:
            row["macro_regime"] = regime["cycle_phase"]
            row["risk_sentiment"] = regime["risk_sentiment"]
        sentiment = load_ticker_sentiment(ticker)
        if sentiment:
            row["sentiment_score"] = sentiment["sentiment_score"]
            row["sentiment_bias"] = sentiment["sentiment_signal"]
        rows.append(row)

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    # Sort by days to earnings (most urgent first)
    result = result.sort_values("days_to_earnings")
    return result.reset_index(drop=True)


def print_report(df: pd.DataFrame, quiet: bool = False):
    """Print a human-readable signal report."""
    if df.empty:
        print("No earnings signals found.")
        return

    actionable = df[df["signal"].str.contains("BUY|SELL|IMMINENT")]
    watch = df[df["signal"] == "WATCH"]

    if not actionable.empty:
        print(f"\n{'='*80}")
        print(f"  ACTIONABLE SIGNALS ({len(actionable)} tickers)")
        print(f"{'='*80}")
        for _, row in actionable.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            iv_chg = f"  IV chg: {row['iv_change_pct']:+.1f}%" if not np.isnan(row.get("iv_change_pct", np.nan)) else ""
            print(f"\n  {row['ticker']:6s}  {row['signal']}{seg}")
            print(f"         {row['description']}")
            print(f"         Earnings: {row['earnings_date']}  Spot: ${row['spot']:.2f}  "
                  f"Straddle: ${row['straddle_cost']:.2f} ({row['straddle_pct']:.1f}%){iv_chg}")

    if not quiet and not watch.empty:
        print(f"\n{'='*80}")
        print(f"  WATCH ({len(watch)} tickers)")
        print(f"{'='*80}")
        for _, row in watch.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            print(f"  {row['ticker']:6s}  {row['days_to_earnings']}d  earnings={row['earnings_date']}  "
                  f"IV={row['avg_iv']*100:.0f}%  straddle={row['straddle_pct']:.1f}%{seg}")

    print(f"\n  Scanned: {len(df)} tickers with upcoming earnings")
    print(f"  Actionable: {len(actionable)}")


def main():
    parser = argparse.ArgumentParser(
        description="Scan pre-earnings IV snapshots for straddle signals"
    )
    parser.add_argument("--data-dir", type=str, default=str(DATA_DIR))
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--segments", action="store_true")
    parser.add_argument("--quiet", action="store_true")

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Error: {data_dir} not found", file=sys.stderr)
        sys.exit(1)

    segment_map = None
    if args.segments and SEGMENT_DIR.exists():
        segment_map = load_segment_map(SEGMENT_DIR)
        print(f"Loaded {len(segment_map)} tickers across segments")

    print(f"Pre-Earnings Straddle Scanner")
    print(f"Data: {data_dir}")

    result = scan(data_dir, segment_map)
    print_report(result, args.quiet)

    if args.output and not result.empty:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)
        print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
