#!/usr/bin/env python3
"""
Dispersion trading signal scanner — signals on correlation mispricing.

Reads dispersion_history.csv, computes z-scores for dispersion level
and implied correlation, and classifies signals.

Key signals (matching OCaml dispersion.ml thresholds):
- Z > 1.5: LONG DISPERSION — buy single-name options, sell index options
  (dispersion too wide → correlation cheap → stocks will diverge)
- Z < -1.5: SHORT DISPERSION — sell single-name options, buy index options
  (dispersion too narrow → correlation expensive → stocks will converge)
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


def load_history(data_dir: Path, min_days: int) -> pd.DataFrame | None:
    """Load dispersion history CSV."""
    history_file = data_dir / "dispersion_history.csv"
    if not history_file.exists():
        return None
    try:
        df = pd.read_csv(history_file)
        if len(df) >= min_days:
            return df
    except Exception:
        pass
    return None


def compute_z_scores(df: pd.DataFrame, window: int = 0) -> dict[str, float]:
    """Compute z-scores for latest observation against history."""
    scores = {}
    for col in ["dispersion_level", "implied_correlation"]:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if len(series) < 3:
            if len(series) >= 1:
                scores[f"{col}_latest"] = series.iloc[-1]
            continue
        if window > 0 and len(series) > window:
            series = series.iloc[-window:]
        mean = series.iloc[:-1].mean()
        std = series.iloc[:-1].std()
        if std > 0:
            scores[f"{col}_z"] = (series.iloc[-1] - mean) / std
        scores[f"{col}_latest"] = series.iloc[-1]
        scores[f"{col}_mean"] = mean

    return scores


def classify_signal(disp_z: float, disp_level: float,
                    implied_corr: float, realized_corr: float) -> tuple[str, str]:
    """Classify dispersion signal."""
    # Z-score based (when history available)
    if not np.isnan(disp_z):
        if disp_z > 1.5:
            return "LONG DISPERSION", (
                f"disp z={disp_z:+.2f} — wide, buy constituents sell index "
                f"(disp={disp_level*100:+.1f}%, impl_corr={implied_corr:.2f})"
            )
        if disp_z < -1.5:
            return "SHORT DISPERSION", (
                f"disp z={disp_z:+.2f} — narrow, sell constituents buy index "
                f"(disp={disp_level*100:+.1f}%, impl_corr={implied_corr:.2f})"
            )
        if disp_z > 1.0:
            return "LEAN LONG DISP", (
                f"disp z={disp_z:+.2f} — moderately wide "
                f"(disp={disp_level*100:+.1f}%, impl_corr={implied_corr:.2f})"
            )
        if disp_z < -1.0:
            return "LEAN SHORT DISP", (
                f"disp z={disp_z:+.2f} — moderately narrow "
                f"(disp={disp_level*100:+.1f}%, impl_corr={implied_corr:.2f})"
            )

    # Correlation divergence fallback (day 1)
    corr_gap = implied_corr - realized_corr
    if abs(corr_gap) > 0.2:
        if corr_gap > 0.2:
            return "LEAN LONG DISP", (
                f"impl_corr={implied_corr:.2f} >> real_corr={realized_corr:.2f} "
                f"— correlation overpriced, disp={disp_level*100:+.1f}%"
            )
        if corr_gap < -0.2:
            return "LEAN SHORT DISP", (
                f"impl_corr={implied_corr:.2f} << real_corr={realized_corr:.2f} "
                f"— correlation underpriced, disp={disp_level*100:+.1f}%"
            )

    return "NEUTRAL", (
        f"disp={disp_level*100:+.1f}%, impl_corr={implied_corr:.2f}, "
        f"real_corr={realized_corr:.2f}"
    )


def scan(data_dir: Path, min_days: int, window: int = 0) -> pd.DataFrame:
    """Run the scan and return a DataFrame (single row for dispersion)."""
    df = load_history(data_dir, min_days)
    if df is None or df.empty:
        return pd.DataFrame()

    regime = load_macro_regime()
    latest = df.iloc[-1]
    scores = compute_z_scores(df, window=window)

    disp_z = scores.get("dispersion_level_z", np.nan)
    corr_z = scores.get("implied_correlation_z", np.nan)

    signal, description = classify_signal(
        disp_z, latest["dispersion_level"],
        latest["implied_correlation"], latest["realized_correlation"]
    )

    row = {
        "date": latest["date"],
        "index": latest["index"],
        "signal": signal,
        "description": description,
        "dispersion_level": latest["dispersion_level"],
        "dispersion_z": disp_z,
        "implied_correlation": latest["implied_correlation"],
        "correlation_z": corr_z,
        "realized_correlation": latest["realized_correlation"],
        "index_iv": latest["index_iv"],
        "weighted_avg_iv": latest["weighted_avg_iv"],
        "days": len(df),
    }
    if regime:
        row["macro_regime"] = regime["cycle_phase"]
        row["risk_sentiment"] = regime["risk_sentiment"]

    return pd.DataFrame([row])


def print_report(df: pd.DataFrame):
    """Print signal report."""
    if df.empty:
        print("No dispersion data found.")
        return

    row = df.iloc[0]
    print(f"\n{'='*80}")
    print(f"  DISPERSION TRADING — {row['index']}")
    print(f"{'='*80}")
    print(f"\n  Signal:          {row['signal']}")
    print(f"  {row['description']}")
    print(f"\n  Index IV:        {row['index_iv']*100:.1f}%")
    print(f"  Weighted Avg IV: {row['weighted_avg_iv']*100:.1f}%")
    print(f"  Dispersion:      {row['dispersion_level']*100:+.1f}%")
    if not np.isnan(row['dispersion_z']):
        print(f"  Dispersion z:    {row['dispersion_z']:+.2f}")
    print(f"  Implied Corr:    {row['implied_correlation']:.3f}")
    print(f"  Realized Corr:   {row['realized_correlation']:.3f}")
    if not np.isnan(row['correlation_z']):
        print(f"  Correlation z:   {row['correlation_z']:+.2f}")
    print(f"  History:         {row['days']} days")


def main():
    parser = argparse.ArgumentParser(
        description="Scan dispersion history for correlation mispricing signals"
    )
    parser.add_argument("--data-dir", type=str, default=str(DATA_DIR))
    parser.add_argument("--min-days", type=int, default=1)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--window", type=int, default=0,
                        help="Z-score lookback window (0=all history)")

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Error: {data_dir} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Dispersion Trading Signal Scanner")
    print(f"Data: {data_dir}")
    if args.window > 0:
        print(f"Z-score window: last {args.window} observations")

    result = scan(data_dir, args.min_days, window=args.window)

    if not args.quiet:
        print_report(result)

    if args.output and not result.empty:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)
        print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
