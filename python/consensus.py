"""(82) Consensus and surprise: the Street's bar per name, dated, and how each name has met it.

A side output. Nothing in a valuation record reads it, no model or belief moves with it, and it
never fails a record. It exists for a downstream reader that uses consensus as the market's
bar and wants each name's own surprise pattern rather than one number for every company.

    uv run python/consensus.py                     # snapshot + history + summary, each sitting or daily
    uv run python/consensus.py --only snapshot     # today's bar for every universe name
    uv run python/consensus.py --only history      # EPS releases and filed quarterly revenue
    uv run python/consensus.py --only summary      # output/consensus/ from what is on disk
    uv run python/consensus.py ZETA MU             # any of the above for a subset of the universe

**Contract.**

Fetched, under `data/consensus/` (never tracked):

- `days/<YYYY-MM-DD>/<TICKER>.json`, one per name per UTC day: `status` "ok"; "none" with
  `reason` when the vendor answers with no consensus for the name, a fund for instance,
  which is not retried that day; or "failed" with `reason` when the fetch itself fails; `periods`, one per vendor period ("0q", "+1q", "0y", "+1y") with its
  `end_date`, the EPS bar (`mean`, `low`, `high`, `analysts`, `year_ago`, per share in
  `eps_currency`), the revenue bar (the same keys, absolute, in `revenue_currency`) and the EPS
  trend (`current`, `7d`, `30d`, `60d`, `90d` before the fetch day). A figure the vendor does
  not carry is null, never zero. The day is the fetch day, which is the as-of date of every
  figure in the file. A period the vendor dates more than STALE_END_DAYS before the fetch
  day cannot be one still being forecast: its `end_date` is null and `end_date_reason` says
  what the vendor sent, the figures kept as they came; otherwise `end_date_reason` is null.
- `days/<YYYY-MM-DD>/manifest.json`: `status` "complete", "partial" (some fetches failed) or
  "gap" (no run that day), with the names that have no consensus listed apart from the
  failures. Run it at each sitting or daily; every day without a run is a gap on the record. A run is idempotent per day: an ok record is never fetched again
  or overwritten, a failed or missing one is retried, and the manifest is rewritten. Every
  calendar day between the first day on disk and today with no directory gets a gap
  manifest, because a bar cannot be taken after the fact.
- `history/<TICKER>.json`, refetched once per day: every past release in the vendor's dated
  earnings table with its final EPS estimate and reported EPS, both on the Street-adjusted
  basis the vendor carries and not GAAP; the estimate is the last consensus before the
  release and the source gives no earlier date for it. Each release is matched to the latest
  filed fiscal period that ends 1 to 120 days before it, or null with the reason. For a name
  with SEC filings, the quarterly revenue as first filed: a three-month figure where one is
  filed, else the fourth quarter derived as the fiscal year less the nine months to the
  third quarter, both filed, and labelled so. `status` "ok"; "none" when the vendor answers
  and its table carries no past release with a reported figure, which is the vendor having
  nothing and not a fetch that failed; "failed" with the exception when the fetch fails.

Derived, under `output/consensus/` (regenerated from `data/` alone, no fetch):

- `summary.jsonl`, one line per name: `eps` per window of the last 8 and 12 releases with an
  estimate and a reported figure: `n`, `beats` (reported above the estimate), `meets`
  (equal), `misses`, `beat_rate` (beats over n), and the median, 25th and 75th percentiles of
  the surprise in percent of the estimate's magnitude, over the releases whose estimate is not
  zero; `revenue` the same windows over the pairs of a snapshotted bar and a filed actual,
  each pair carrying how many days before the release its bar was taken, in percent and absolute, empty with its reason until a snapshot precedes a report;
  `current`, the latest ok snapshot's 0q and +1q bars with the day they were taken.
- `pooled.json`: per window, the beats and releases summed across every name with a window,
  and the pooled beat rate. Shrinkage toward it is the reader's, not this tool's.
- `summary.txt`: the same, one line per name.

Sources: the vendor's quoteSummary earningsTrend module, reached through yfinance 1.7.0's
analysis scraper (a private surface of the library, so a change there is a failed record with
the reason, never a silent hole), the vendor's dated earnings table, and SEC companyfacts.
Keyless; the SEC identity in the env file names the caller as every SEC read here does.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, cast

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data" / "consensus"
OUT = REPO_ROOT / "output" / "consensus"
UNIVERSE = REPO_ROOT / "reference" / "universe.json"

PERIODS = ("0q", "+1q", "0y", "+1y")
# a quarter or a year still carrying a forecast has not been reported; a filer reports within
# about three months of the period's end, so an end further back than this is the vendor's error
STALE_END_DAYS = 120
WINDOWS = (8, 12)
TREND_KEYS = (("current", "current"), ("7daysAgo", "7d"), ("30daysAgo", "30d"), ("60daysAgo", "60d"), ("90daysAgo", "90d"))
MAX_REPORT_LAG_DAYS = 120          # a release reports the latest period that ended at most this long before it
END_TOLERANCE_DAYS = 7             # a vendor period end and a filed one name the same quarter within this
QUARTER_DAYS = (80, 100)
YEAR_DAYS = (350, 380)
NINE_MONTH_DAYS = (260, 290)
PACE_SECONDS = 0.3
# (82) Revenue tags read here beyond the shared total_revenue list, ranked after it. Lumentum
# files its quarters under the including-assessed-tax element, which the shared list does not
# name, so its releases matched no fiscal period. The shared list is not widened here: every
# element it names enters the annual fetcher's restatement scan, so that is its own measured
# change.
REVENUE_EXTRA = {"us-gaap": ["RevenueFromContractWithCustomerIncludingAssessedTax"], "ifrs-full": []}

SOURCE_TREND = "vendor quoteSummary earningsTrend (yfinance 1.7.0 analysis scraper)"
SOURCE_HISTORY = "vendor dated earnings table (yfinance 1.7.0 get_earnings_dates)"
BASIS = "Street-adjusted EPS as the vendor carries it, not GAAP"
ESTIMATE_AS_OF = "the last consensus before the release; the source gives no earlier date for it"
GAP_REASON = "no run on this day; a consensus bar cannot be taken after the fact"
NO_RELEASES = "the vendor's dated earnings table carries no past release with a reported figure"
NO_FILER = "no SEC filer for this name: no filed period ends or quarterly revenue"
NO_PERIOD = f"no filed fiscal period ends 1 to {MAX_REPORT_LAG_DAYS} days before the release"
NO_REVENUE_PAIRS = "no revenue bar was snapshotted before a release whose filed quarter is on disk"
ZERO_ESTIMATE = "estimate is zero: no surprise in percent"

Json = dict[str, Any]


# ---------------------------------------------------------------- the daily snapshot


def _raw(node: object) -> float | None:
    """The vendor wraps every figure as {"raw": x, "fmt": ...}; an absent or empty one is None."""
    if isinstance(node, Mapping):
        value = cast(Mapping[str, object], node).get("raw")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _bar(block: object, year_ago_key: str) -> Json:
    b: Mapping[str, object] = cast(Mapping[str, object], block) if isinstance(block, Mapping) else {}
    analysts = _raw(b.get("numberOfAnalysts"))
    return {
        "mean": _raw(b.get("avg")),
        "low": _raw(b.get("low")),
        "high": _raw(b.get("high")),
        "analysts": int(analysts) if analysts is not None else None,
        "year_ago": _raw(b.get(year_ago_key)),
    }


def parse_trend(trend: Iterable[object]) -> tuple[list[Json], str | None, str | None]:
    """The four vendor periods with their end dates, bars and EPS trend, and the two currencies."""
    periods: list[Json] = []
    eps_currency: str | None = None
    revenue_currency: str | None = None
    for item in trend:
        if not isinstance(item, Mapping):
            continue
        t = cast(Mapping[str, object], item)
        period = t.get("period")
        if period not in PERIODS:
            continue
        eps = cast(Mapping[str, object], t.get("earningsEstimate") or {})
        revenue = cast(Mapping[str, object], t.get("revenueEstimate") or {})
        trend_block = cast(Mapping[str, object], t.get("epsTrend") or {})
        eps_currency = eps_currency or cast(str | None, eps.get("earningsCurrency"))
        revenue_currency = revenue_currency or cast(str | None, revenue.get("revenueCurrency"))
        end = t.get("endDate")
        periods.append({
            "period": period,
            "end_date": end if isinstance(end, str) and end else None,
            "eps": _bar(eps, "yearAgoEps"),
            "revenue": _bar(revenue, "yearAgoRevenue"),
            "eps_trend": {short: _raw(trend_block.get(key)) for key, short in TREND_KEYS},
        })
    periods.sort(key=lambda p: PERIODS.index(cast(str, p["period"])))
    return periods, eps_currency, revenue_currency


def snapshot_record(ticker: str, day: date, fetched_at: str, trend: object) -> Json:
    """One name's bar for one day: ok with the periods; none, the vendor answering with no
    consensus, which is a state of the name and not retried that day; or failed, the fetch
    itself going wrong, which a rerun the same day retries."""
    base: Json = {"ticker": ticker, "date": day.isoformat(), "fetched_at": fetched_at, "source": SOURCE_TREND}
    if isinstance(trend, Exception):
        return {**base, "status": "failed", "reason": f"vendor failed: {type(trend).__name__}: {trend}", "periods": []}
    periods, eps_currency, revenue_currency = parse_trend(cast(Iterable[object], trend or []))
    if not periods:
        return {**base, "status": "none", "reason": "the vendor carries no consensus for this name", "periods": []}
    if all(p["eps"]["mean"] is None and p["revenue"]["mean"] is None for p in periods):
        return {**base, "status": "none", "reason": "the vendor lists the periods but no EPS or revenue estimate in any", "periods": []}
    for p in periods:
        end = cast(str | None, p["end_date"])
        p["end_date_reason"] = None
        if end is None:
            continue
        try:
            behind = (day - date.fromisoformat(end)).days
        except ValueError:
            p["end_date"], p["end_date_reason"] = None, f"the vendor's period end {end!r} is not a date"
            continue
        if behind > STALE_END_DAYS:
            p["end_date"] = None
            p["end_date_reason"] = (f"the vendor dates this period {end}, {behind} days before the snapshot; "
                                    f"a period still being forecast cannot have ended more than {STALE_END_DAYS} days ago")
    return {**base, "status": "ok", "reason": None, "eps_currency": eps_currency,
            "revenue_currency": revenue_currency, "periods": periods}


def day_dirs(root: Path) -> list[date]:
    days: list[date] = []
    if (root / "days").is_dir():
        for p in (root / "days").iterdir():
            try:
                days.append(date.fromisoformat(p.name))
            except ValueError:
                continue
    return sorted(days)


def missing_days(existing: Iterable[date], today: date) -> list[date]:
    """Every calendar day from the first day on disk to the day before today that has no
    directory. With no earlier day there is nothing to call missing."""
    have = set(existing)
    earlier = [d for d in have if d < today]
    if not earlier:
        return []
    out: list[date] = []
    d = min(earlier) + timedelta(days=1)
    while d < today:
        if d not in have:
            out.append(d)
        d += timedelta(days=1)
    return out


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")   # a cron run and a sitting may overlap
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    tmp.replace(path)


def _read_json(path: Path) -> Json | None:
    try:
        return cast(Json, json.loads(path.read_text()))
    except (OSError, ValueError):
        return None


def write_gaps(root: Path, today: date) -> list[date]:
    gaps = missing_days(day_dirs(root), today)
    for d in gaps:
        _write_json(root / "days" / d.isoformat() / "manifest.json",
                    {"date": d.isoformat(), "status": "gap", "reason": GAP_REASON, "names": 0, "ok": 0, "none": [], "failed": []})
    return gaps


def run_snapshot(tickers: list[str], root: Path, today: date, fetch_trend: Callable[[str], object],
                 now: Callable[[], str] = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 pace: float = PACE_SECONDS, log: Callable[[str], None] = print) -> Json:
    """Today's bar for every ticker, idempotent per day, with gap manifests for missed days."""
    gaps = write_gaps(root, today)
    for g in gaps:
        log(f"gap: {g} ({GAP_REASON})")
    folder = root / "days" / today.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    fetched = 0
    for ticker in tickers:
        path = folder / f"{ticker}.json"
        held = _read_json(path)
        if held is not None and held.get("status") in ("ok", "none"):
            continue
        if fetched and pace:
            time.sleep(pace)
        try:
            trend = fetch_trend(ticker)
        except Exception as e:  # noqa: BLE001 - the vendor is the untrusted edge; any failure is a reason
            trend = e
        fetched += 1
        record = snapshot_record(ticker, today, now(), trend)
        _write_json(path, record)
        log(f"{ticker}: {record['status']}{'' if record['status'] == 'ok' else ' - ' + str(record['reason'])}")
    records = [r for t in tickers if (r := _read_json(folder / f"{t}.json")) is not None]
    failed = sorted(cast(str, r["ticker"]) for r in records if r.get("status") == "failed")
    failed += sorted(t for t in tickers if not (folder / f"{t}.json").exists())
    none = sorted(cast(str, r["ticker"]) for r in records if r.get("status") == "none")
    manifest: Json = {"date": today.isoformat(), "status": "complete" if not failed else "partial",
                      "reason": None if not failed else f"{len(failed)} name(s) failed; rerun today to retry them",
                      "names": len(tickers), "ok": len(tickers) - len(failed) - len(none),
                      "none": none, "failed": failed}
    _write_json(folder / "manifest.json", manifest)
    return manifest


