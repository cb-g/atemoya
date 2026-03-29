#!/usr/bin/env python3
"""
Earnings vol (IV crush) signal scanner — ranks tickers by term structure setup.

Reads *_earnings_vol.csv files and applies the 3-gate filter from the OCaml
filter engine:
  1. Term slope <= -0.05 (front month IV >= 5% higher = backwardation)
  2. Volume >= 1M shares (30-day average)
  3. IV/RV ratio >= 1.1 (implied vol exceeds realized by >= 10%)

Signals:
- SELL IV: all 3 gates pass — sell front-month IV via calendar spread or short straddle
- LEAN SELL IV: slope + 1 other gate — moderate conviction
- WATCH: slope passes only — monitor for gate improvement
- NEUTRAL: no backwardation
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

# Filter thresholds (matching OCaml default_criteria)
SLOPE_THRESHOLD = -0.05
VOLUME_THRESHOLD = 1_000_000.0
IV_RV_THRESHOLD = 1.1


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
    """Load earnings vol history CSVs from both yfinance and thetadata sources."""
    histories = {}
    ticker_dfs: dict[str, list[pd.DataFrame]] = {}
    for pattern in ("*_earnings_vol_yfinance.csv", "*_earnings_vol_thetadata.csv"):
        for f in sorted(data_dir.glob(pattern)):
            ticker = f.stem.replace("_earnings_vol_yfinance", "").replace("_earnings_vol_thetadata", "")
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


def compute_z_scores(df: pd.DataFrame, window: int = 0) -> dict[str, float]:
    """Compute z-scores for latest observation against history.

    Args:
        df: Full history DataFrame.
        window: Number of recent observations to use for mean/std.
                0 means use all history (default).
                E.g., window=72 ≈ last 4 earnings cycles (4 × 18 days).
    """
    scores = {}
    for col in ["term_slope", "iv_rv_ratio", "front_iv"]:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if len(series) < 3:
            # Not enough history for z-scores, just return latest
            if len(series) >= 1:
                scores[f"{col}_latest"] = series.iloc[-1]
            continue
        # Apply window: use only the last N observations (including latest)
        if window > 0 and len(series) > window:
            series = series.iloc[-window:]
        mean = series.iloc[:-1].mean()
        std = series.iloc[:-1].std()
        if std > 0:
            scores[f"{col}_z"] = (series.iloc[-1] - mean) / std
        scores[f"{col}_latest"] = series.iloc[-1]
        scores[f"{col}_mean"] = mean

    return scores


def classify_signal(latest: pd.Series) -> tuple[str, str]:
    """Classify earnings vol signal using the 3-gate filter."""
    term_slope = latest["term_slope"]
    volume = latest["volume"]
    iv_rv = latest["iv_rv_ratio"]

    passes_slope = term_slope <= SLOPE_THRESHOLD
    passes_volume = volume >= VOLUME_THRESHOLD
    passes_iv_rv = iv_rv >= IV_RV_THRESHOLD

    gates_passed = sum([passes_slope, passes_volume, passes_iv_rv])

    if not passes_slope:
        # No backwardation = automatic neutral (contango or flat)
        return "NEUTRAL", f"term slope={term_slope:+.4f} (no backwardation)"

    if gates_passed == 3:
        return "SELL IV", (
            f"slope={term_slope:+.4f}, vol={volume/1e6:.1f}M, IV/RV={iv_rv:.2f} "
            f"— all gates pass, sell front-month IV"
        )
    elif gates_passed == 2:
        missing = []
        if not passes_volume:
            missing.append(f"vol={volume/1e6:.1f}M<1M")
        if not passes_iv_rv:
            missing.append(f"IV/RV={iv_rv:.2f}<1.1")
        return "LEAN SELL IV", (
            f"slope={term_slope:+.4f}, {' '.join(missing)} "
            f"— backwardation + 1 gate"
        )
    else:
        return "WATCH", (
            f"slope={term_slope:+.4f}, vol={volume/1e6:.1f}M, IV/RV={iv_rv:.2f} "
            f"— backwardation only"
        )


def scan(data_dir: Path, segment_map: dict[str, str] | None = None,
         window: int = 0) -> pd.DataFrame:
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
        scores = compute_z_scores(df, window=window)

        row = {
            "ticker": ticker,
            "snapshots": len(df),
            "signal": signal,
            "description": description,
            "days_to_earnings": int(latest["days_to_earnings"]),
            "earnings_date": latest["earnings_date"],
            "front_iv": latest["front_iv"],
            "back_iv": latest["back_iv"],
            "term_slope": latest["term_slope"],
            "volume": latest["volume"],
            "rv": latest["rv"],
            "iv_rv_ratio": latest["iv_rv_ratio"],
            "spot": latest["spot"],
            "term_slope_z": scores.get("term_slope_z", np.nan),
            "iv_rv_z": scores.get("iv_rv_ratio_z", np.nan),
        }
        if segment_map is not None:
            seg = segment_map.get(ticker)
            if seg is None:
                seg = price_to_segment(latest["spot"])
            row["segment"] = seg
        if regime:
            row["macro_regime"] = regime["cycle_phase"]
            row["risk_sentiment"] = regime["risk_sentiment"]
        rows.append(row)

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    # Sort by term slope (most backwardated first), then days to earnings
    result = result.sort_values(["term_slope", "days_to_earnings"])
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
        print("No earnings vol signals found.")
        return

    actionable = df[df["signal"].str.contains("SELL")]
    watch = df[df["signal"] == "WATCH"]
    neutral = df[df["signal"] == "NEUTRAL"]

    if not actionable.empty:
        print(f"\n{'='*80}")
        print(f"  ACTIONABLE SIGNALS ({len(actionable)} tickers)")
        print(f"{'='*80}")
        for _, row in actionable.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            print(f"\n  {row['ticker']:6s}  {row['signal']}{seg}")
            print(f"         {row['description']}")
            print(f"         Earnings: {row['earnings_date']} ({row['days_to_earnings']}d)  "
                  f"Spot: ${row['spot']:.2f}")
            print(f"         Front IV={row['front_iv']*100:.1f}%  Back IV={row['back_iv']*100:.1f}%  "
                  f"RV={row['rv']*100:.1f}%")

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
                print(f"    {row['ticker']:6s}  {row['signal']}  slope={row['term_slope']:+.4f}")
                print(f"           {row['description']}")

    if not quiet and not watch.empty:
        print(f"\n{'='*80}")
        print(f"  WATCH ({len(watch)} tickers)")
        print(f"{'='*80}")
        for _, row in watch.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            print(f"  {row['ticker']:6s}  {row['days_to_earnings']}d  slope={row['term_slope']:+.4f}  "
                  f"vol={row['volume']/1e6:.1f}M  IV/RV={row['iv_rv_ratio']:.2f}{seg}")

    if not quiet and not neutral.empty:
        print(f"\n{'='*80}")
        print(f"  NEUTRAL ({len(neutral)} tickers)")
        print(f"{'='*80}")
        for _, row in neutral.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            print(f"  {row['ticker']:6s}  {row['days_to_earnings']}d  slope={row['term_slope']:+.4f}{seg}")

    print(f"\n  Scanned: {len(df)} tickers with upcoming earnings")
    print(f"  Actionable: {len(actionable)}")
    print(f"  Watch: {len(watch)}")


def main():
    parser = argparse.ArgumentParser(
        description="Scan earnings vol snapshots for IV crush signals"
    )
    parser.add_argument("--data-dir", type=str, default=str(DATA_DIR))
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--segments", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--window", type=int, default=0,
                        help="Z-score lookback window (0=all history, 72≈4 earnings cycles)")

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Error: {data_dir} not found", file=sys.stderr)
        sys.exit(1)

    segment_map = None
    if args.segments and SEGMENT_DIR.exists():
        segment_map = load_segment_map(SEGMENT_DIR)
        print(f"Loaded {len(segment_map)} tickers across segments")

    print(f"Earnings Vol (IV Crush) Scanner")
    print(f"Data: {data_dir}")
    print(f"Gates: slope<={SLOPE_THRESHOLD}, vol>={VOLUME_THRESHOLD/1e6:.0f}M, IV/RV>={IV_RV_THRESHOLD}")
    if args.window > 0:
        print(f"Z-score window: last {args.window} observations")

    result = scan(data_dir, segment_map, window=args.window)
    print_report(result, args.quiet, args.segments)

    if args.output and not result.empty:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)
        print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
