"""(68) The earnings gate: when the next results release is, what the last ones did, and
what the option market charges for the next one.

Every options readout picks an expiry without knowing whether a release sits inside it, and
a spread or a hedge across one is a different instrument. This puts the event on the record.

**Filed and keyless.** The past releases are every 8-K carrying item 2.02, Results of
Operations and Financial Condition, from SEC's own submissions index, over the last five
years. A filer with no 2.02 at all -- a foreign private issuer files 6-K, a trust files
neither -- falls back to the vendor's dates, and the record says which it read. The next
date is the vendor's where it carries one and a projection from the filed cadence otherwise,
and the record says which: a projection presented as a filed date would be a forecast
wearing a filing's clothes.

No score, no weight and no signal. It never fails a record and nothing in the valuation
reads it.
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, cast

import boundary

BENCHMARK = "SPY"
YEARS = 5
EVENTS = 8                 # the last eight, for the cadence and the realised median
ITEM = "2.02"
FORM = "8-K"               # (68) the amendment restates a release already dated; see below
AFTER_CLOSE_UTC = 20       # 16:00 New York in either offset is 20:00 or 21:00 UTC
BEFORE_OPEN_UTC = 14       # 09:30 New York is 13:30 or 14:30 UTC

NO_CALENDAR = "no release calendar: neither a filed item 2.02 nor a vendor earnings date"
SCOPE_LIMITS = [
    "the past releases are 8-K item 2.02 filings as filed: a filer that reports results and operating "
    "statistics separately files item 2.02 for both, and both are counted",
    "an 8-K/A amending a release is not counted again; the original dates the event",
    "the move across a release is close to close, split-corrected by the vendor's own adjustment, and "
    "carries whatever else moved the price that day",
    "a projected next date is the filed cadence continued and is not a filing; the record says which it is",
]

_history: dict[str, Any] = {}


def _items_of(index: Mapping[str, object]) -> tuple[list[str], list[str], list[str]]:
    """(form, filing date, items) columns, from a submissions index or one of the older pages
    beside it, whose arrays sit at the top level rather than under `filings.recent`."""
    filings = cast(Mapping[str, object], index.get("filings") or {})
    recent = cast(Mapping[str, Any], filings.get("recent") or index)
    return (cast(list[str], recent.get("form") or []),
            cast(list[str], recent.get("filingDate") or []),
            cast(list[str], recent.get("items") or []))


def _acceptance_of(index: Mapping[str, object]) -> list[str]:
    filings = cast(Mapping[str, object], index.get("filings") or {})
    recent = cast(Mapping[str, Any], filings.get("recent") or index)
    return cast(list[str], recent.get("acceptanceDateTime") or [])


def results_filings(index: Mapping[str, object]) -> list[tuple[date, str]]:
    """(filing date, acceptance stamp) per 8-K carrying item 2.02, oldest first.

    **The form gate is not optional.** `items` is an N.NN-shaped, comma-joined string on
    forms other than the 8-K, and ABS-15G's own numbering runs 1.01 .. 2.03: a shape-only
    match would eventually read an asset-backed due-diligence item as an earnings release.
    The component test matters too -- the field reads `2.02,9.01`, never `2.02` alone -- and
    an amendment is left out, because an 8-K/A restates a release the original already
    dated and counting it would put a second event a few days after a real one."""
    forms, dates, items = _items_of(index)
    stamps = _acceptance_of(index)
    out: list[tuple[date, str]] = []
    n = min(len(forms), len(dates), len(items))
    for i in range(n):
        if forms[i] != FORM or ITEM not in [part.strip() for part in items[i].split(",")]:
            continue
        try:
            filed = date.fromisoformat(dates[i])
        except ValueError:
            continue
        out.append((filed, stamps[i] if i < len(stamps) else ""))
    return sorted(out)


def filed_releases(cik: str, index: Mapping[str, object] | None, first: date, last: date,
                   user_agent: str) -> list[tuple[date, str]]:
    """Every item 2.02 filed in [first, last], across `recent` and the older pages.

    `filings.recent` is a year or a thousand filings, whichever is more, so for a heavy filer
    it is barely the year: reading only it would give the five biggest banks one year of
    cadence instead of five (67). One filing date is one release: a filer that files two
    accessions the same day has announced once, and counting both would halve its cadence."""
    import fetch_sec  # noqa: PLC0415

    if index is None:
        return []
    found = dict(results_filings(index))
    for name in fetch_sec.submissions_pages(index, first, last):
        try:
            page = fetch_sec.submissions_page(name, user_agent)
        except Exception:  # noqa: BLE001 - a page that will not come is a gap, named by the caller
            continue
        for filed, stamp in results_filings(page):
            found.setdefault(filed, stamp)
    return sorted((d, s) for d, s in found.items() if first <= d <= last)


def vendor_releases(ticker: Any, as_of: date) -> tuple[list[tuple[date, str]], date | None, str]:
    """The vendor's past release dates, its next one, and which of its two surfaces gave it.

    Three distinct states all mean no next date from the calendar and none may raise: the key
    absent from the dict, an empty list, and a list of two, which is an estimated RANGE rather
    than a confirmed day. A range is a projection by another name, and a projection presented
    as a vendor date would be a forecast wearing a vendor's clothes. The dated table is the
    second surface and carries future rows of its own; it is read only when the calendar is
    silent, and the record says which one answered.

    Every stamp in the table is localised to New York whatever the listing, so a release is
    dated by its New York calendar day. That is a conversion, not an identity: an evening
    release in Asia lands on the previous New York day."""
    past: list[tuple[date, str]] = []
    ahead: list[date] = []
    try:
        frame = ticker.get_earnings_dates(limit=40)
    except Exception:  # noqa: BLE001
        frame = None
    if frame is not None and len(frame) > 0:
        for stamp in frame.index:
            try:
                when = stamp.date()
            except AttributeError:
                continue
            if when <= as_of:
                past.append((when, str(stamp)))
            else:
                ahead.append(when)
    nxt: date | None = None
    try:
        calendar = cast(Mapping[str, object], ticker.get_calendar() or {})
        listed = calendar.get("Earnings Date")
    except Exception:  # noqa: BLE001
        listed = None
    source = "vendor calendar"
    if isinstance(listed, list) and len(cast(list[object], listed)) == 1:
        only = cast(list[object], listed)[0]
        if isinstance(only, date) and only > as_of:
            nxt = only
    if nxt is None and ahead:
        nxt, source = min(ahead), "vendor dated earnings table"
    return sorted(set(past)), nxt, source


def cadence_days(dates: list[date]) -> float | None:
    """The median interval of the last [EVENTS] releases, in calendar days.

    Recorded on the block whether or not it is used, because it is the reader's check that
    the cadence is quarterly: a filer that reports operating statistics under item 2.02 as
    well as results has twice the releases and half the interval, and the number says so."""
    recent = sorted(dates)[-EVENTS:]
    gaps = [(b - a).days for a, b in zip(recent, recent[1:]) if (b - a).days > 0]
    return statistics.median(gaps) if gaps else None


def project_next(dates: list[date], as_of: date) -> tuple[date, float] | None:
    """The last release plus the median interval, stepped forward until it is in the future."""
    if not dates:
        return None
    cadence = cadence_days(dates)
    if cadence is None or cadence <= 0:
        return None
    nxt = max(dates)
    for _ in range(40):
        nxt = nxt + timedelta(days=round(cadence))
        if nxt > as_of:
            return nxt, cadence
    return None


def session_of(stamp: str) -> str:
    """Whether a release landed after the close, before the open, or inside the session.

    It decides which two closes bracket it, and the two answers differ by a whole day: a
    release made after the close on D moves D to D+1, one made before the open on D moves
    D-1 to D. The index carries the acceptance time, so this is read rather than assumed."""
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return "after_close"            # the filed convention for a results 8-K, when unstamped
    hour = when.astimezone(timezone.utc).hour if when.tzinfo else when.hour
    if hour >= AFTER_CLOSE_UTC:
        return "after_close"
    if hour < BEFORE_OPEN_UTC:
        return "before_open"
    return "intraday"


def bracketing_closes(closes: Mapping[date, float], when: date, session: str
                      ) -> tuple[date, date] | None:
    """The two trading days the release sits between, on that session rule."""
    days = sorted(closes)
    if session == "after_close":
        before = [d for d in days if d <= when]
        after = [d for d in days if d > when]
    else:
        before = [d for d in days if d < when]
        after = [d for d in days if d >= when]
    if not before or not after:
        return None
    return before[-1], after[0]


def event_of(closes: Mapping[date, float], market: Mapping[date, float], when: date, session: str
             ) -> boundary.EarningsEvent | None:
    """One release's close-to-close move and the benchmark's over the same two dates.

    The closes are the vendor's own adjusted series, so their ratio is already split-
    corrected; multiplying by a split factor here would put the split jump back in."""
    pair = bracketing_closes(closes, when, session)
    if pair is None:
        return None
    before, after = pair
    if closes[before] <= 0:
        return None
    own = closes[after] / closes[before] - 1.0
    market_pair = bracketing_closes(market, when, session)
    if market_pair is None or market[market_pair[0]] <= 0:
        return None
    bench = market[market_pair[1]] / market[market_pair[0]] - 1.0
    return boundary.EarningsEvent(filed=when.isoformat(), before=before.isoformat(),
                                  after=after.isoformat(), own=own, benchmark=bench,
                                  excess=own - bench)


def history_of(symbol: str) -> Mapping[date, float]:
    """The vendor's closes, fetched once per symbol per process: the benchmark is read for
    every name in a universe fetch and one series serves them all."""
    import pit  # noqa: PLC0415

    if symbol not in _history:
        _history[symbol] = pit.History.fetch(symbol)
    return cast(Mapping[date, float], _history[symbol].closes)


def calendar_of(symbol: str, ticker: Any, as_of: date, *, cik: str | None = None,
                index: Mapping[str, object] | None = None, user_agent: str = "",
                ) -> tuple[boundary.EarningsCalendar | None, str | None]:
    """The release calendar, or the reason there is none.

    The filed path where the filer files item 2.02, the vendor's where it does not. That
    second case is wider than a name without a CIK: a foreign private issuer files 6-K and a
    trust files neither, so the fallback is keyed on the absence of a filed release rather
    than on the absence of a filer, and the record says which source it read and why."""
    first = as_of - timedelta(days=round(YEARS * 365.25))
    filed = filed_releases(cik, index, first, as_of, user_agent) if cik else []
    vendor_past, vendor_next, vendor_source = vendor_releases(ticker, as_of)   # one read, not two
    if filed:
        releases, past_source = filed, "SEC 8-K item 2.02"
        past_why = f"{len(filed)} item 2.02 filing(s) in the {YEARS} years to {as_of}"
    else:
        releases = [(d, s) for d, s in vendor_past if d >= first]
        past_source = "vendor"
        past_why = ("no CIK: the filer is on the vendor path" if cik is None
                    else f"CIK {cik} filed no 8-K item 2.02 in the {YEARS} years to {as_of}: "
                         "a foreign private issuer files 6-K, and a trust files neither")
    dates = [d for d, _ in releases]
    if vendor_next is not None:
        next_date, next_source, next_as_of = vendor_next, vendor_source, as_of.isoformat()
    else:
        projected = project_next(dates, as_of)
        if projected is None:
            return None, NO_CALENDAR
        next_date, next_source = projected[0], "filed cadence, projected"
        next_as_of = max(dates).isoformat()
    cadence = cadence_days(dates)

    closes = history_of(symbol)
    market = history_of(BENCHMARK)
    events = [e for d, stamp in releases[-EVENTS:]
              if (e := event_of(closes, market, d, session_of(stamp))) is not None]
    excesses = [abs(e.excess) for e in events]
    realised = statistics.median(excesses) if excesses else None
    realised_reason = None if excesses else (
        f"no release in the last {EVENTS} has a close on both sides of it in the vendor's history")
    return boundary.EarningsCalendar(
        past_source=past_source, past_source_why=past_why, past_count=len(dates),
        past_dates=[d.isoformat() for d in dates], next_date=next_date.isoformat(),
        next_source=next_source, next_source_as_of=next_as_of, cadence_days=cadence,
        events=events, realised_median_abs_excess=realised, realised_reason=realised_reason,
        benchmark=BENCHMARK, scope_limits=list(SCOPE_LIMITS)), None