def vendor_trend(ticker: str) -> object:
    import yfinance as yf  # noqa: PLC0415

    analysis = cast(Any, yf.Ticker(ticker))._analysis  # the module behind earnings_estimate, revenue_estimate, eps_trend
    data: Mapping[str, Any] = analysis._fetch(["earningsTrend"]) or {}   # None when the vendor answers 404
    summary: Mapping[str, Any] = data.get("quoteSummary") or {}
    result = cast(list[Mapping[str, Any]], summary.get("result") or [])
    if not result:
        return []
    return cast(Mapping[str, Any], result[0].get("earningsTrend") or {}).get("trend") or []


# ---------------------------------------------------------------- releases and filed quarters


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _entries(facts: Mapping[str, object], taxonomy: str, tags: Iterable[str], unit: str) -> list[tuple[str, Mapping[str, object]]]:
    section = cast(Mapping[str, object], cast(Mapping[str, object], facts.get("facts") or {}).get(taxonomy) or {})
    out: list[tuple[str, Mapping[str, object]]] = []
    for tag in tags:
        units = cast(Mapping[str, object], cast(Mapping[str, object], section.get(tag) or {}).get("units") or {})
        for e in cast(list[object], units.get(unit) or []):
            if isinstance(e, Mapping):
                out.append((tag, cast(Mapping[str, object], e)))
    return out


