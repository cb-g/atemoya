"""Single-source selection for dual-provider IV-history series.

The pricing scanners archive two histories per ticker: a ThetaData backfill/replay
(`*_thetadata.csv`) and the live yfinance collection (`*_yfinance.csv`). These are
NOT interchangeable measurements of the same quantity:

  - ThetaData ATM IV is computed with our own Newton-Raphson from bid/ask *mids*,
    then read off an SVI fit at a target tenor.
  - yfinance ATM IV is the *median* of Yahoo's own `impliedVolatility` column over
    a wide ATM band (last-trade based, often stale/off-hours, no smile fit).

Empirically yfinance runs ~4 vol points hot (median +3, 53% of tickers >3 vol pts,
day-to-day correlation only ~0.27). Concatenating the two into one series therefore
introduces a level discontinuity at every source boundary, which corrupts the
z-score of the latest observation (the live tail is yfinance-sourced for ~40% of
tickers → systematic false "IV rich / sell-vol" signals).

The fix: pick a single source per ticker. Use ThetaData alone whenever it has enough
history; fall back to yfinance alone only for tickers ThetaData never covered. Each
branch is internally consistent, so z-scores compare like with like.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pandas as pd


def prefer_thetadata(
    thetadata_frames: list[pd.DataFrame],
    yfinance_frames: list[pd.DataFrame],
    dedup_subset: list[str],
    min_days: int,
) -> pd.DataFrame | None:
    """Choose one provider's history, ThetaData preferred — never mix the two.

    Args:
        thetadata_frames: DataFrames read from the ticker's `*_thetadata.csv` file(s).
        yfinance_frames: DataFrames read from the ticker's `*_yfinance.csv` file(s).
        dedup_subset: Columns identifying a unique observation (e.g. ["date"] or
            ["date", "dte_pair"]). The first column is also used as the sort key.
        min_days: Minimum rows (after intra-source dedup) for a source to qualify.

    Returns:
        The chosen source's DataFrame, sorted ascending by ``dedup_subset[0]`` and
        de-duplicated within that source (latest write wins), or None if neither
        source has at least ``min_days`` rows.
    """
    for frames in (thetadata_frames, yfinance_frames):
        if not frames:
            continue
        df = pd.concat(frames, ignore_index=True)
        df = (
            df.drop_duplicates(subset=dedup_subset, keep="last")
            .sort_values(dedup_subset[0])
            .reset_index(drop=True)
        )
        if len(df) >= min_days:
            return df
    return None


def _staleness_threshold(max_staleness_days: int | None) -> int:
    """Resolve the staleness threshold in calendar days: explicit arg, else env
    SCAN_MAX_STALENESS_DAYS, else 10."""
    if max_staleness_days is not None:
        return max_staleness_days
    try:
        return int(os.environ.get("SCAN_MAX_STALENESS_DAYS", "10"))
    except ValueError:
        return 10


def _parse_dt(value):
    """Parse a history date/timestamp cell to a pandas Timestamp.

    Handles ISO date strings ("2026-06-05") and unix-epoch numerics (skew_trading
    stores epoch seconds, e.g. 1775080800.0; ISO strings with dashes fail float()
    and fall through to the string parser). Returns NaT if unparseable.
    """
    try:
        fv = float(value)
    except (TypeError, ValueError):
        try:
            return pd.to_datetime(value)
        except Exception:
            return pd.NaT
    unit = "ms" if fv > 1e11 else "s"
    try:
        return pd.to_datetime(fv, unit=unit)
    except Exception:
        return pd.NaT


def filter_stale(
    histories: dict,
    date_col: str,
    label: str = "scan",
    max_staleness_days: int | None = None,
) -> dict:
    """Drop tickers whose latest observation is stale, so a scanner never emits a
    'live' signal off frozen data.

    Staleness is measured against ``as_of`` = the most recent latest-observation
    across the whole universe (deterministic, and robust to being run on a
    snapshot): a ticker is dropped when its latest obs is more than
    ``max_staleness_days`` calendar days behind ``as_of``. This catches names whose
    collection silently froze (e.g. stuck ~2 months back) while the rest of the
    book moved on — the scanner's ``df.iloc[-1]`` would otherwise z-score and emit
    off that stale row.

    Threshold defaults to env ``SCAN_MAX_STALENESS_DAYS`` (else 10). Logs the
    dropped count to stderr, and warns loudly if ``as_of`` itself is far behind
    today's date (a likely sign the whole collection has stalled). Returns the
    filtered dict.
    """
    days = _staleness_threshold(max_staleness_days)
    if not histories:
        return histories
    latest: dict = {}
    for ticker, df in histories.items():
        dt = _parse_dt(df[date_col].iloc[-1]) if len(df) else pd.NaT
        if pd.notna(dt):
            latest[ticker] = dt
    if not latest:
        return histories
    as_of = max(latest.values())
    cutoff = as_of - pd.Timedelta(days=days)
    fresh = {t: df for t, df in histories.items() if t in latest and latest[t] >= cutoff}
    dropped = len(histories) - len(fresh)
    if dropped:
        print(
            f"[{label}] dropped {dropped}/{len(histories)} stale tickers "
            f"(latest obs >{days}d behind as-of {as_of.date()})",
            file=sys.stderr,
        )
    try:
        age = (pd.Timestamp(date.today()) - as_of).days
        if age > days:
            print(
                f"[{label}] WARNING: freshest data is {age}d old (as-of "
                f"{as_of.date()}) — collection may be stalled; remaining signals "
                f"are stale",
                file=sys.stderr,
            )
    except Exception:
        pass
    return fresh


def is_stale(
    df,
    date_col: str,
    label: str = "scan",
    max_staleness_days: int | None = None,
) -> bool:
    """Whether a single-series history's latest obs is stale vs today's date.

    For index/series scanners with no peer universe to compare against (e.g.
    dispersion), staleness is measured against the wall-clock date. Returns True
    (and logs) when the latest obs is older than the threshold.
    """
    days = _staleness_threshold(max_staleness_days)
    latest = _parse_dt(df[date_col].iloc[-1]) if len(df) else pd.NaT
    if pd.isna(latest):
        return False
    age = (pd.Timestamp(date.today()) - latest).days
    if age > days:
        print(
            f"[{label}] latest obs is {age}d old (>{days}d) — skipping as stale "
            f"(as-of {latest.date()})",
            file=sys.stderr,
        )
        return True
    return False
