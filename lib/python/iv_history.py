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
