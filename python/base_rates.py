"""Base rates of sales growth: how often companies of a given size actually grew that fast.

    uv run python/base_rates.py [--first-year 2009] [--last-year YYYY] [--refresh]

A record says what growth the price needs; this builds the reference class that says how
often such growth has happened. The outside view beside the declared belief, after
Mauboussin and Callahan's base-rate work: a frequency from history, never a belief and
never an input to a fair value.

Source. SEC's frames API serves one value per filer for an element, a unit and a calendar
year: `https://data.sec.gov/api/xbrl/frames/us-gaap/<element>/USD/CY<year>.json`, a fiscal
year being assigned to the calendar year it mostly covers. One request per element and
year, so the whole class is a few dozen requests. Each response is kept as fetched under
`data/base_rates/frames/` (a year that has closed does not change much; `--refresh`
re-fetches). Nothing fetched is tracked.

Contract. `data/reference/base_rates.json` holds, per horizon in HORIZONS and per size
bucket in BUCKETS (starting revenue in dollars, nominal), over every start year the frames
allow: `n`, the companies whose revenue is filed at both ends; `not_reported_at_end`, those
with a starting revenue and none at the end (acquired, delisted, failed, or simply not
filing that element: they are counted and left out, so the table describes survivors and
says how many did not); and `percentiles`, the 1st to 99th percentile of the compound annual
growth of revenue over the horizon. A company's revenue for a year is the largest of the
revenue elements it filed for that year, since the total includes its parts. Start years
overlap, so the windows are not independent draws: a frequency, with no error bar claimed.
A table needs MIN_CELL companies or it is left out and the record says so.

The record's `base_rate` block (ocaml/lib/base_rates.ml) reads the five-year table."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import cast

import fetch_sec

REPO_ROOT = Path(__file__).resolve().parents[1]
FRAMES = REPO_ROOT / "data" / "base_rates" / "frames"
OUT = REPO_ROOT / "data" / "reference" / "base_rates.json"
URL = "https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/USD/CY{year}.json"
TAGS = ("Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax")
HORIZONS = (3, 5, 10)
# starting revenue in dollars, nominal: [lower, upper); the labels are what the record prints
BUCKETS: tuple[tuple[str, float, float | None], ...] = (
    ("10m to 100m", 1e7, 1e8), ("100m to 1bn", 1e8, 1e9), ("1bn to 10bn", 1e9, 1e10),
    ("10bn to 50bn", 1e10, 5e10), ("50bn and above", 5e10, None))
MIN_CELL = 30
FIRST_YEAR = 2009   # the first full year of XBRL filing for large filers


def frame(tag: str, year: int, user_agent: str, *, refresh: bool = False) -> list[dict[str, object]]:
    """One element's values for one calendar year, as fetched and cached; [] when SEC has none."""
    path = FRAMES / f"{tag}-CY{year}.json"
    if path.exists() and not refresh:
        return cast(list[dict[str, object]], json.loads(path.read_text()).get("data", []))
    try:
        body = fetch_sec._get(URL.format(tag=tag, year=year), user_agent)  # pyright: ignore[reportPrivateUsage]
    except Exception as e:  # noqa: BLE001
        if "404" in str(e):
            body = b'{"data": []}'
        else:
            raise
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return cast(list[dict[str, object]], json.loads(body).get("data", []))


def revenues(frames: dict[tuple[str, int], list[dict[str, object]]]) -> dict[int, dict[int, float]]:
    """cik -> year -> revenue: the largest positive value among the elements filed for the year."""
    out: dict[int, dict[int, float]] = {}
    for (_, year), rows in frames.items():
        for row in rows:
            cik, val = row.get("cik"), row.get("val")
            if isinstance(cik, int) and isinstance(val, (int, float)) and not isinstance(val, bool) and val > 0:
                by_year = out.setdefault(cik, {})
                by_year[year] = max(by_year.get(year, 0.0), float(val))
    return out


def bucket_of(revenue: float) -> str | None:
    for label, lower, upper in BUCKETS:
        if revenue >= lower and (upper is None or revenue < upper):
            return label
    return None


def percentiles(values: list[float]) -> list[float]:
    """The 1st to 99th percentile, linear between order statistics."""
    ordered = sorted(values)
    n = len(ordered)
    out: list[float] = []
    for p in range(1, 100):
        x = (n - 1) * p / 100
        lo = int(x)
        hi = min(lo + 1, n - 1)
        out.append(ordered[lo] + (ordered[hi] - ordered[lo]) * (x - lo))
    return out


def tables(revenue: dict[int, dict[int, float]], first: int, last: int) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for horizon in HORIZONS:
        growth: dict[str, list[float]] = {label: [] for label, _, _ in BUCKETS}
        lost: dict[str, int] = {label: 0 for label, _, _ in BUCKETS}
        for by_year in revenue.values():
            for start in range(first, last - horizon + 1):
                r0 = by_year.get(start)
                if r0 is None:
                    continue
                label = bucket_of(r0)
                if label is None:
                    continue
                r1 = by_year.get(start + horizon)
                if r1 is None:
                    lost[label] += 1
                else:
                    growth[label].append((r1 / r0) ** (1 / horizon) - 1)
        for label, lower, upper in BUCKETS:
            if len(growth[label]) < MIN_CELL:
                continue
            out.append({"horizon_years": horizon, "bucket": label, "lower": lower, "upper": upper, "n": len(growth[label]),
                        "not_reported_at_end": lost[label], "percentiles": percentiles(growth[label])})
    return out


def build(first: int, last: int, user_agent: str, *, refresh: bool = False, log: bool = True) -> dict[str, object]:
    frames: dict[tuple[str, int], list[dict[str, object]]] = {}
    for year in range(first, last + 1):
        for tag in TAGS:
            frames[(tag, year)] = frame(tag, year, user_agent, refresh=refresh)
        if log:
            print(f"CY{year}: {sum(len(frames[(t, year)]) for t in TAGS)} values", flush=True)
    revenue = revenues(frames)
    return {
        "source": "SEC XBRL frames API, us-gaap revenue elements in USD by calendar year; compound annual growth of revenue by starting size",
        "built": date.today().isoformat(), "first_year": first, "last_year": last, "elements": list(TAGS),
        "companies": len(revenue), "min_cell": MIN_CELL, "tables": tables(revenue, first, last),
        "notes": ["Survivors only: a company with no revenue filed at the end of a window is counted in not_reported_at_end and left out of the percentiles.",
                  "Start years overlap, so the windows are not independent; a frequency, no error bar.",
                  "Size buckets are nominal dollars at the start of the window."],
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--first-year", type=int, default=FIRST_YEAR)
    parser.add_argument("--last-year", type=int, default=date.today().year - 1, help="the last calendar year with annual reports filed; default last year")
    parser.add_argument("--refresh", action="store_true", help="fetch every frame again")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    first: int = args.first_year
    last: int = args.last_year
    out: Path = args.out
    table = build(first, last, fetch_sec.identity(), refresh=bool(args.refresh))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(table, indent=1) + "\n")
    rows = cast(list[dict[str, object]], table["tables"])
    print(f"{table['companies']} companies, {len(rows)} tables -> {out}")
    for t in rows:
        p = cast(list[float], t["percentiles"])
        print(f"  {t['horizon_years']:>2}y {str(t['bucket']):>14}: n={t['n']:>6}, not reported at end {t['not_reported_at_end']:>6}, "
              f"p10 {p[9]:+.3f}  p50 {p[49]:+.3f}  p90 {p[89]:+.3f}  p99 {p[98]:+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