def revenue_unit(facts: Mapping[str, object], taxonomy: str, tags: Iterable[str]) -> str | None:
    """The currency the filer reports revenue in: the unit carrying the most revenue facts."""
    section = cast(Mapping[str, object], cast(Mapping[str, object], facts.get("facts") or {}).get(taxonomy) or {})
    counts: dict[str, int] = {}
    for tag in tags:
        units = cast(Mapping[str, object], cast(Mapping[str, object], section.get(tag) or {}).get("units") or {})
        for unit, entries in units.items():
            counts[unit] = counts.get(unit, 0) + len(cast(list[object], entries))
    return max(sorted(counts), key=lambda u: counts[u]) if counts else None


def filed_period_ends(facts: Mapping[str, object], taxonomy: str, tags: Iterable[str], unit: str) -> list[date]:
    """The ends of the quarters and years the filer reports revenue for, on any form."""
    ends: set[date] = set()
    for _, e in _entries(facts, taxonomy, tags, unit):
        start, end = e.get("start"), e.get("end")
        if isinstance(start, str) and isinstance(end, str):
            span = _days(start, end)
            if QUARTER_DAYS[0] <= span <= QUARTER_DAYS[1] or YEAR_DAYS[0] <= span <= YEAR_DAYS[1]:
                ends.add(date.fromisoformat(end))
    return sorted(ends)


