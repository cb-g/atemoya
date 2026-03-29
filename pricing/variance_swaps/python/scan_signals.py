#!/usr/bin/env python3
"""
Variance swap signal scanner — ranks tickers by IV and variance z-scores.

Reads *_iv_history.csv files, computes z-scores for ATM IV, implied variance,
and near-expiry term structure, then outputs a ranked watchlist.

Key signals:
- High ATM IV z-score: vol is expensive → sell variance (short vol)
- Low ATM IV z-score: vol is cheap → buy variance (long vol)
- Near-expiry compression: term structure flattening signals regime change
"""

import argparse
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


def load_histories(data_dir: Path, min_days: int) -> dict[str, pd.DataFrame]:
    """Load all IV history CSVs with at least min_days observations."""
    histories = {}
    for f in sorted(data_dir.glob("*_iv_history.csv")):
        ticker = f.stem.replace("_iv_history", "")
        try:
            df = pd.read_csv(f)
            if len(df) >= min_days:
                histories[ticker] = df
        except Exception:
            continue
    return histories


def compute_z_scores(df: pd.DataFrame) -> dict[str, float]:
    """Compute z-scores for latest observation against history."""
    scores = {}
    for col in ["atm_iv", "implied_var"]:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if len(series) < 3:
            continue
        mean = series.iloc[:-1].mean()
        std = series.iloc[:-1].std()
        if std > 0:
            scores[f"{col}_z"] = (series.iloc[-1] - mean) / std
            scores[f"{col}_latest"] = series.iloc[-1]
            scores[f"{col}_mean"] = mean

    # Spot change z-score (is underlying moving more than usual?)
    if "spot_price" in df.columns:
        spots = df["spot_price"].dropna()
        if len(spots) >= 3:
            returns = spots.pct_change().dropna()
            if len(returns) >= 2:
                mean_ret = returns.iloc[:-1].mean()
                std_ret = returns.iloc[:-1].std()
                if std_ret > 0:
                    scores["spot_return_z"] = (returns.iloc[-1] - mean_ret) / std_ret

    return scores


def classify_signal(z_iv: float) -> tuple[str, str]:
    """Classify variance swap signal from ATM IV z-score."""
    if abs(z_iv) < 1.0:
        return "NEUTRAL", "z-scores within 1 std"

    if z_iv > 1.5:
        return "SELL VARIANCE", f"IV z={z_iv:+.2f} — vol expensive, sell variance swap"
    if z_iv < -1.5:
        return "BUY VARIANCE", f"IV z={z_iv:+.2f} — vol cheap, buy variance swap"

    if z_iv > 1.0:
        return "LEAN SELL VAR", f"IV z={z_iv:+.2f} — vol moderately expensive"
    if z_iv < -1.0:
        return "LEAN BUY VAR", f"IV z={z_iv:+.2f} — vol moderately cheap"

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

        z_iv = scores.get("atm_iv_z", 0.0)
        z_var = scores.get("implied_var_z", 0.0)
        z_spot = scores.get("spot_return_z", 0.0)

        max_z = max(abs(z_iv), abs(z_var))

        signal, description = classify_signal(z_iv)

        row = {
            "ticker": ticker,
            "days": len(df),
            "signal": signal,
            "description": description,
            "atm_iv_z": z_iv,
            "implied_var_z": z_var,
            "spot_return_z": z_spot,
            "max_abs_z": max_z,
            "atm_iv_latest": scores.get("atm_iv_latest", np.nan),
            "implied_var_latest": scores.get("implied_var_latest", np.nan),
        }
        if segment_map is not None:
            seg = segment_map.get(ticker)
            if seg is None and "spot_price" in df.columns:
                spot = df["spot_price"].dropna()
                if not spot.empty:
                    seg = price_to_segment(spot.iloc[-1])
            row["segment"] = seg if seg else "unknown"
        if regime:
            row["macro_regime"] = regime["cycle_phase"]
            row["risk_sentiment"] = regime["risk_sentiment"]
        rows.append(row)

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    result = result[result["max_abs_z"] >= threshold].sort_values("max_abs_z", ascending=False)
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
            print(f"\n  {row['ticker']:6s}  {row['signal']}{seg}")
            print(f"         {row['description']}")
            print(f"         IV z={row['atm_iv_z']:+.2f}  var z={row['implied_var_z']:+.2f}  "
                  f"spot z={row['spot_return_z']:+.2f}  ({row['days']} days)")
            print(f"         ATM IV={row['atm_iv_latest']*100:.1f}%")

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
                print(f"    {row['ticker']:6s}  {row['signal']}  max|z|={row['max_abs_z']:.2f}")
                print(f"           {row['description']}")

    if not quiet and not neutral.empty:
        print(f"\n{'='*80}")
        print(f"  NEUTRAL ({len(neutral)} tickers)")
        print(f"{'='*80}")
        for _, row in neutral.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            print(f"  {row['ticker']:6s}  max|z|={row['max_abs_z']:.2f}  "
                  f"IV z={row['atm_iv_z']:+.2f}  var z={row['implied_var_z']:+.2f}{seg}")

    print(f"\n  Scanned: {len(df)} tickers above threshold")
    print(f"  Actionable: {len(actionable)}")


def main():
    parser = argparse.ArgumentParser(
        description="Scan variance swap history for z-score based signals"
    )
    parser.add_argument("--data-dir", type=str, default=str(DATA_DIR))
    parser.add_argument("--min-days", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.5)
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

    print(f"Variance Swap Signal Scanner")
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
