"""The naive baseline: the anchor study's rows sorted by plain cheapness instead of an anchor.

    uv run python/baseline_study.py [--panel output/pit/panel.jsonl] [--pit data/pit] [--as-of YYYY-MM-DD] [--out output/baseline_study]

The anchor study (80) found that the margin of safety did not precede the price on its own
side over 2022-03 to 2026-06. That alone cannot tell a broken anchor from a market that
paid for what every cheapness measure calls dear. This puts three measures that need no
model beside the anchor on the same rows, the same dates and the same forward windows:

- `earnings_yield`: the latest annual net income known on the date over the market cap.
  A loss is a negative yield and ranks dearest.
- `book_to_price`: book equity over the market cap; null when book equity is zero or
  negative, where the ratio orders nothing.
- `ebit_to_ev`: EBIT over market cap plus financial debt less cash; null where EBIT is not
  filed (banks, insurers) or the enterprise value is not positive.

Each reads the point-in-time boundary file `data/pit/<date>/<TICKER>.json`, the same file
the valuation read: the newest fiscal year filed by the date and the date's market cap.
Statements in another currency than the price convert through USD at the date's own
`reference/fx_rates.json`; a measure with no rate for a leg is null with the reason.

Tables, each quintile cut within the date (1 the dearest, 5 the cheapest), cells as the
anchor study prints them:

1. every measure on every row that carries it, valued or refused;
2. on the rows the anchor valued and that carry the measure, the measure's quintiles
   beside the margin of safety's, both re-cut within that same set, so the two sorts are
   compared on identical rows;
3. the within-date Spearman rank correlation of the margin of safety with each measure,
   the median over the dates and its range: how far the anchor is the naive sort;
4. the cheapest quintile's median less the dearest's at each horizon, for the anchor and
   each measure, one line each;
5. the same difference within each model's own rows, the quintiles re-cut there, because a
   margin of safety from one model does not rank against another's and the pooled cut in
   2 and 4 mixes them;
6. the R&D shadow: on the generic DCF's rows that carry one, the shadow's margin of safety
   in quintiles beside the headline's and the earnings yield on the same rows, the rank
   correlation of the two margins and how many rows change quintile;
7. the options-implied expected return: every row that carries one, in quintiles of it
   within the date, with the earnings yield and the margin of safety on the same rows and
   its rank correlation with each. The options store is young, so this is a few dates.

**Descriptive only**, under the anchor study's rules: no statistic the sample can carry, a
cell under MIN_CELL rows a count alone, nothing fed back into a model, a belief or a
signal. The held-out names and dates in `reference/holdout.json` are not read without
`--holdout`. Closes come from the anchor study's cache, cut at `--as-of`."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import anchor_study as study
from anchor_study import HORIZONS, MIN_CELL, Record

PIT = study.REPO_ROOT / "data" / "pit"
OUT = study.REPO_ROOT / "output" / "baseline_study"
MEASURES = ("earnings_yield", "book_to_price", "ebit_to_ev")
MIN_RANKED = 5   # a date with fewer rows carrying a measure cuts no quintiles and ranks no correlation

Json = dict[str, object]


@dataclass
class Measures:
    earnings_yield: float | None = None
    book_to_price: float | None = None
    ebit_to_ev: float | None = None
    reason: str | None = None   # why all three are null, when they are

    def get(self, name: str) -> float | None:
        return cast(float | None, getattr(self, name))


def usd_per_unit(currency: str | None, fx: Json) -> float | None:
    if currency is None:
        return None
    if currency == "USD":
        return 1.0
    entry = cast(dict[str, Json], fx.get("currencies", {})).get(currency)
    return None if entry is None else study.as_float(entry.get("usd_per_unit"))


def measures_of(boundary: Json, fx: Json) -> Measures:
    """The three ratios from one point-in-time boundary file, statements and market cap on
    one currency basis; null with the reason rather than a ratio across two currencies."""
    cap = study.as_float(boundary.get("market_cap"))
    periods = cast(list[Json], boundary.get("periods") or [])
    if cap is None or cap <= 0:
        return Measures(reason="no market cap on the date")
    if not periods:
        return Measures(reason="no statements known on the date")
    statements, trading = cast(str | None, boundary.get("financial_currency")), cast(str | None, boundary.get("trading_currency"))
    rate = 1.0
    if statements != trading:
        s, t = usd_per_unit(statements, fx), usd_per_unit(trading, fx)
        if s is None or t is None or t == 0:
            return Measures(reason=f"no rate on the date to bring {statements} statements to the {trading} price")
        rate = s / t
    latest = periods[0]
    income, book, ebit = (study.as_float(latest.get(k)) for k in ("net_income", "book_equity", "ebit"))
    debt, cash = study.as_float(latest.get("total_debt")), study.as_float(latest.get("cash"))
    out = Measures()
    if income is not None:
        out.earnings_yield = income * rate / cap
    if book is not None and book > 0:
        out.book_to_price = book * rate / cap
    if ebit is not None and debt is not None and cash is not None:
        ev = cap + (debt - cash) * rate
        if ev > 0:
            out.ebit_to_ev = ebit * rate / ev
    if out.earnings_yield is None and out.book_to_price is None and out.ebit_to_ev is None:
        out.reason = "the latest period carries no net income, no positive book equity and no EBIT with debt and cash"
    return out


def load_measures(records: list[Record], pit: Path) -> dict[tuple[str, str], Measures]:
    out: dict[tuple[str, str], Measures] = {}
    fx_by_date: dict[str, Json] = {}
    for r in records:
        if r.as_of not in fx_by_date:
            fx_path = pit / r.as_of / "reference" / "fx_rates.json"
            fx_by_date[r.as_of] = cast(Json, json.loads(fx_path.read_text())) if fx_path.exists() else {}
        path = pit / r.as_of / f"{r.ticker}.json"
        if not path.exists():
            out[(r.ticker, r.as_of)] = Measures(reason="no point-in-time boundary file on disk")
            continue
        out[(r.ticker, r.as_of)] = measures_of(cast(Json, json.loads(path.read_text())), fx_by_date[r.as_of])
    return out


def load_shadow_margins(records: list[Record], pit_out: Path) -> dict[tuple[str, str], float]:
    """The R&D shadow's margin of safety per (name, date), from the date's own valuations
    file; only the records that carry a block."""
    out: dict[tuple[str, str], float] = {}
    for d in sorted({r.as_of for r in records}):
        path = pit_out / d / "valuations.jsonl"
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            v = cast(Json, json.loads(line))
            block = v.get("rd_shadow")
            if isinstance(block, dict):
                margin = study.as_float(cast(Json, block).get("margin_of_safety"))
                if margin is not None:
                    out[(str(v["ticker"]), d)] = margin
    return out


def load_expected_returns(records: list[Record], pit_out: Path) -> dict[tuple[str, str], float]:
    """The options-implied expected return per (name, date), from the date's own valuations
    file; only the records that carry the block, whatever their status."""
    out: dict[tuple[str, str], float] = {}
    for d in sorted({r.as_of for r in records}):
        path = pit_out / d / "valuations.jsonl"
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            v = cast(Json, json.loads(line))
            block = v.get("options_expected_return")
            if isinstance(block, dict):
                value = study.as_float(cast(Json, block).get("expected_return"))
                if value is not None:
                    out[(str(v["ticker"]), d)] = value
    return out


def expected_return_section(records: list[Record], expected: dict[tuple[str, str], float], measures: dict[tuple[str, str], Measures]) -> list[str]:
    """Every row that carries the options-implied expected return, valued or refused, cut
    into quintiles of it within the date (5 the highest expected return), with the earnings
    yield beside it on the same rows. The options store is young, so few dates carry it and
    the year-ahead cells are mostly counts."""
    rows = [r for r in records if (r.ticker, r.as_of) in expected]
    dates = sorted({r.as_of for r in rows})
    title = f"the options-implied expected return: {len(rows)} rows on {len({r.ticker for r in rows})} names over {len(dates)} dates carry one"
    lines = ["", title, "-" * len(title)]
    if not rows:
        return lines + ["  none: the panel's dates precede the options store, or the batch ran without it"]
    lines.append(f"  dates: {', '.join(dates)}; quintile 1 the lowest expected return, 5 the highest")
    q = quintiles_within_date([(r, expected[(r.ticker, r.as_of)]) for r in rows])
    lines += quintile_block("by options-implied expected return", rows, q) + [""]
    lines += ["the highest quintile's median excess less the lowest's, on those rows:", spread_line("options-implied expected return", rows, q)]
    with_yield = [(r, cast(float, measures[(r.ticker, r.as_of)].earnings_yield)) for r in rows if measures[(r.ticker, r.as_of)].earnings_yield is not None]
    lines.append(spread_line("earnings_yield (cheapest less dearest)", [r for r, _ in with_yield], quintiles_within_date(with_yield)))
    valued = [(r, r.margin_of_safety) for r in rows if r.status == "Ok" and r.margin_of_safety is not None]
    lines.append(spread_line("margin of safety (cheapest less dearest)", [r for r, _ in valued], quintiles_within_date(valued)))
    for label, other in (("the earnings yield", {k: m.earnings_yield for k, m in measures.items()}),
                         ("the margin of safety", {(r.ticker, r.as_of): r.margin_of_safety for r in rows if r.status == "Ok"})):
        per_date: list[float] = []
        for d in dates:
            pairs = [(expected[(r.ticker, d)], x) for r in rows if r.as_of == d and (x := other.get((r.ticker, d))) is not None]
            rho = spearman([a for a, _ in pairs], [b for _, b in pairs])
            if rho is not None:
                per_date.append(rho)
        if per_date:
            lines.append(f"  rank correlation with {label}, within the date: median {statistics.median(per_date):+.2f} over {len(per_date)} dates (lowest {min(per_date):+.2f}, highest {max(per_date):+.2f})")
    return lines


def shadow_section(valued: list[Record], shadow: dict[tuple[str, str], float], measures: dict[tuple[str, str], Measures]) -> list[str]:
    """On the generic DCF's rows that carry an R&D shadow: the shadow's margin of safety, the
    headline's and the earnings yield, each cut into quintiles on those same rows."""
    rows = [r for r in valued if r.model == "dcf" and (r.ticker, r.as_of) in shadow]
    title = f"the R&D shadow: {len(rows)} generic-DCF rows on {len({r.ticker for r in rows})} names carry one"
    lines = ["", title, "-" * len(title)]
    if not rows:
        return lines + ["  none: the panel was built before the shadow, or no row has the research and development history it needs"]
    q_shadow = quintiles_within_date([(r, shadow[(r.ticker, r.as_of)]) for r in rows])
    q_head = quintiles_within_date([(r, cast(float, r.margin_of_safety)) for r in rows])
    lines += quintile_block("by the shadow's margin of safety", rows, q_shadow) + [""]
    lines += quintile_block("the same rows by the headline's margin of safety", rows, q_head) + [""]
    lines += ["the cheapest quintile's median excess less the dearest's, on those rows:",
              spread_line("shadow margin of safety", rows, q_shadow), spread_line("headline margin of safety", rows, q_head)]
    with_yield = [(r, cast(float, measures[(r.ticker, r.as_of)].earnings_yield)) for r in rows if measures[(r.ticker, r.as_of)].earnings_yield is not None]
    lines.append(spread_line("earnings_yield", [r for r, _ in with_yield], quintiles_within_date(with_yield)))
    per_date: list[float] = []
    moved = sum(1 for r in rows if q_shadow.get((r.ticker, r.as_of)) != q_head.get((r.ticker, r.as_of)))
    for d in sorted({r.as_of for r in rows}):
        pairs = [(shadow[(r.ticker, d)], cast(float, r.margin_of_safety)) for r in rows if r.as_of == d]
        rho = spearman([a for a, _ in pairs], [b for _, b in pairs])
        if rho is not None:
            per_date.append(rho)
    if per_date:
        lines.append(f"  rank correlation of the shadow's margin with the headline's, within the date: median {statistics.median(per_date):+.2f} over {len(per_date)} dates (lowest {min(per_date):+.2f})")
    lines.append(f"  rows whose quintile differs between the two: {moved} of {len(rows)}")
    return lines