def fiscal_period_of(report: date, ends: Iterable[date]) -> tuple[str | None, str | None]:
    candidates = [e for e in ends if 1 <= (report - e).days <= MAX_REPORT_LAG_DAYS]
    if not candidates:
        return None, NO_PERIOD
    return max(candidates).isoformat(), None


def _first_filed(entries: list[tuple[str, Mapping[str, object]]], start_span: tuple[int, int]) -> dict[str, tuple[float, str, str, str]]:
    """end -> (value, tag, start, filed) for each period of the span, as first filed; the tag
    list's order decides between tags carrying the same period."""
    best: dict[str, tuple[float, str, str, str]] = {}
    order: dict[str, int] = {}
    for rank, (tag, e) in enumerate(entries):
        order.setdefault(tag, rank)
    for tag, e in entries:
        start, end, filed, val = e.get("start"), e.get("end"), e.get("filed"), e.get("val")
        if not (isinstance(start, str) and isinstance(end, str) and isinstance(filed, str) and isinstance(val, (int, float))):
            continue
        if not (start_span[0] <= _days(start, end) <= start_span[1]):
            continue
        held = best.get(end)
        key = (order[tag], filed)
        if held is None or key < (order[held[1]], held[3]):
            best[end] = (float(val), tag, start, filed)
    return best


