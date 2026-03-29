#!/usr/bin/env python3
"""
Skew signal scanner — ranks all tickers by z-score extremes.

Reads *_skew_history.csv files, computes rolling z-scores for RR25, BF25,
ATM vol, and skew slope, then outputs a ranked watchlist of actionable trades.

With --segments, also breaks down results by underlying price segment
(using liquid_options_*_USD.txt files from the liquidity module).

Designed to run daily after the skew collector finishes, from cron or quickstart.
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Optional macro regime context (enriches output when available)
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
try:
    from lib.python.context import load_macro_regime
except ImportError:
    load_macro_regime = lambda: None

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
SEGMENT_DIR = Path(__file__).resolve().parents[2] / "liquidity" / "data"

METRICS = ["rr25", "bf25", "skew_slope", "atm_vol"]

COLUMNS = [
    "timestamp", "ticker", "expiry", "rr25", "bf25", "skew_slope",
    "atm_vol", "put_25d_vol", "call_25d_vol", "put_25d_strike", "call_25d_strike",
]


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
        # Parse segment label from filename
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


def load_histories(data_dir: Path, min_days: int) -> dict[str, pd.DataFrame]:
    """Load skew history CSVs from both yfinance and thetadata sources.

    Merges both sources per ticker, deduplicates by timestamp (yfinance
    preferred for overlapping dates), requires at least min_days observations.
    """
    histories = {}
    ticker_dfs: dict[str, list[pd.DataFrame]] = {}
    for pattern in ("*_skew_history_yfinance.csv", "*_skew_history_thetadata.csv"):
        for f in sorted(data_dir.glob(pattern)):
            ticker = f.stem.replace("_skew_history_yfinance", "").replace("_skew_history_thetadata", "")
            try:
                df = pd.read_csv(f, names=COLUMNS, header=0)
                if not df.empty:
                    ticker_dfs.setdefault(ticker, []).append(df)
            except Exception:
                continue

    for ticker, dfs in ticker_dfs.items():
        merged = pd.concat(dfs, ignore_index=True)
        merged = merged.drop_duplicates(subset=["timestamp"], keep="first")
        merged = merged.sort_values("timestamp").reset_index(drop=True)
        if len(merged) >= min_days:
            histories[ticker] = merged

    return histories


def compute_z_scores(df: pd.DataFrame) -> dict[str, float]:
    """Compute z-scores for the latest observation against the full history."""
    scores = {}
    for metric in METRICS:
        series = df[metric].dropna()
        if len(series) < 3:
            continue
        mean = series.iloc[:-1].mean()
        std = series.iloc[:-1].std()
        if std > 0:
            scores[f"{metric}_z"] = (series.iloc[-1] - mean) / std
            scores[f"{metric}_latest"] = series.iloc[-1]
            scores[f"{metric}_mean"] = mean
    return scores


def classify_signal(z_rr25: float, z_bf25: float) -> tuple[str, str]:
    """
    Classify trade signal from RR25 and BF25 z-scores.

    Returns (direction, description).
    """
    if abs(z_rr25) < 1.0 and abs(z_bf25) < 1.0:
        return "NEUTRAL", "z-scores within 1 std"

    if z_rr25 > 1.5:
        return "LONG SKEW", f"RR25 z={z_rr25:+.2f} — skew is cheap, buy put spread / sell call spread"
    if z_rr25 < -1.5:
        return "SHORT SKEW", f"RR25 z={z_rr25:+.2f} — skew is rich, sell put spread / buy call spread"

    if z_bf25 > 1.5:
        return "SHORT WINGS", f"BF25 z={z_bf25:+.2f} — wings expensive, sell butterfly"
    if z_bf25 < -1.5:
        return "LONG WINGS", f"BF25 z={z_bf25:+.2f} — wings cheap, buy butterfly"

    # Moderate signals (1.0-1.5)
    if z_rr25 > 1.0:
        return "LEAN LONG SKEW", f"RR25 z={z_rr25:+.2f} — skew moderately cheap"
    if z_rr25 < -1.0:
        return "LEAN SHORT SKEW", f"RR25 z={z_rr25:+.2f} — skew moderately rich"

    if z_bf25 > 1.0:
        return "LEAN SHORT WINGS", f"BF25 z={z_bf25:+.2f} — wings moderately expensive"
    if z_bf25 < -1.0:
        return "LEAN LONG WINGS", f"BF25 z={z_bf25:+.2f} — wings moderately cheap"

    return "NEUTRAL", "no strong signal"


def scan(data_dir: Path, min_days: int, threshold: float,
         segment_map: dict[str, str] | None = None) -> pd.DataFrame:
    """Run the full scan and return a ranked DataFrame."""
    histories = load_histories(data_dir, min_days)
    if not histories:
        return pd.DataFrame()

    rows = []
    regime = load_macro_regime()
    for ticker, df in histories.items():
        scores = compute_z_scores(df)
        if not scores:
            continue

        z_rr25 = scores.get("rr25_z", 0.0)
        z_bf25 = scores.get("bf25_z", 0.0)
        z_atm = scores.get("atm_vol_z", 0.0)
        z_slope = scores.get("skew_slope_z", 0.0)

        # Max absolute z-score across all metrics — used for ranking
        max_z = max(abs(z_rr25), abs(z_bf25), abs(z_atm), abs(z_slope))

        signal, description = classify_signal(z_rr25, z_bf25)

        row = {
            "ticker": ticker,
            "days": len(df),
            "signal": signal,
            "description": description,
            "rr25_z": z_rr25,
            "bf25_z": z_bf25,
            "atm_vol_z": z_atm,
            "skew_slope_z": z_slope,
            "max_abs_z": max_z,
            "rr25_latest": scores.get("rr25_latest", np.nan),
            "atm_vol_latest": scores.get("atm_vol_latest", np.nan),
        }
        if segment_map is not None:
            seg = segment_map.get(ticker)
            if seg is None:
                # Derive from midpoint of 25-delta strikes
                put_k = df["put_25d_strike"].dropna()
                call_k = df["call_25d_strike"].dropna()
                if not put_k.empty and not call_k.empty:
                    spot_est = (put_k.iloc[-1] + call_k.iloc[-1]) / 2
                    seg = price_to_segment(spot_est)
                else:
                    seg = "unknown"
            row["segment"] = seg
        if regime:
            row["macro_regime"] = regime["cycle_phase"]
            row["risk_sentiment"] = regime["risk_sentiment"]
        rows.append(row)

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    # Filter by threshold and sort by max z-score
    result = result[result["max_abs_z"] >= threshold].sort_values("max_abs_z", ascending=False)
    return result.reset_index(drop=True)


def print_ticker_row(row: pd.Series):
    """Print one ticker's signal details."""
    print(f"\n  {row['ticker']:6s}  {row['signal']}")
    print(f"         {row['description']}")
    print(f"         RR25 z={row['rr25_z']:+.2f}  BF25 z={row['bf25_z']:+.2f}  "
          f"ATM vol z={row['atm_vol_z']:+.2f}  slope z={row['skew_slope_z']:+.2f}  "
          f"({row['days']} days)")
    print(f"         RR25={row['rr25_latest']*100:+.2f}%  ATM vol={row['atm_vol_latest']*100:.1f}%")


