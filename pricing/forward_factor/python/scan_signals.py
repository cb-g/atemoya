#!/usr/bin/env python3
"""
Forward factor signal scanner — ranks tickers by term structure backwardation.

Reads *_ff_history.csv files, computes z-scores for forward factor across
history, and classifies signals.

Key signals (matching OCaml scanner thresholds):
- FF >= 1.00: EXTREME backwardation — exceptional calendar spread setup
- FF >= 0.50: STRONG backwardation — high quality
- FF >= 0.20: VALID backwardation — entry threshold
- FF < 0.20: Below threshold, skip
- FF < 0:    Contango, avoid

Z-scores add historical context: is today's FF extreme relative to this
ticker's own history?
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
SEGMENT_DIR = Path(__file__).resolve().parents[2] / "liquidity" / "data"

# Forward factor thresholds (matching OCaml types.ml)
FF_EXTREME = 1.00
FF_STRONG = 0.50
FF_VALID = 0.20


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


def load_histories(data_dir: Path, min_days: int) -> dict[str, pd.DataFrame]:
    """Load all forward factor history CSVs with at least min_days observations."""
    histories = {}
    for f in sorted(data_dir.glob("*_ff_history.csv")):
        ticker = f.stem.replace("_ff_history", "")
        try:
            df = pd.read_csv(f)
            if len(df) >= min_days:
                histories[ticker] = df
        except Exception:
            continue
    return histories


def compute_z_scores(series: pd.Series, window: int = 0) -> tuple[float, float, float]:
    """Compute z-score for latest value against history.

    Args:
        series: Time series of values.
        window: Lookback window (0 = all history).

    Returns:
        (z_score, latest, mean) — z_score is NaN if insufficient data.
    """
    series = series.dropna()
    if len(series) < 1:
        return np.nan, np.nan, np.nan

    latest = series.iloc[-1]

    if len(series) < 3:
        return np.nan, latest, np.nan

    if window > 0 and len(series) > window:
        series = series.iloc[-window:]

    mean = series.iloc[:-1].mean()
    std = series.iloc[:-1].std()
    z = (latest - mean) / std if std > 0 else np.nan

    return z, latest, mean


def classify_signal(ff: float, ff_z: float) -> tuple[str, str]:
    """Classify forward factor signal."""
    if ff >= FF_EXTREME:
        signal = "SELL CALENDAR"
        desc = f"FF={ff:.2f} ({ff*100:.0f}%) — EXTREME backwardation, exceptional setup"
    elif ff >= FF_STRONG:
        signal = "SELL CALENDAR"
        desc = f"FF={ff:.2f} ({ff*100:.0f}%) — STRONG backwardation"
    elif ff >= FF_VALID:
        signal = "LEAN SELL CAL"
        desc = f"FF={ff:.2f} ({ff*100:.0f}%) — valid backwardation"
    elif ff >= 0:
        return "NEUTRAL", f"FF={ff:.2f} — weak backwardation, below threshold"
    else:
        return "NEUTRAL", f"FF={ff:.2f} — contango, avoid"

    # Enrich with z-score context if available
    if not np.isnan(ff_z):
        desc += f" (z={ff_z:+.1f})"

    return signal, desc


def scan(data_dir: Path, min_days: int, threshold: float,
         preferred_pair: str | None = None,
         segment_map: dict[str, str] | None = None,
         window: int = 0) -> pd.DataFrame:
    """Run the full scan and return a ranked DataFrame."""
    histories = load_histories(data_dir, min_days)
    if not histories:
        return pd.DataFrame()

    rows = []
    for ticker, df in histories.items():
        # For each ticker, pick the best DTE pair (highest FF) or preferred pair
        if preferred_pair:
            pair_df = df[df["dte_pair"] == preferred_pair]
        else:
            pair_df = df

        if pair_df.empty:
            continue

        # Get the latest observation per DTE pair, pick highest FF
        latest_per_pair = pair_df.groupby("dte_pair").last()
        best_pair = latest_per_pair["forward_factor"].idxmax()
        latest = latest_per_pair.loc[best_pair]

        ff = latest["forward_factor"]

        # Compute z-score on this DTE pair's FF history
        pair_series = df[df["dte_pair"] == best_pair]["forward_factor"]
        ff_z, _, ff_mean = compute_z_scores(pair_series, window=window)

        signal, description = classify_signal(ff, ff_z)

        max_z = abs(ff_z) if not np.isnan(ff_z) else abs(ff / 0.1) if ff != 0 else 0

        row = {
            "ticker": ticker,
            "days": len(pair_series),
            "dte_pair": best_pair,
            "signal": signal,
            "description": description,
            "forward_factor": ff,
            "ff_z": ff_z,
            "front_iv": latest["front_iv"],
            "back_iv": latest["back_iv"],
            "forward_vol": latest["forward_vol"],
            "max_abs_z": max_z,
        }
        if segment_map is not None:
            seg = segment_map.get(ticker, "unknown")
            row["segment"] = seg
        rows.append(row)

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    # Filter by threshold and sort by FF descending
    result = result[result["forward_factor"] >= threshold].sort_values(
        "forward_factor", ascending=False
    )
    return result.reset_index(drop=True)


def _segment_sort_key(label: str) -> tuple:
    m = re.match(r"\$(\d+)-\$(\d+)", label)
    if m:
        return (0, int(m.group(1)))
    if label.startswith("above"):
        return (1, 0)
    return (2, 0)


def print_report(df: pd.DataFrame, quiet: bool = False, segments: bool = False):
    """Print a human-readable signal report."""
    if df.empty:
        print("No signals found above threshold.")
        return

    actionable = df[~df["signal"].str.contains("NEUTRAL")]
    neutral = df[df["signal"].str.contains("NEUTRAL")]

    if not actionable.empty:
        print(f"\n{'='*80}")
        print(f"  ACTIONABLE SIGNALS ({len(actionable)} tickers)")
        print(f"{'='*80}")
        for _, row in actionable.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            print(f"\n  {row['ticker']:6s}  {row['signal']}  [{row['dte_pair']}]{seg}")
            print(f"         {row['description']}")
            z_str = f"  z={row['ff_z']:+.2f}" if not np.isnan(row['ff_z']) else ""
            print(f"         Front IV={row['front_iv']*100:.1f}%  Back IV={row['back_iv']*100:.1f}%  "
                  f"Fwd Vol={row['forward_vol']*100:.1f}%{z_str}  ({row['days']} days)")

    if segments and "segment" in df.columns:
        seg_actionable = actionable if not actionable.empty else pd.DataFrame()
        segment_order = sorted(df["segment"].unique(), key=_segment_sort_key)

        print(f"\n{'='*80}")
        print(f"  BY SEGMENT")
        print(f"{'='*80}")
        for seg in segment_order:
            seg_act = seg_actionable[seg_actionable["segment"] == seg] if not seg_actionable.empty else pd.DataFrame()
            seg_df = df[df["segment"] == seg]
            print(f"\n  --- {seg} ({len(seg_act)} actionable / {len(seg_df)} scanned) ---")
            if seg_act.empty:
                print(f"    no actionable signals")
                continue
            for _, row in seg_act.iterrows():
                print(f"    {row['ticker']:6s}  {row['signal']}  FF={row['forward_factor']:.2f}  [{row['dte_pair']}]")
                print(f"           {row['description']}")

    if not quiet and not neutral.empty:
        print(f"\n{'='*80}")
        print(f"  BELOW THRESHOLD ({len(neutral)} tickers)")
        print(f"{'='*80}")
        for _, row in neutral.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            print(f"  {row['ticker']:6s}  FF={row['forward_factor']:+.4f}  [{row['dte_pair']}]{seg}")

    print(f"\n  Scanned: {len(df)} tickers above threshold")
    print(f"  Actionable: {len(actionable)}")


def main():
    parser = argparse.ArgumentParser(
        description="Scan forward factor history for calendar spread signals"
    )
    parser.add_argument("--data-dir", type=str, default=str(DATA_DIR))
    parser.add_argument("--min-days", type=int, default=1)
    parser.add_argument("--threshold", type=float, default=0.0,
                        help="Min FF to include in output (default: 0.0, show all)")
    parser.add_argument("--dte-pair", type=str, default=None,
                        help="Filter to specific DTE pair (e.g., '60-90')")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--segments", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--window", type=int, default=0,
                        help="Z-score lookback window (0=all history)")

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Error: {data_dir} not found", file=sys.stderr)
        sys.exit(1)

    segment_map = None
    if args.segments and SEGMENT_DIR.exists():
        segment_map = load_segment_map(SEGMENT_DIR)
        print(f"Loaded {len(segment_map)} tickers across segments")

    print(f"Forward Factor Signal Scanner")
    print(f"Data: {data_dir}")
    print(f"Thresholds: FF>={FF_VALID} (valid), >={FF_STRONG} (strong), >={FF_EXTREME} (extreme)")
    if args.dte_pair:
        print(f"DTE pair filter: {args.dte_pair}")
    if args.window > 0:
        print(f"Z-score window: last {args.window} observations")

    result = scan(data_dir, args.min_days, args.threshold,
                  preferred_pair=args.dte_pair,
                  segment_map=segment_map, window=args.window)
    print_report(result, args.quiet, args.segments)

    if args.output and not result.empty:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)
        print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