def filed_quarter_revenue(facts: Mapping[str, object], taxonomy: str, tags: list[str], unit: str) -> list[Json]:
    """Quarterly revenue as first filed: three-month figures where filed, and a fourth quarter
    derived as the fiscal year less the nine months to the third quarter where both are filed
    and no three-month figure is."""
    entries = _entries(facts, taxonomy, tags, unit)
    quarters = _first_filed(entries, QUARTER_DAYS)
    years = _first_filed(entries, YEAR_DAYS)
    nines = _first_filed(entries, NINE_MONTH_DAYS)
    out: dict[str, Json] = {
        end: {"end": end, "value": v, "currency": unit, "basis": f"three months as first filed ({tag}, filed {filed})"}
        for end, (v, tag, _, filed) in quarters.items()
    }
    for end, (fy, tag, start, filed) in years.items():
        if any(abs(_days(end, q)) <= END_TOLERANCE_DAYS for q in out):
            continue
        nine = [(n_end, n) for n_end, n in nines.items()
                if abs(_days(start, n[2])) <= END_TOLERANCE_DAYS and 0 < _days(n_end, end) <= QUARTER_DAYS[1]]
        if len(nine) != 1:
            continue
        n_end, (nv, ntag, _, nfiled) = nine[0]
        out[end] = {"end": end, "value": fy - nv, "currency": unit,
                    "basis": f"fiscal year less the nine months to {n_end}, both filed ({tag} filed {filed}; {ntag} filed {nfiled})"}
    return [out[k] for k in sorted(out)]


def release_rows(rows: Iterable[tuple[date, str, float | None, float | None]], as_of: date,
                 ends: list[date] | None) -> list[Json]:
    """Past releases with a reported figure, oldest first, each matched to its fiscal period."""
    out: list[Json] = []
    for when, stamp, estimate, reported in sorted(rows, key=lambda r: r[0]):
        if when > as_of or reported is None:
            continue
        if ends is None:
            period, why = None, NO_FILER
        else:
            period, why = fiscal_period_of(when, ends)
        out.append({"report_date": when.isoformat(), "release_stamp": stamp, "eps_estimate": estimate,
                    "eps_reported": reported, "fiscal_period_end": period, "fiscal_period_reason": why})
    return out


def _num(x: object) -> float | None:
    if isinstance(x, (int, float)) and not isinstance(x, bool) and x == x:
        return float(x)
    return None


def vendor_releases(ticker: str) -> list[tuple[date, str, float | None, float | None]]:
    import yfinance as yf  # noqa: PLC0415

    frame = cast(Any, yf.Ticker(ticker)).get_earnings_dates(limit=40)
    if frame is None or len(frame) == 0:
        return []
    out: list[tuple[date, str, float | None, float | None]] = []
    for stamp, row in frame.iterrows():
        out.append((stamp.date(), str(stamp), _num(row.get("EPS Estimate")), _num(row.get("Reported EPS"))))
    return out


