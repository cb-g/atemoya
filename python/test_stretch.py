"""Stretch (52): each measure on a synthetic series against hand values, the percentile, the
counts, the thresholds' strict loader, the short-history null, and no close after the date."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import pytest
import stretch as st

T = st.load_thresholds(Path(__file__).resolve().parent.parent / "reference" / "stretch.json")


def series(n: int, *, start: float = 100.0, step: float = 0.5, drop_last: float | None = None) -> tuple[dict[date, float], dict[date, float]]:
    """n weekdays of closes rising by step a day, volume 1000 with the last five at 2000; the
    last close replaced by drop_last when given."""
    closes: dict[date, float] = {}
    volumes: dict[date, float] = {}
    d = date(2024, 1, 1)
    i = 0
    while len(closes) < n:
        if d.weekday() < 5:
            last_five = i >= n - 5
            closes[d] = start + step * i
            volumes[d] = 2000.0 if last_five else 1000.0
            i += 1
        d += timedelta(days=1)
    if drop_last is not None:
        closes[max(closes)] = drop_last
    return closes, volumes


def test_measures_by_hand() -> None:
    closes, volumes = series(300)
    days = sorted(closes)
    c = [closes[d] for d in days]
    m = st.measures_at(c, [volumes[d] for d in days], [0.1, 0.2, 0.3])
    assert m is not None
    last = c[-1]
    assert math.isclose(m["dd_120"], last / max(c[-120:]) - 1.0) and m["dd_120"] == 0.0  # a rising series closes at its high
    assert math.isclose(m["above_120_low"], last / c[-120] - 1.0)
    assert math.isclose(m["vs_ma50"], last / (sum(c[-50:]) / 50) - 1.0) and math.isclose(m["vs_ma200"], last / (sum(c[-200:]) / 200) - 1.0)
    assert m["rsi_14"] == 100.0  # no down day: Wilder's RSI at its ceiling
    assert m["rv_20"] is not None and m["rv_20"] > 0 and math.isclose(m["rv_ratio"], m["rv_20"] / 0.2)  # the median of the history given
    assert math.isclose(m["vol_5_60"], 2.0)
    # a fall on the last day: RSI drops below the ceiling and the drawdown turns negative
    closes2, volumes2 = series(300, drop_last=100.0)
    c2 = [closes2[d] for d in sorted(closes2)]
    m2 = st.measures_at(c2, [volumes2[d] for d in sorted(closes2)], [0.2])
    assert m2 is not None and m2["dd_120"] < -0.3 and m2["rsi_14"] < 100.0 and m2["vs_ma50"] < 0
    # Wilder by hand on a short series
    assert st.rsi_wilder([1.0] * 20) == 100.0
    ups = [10.0 + (i % 2) for i in range(30)]  # alternating +1 and -1: average gain equals average loss
    r = st.rsi_wilder(ups)
    assert r is not None and 45.0 < r < 55.0


def test_percentile_counts_and_loader(tmp_path: Path) -> None:
    assert st.percentile(0.3, [0.1, 0.2, 0.3, 0.4]) == 75.0 and st.percentile(0.05, [0.1, 0.2]) == 0.0 and st.percentile(1.0, [0.1]) == 100.0
    m = {"dd_120": -0.41, "above_120_low": 0.0, "vs_ma50": -0.217, "vs_ma200": -0.326, "rsi_14": 27.4, "rv_20": 0.7, "rv_ratio": 1.4, "vol_5_60": 1.2}
    assert st.counts(m, T) == (3, 0)  # PLTR on 2026-06-25 under the declared thresholds: RSI 27 misses the 25
    m["rsi_14"] = 22.5
    assert st.counts(m, T) == (4, 0)
    high = {"dd_120": 0.0, "above_120_low": 0.71, "vs_ma50": 0.16, "vs_ma200": 0.31, "rsi_14": 80.0, "rv_20": 0.5, "rv_ratio": 1.0, "vol_5_60": 1.0}
    assert st.counts(high, T) == (0, 4)
    text = (Path(__file__).resolve().parent.parent / "reference" / "stretch.json").read_text()
    assert st.load_thresholds_text(text).low.dd_120 == -0.25
    bad = json.loads(text); bad["low"]["vs_ma100"] = -0.1
    with pytest.raises(st.StretchError, match="exactly"):
        st.load_thresholds_text(json.dumps(bad))
    bad = json.loads(text); bad["tuned_on"] = "2026-09-22"
    with pytest.raises(st.StretchError, match="unknown field"):
        st.load_thresholds_text(json.dumps(bad))
    bad = json.loads(text); del bad["why"]
    with pytest.raises(st.StretchError, match="lacks why"):
        st.load_thresholds_text(json.dumps(bad))


def test_short_history_is_null_and_point_in_time_uses_no_later_close() -> None:
    closes, volumes = series(200)
    block, why = st.compute(closes, volumes, max(closes), T)
    assert block is None and why is not None and why.startswith("price history shorter than 250 trading days")
    closes, volumes = series(600)
    days = sorted(closes)
    d = days[-40]
    early, _ = st.compute(closes, volumes, d, T)
    trimmed = {k: v for k, v in closes.items() if k <= d}
    same, _ = st.compute(trimmed, {k: v for k, v in volumes.items() if k <= d}, d, T)
    assert early is not None and same is not None and early == same and early.as_of == d.isoformat() and early.history_days == len(trimmed)
    late, _ = st.compute(closes, volumes, max(closes), T)
    assert late is not None and late.history_days == 600 and late.thresholds_version == T.as_of and 0 <= late.stretch_low <= 4 and 0 <= late.stretch_high <= 4
    assert all(0.0 <= getattr(late, k).percentile <= 100.0 for k in st.MEASURES)