def print_report(df: pd.DataFrame, quiet: bool = False, segments: bool = False):
    """Print a human-readable signal report."""
    if df.empty:
        print("No signals found above threshold.")
        return

    actionable = df[~df["signal"].str.contains("NEUTRAL")]
    neutral = df[df["signal"].str.contains("NEUTRAL")]

    # Overall ranking
    if not actionable.empty:
        print(f"\n{'='*80}")
        print(f"  ACTIONABLE SIGNALS ({len(actionable)} tickers)")
        print(f"{'='*80}")
        for _, row in actionable.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            print(f"\n  {row['ticker']:6s}  {row['signal']}{seg}")
            print(f"         {row['description']}")
            print(f"         RR25 z={row['rr25_z']:+.2f}  BF25 z={row['bf25_z']:+.2f}  "
                  f"ATM vol z={row['atm_vol_z']:+.2f}  slope z={row['skew_slope_z']:+.2f}  "
                  f"({row['days']} days)")
            print(f"         RR25={row['rr25_latest']*100:+.2f}%  ATM vol={row['atm_vol_latest']*100:.1f}%")

    # Per-segment breakdown
    if segments and "segment" in df.columns:
        seg_actionable = actionable if not actionable.empty else pd.DataFrame()
        segment_order = sorted(df["segment"].unique(), key=_segment_sort_key)

        print(f"\n{'='*80}")
        print(f"  BY SEGMENT")
        print(f"{'='*80}")

        for seg in segment_order:
            seg_df = df[df["segment"] == seg]
            seg_act = seg_actionable[seg_actionable["segment"] == seg] if not seg_actionable.empty else pd.DataFrame()

            print(f"\n  --- {seg} ({len(seg_act)} actionable / {len(seg_df)} scanned) ---")

            if seg_act.empty:
                print(f"    no actionable signals")
                continue

            for _, row in seg_act.iterrows():
                print(f"    {row['ticker']:6s}  {row['signal']}  max|z|={row['max_abs_z']:.2f}")
                print(f"           {row['description']}")

    if not quiet and not neutral.empty:
        print(f"\n{'='*80}")
        print(f"  NEUTRAL ({len(neutral)} tickers)")
        print(f"{'='*80}")
        for _, row in neutral.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            print(f"  {row['ticker']:6s}  max|z|={row['max_abs_z']:.2f}  "
                  f"RR25 z={row['rr25_z']:+.2f}  BF25 z={row['bf25_z']:+.2f}{seg}")

    print(f"\n  Scanned: {len(df)} tickers above threshold")
    print(f"  Actionable: {len(actionable)}")