# ---------------------------------------------------------------- the summary


def _percentiles(xs: list[float]) -> tuple[float | None, float | None, float | None]:
    if not xs:
        return None, None, None
    if len(xs) == 1:
        return xs[0], xs[0], xs[0]
    q = statistics.quantiles(xs, n=4, method="inclusive")
    return q[0], statistics.median(xs), q[2]


def window_stats(pairs: list[tuple[float, float]], window: int, *, absolute: bool = False) -> Json:
    """(estimate, actual) pairs oldest first; the last `window` of them."""
    last = pairs[-window:]
    beats = sum(1 for est, act in last if act > est)
    meets = sum(1 for est, act in last if act == est)
    pct = [(act - est) / abs(est) * 100.0 for est, act in last if est != 0]
    q25, med, q75 = _percentiles(pct)
    out: Json = {"window": window, "n": len(last), "beats": beats, "meets": meets, "misses": len(last) - beats - meets,
                 "beat_rate": beats / len(last) if last else None,
                 "surprise_pct": {"median": med, "q25": q25, "q75": q75, "n": len(pct),
                                  "reason": None if len(pct) == len(last) else f"{len(last) - len(pct)} release(s): {ZERO_ESTIMATE}"}}
    if absolute:
        a25, amed, a75 = _percentiles([act - est for est, act in last])
        out["surprise_abs"] = {"median": amed, "q25": a25, "q75": a75}
    return out


