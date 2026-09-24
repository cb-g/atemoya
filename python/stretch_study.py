"""(67) What did stretch and the insider block actually precede?

Two episodes said insiders did not call the bottoms stretch caught. This walks every
trading day the vendor serves, finds every stretch episode on record, measures what
followed against SPY over the same dates, and reads the Form 4 block as it stood the day
before each episode began.

**Descriptive only.** Medians, quartiles and counts; no statistic the sample cannot carry,
no fitted model, no hit rate presented as an edge, no threshold moved after seeing a table.
A cell of fewer than MIN_CELL episodes prints its count and nothing else, because a median
of eight things is a number pretending to be a measurement.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping, cast

import boundary
import reference
import stretch

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "output" / "stretch_study"
CACHE = REPO_ROOT / "data" / "stretch_study"
UNIVERSE = REPO_ROOT / "reference" / "universe.json"
BENCHMARK = "SPY"
HORIZONS = (20, 60, 120)
QUIET_DAYS = 20            # trading days below 3 before a new episode can start
MIN_HISTORY_DAYS = 750     # the third year onward, in trading days
MIN_CELL = 10              # below this a cell is a count, never a median
OVERLAP_DAYS = 120
INSIDER_WINDOW_DAYS = 90    # the block's own near window; the study reads no other
NO_FORM_4 = "no Form 4 filed at all: the form covers insiders of SEC registrants, and this filer files none"
SIDES = ("low", "high")


@dataclass(frozen=True)
class Episode:
    ticker: str
    side: str
    date: str
    close: float
    dd_120: float
    above_120_low: float
    vs_ma50: float
    vs_ma200: float
    rsi_14: float
    stretch_low: int
    stretch_high: int
    forward: dict[str, float | None]          # "20" -> simple return
    benchmark: dict[str, float | None]
    excess: dict[str, float | None]
    insider_state: str                        # bought | sold | neither | unknown
    insider_buyers: int | None
    insider_sellers: int | None
    insider_net_dollars: float | None
    insider_cluster: bool | None
    insider_chief_bought: bool | None
    insider_reason: str | None
    overlaps_previous: bool                   # another episode on this name, same side, within 120 days


def forward_returns(closes: dict[date, float], days: list[date], i: int) -> dict[str, float | None]:
    """Simple returns at +20, +60 and +120 TRADING days; null where the window runs past
    the last close rather than short-changing the horizon."""
    base = closes[days[i]]
    out: dict[str, float | None] = {}
    for h in HORIZONS:
        j = i + h
        out[str(h)] = (closes[days[j]] / base - 1.0) if j < len(days) and base > 0 else None
    return out


def episode_days(closes: dict[date, float], volumes: dict[date, float],
                 t: reference.StretchThresholds) -> list[tuple[int, str, dict[str, float], int, int]]:
    """Every episode start, as (index into the sorted days, side, measures, low, high).

    The counts come from the block's own measures_at and counts, on closes up to and
    including that day and nothing after it. The percentiles the block also records play no
    part in a count, so they are not computed here; the counts are identical either way."""
    days = sorted(closes)
    c = [closes[d] for d in days]
    v = [volumes.get(d, 0.0) for d in days]
    quiet = {side: QUIET_DAYS for side in SIDES}      # start eligible after the warm-up
    out: list[tuple[int, str, dict[str, float], int, int]] = []
    for e in range(MIN_HISTORY_DAYS, len(c) + 1):
        m = stretch.measures_at(c[:e], v[:e], [])
        if m is None:
            continue
        low, high = stretch.counts(m, t)
        for side, count in (("low", low), ("high", high)):
            if count >= 3:
                if quiet[side] >= QUIET_DAYS:
                    out.append((e - 1, side, m, low, high))
                quiet[side] = 0
            else:
                quiet[side] += 1
    return out


@dataclass(frozen=True)
class InsiderState:
    """What the Form 4 record said on the day before an episode, over the 90 days behind it.

    Only the 90-day window: the cache is filled for exactly these windows, so a 365-day
    figure computed from it would be a subset dressed as a total. [state] is `unknown`
    whenever the window cannot be read in full -- no CIK, no index, no Form 4 on file at
    all, or a filing the cache does not hold -- and the reason says which, because a window
    missing one filing may be missing the only purchase."""
    state: str                                # bought | sold | neither | unknown
    reason: str | None
    buyers: int | None = None
    sellers: int | None = None
    net_dollars: float | None = None
    cluster: bool | None = None
    chief_bought: bool | None = None


def state_of(w: boundary.InsiderWindow) -> str:
    """The three states the tables split on. Brief 66's own wording: any open-market buyer,
    net selling by two or more distinct sellers, or neither."""
    if w.buyers > 0:
        return "bought"
    if w.net_dollars < 0 and w.sellers >= 2:
        return "sold"
    return "neither"


def quantiles(values: list[float]) -> tuple[float, float, float]:
    """Median and the 25th/75th, on the sample as it is."""
    s = sorted(values)
    n = len(s)
    return (statistics.median(s), s[max(0, (n - 1) // 4)], s[min(n - 1, (3 * (n - 1)) // 4)])


def cell(episodes: list[Episode], horizon: int) -> str:
    """One table cell: the count always, the numbers only when the count can carry them."""
    values = [x for e in episodes if (x := e.excess[str(horizon)]) is not None]
    if len(values) < MIN_CELL:
        return f"n={len(values)}"
    med, q1, q3 = quantiles(values)
    positive = sum(1 for x in values if x > 0)
    return f"n={len(values)} median {med:+.3f} (IQR {q1:+.3f} to {q3:+.3f}), positive {positive}/{len(values)}"


def table(episodes: list[Episode], title: str) -> str:
    """Per side, then per side and insider state. Counts everywhere, medians only where
    MIN_CELL allows; nothing is weighted, ranked or fitted."""
    lines = [title, "=" * len(title)]
    for side in SIDES:
        rows = [e for e in episodes if e.side == side]
        names = len({e.ticker for e in rows})
        lines.append(f"\nstretch-{side}: {len(rows)} episodes on {names} names")
        for h in HORIZONS:
            forward = [x for e in rows if (x := e.forward[str(h)]) is not None]
            own = (f"median forward {statistics.median(forward):+.3f}" if len(forward) >= MIN_CELL
                   else f"n={len(forward)}")
            lines.append(f"  +{h:>3}d  own {own:<28s} excess over {BENCHMARK}: {cell(rows, h)}")
        for state in ("bought", "sold", "neither", "unknown"):
            sub = [e for e in rows if e.insider_state == state]
            if not sub:
                continue
            lines.append(f"  insiders {state}: {len(sub)} episodes on {len({e.ticker for e in sub})} names")
            for h in HORIZONS:
                lines.append(f"    +{h:>3}d  excess: {cell(sub, h)}")
    return "\n".join(lines)


def sentence(episodes: list[Episode], side: str) -> str:
    """One sentence per side, written from the table and saying only what it says."""
    rows = [e for e in episodes if e.side == side]
    names = len({e.ticker for e in rows})
    values = [x for e in rows if (x := e.excess["60"]) is not None]
    bought = sum(1 for e in rows if e.insider_state == "bought")
    if len(values) < MIN_CELL:
        return (f"stretch-{side} fired {len(rows)} times on {names} names; too few carry a 60-day "
                f"forward return to quote a median; insiders bought before {bought} of them.")
    med, q1, q3 = quantiles(values)
    return (f"stretch-{side} fired {len(rows)} times on {names} names; the median 60-day excess over "
            f"{BENCHMARK} was {med:+.3f} (IQR {q1:+.3f} to {q3:+.3f}, n={len(values)}); "
            f"insiders bought before {bought} of them.")


def first_per_name_per_year(episodes: list[Episode]) -> list[Episode]:
    """The same table with one episode per name per side per calendar year, so the reader
    sees whether a handful of names carry the whole thing."""
    seen: set[tuple[str, str, int]] = set()
    out: list[Episode] = []
    for e in sorted(episodes, key=lambda x: (x.ticker, x.side, x.date)):
        key = (e.ticker, e.side, int(e.date[:4]))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def write(episodes: list[Episode], out: Path = OUT) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "episodes.jsonl").open("w") as f:
        for e in sorted(episodes, key=lambda x: (x.date, x.ticker, x.side)):
            f.write(json.dumps(asdict(e), sort_keys=True) + "\n")
    overlapping = sum(1 for e in episodes if e.overlaps_previous)
    by_state = Counter(e.insider_state for e in episodes)
    text = "\n\n".join([
        table(episodes, "All episodes"),
        table(first_per_name_per_year(episodes), "First per name, per side, per calendar year"),
        "\n".join([
            "",
            f"{overlapping} of {len(episodes)} episodes have another on the same name and side within "
            f"{OVERLAP_DAYS} days.",
            f"insider state: " + ", ".join(f"{k} {v}" for k, v in sorted(by_state.items())),
            "",
            sentence(episodes, "low"),
            sentence(episodes, "high"),
            "",
            "Descriptive only: counts, medians and quartiles on the sample as it is. No statistic the "
            "sample cannot carry, no fitted model, no threshold moved after the fact. A cell under "
            f"{MIN_CELL} episodes prints its count alone.",
        ]),
    ])
    (out / "summary.txt").write_text(text + "\n")
    return out / "summary.txt"


# --- the run ---------------------------------------------------------------------------


def insiders_before(cik: str | None, day: date, index: Mapping[str, object] | None) -> InsiderState:
    """The 90-day window ending the day BEFORE the episode: nothing filed on the episode's
    own day or after it is read, so the state is what a reader had when it began.

    The filing window runs a further [INSIDER_FILING_LAG_DAYS] back, because a Form 4 is
    filed after the transaction it reports and a filing just outside can carry a transaction
    just inside. Reads `filings.recent` and the older pages on disk, and fetches nothing."""
    import fetch_sec  # noqa: PLC0415
    import insiders as insiders_mod  # noqa: PLC0415

    if cik is None:
        return InsiderState("unknown", insiders_mod.NO_CIK)
    if index is None:
        return InsiderState("unknown", "SEC submissions index unavailable")
    if not insiders_mod.form4_filings(index):
        # a filer whose whole recent index carries no Form 4 files none: a foreign private
        # issuer, or a registrant with no reporting insiders. Counting that as nobody buying
        # or selling would read a form that is not filed as a decision that was not taken
        return InsiderState("unknown", NO_FORM_4)
    as_of = day - timedelta(days=1)
    first = as_of - timedelta(days=INSIDER_WINDOW_DAYS + fetch_sec.INSIDER_FILING_LAG_DAYS)
    filings, absent = fetch_sec.form4_filings_cached(cik, index, first, as_of)
    if absent:
        # `recent` is a year, not a history: an unread older page is a quarter this cannot see
        return InsiderState("unknown", f"{len(absent)} older submissions page(s) are not cached")
    # the tallies of excluded codes and of documents read are brief 66's business, not the
    # study's: what is counted here is purchases and sales, and those are in [found]
    found, _excluded, _read, missing = fetch_sec.insiders_cached(cik, filings)
    if missing:
        return InsiderState("unknown", f"{missing} Form 4 filing(s) in the window are not cached")
    # a window read in full that holds nothing is zero, not unknown: nothing was filed, and
    # that is an answer rather than an absence
    kept = insiders_mod.deduplicate(found)
    w = insiders_mod.window(kept, as_of, INSIDER_WINDOW_DAYS)
    return InsiderState(
        state_of(w), None, buyers=w.buyers, sellers=w.sellers, net_dollars=w.net_dollars,
        cluster=insiders_mod.cluster(kept, as_of, INSIDER_WINDOW_DAYS) is not None,
        chief_bought=w.ceo_or_cfo_bought)


def closes_of(ticker: str, as_of: date, *, cache: Path = CACHE) -> tuple[dict[date, float], dict[date, float]]:
    """The vendor's closes and volumes to [as_of], fetched once and then read from disk.

    The vendor serves its history to the present, and the present moves: the close for the
    current day is still forming, so two runs an hour apart give a different benchmark return
    at the horizons that reach it. The series is therefore fetched once per name and date and
    cached under a gitignored path, which is what makes the run repeat. Delete the directory
    to re-fetch."""
    import pit  # noqa: PLC0415

    path = cache / f"{ticker}-{as_of.isoformat()}.json"
    if path.exists():
        stored = cast(dict[str, list[float]], json.loads(path.read_text()))
        return ({date.fromisoformat(d): v[0] for d, v in stored.items()},
                {date.fromisoformat(d): v[1] for d, v in stored.items()})
    h = pit.History.fetch(ticker)
    closes = {d: c for d, c in h.closes.items() if d <= as_of}
    volumes = {d: h.volumes.get(d, 0.0) for d in closes}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({d.isoformat(): [closes[d], volumes[d]] for d in sorted(closes)},
                               sort_keys=True))
    return closes, volumes


def fill(tickers: list[tuple[str, str | None]], as_of: date) -> int:
    """Fetch what the study reads and nothing else: the older submissions pages its windows
    reach into, then the Form 4 documents filed in those windows.

    The one place that fetches. Paced by `fetch_sec`, and a document is immutable once filed
    so it is written once and kept; only the index ages. Returns the number of documents that
    could not be read, which is 0 on a clean fill."""
    import urllib.error  # noqa: PLC0415

    import fetch  # noqa: PLC0415
    import fetch_sec  # noqa: PLC0415

    sec = fetch.SecContext()
    t = stretch.load_thresholds()
    lag = INSIDER_WINDOW_DAYS + fetch_sec.INSIDER_FILING_LAG_DAYS
    episodes: list[tuple[str, str, date]] = []
    pages: dict[str, str] = {}
    for ticker, cik in tickers:
        if cik is None:
            continue
        try:
            closes, volumes = closes_of(ticker, as_of)
        except Exception as e:  # noqa: BLE001
            print(f"  {ticker}: no history ({e})", flush=True)
            continue
        days = sorted(closes)
        if len(days) < MIN_HISTORY_DAYS:
            continue
        found = episode_days(closes, volumes, t)
        if not found:
            continue
        index = fetch_sec.submissions(cik, sec.user_agent)
        if index is None:
            continue
        episodes += [(ticker, cik, days[i]) for i, _, _, _, _ in found]
        first = min(days[i] for i, _, _, _, _ in found) - timedelta(days=1 + lag)
        last = max(days[i] for i, _, _, _, _ in found) - timedelta(days=1)
        for name in fetch_sec.submissions_pages(index, first, last):
            pages[name] = ticker
    print(f"{len({e[0] for e in episodes})} names with episodes, {len(episodes)} episodes, "
          f"{len(pages)} older submissions page(s) wanted", flush=True)

    got = 0
    for name in sorted(pages):
        if (fetch_sec.CACHE_DIR / name).exists():
            continue
        try:
            fetch_sec.submissions_page(name, sec.user_agent)
            got += 1
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"  page {name} ({pages[name]}): {type(e).__name__}: {e}", flush=True)
    print(f"{got} page(s) fetched", flush=True)

    wanted: dict[str, set[tuple[str, str]]] = {}
    for _ticker, cik, day in episodes:
        as_of_window = day - timedelta(days=1)
        index = fetch_sec.submissions(cik, sec.user_agent)
        filings, _absent = fetch_sec.form4_filings_cached(
            cik, index, as_of_window - timedelta(days=lag), as_of_window)
        for accession, _filed, document in filings:
            wanted.setdefault(cik, set()).add((accession, document))
    want = sum(len(v) for v in wanted.values())
    fetched = failed = 0
    for cik in sorted(wanted):
        for accession, document in sorted(wanted[cik]):
            try:
                if not fetch_sec.insider_document(cik, accession, document, sec.user_agent):
                    continue
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
                print(f"  CIK {cik} {accession}: {type(e).__name__}: {e}", flush=True)
                failed += 1
                continue
            fetched += 1
            if fetched % 200 == 0:
                print(f"  {fetched} document(s) fetched, {failed} unreachable", flush=True)
    print(f"{want} document(s) in the windows, {fetched} fetched, {failed} unreachable")
    if failed:
        print("re-run --fill: a 503 is SEC asking for a slower pace, not a missing document")
    return failed


def study(tickers: list[tuple[str, str | None]], as_of: date, *, out: Path = OUT) -> list[Episode]:
    """Every episode on every name, with what followed and what the insiders had done.

    Every close after [as_of] is dropped before anything is computed. The vendor serves its
    history to the present and the present moves, so a walk that took it whole would find one
    more episode in the afternoon than it found in the morning; cut at the snapshot's own date
    the run repeats. Vendor revisions to older closes are outside this and are not claimed."""
    import fetch  # noqa: PLC0415
    import fetch_sec  # noqa: PLC0415

    t = stretch.load_thresholds()
    sec = fetch.SecContext()
    market, _ = closes_of(BENCHMARK, as_of)
    market_days = sorted(market)
    episodes: list[Episode] = []
    for ticker, cik in tickers:
        try:
            closes, volumes = closes_of(ticker, as_of)
        except Exception as e:  # noqa: BLE001 - a name the vendor will not serve is skipped, not fatal
            print(f"  {ticker}: no history ({e})", flush=True)
            continue
        days = sorted(closes)
        if len(days) < MIN_HISTORY_DAYS:
            print(f"  {ticker}: {len(days)} closes, under the {MIN_HISTORY_DAYS} the walk needs", flush=True)
            continue
        found = episode_days(closes, volumes, t)
        # the index once per name, not once per episode: it is the only thing here that ages
        index = fetch_sec.submissions(cik, sec.user_agent) if cik and found else None
        last: dict[str, date] = {}
        for i, side, m, low, high in found:
            day = days[i]
            forward = forward_returns(closes, days, i)
            # the benchmark over the SAME dates, so a market-wide selloff is not read as a call
            bench: dict[str, float | None] = {}
            excess: dict[str, float | None] = {}
            j = next((k for k, d in enumerate(market_days) if d >= day), None)
            for horizon in HORIZONS:
                b = None
                if j is not None and j + horizon < len(market_days):
                    base = market[market_days[j]]
                    b = market[market_days[j + horizon]] / base - 1.0 if base > 0 else None
                bench[str(horizon)] = b
                own = forward[str(horizon)]
                excess[str(horizon)] = None if own is None or b is None else own - b
            ins = insiders_before(cik, day, index)
            previous = last.get(side)
            episodes.append(Episode(
                ticker=ticker, side=side, date=day.isoformat(), close=closes[day],
                dd_120=m["dd_120"], above_120_low=m["above_120_low"], vs_ma50=m["vs_ma50"],
                vs_ma200=m["vs_ma200"], rsi_14=m["rsi_14"], stretch_low=low, stretch_high=high,
                forward=forward, benchmark=bench, excess=excess,
                insider_state=ins.state, insider_buyers=ins.buyers, insider_sellers=ins.sellers,
                insider_net_dollars=ins.net_dollars, insider_cluster=ins.cluster,
                insider_chief_bought=ins.chief_bought, insider_reason=ins.reason,
                overlaps_previous=previous is not None and (day - previous).days <= OVERLAP_DAYS))
            last[side] = day
        print(f"  {ticker}: {len(found)} episode(s) over {len(days)} closes", flush=True)
    write(episodes, out)
    return episodes


def universe(snapshot: Path, tickers: list[str]) -> list[tuple[str, str | None]]:
    """Every name in the snapshot with the CIK the pipeline resolves for it.

    From the ticker map and the universe's declared CIKs (14, 22), never from a record's
    prose: a name whose provider reason names a companyfacts lag rather than a CIK has a CIK
    all the same, and reading the reason would quietly put it on the no-CIK pile."""
    import fetch  # noqa: PLC0415
    import json as json_mod  # noqa: PLC0415
    import universe as universe_file  # noqa: PLC0415

    sec = fetch.SecContext()
    declared = {e.ticker.upper(): e.cik for e in universe_file.load(UNIVERSE).tickers}
    wanted: list[tuple[str, str | None]] = []
    for path in sorted(snapshot.glob("*.json")):
        if ".shadow-" in path.name:
            continue
        ticker = str(json_mod.loads(path.read_text())["ticker"])
        if tickers and ticker not in tickers:
            continue
        cik, _source = fetch.cik_of(ticker, sec.tickers, declared.get(ticker.upper()))
        wanted.append((ticker, cik))
    return wanted


def main(argv: list[str]) -> int:
    """Walk the universe, or the tickers named."""
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="*", help="default: every name in the latest snapshot")
    parser.add_argument("--snapshot", type=Path, default=REPO_ROOT / "data" / "snapshots" / "2026-09-24")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None,
                        help="the last close the walk may see; the snapshot's own date by default")
    parser.add_argument("--fill", action="store_true",
                        help="fetch the submissions pages and Form 4 documents the study reads, then stop")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    as_of = args.as_of or date.fromisoformat(args.snapshot.name)
    names = universe(args.snapshot, args.tickers)
    if args.fill:
        return 1 if fill(names, as_of) else 0
    episodes = study(names, as_of, out=args.out)
    print(f"{len(episodes)} episodes -> {args.out}")
    print()
    print((args.out / "summary.txt").read_text())
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
