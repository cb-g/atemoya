"""The statistics the panel studies share, in one place.

Every study under `anchor_study`, `broad_study` and the `rule_*` scripts asks the same few
questions of a column of pairs: does an estimate forecast a target, as it is and fitted; how
do two columns rank against each other; what does a least-squares line say; and what do the
daily closes a panel reads give over a June-to-June year. Each study used to carry its own
copy or borrow a sibling's, so a reader of the surprise study had to know a betas script
existed to find the rank correlation. These are the shared ones; nothing here reads a panel,
fetches, or writes a table, and no study's numbers move by the move.

The thresholds are the studies' own: a forecast line needs MIN_PAIRS rows, a rank correlation
anchor_study's small-cell floor unless the caller says otherwise, and winsorising holds both
sides of a column to the first and ninety-ninth percentile of the pooled sample unless told
other percentiles.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np

import anchor_study as study

MIN_PAIRS = 30                  # fewer pairs than this and no forecast or fitted line is printed
PERCENTILES = (1.0, 99.0)       # winsorising: both sides held to these percentiles of the pooled sample

Json = dict[str, object]
Daily = dict[str, float]        # day "YYYY-MM-DD" -> split-adjusted close


# --- forecasts and fits -------------------------------------------------------------------

@dataclass(frozen=True)
class Forecast:
    pairs: int
    r2_as_is: float
    rmse_as_is: float
    intercept: float
    slope: float
    r2_fitted: float


def forecast(xs: list[float], ys: list[float]) -> Forecast | None:
    """The target on the estimate: as it is, and fitted. None under MIN_PAIRS pairs or where
    the target does not vary; an estimate that does not vary fits as the target's mean."""
    n = len(xs)
    if n < MIN_PAIRS or n != len(ys):
        return None
    x, y = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
    sst = float(((y - y.mean()) ** 2).sum())
    sxx = float(((x - x.mean()) ** 2).sum())
    if sst <= 0:
        return None
    sse_as_is = float(((y - x) ** 2).sum())
    if sxx <= 0:
        slope, intercept = 0.0, float(y.mean())
    else:
        slope = float(((x - x.mean()) * (y - y.mean())).sum()) / sxx
        intercept = float(y.mean()) - slope * float(x.mean())
    sse = float(((y - intercept - slope * x) ** 2).sum())
    return Forecast(pairs=n, r2_as_is=1 - sse_as_is / sst, rmse_as_is=math.sqrt(sse_as_is / n), intercept=intercept, slope=slope, r2_fitted=1 - sse / sst)


def fit(xs: list[list[float]], ys: list[float]) -> tuple[list[float], float] | None:
    """Least squares with an intercept: the coefficients after it and the adjusted R-squared; None
    under MIN_PAIRS rows or where the target does not vary."""
    n = len(ys)
    if n < MIN_PAIRS or n != len(xs):
        return None
    x = np.column_stack([np.ones(n)] + [np.asarray(c, dtype=float) for c in zip(*xs, strict=True)])
    y = np.asarray(ys, dtype=float)
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    residual = y - x @ coef
    sst = float(((y - y.mean()) ** 2).sum())
    if sst <= 0:
        return None
    k = x.shape[1] - 1
    r2 = 1 - float((residual ** 2).sum()) / sst
    adjusted = 1 - (1 - r2) * (n - 1) / (n - k - 1) if n - k - 1 > 0 else r2
    return [float(c) for c in coef[1:]], adjusted


# --- ranks ----------------------------------------------------------------------------------

def ranks(values: list[float]) -> np.ndarray:
    """Ranks from one, ties given the mean of the ranks they span."""
    v = np.asarray(values, dtype=float)
    order = np.argsort(v, kind="stable")
    out = np.empty(len(v), dtype=float)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        out[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(pairs: list[tuple[float, float]], *, min_pairs: int = study.MIN_CELL) -> float | None:
    """The rank correlation; None under min_pairs pairs or where either side does not vary."""
    if len(pairs) < min_pairs:
        return None
    a, b = ranks([x for x, _ in pairs]), ranks([y for _, y in pairs])
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


# --- winsorising ----------------------------------------------------------------------------

def winsorise(column: np.ndarray, percentiles: tuple[float, float] = PERCENTILES) -> np.ndarray:
    """The column held to its own percentiles."""
    lo, hi = np.percentile(column, percentiles)
    return np.clip(column, lo, hi)


def winsorise_pairs(pairs: list[tuple[float, float]], percentiles: tuple[float, float] = PERCENTILES) -> tuple[list[tuple[float, float]], int]:
    """Both sides held to the pooled percentiles and the count of values moved; under MIN_PAIRS
    pairs nothing moves, since a percentile of a handful is one of them."""
    if len(pairs) < MIN_PAIRS:
        return pairs, 0
    xs, ys = np.asarray([x for x, _ in pairs]), np.asarray([y for _, y in pairs])
    moved = 0
    out: list[np.ndarray] = []
    for column in (xs, ys):
        clipped = winsorise(column, percentiles)
        moved += int((clipped != column).sum())
        out.append(clipped)
    return list(zip(out[0].tolist(), out[1].tolist())), moved


# --- daily closes ---------------------------------------------------------------------------

def load_daily(path: Path) -> Daily | None:
    """A name's history file under the rule panel's `histories/`: day -> close, positive closes
    only; None where the file or its closes are missing."""
    if not path.exists():
        return None
    closes = cast(Json, json.loads(path.read_text())).get("closes")
    if not isinstance(closes, dict):
        return None
    return {str(day): float(v) for day, v in cast(dict[str, object], closes).items() if isinstance(v, (int, float)) and v > 0}


def daily_returns(closes: Daily, first: str, last: str) -> dict[str, float]:
    """day -> the return into it, for the days after [first] up to [last], each on the
    trading day before it."""
    days = sorted(closes)
    return {day: closes[day] / closes[before] - 1 for before, day in zip(days, days[1:], strict=False) if first < day <= last}


def window(year: int, day: str, k: int) -> tuple[str, str]:
    """The year ending k years after a June date (k = 0 the year to it): (first, last) days,
    returns counted after the first up to the last."""
    return f"{year + k - 1}{day[4:]}", f"{year + k}{day[4:]}"