def quintiles_within_date(rows: list[tuple[Record, float]]) -> dict[tuple[str, str], int]:
    """1 the lowest value, 5 the highest, cut within each date over exactly the rows given."""
    by_date: dict[str, list[tuple[Record, float]]] = {}
    for r, v in rows:
        by_date.setdefault(r.as_of, []).append((r, v))
    out: dict[tuple[str, str], int] = {}
    for group in by_date.values():
        if len(group) < MIN_RANKED:
            continue
        ordered = sorted(group, key=lambda rv: (rv[1], rv[0].ticker))
        n = len(ordered)
        for k, (r, _) in enumerate(ordered):
            out[(r.ticker, r.as_of)] = min(5, 1 + (k * 5) // n)
    return out


def ranks(values: list[float]) -> list[float]:
    """Average ranks, ties sharing the mean of the places they span."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < MIN_RANKED:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sxx * syy) ** 0.5


def quintile_block(title: str, rows: list[Record], q: dict[tuple[str, str], int]) -> list[str]:
    return study.block(title, [(f"quintile {k}", [r for r in rows if q.get((r.ticker, r.as_of)) == k]) for k in range(1, 6)])


def spread_line(label: str, rows: list[Record], q: dict[tuple[str, str], int]) -> str:
    parts: list[str] = []
    for h in HORIZONS:
        ends: list[float | None] = []
        for k in (5, 1):
            values = [x for r in rows if q.get((r.ticker, r.as_of)) == k and (x := r.excess.get(str(h))) is not None]
            ends.append(statistics.median(values) if len(values) >= MIN_CELL else None)
        top, bottom = ends
        parts.append(f"+{h}d {'n under ' + str(MIN_CELL) if top is None or bottom is None else f'{top - bottom:+.3f}'}")
    return f"  {label}: {', '.join(parts)}"


def report(records: list[Record], measures: dict[tuple[str, str], Measures], as_of: date, holdout_line: str,
           shadow: dict[tuple[str, str], float] | None = None, expected: dict[tuple[str, str], float] | None = None) -> str:
    dates = sorted({r.as_of for r in records})
    lines = [
        f"The naive baseline: {len(records)} panel rows, {len({r.ticker for r in records})} names, {len(dates)} quarter-ends {dates[0]} to {dates[-1]}, closes cut at {as_of.isoformat()}.",
        "Descriptive only, under the anchor study's rules: the excess over SPY at +63, +126 and +252 trading days, quintiles cut within the date, 1 the dearest and 5 the cheapest. No statistic the sample can carry. A cell under ten rows is a count alone.",
        holdout_line,
        "",
    ]
    reasons: dict[str, int] = {}
    for r in records:
        why = measures[(r.ticker, r.as_of)].reason
        if why is not None:
            reasons[why] = reasons.get(why, 0) + 1
    lines += ["rows carrying no measure", "------------------------"]
    lines += [f"  {n}: {why}" for why, n in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))] or ["  none"]
    lines.append("")

    for name in MEASURES:
        rows = [(r, v) for r in records if (v := measures[(r.ticker, r.as_of)].get(name)) is not None]
        lines += quintile_block(f"{name}, every row that carries it ({len(rows)} rows)", [r for r, _ in rows], quintiles_within_date(rows)) + [""]

    valued = [r for r in records if r.status == "Ok" and r.margin_of_safety is not None]
    spreads: list[str] = []
    for name in MEASURES:
        both = [(r, cast(float, measures[(r.ticker, r.as_of)].get(name))) for r in valued if measures[(r.ticker, r.as_of)].get(name) is not None]
        rows = [r for r, _ in both]
        q_measure = quintiles_within_date(both)
        q_anchor = quintiles_within_date([(r, cast(float, r.margin_of_safety)) for r in rows])
        lines += quintile_block(f"the rows the anchor valued that carry {name} ({len(rows)} rows): by {name}", rows, q_measure) + [""]
        lines += quintile_block(f"the same {len(rows)} rows: by margin of safety", rows, q_anchor) + [""]
        spreads += [f"on the {len(rows)} valued rows carrying {name}:", spread_line(name, rows, q_measure), spread_line("margin of safety", rows, q_anchor)]

    lines += ["rank correlation of the margin of safety with each measure, within the date (Spearman)",
              "---------------------------------------------------------------------------------------"]
    for name in MEASURES:
        per_date: list[float] = []
        for d in dates:
            pairs = [(cast(float, r.margin_of_safety), cast(float, measures[(r.ticker, d)].get(name)))
                     for r in valued if r.as_of == d and measures[(r.ticker, d)].get(name) is not None]
            rho = spearman([a for a, _ in pairs], [b for _, b in pairs])
            if rho is not None:
                per_date.append(rho)
        lines.append(f"  {name}: no date ranks {MIN_RANKED} rows" if not per_date else
                     f"  {name}: median {statistics.median(per_date):+.2f} over {len(per_date)} dates (lowest {min(per_date):+.2f}, highest {max(per_date):+.2f})")
    lines += ["", "the cheapest quintile's median excess less the dearest's", "--------------------------------------------------------"] + spreads
    lines += ["", "the same difference within each model's own rows, quintiles re-cut there", "-----------------------------------------------------------------------"]
    for model in sorted({r.model for r in valued if r.model}):
        for name in MEASURES:
            both = [(r, cast(float, measures[(r.ticker, r.as_of)].get(name))) for r in valued if r.model == model and measures[(r.ticker, r.as_of)].get(name) is not None]
            if not both:
                continue
            rows = [r for r, _ in both]
            lines += [f"{model}, {len(rows)} rows on {len({r.ticker for r in rows})} names carrying {name}:",
                      spread_line(name, rows, quintiles_within_date(both)),
                      spread_line("margin of safety", rows, quintiles_within_date([(r, cast(float, r.margin_of_safety)) for r in rows]))]
    lines += shadow_section(valued, shadow or {}, measures)
    lines += expected_return_section(records, expected or {}, measures)
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", type=Path, default=study.PANEL)
    parser.add_argument("--pit", type=Path, default=PIT, help="the point-in-time boundary files, one directory per date")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today(), help="the day the closes are cut at; the study repeats byte for byte at the same cut")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--holdout", action="store_true", help="read the held-out names and dates too; a one-time act, recorded in reference/holdout.json")
    args = parser.parse_args(argv)
    panel: Path = args.panel
    pit: Path = args.pit
    as_of: date = args.as_of
    out: Path = args.out
    opened: bool = args.holdout
    records, holdout_line = study.set_aside(study.load_panel(panel, panel.parent), study.load_holdout(), opened=opened)
    study.attach_forward(records, as_of)
    measures = load_measures(records, pit)
    out.mkdir(parents=True, exist_ok=True)
    (out / "records.jsonl").write_text("".join(
        json.dumps({"ticker": r.ticker, "as_of": r.as_of, "status": r.status, "margin_of_safety": r.margin_of_safety, "excess": r.excess,
                    **{m: measures[(r.ticker, r.as_of)].get(m) for m in MEASURES}, "measures_reason": measures[(r.ticker, r.as_of)].reason},
                   sort_keys=True) + "\n" for r in records))
    text = report(records, measures, as_of, holdout_line, load_shadow_margins(records, panel.parent),
                  load_expected_returns(records, panel.parent))
    (out / "tables.txt").write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