def _segment_sort_key(label: str) -> tuple:
    """Sort segments numerically: $1-$10 before $11-$20 before above $200."""
    m = re.match(r"\$(\d+)-\$(\d+)", label)
    if m:
        return (0, int(m.group(1)))
    if label.startswith("above"):
        return (1, 0)
    return (2, 0)


def main():
    parser = argparse.ArgumentParser(
        description="Scan skew history for z-score based trade signals"
    )
    parser.add_argument(
        "--data-dir", type=str, default=str(DATA_DIR),
        help="Skew history data directory",
    )
    parser.add_argument(
        "--min-days", type=int, default=5,
        help="Minimum days of history required (default: 5)",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.5,
        help="Minimum max|z-score| to include in output (default: 0.5)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Save results to CSV (overall). With --segments, also saves per-segment CSVs.",
    )
    parser.add_argument(
        "--segments", action="store_true",
        help="Break down results by underlying price segment",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Only show actionable signals, suppress neutral",
    )

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Error: {data_dir} not found", file=sys.stderr)
        sys.exit(1)

    segment_map = None
    if args.segments:
        if SEGMENT_DIR.exists():
            segment_map = load_segment_map(SEGMENT_DIR)
            print(f"Loaded {len(segment_map)} tickers across segments")
        else:
            print(f"Warning: segment dir {SEGMENT_DIR} not found, running without segments",
                  file=sys.stderr)

    print(f"Skew Signal Scanner")
    print(f"Data: {data_dir}")
    print(f"Min days: {args.min_days}, Threshold: {args.threshold}")

    result = scan(data_dir, args.min_days, args.threshold, segment_map)
    print_report(result, args.quiet, args.segments)

    if args.output and not result.empty:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)
        print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