def _near(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and abs(_days(a, b)) <= END_TOLERANCE_DAYS


def revenue_pairs(snapshots: list[Json], releases: list[Json], quarters: list[Json]) -> list[Json]:
    """For each filed quarter with a release after it: the latest bar snapshotted for that
    quarter on a day before the release, and the filed figure. Oldest first."""
    out: list[Json] = []
    for q in quarters:
        end = cast(str, q["end"])
        after = [r for r in releases if 1 <= _days(end, cast(str, r["report_date"])) <= MAX_REPORT_LAG_DAYS]
        if not after:
            continue
        report = min(cast(str, r["report_date"]) for r in after)
        bars: list[tuple[str, Json, str]] = []
        for s in snapshots:
            if s.get("status") != "ok" or cast(str, s["date"]) >= report:
                continue
            for p in cast(list[Json], s["periods"]):
                if p["period"] in ("0q", "+1q") and _near(p["end_date"], end) and p["revenue"]["mean"] is not None:
                    bars.append((cast(str, s["date"]), p, cast(str, s.get("revenue_currency") or "")))
        if not bars:
            continue
        taken, bar, currency = max(bars, key=lambda b: b[0])
        if currency and currency != q["currency"]:
            continue
        mean = cast(float, bar["revenue"]["mean"])
        actual = cast(float, q["value"])
        out.append({"quarter_end": end, "report_date": report, "bar_taken": taken, "bar_age_days": _days(taken, report),
                    "bar_period": bar["period"],
                    "mean": mean, "low": bar["revenue"]["low"], "high": bar["revenue"]["high"],
                    "analysts": bar["revenue"]["analysts"], "actual": actual, "actual_basis": q["basis"],
                    "currency": q["currency"], "surprise_abs": actual - mean,
                    "surprise_pct": (actual - mean) / abs(mean) * 100.0 if mean else None})
    return out


def current_of(snapshots: list[Json]) -> Json | None:
    ok = [s for s in snapshots if s.get("status") == "ok"]
    if not ok:
        return None
    latest = max(ok, key=lambda s: cast(str, s["date"]))
    keep = [p for p in cast(list[Json], latest["periods"]) if p["period"] in ("0q", "+1q")]
    return {"as_of": latest["date"], "eps_currency": latest.get("eps_currency"),
            "revenue_currency": latest.get("revenue_currency"), "periods": keep}


def summarize(ticker: str, history: Json | None, snapshots: list[Json]) -> Json:
    out: Json = {"ticker": ticker, "basis": BASIS, "estimate_as_of": ESTIMATE_AS_OF}
    if history is None or history.get("status") != "ok":
        out["eps"] = None
        out["eps_reason"] = "no release history on disk" if history is None else history.get("reason")
        releases: list[Json] = []
    else:
        releases = cast(list[Json], history["releases"])
        pairs = [(cast(float, r["eps_estimate"]), cast(float, r["eps_reported"]))
                 for r in releases if r["eps_estimate"] is not None and r["eps_reported"] is not None]
        out["eps"] = [window_stats(pairs, w) for w in WINDOWS] if pairs else None
        out["eps_reason"] = None if pairs else "no release carries both an estimate and a reported figure"
        out["last_release"] = releases[-1]["report_date"] if releases else None
    quarters = cast(list[Json], (history or {}).get("filed_revenue") or [])
    rpairs = revenue_pairs(snapshots, releases, quarters)
    out["revenue_pairs"] = rpairs
    out["revenue"] = [window_stats([(p["mean"], p["actual"]) for p in rpairs], w, absolute=True) for w in WINDOWS] if rpairs else None
    out["revenue_reason"] = None if rpairs else (
        cast(str, (history or {}).get("filed_revenue_reason") or NO_REVENUE_PAIRS) if not quarters else NO_REVENUE_PAIRS)
    out["current"] = current_of(snapshots)
    out["current_reason"] = None if out["current"] else "no ok snapshot on disk"
    return out


def pooled(summaries: list[Json]) -> Json:
    out: Json = {"basis": BASIS, "windows": []}
    for i, w in enumerate(WINDOWS):
        rows = [cast(list[Json], s["eps"])[i] for s in summaries if s.get("eps")]
        n = sum(cast(int, r["n"]) for r in rows)
        beats = sum(cast(int, r["beats"]) for r in rows)
        out["windows"].append({"window": w, "names": len(rows), "releases": n, "beats": beats,
                               "beat_rate": beats / n if n else None})
    return out


def _fmt(x: object, spec: str = ".2f") -> str:
    return "-" if x is None else format(cast(float, x), spec)


def summary_text(summaries: list[Json], pool: Json, as_of: date) -> str:
    lines = [f"consensus (82), {as_of}: {BASIS}; the estimate is {ESTIMATE_AS_OF}", ""]
    for w in cast(list[Json], pool["windows"]):
        lines.append(f"pooled, last {w['window']}: {w['beats']} beats in {w['releases']} releases over {w['names']} names, rate {_fmt(w['beat_rate'], '.3f')}")
    lines.append("")
    for s in summaries:
        eps = cast(list[Json] | None, s.get("eps"))
        if eps:
            part = "; ".join(f"last {e['window']}: n {e['n']} beat {_fmt(e['beat_rate'], '.2f')} median {_fmt(e['surprise_pct']['median'], '+.1f')}%"
                             for e in eps)
        else:
            part = f"no EPS history: {s.get('eps_reason')}"
        rev = cast(list[Json] | None, s.get("revenue"))
        rpart = (f"revenue last {rev[0]['window']}: n {rev[0]['n']} beat {_fmt(rev[0]['beat_rate'], '.2f')}" if rev
                 else "revenue: none paired yet")
        cur = cast(Json | None, s.get("current"))
        cpart = f"bar as of {cur['as_of']}" if cur else "no bar"
        lines.append(f"{s['ticker']:10} {part}; {rpart}; {cpart}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- running it


def _universe_entries(path: Path) -> list[Any]:
    import universe  # noqa: PLC0415

    return list(universe.load_text(path.read_text()).tickers)


def run_history(entries: list[Any], root: Path, today: date, log: Callable[[str], None] = print) -> None:
    import fetch  # noqa: PLC0415
    import fetch_sec  # noqa: PLC0415

    agent = fetch_sec.identity()
    table = fetch_sec.tickers_table(agent)
    tags = fetch_sec.load_tags()
    for i, entry in enumerate(entries):
        ticker = cast(str, entry.ticker)
        path = root / "history" / f"{ticker}.json"
        held = _read_json(path)
        if held is not None and held.get("fetched_on") == today.isoformat():
            continue
        if i and PACE_SECONDS:
            time.sleep(PACE_SECONDS)
        record: Json = {"ticker": ticker, "fetched_on": today.isoformat(), "source": SOURCE_HISTORY,
                        "basis": BASIS, "estimate_as_of": ESTIMATE_AS_OF}
        cik, _ = fetch.cik_of(ticker, table, cast(str | None, getattr(entry, "cik", None)))
        ends: list[date] | None = None
        quarters: list[Json] = []
        quarters_reason: str | None = NO_FILER
        if cik:
            facts = fetch_sec.companyfacts(cik, agent)
            if facts is not None:
                for taxonomy in fetch_sec.TAXONOMIES:
                    revenue_tags = list(dict(fetch_sec.taxonomy_fields(tags, taxonomy))["total_revenue"].tags) + REVENUE_EXTRA[taxonomy]
                    unit = revenue_unit(facts, taxonomy, revenue_tags)
                    if unit is None:
                        continue
                    ends = filed_period_ends(facts, taxonomy, revenue_tags, unit)
                    quarters = filed_quarter_revenue(facts, taxonomy, revenue_tags, unit)
                    quarters_reason = None if quarters else f"CIK {cik}: no quarterly revenue filed under {taxonomy}"
                    break
                else:
                    quarters_reason = f"CIK {cik}: no revenue tag in companyfacts"
            else:
                quarters_reason = f"CIK {cik}: SEC has no companyfacts"
        try:
            rows = vendor_releases(ticker)
            record["status"], record["reason"] = "ok", None
            record["releases"] = release_rows(rows, today, ends)
            if not record["releases"]:
                record["status"], record["reason"] = "none", NO_RELEASES
        except Exception as e:  # noqa: BLE001
            record["status"], record["reason"], record["releases"] = "failed", f"vendor failed: {type(e).__name__}: {e}", []
        record["filed_revenue"] = quarters
        record["filed_revenue_reason"] = quarters_reason
        _write_json(path, record)
        log(f"{ticker}: {record['status']}, {len(record['releases'])} release(s), {len(quarters)} filed quarter(s)")


def snapshots_of(root: Path, ticker: str) -> list[Json]:
    out: list[Json] = []
    for d in day_dirs(root):
        r = _read_json(root / "days" / d.isoformat() / f"{ticker}.json")
        if r is not None:
            out.append(r)
    return out


def run_summary(tickers: list[str], root: Path, out_dir: Path, today: date) -> Json:
    summaries = [summarize(t, _read_json(root / "history" / f"{t}.json"), snapshots_of(root, t)) for t in tickers]
    pool = pooled(summaries)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.jsonl").write_text("".join(json.dumps(s, ensure_ascii=False, allow_nan=False) + "\n" for s in summaries))
    _write_json(out_dir / "pooled.json", {"as_of": today.isoformat(), **pool})
    (out_dir / "summary.txt").write_text(summary_text(summaries, pool, today))
    return pool


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", dest="step", choices=("snapshot", "history", "summary"), default="all")
    parser.add_argument("--universe", type=Path, default=UNIVERSE)
    parser.add_argument("--today", type=date.fromisoformat, default=None, help="the UTC day the run is for (default: today's UTC date)")
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("tickers", nargs="*", help="a subset of the universe")
    args = parser.parse_args(argv)
    today = cast(date, args.today or datetime.now(timezone.utc).date())
    entries = _universe_entries(args.universe)
    if args.tickers:
        wanted = set(cast(list[str], args.tickers))
        entries = [e for e in entries if e.ticker in wanted]
    tickers = [cast(str, e.ticker) for e in entries]
    def log(s: str) -> None:
        print(s, flush=True)

    if args.step in ("all", "snapshot"):
        m = run_snapshot(tickers, args.data, today, vendor_trend, log=log)
        log(f"snapshot {today}: {m['status']}, {m['ok']} of {m['names']} ok")
    if args.step in ("all", "history"):
        run_history(entries, args.data, today, log=log)
    if args.step in ("all", "summary"):
        pool = run_summary(tickers, args.data, args.out, today)
        for w in cast(list[Json], pool["windows"]):
            log(f"pooled last {w['window']}: rate {_fmt(w['beat_rate'], '.3f')} over {w['releases']} releases")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
