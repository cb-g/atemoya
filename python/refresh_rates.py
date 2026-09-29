"""Refresh sovereign risk-free curves in data/reference/risk_free_rates.json from their sources.

Nothing fetched from a provider is tracked (29): the file is gitignored, every user runs
this with their own FRED key before the first valuation, and a missing curve fails the
record naming this refresher.

    uv run python/refresh_rates.py --all
    uv run python/refresh_rates.py --country Brazil --country "South Korea"

reference/rate_sources.json is the registry: per country a tier (official, fred_oecd_10y,
manual), a parser, and what it provides. Each fetched entry is written with `source`,
`tier`, `as_of` (the observation date, or the period end of a monthly average), `rates`
keyed by the requested tenor, `tenor_used` where a tenor was substituted (the 7y taken from
a 10y is recorded, never silent), and `estimated` where a tenor is interpolated.

Every observation is validated before anything is written: rates as decimals inside
(-0.02, 0.40), an as_of neither in the future nor older than 90 days, every tenor the
registry claims present. A country that fails leaves its existing entry untouched; the file
is rewritten atomically once, with the successes, and the exit status is non-zero if any
requested country failed. Manual countries are reported, not fetched.

FRED_API_KEY comes from the environment or .env at the repo root, as before.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import io
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
from typing import cast
import urllib.request
from collections.abc import Callable, Mapping
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

import reference

REPO_ROOT = Path(__file__).resolve().parent.parent
RATES_PATH = REPO_ROOT / "data" / "reference" / "risk_free_rates.json"
REGISTRY_PATH = REPO_ROOT / "reference" / "rate_sources.json"
DOTENV_PATH = REPO_ROOT / ".env"
FRED_OBSERVATIONS = "https://api.stlouisfed.org/fred/series/observations"
PLAUSIBLE_RATE = (-0.02, 0.40)  # decimal per year; outside this the response is not trusted
MAX_OBSERVATION_AGE_DAYS = 90  # a "current" observation older than this is a broken parser, not data
USER_AGENT = "atemoya/0.1 (risk-free curve refresh)"
TENOR_ORDER = ("1y", "2y", "3y", "5y", "7y", "10y")


class RefreshError(Exception):
    """A fetch or parse that must not write anything."""


class Observation(BaseModel):
    """One row of a FRED observations response, untrusted until validated."""

    model_config = ConfigDict(frozen=True, strict=True)

    date: date
    value: str  # percent as text, or "." on a non-trading day


class Observations(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    observations: list[Observation]


class Fetched(BaseModel):
    """What a parser hands back: an observation date and decimal rates by requested tenor."""

    model_config = ConfigDict(frozen=True, strict=True)

    as_of: date
    rates: dict[str, float]
    estimated: list[str] = []
    tenor_used: dict[str, str] = {}
    notes: list[str] = []


# --- configuration ---------------------------------------------------------------------


def _api_key() -> str:
    key = os.environ.get("FRED_API_KEY", "")
    if not key and DOTENV_PATH.is_file():
        for line in DOTENV_PATH.read_text().splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and name.strip() == "FRED_API_KEY":
                key = value.strip().strip("'\"")
    if not key:
        raise RefreshError(
            "FRED_API_KEY is not set: put it in .env at the repo root (see .env.example) or export it"
        )
    return key


def _get(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as e:  # the URL may hold a key, so it is never echoed
        raise RefreshError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:200]}") from e
    except urllib.error.URLError as e:
        raise RefreshError(f"cannot reach the source: {e.reason}") from e


def _percent(text: str, what: str) -> float:
    try:
        return round(float(text.replace(",", ".")) / 100.0, 6)
    except ValueError as e:
        raise RefreshError(f"{what}: {text!r} is not a number") from e


def _month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


# --- parsers: pure functions of fetched text, tested on saved fixtures -------------------


def parse_fred_latest(body: bytes, series_id: str) -> tuple[date, str]:
    """The newest observation with a value from one FRED observations response, as text."""
    try:
        parsed = Observations.model_validate_json(body)
    except ValidationError as e:
        raise RefreshError(f"{series_id}: unexpected FRED response: {e}") from e
    for observation in parsed.observations:  # newest first: sort_order=desc
        if observation.value != ".":
            return observation.date, observation.value
    raise RefreshError(f"{series_id}: none of the last {len(parsed.observations)} observations has a value")


def parse_fred_series(body: bytes, series_id: str) -> tuple[date, float]:
    """The newest observation as a decimal rate (FRED quotes yields in percent)."""
    observed, text = parse_fred_latest(body, series_id)
    return observed, _percent(text, series_id)


def parse_boc_valet(body: bytes, series: Mapping[str, str]) -> Fetched:
    """Bank of Canada Valet JSON: the latest observation carrying every requested series."""
    try:
        observations = json.loads(body)["observations"]
    except (ValueError, KeyError, TypeError) as e:
        raise RefreshError(f"Valet: unexpected response: {e}") from e
    for obs in sorted(observations, key=lambda o: str(o.get("d", "")), reverse=True):  # newest first
        try:
            rates = {tenor: _percent(obs[sid]["v"], sid) for tenor, sid in series.items()}
            return Fetched(as_of=date.fromisoformat(obs["d"]), rates=rates)
        except (KeyError, TypeError):
            continue
    raise RefreshError("Valet: no observation carries every requested series")


def parse_ecb_yc(body: bytes, series: Mapping[str, str]) -> Fetched:
    """ECB SDMX CSV: one row per key and period; the latest period carrying every key."""
    by_period: dict[str, dict[str, float]] = {}
    key_to_tenor = {sid: tenor for tenor, sid in series.items()}
    for row in csv.DictReader(io.StringIO(body.decode("utf-8-sig"))):
        suffix = row.get("KEY", "").rsplit(".", 1)[-1]
        if suffix in key_to_tenor and row.get("OBS_VALUE"):
            by_period.setdefault(row["TIME_PERIOD"], {})[key_to_tenor[suffix]] = _percent(row["OBS_VALUE"], suffix)
    for period in sorted(by_period, reverse=True):
        if set(by_period[period]) == set(series):
            return Fetched(as_of=date.fromisoformat(period), rates=by_period[period])
    raise RefreshError("ECB: no period carries every requested tenor")


def parse_dst_statbank(body: bytes, what: str) -> tuple[date, float]:
    """Statistics Denmark StatBank BULK CSV: `TYPE;TID;INDHOLD` after a header row, the
    period as YYYYMmm and a decimal comma. The newest period wins; the series is a monthly
    average, so the caller dates it at that month's end."""
    latest: tuple[date, float] | None = None
    for line in body.decode("utf-8-sig").splitlines():
        cells = line.split(";")
        if len(cells) < 3 or not re.fullmatch(r"\d{4}M\d{2}", cells[-2].strip()):
            continue  # the header row, and any row whose period is not a month
        period = cells[-2].strip()
        observed = _month_end(date(int(period[:4]), int(period[5:]), 1))
        rate = _percent(cells[-1].strip(), what)
        if latest is None or observed > latest[0]:
            latest = (observed, rate)
    if latest is None:
        raise RefreshError(f"StatBank: no monthly observation for {what}")
    return latest


BUNDESBANK_MISSING = "."  # the Bundesbank's marker for a day with no observation (a holiday, a gap)


def parse_bundesbank_lines(body: bytes, what: str) -> tuple[date, float]:
    """Bundesbank REST CSV: `date;value;flags` rows after a metadata block; decimal comma.
    A row whose value is the placeholder `.` is a day the Bundesbank published no
    observation for (the response ran to a holiday on 2026-09-29 and the whole refresh
    fell over on it); such rows are skipped and the newest numeric observation is the one
    returned, still subject to the caller's age check."""
    latest: tuple[date, float] | None = None
    for line in body.decode("utf-8-sig").splitlines():
        parts = line.split(";")
        if len(parts) < 2 or len(parts[0]) != 10 or not parts[0][:4].isdigit():
            continue
        value = parts[1].strip()
        if not value or value == BUNDESBANK_MISSING:
            continue
        latest = (date.fromisoformat(parts[0]), _percent(value, what))
    if latest is None:
        raise RefreshError(f"{what}: no dated observation in the response")
    return latest


def parse_mof_jgb(body: bytes, series: Mapping[str, str]) -> Fetched:
    """Japan MoF CSV: a title line, a header (Date,1Y,2Y,...), then dated rows YYYY/M/D."""
    lines = body.decode("utf-8", "replace").splitlines()
    header_index = next((i for i, l in enumerate(lines) if l.startswith("Date,")), None)
    if header_index is None:
        raise RefreshError("MoF: no header row starting with Date")
    columns = lines[header_index].split(",")
    latest: Fetched | None = None
    for line in lines[header_index + 1 :]:
        cells = line.split(",")
        if len(cells) < len(columns) or not cells[0][:4].isdigit():
            continue
        row = dict(zip(columns, cells))
        try:
            rates = {tenor: _percent(row[col], col) for tenor, col in series.items()}
        except (KeyError, RefreshError):
            continue
        latest = Fetched(as_of=datetime.strptime(cells[0], "%Y/%m/%d").date(), rates=rates)
    if latest is None:
        raise RefreshError("MoF: no complete dated row")
    return latest


def _brazil_day(text: str) -> date:
    return datetime.strptime(text, "%d/%m/%Y").date()


def parse_tesouro_direto(body: bytes, tenors: list[str]) -> Fetched:
    """Tesouro Nacional CSV: on the latest base date, the fixed-rate bonds (Tesouro Prefixado,
    with and without coupons) give (years to maturity, mid yield) points; each requested
    tenor is linearly interpolated between the two bracketing bonds and marked estimated."""
    rows = list(csv.DictReader(io.StringIO(body.decode("latin-1")), delimiter=";"))
    fixed = [r for r in rows if r.get("Tipo Titulo", "").startswith("Tesouro Prefixado")]
    if not fixed:
        raise RefreshError("Tesouro Direto: no fixed-rate bond rows")
    base = max(_brazil_day(r["Data Base"]) for r in fixed)
    points: list[tuple[float, float]] = []
    for r in fixed:
        if _brazil_day(r["Data Base"]) != base:
            continue
        years = (_brazil_day(r["Data Vencimento"]) - base).days / 365.25
        mid = (_percent(r["Taxa Compra Manha"], "compra") + _percent(r["Taxa Venda Manha"], "venda")) / 2
        points.append((years, mid))
    points.sort()
    rates: dict[str, float] = {}
    for tenor in tenors:
        target = float(tenor.rstrip("y"))
        below = [p for p in points if p[0] <= target]
        above = [p for p in points if p[0] >= target]
        if not below or not above:
            raise RefreshError(f"Tesouro Direto: no bonds bracket the {tenor} tenor on {base}")
        (y0, r0), (y1, r1) = below[-1], above[0]
        rates[tenor] = round(r0 if y1 == y0 else r0 + (r1 - r0) * (target - y0) / (y1 - y0), 6)
    return Fetched(as_of=base, rates=rates, estimated=list(tenors),
                   notes=[f"interpolated from {len(points)} fixed-rate bonds on the mid of the morning buy and sell yields"])


# --- fetchers: one per registry parser -------------------------------------------------


def fetch_fred_dgs(rule: reference.RateSource) -> Fetched:
    key = _api_key()
    points: dict[str, tuple[date, float]] = {}
    for tenor, series_id in rule.series:
        query = urllib.parse.urlencode(
            {"series_id": series_id, "api_key": key, "file_type": "json", "sort_order": "desc", "limit": 5}
        )
        points[tenor] = parse_fred_series(_get(f"{FRED_OBSERVATIONS}?{query}"), series_id)
    dates = sorted({observed for observed, _ in points.values()})
    notes = (
        ["tenors observed on different dates: " + ", ".join(f"{t} {d.isoformat()}" for t, (d, _) in points.items())]
        if len(dates) > 1 else []
    )
    return Fetched(as_of=dates[0], rates={t: r for t, (_, r) in points.items()}, notes=notes)


def fetch_fred_oecd_10y(rule: reference.RateSource) -> Fetched:
    key = _api_key()
    series = dict(rule.series)
    series_id = series["10y"]
    query = urllib.parse.urlencode(
        {"series_id": series_id, "api_key": key, "file_type": "json", "sort_order": "desc", "limit": 3}
    )
    observed, rate = parse_fred_series(_get(f"{FRED_OBSERVATIONS}?{query}"), series_id)
    return _substituted(Fetched(as_of=_month_end(observed), rates={"10y": rate},
                                notes=[f"monthly average for {observed.strftime('%B %Y')}; as_of is that month's end"]), rule)


def _substituted(fetched: Fetched, rule: reference.RateSource) -> Fetched:
    """Fill requested tenors from the registry's substitution map, recording each one."""
    rates, used = dict(fetched.rates), dict(fetched.tenor_used)
    for requested, available in rule.substitute:
        if requested not in rates and available in rates:
            rates[requested] = rates[available]
            used[requested] = available
    return fetched.model_copy(update={"rates": rates, "tenor_used": used})


def _post(url: str, data: Mapping[str, str], timeout: int = 60) -> bytes:
    """A form POST; the one source that answers nothing to a GET is ChinaBond (75)."""
    body = urllib.parse.urlencode(dict(data)).encode()
    request = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as e:
        raise RefreshError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:200]}") from e
    except urllib.error.URLError as e:
        raise RefreshError(f"cannot reach the source: {e.reason}") from e


def parse_chinabond_czb(body: bytes, curve_id: str, tenors: list[str]) -> Fetched:
    """(75) ChinaBond's yield-curve answer: a list of curves, each with its id, its name, the
    date it is for and `seriesData`, pairs of (years, yield in per cent) on a fine grid that
    carries every whole-year tenor. The curve is picked by id; a requested tenor the grid
    does not carry is an error, never an interpolation."""
    raw = cast(object, json.loads(body.decode("utf-8")))
    listed: list[object] = cast(list[object], raw) if isinstance(raw, list) else []
    curves = [cast(Mapping[str, object], c) for c in listed if isinstance(c, dict) and str(cast(Mapping[str, object], c).get("ycDefId")) == curve_id]
    if not curves:
        raise RefreshError(f"ChinaBond: curve {curve_id} not in the answer ({len(listed)} curve(s))")
    curve = curves[0]
    try:
        observed = date.fromisoformat(str(curve["worktime"])[:10])
        grid = {float(cast(float, x)): float(cast(float, y)) for x, y in cast(list[tuple[object, object]], curve["seriesData"])}
    except (KeyError, TypeError, ValueError) as e:
        raise RefreshError(f"ChinaBond: malformed curve: {e}") from e
    rates: dict[str, float] = {}
    for tenor in tenors:
        years = float(tenor[:-1])
        if years not in grid:
            raise RefreshError(f"ChinaBond: the grid carries no {tenor} point")
        rates[tenor] = round(grid[years] / 100.0, 6)
    return Fetched(as_of=observed, rates=rates, notes=[f"ChinaBond curve {curve.get('ycDefName', '')} for {observed.isoformat()}"])


def fetch_chinabond_czb(rule: reference.RateSource) -> Fetched:
    """(75) China. China Central Depository & Clearing publishes the China Government Bond
    yield curve at yield.chinabond.com.cn; the chart's own endpoint answers a form POST,
    keyless, with the latest day's curve on a grid of years."""
    series = dict(rule.series)
    return parse_chinabond_czb(_post(rule.url, {"locale": "en_US"}), series["curve"], list(rule.tenors))


MAS_TENORS = {"6-Mth": "6m", "1-Year": "1y", "2-Year": "2y", "5-Year": "5y", "10-Year": "10y", "15-Year": "15y", "20-Year": "20y", "30-Year": "30y", "50-Year": "50y"}


def parse_mas_sgs_html(body: bytes, tenors: list[str]) -> Fetched:
    """(77) MAS's own Daily SGS Prices page, server-rendered: the closing-levels table has a
    row of benchmark tenors, a row saying which cells are prices and which yields (a bill
    carries a yield alone, a bond a price then a yield), and a dated row per business day.
    The newest dated row is the observation; a requested tenor the table does not carry
    is an error, never an interpolation."""
    import html as html_mod
    import re

    page = body.decode("utf-8", errors="replace")
    table = re.search(r'<table[^>]*id="ContentPlaceHolder1_ClosingLevelsTable".*?</table>', page, re.S)
    if table is None:
        raise RefreshError("MAS: the closing-levels table is not on the page")
    rows: list[list[str]] = []
    for tr in re.findall(r"<tr.*?</tr>", table.group(0), re.S):
        cells = [re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        rows.append(cells)
    tenor_row = next((r for r in rows if len(r) > 2 and r[1] in MAS_TENORS), None)
    kind_row = next((r for r in rows if r and set(r) <= {"Yield", "Price"}), None)
    dated = [r for r in rows if r and re.fullmatch(r"\d{1,2} [A-Z][a-z]{2} \d{4}", r[0])]
    if tenor_row is None or kind_row is None or not dated:
        raise RefreshError("MAS: the closing-levels table has not the shape this parser reads (tenor row, kind row, dated rows)")
    # which value cell carries each tenor's yield
    yield_at: dict[str, int] = {}
    i = 0
    for label in tenor_row[1:]:
        if i >= len(kind_row):
            break
        if kind_row[i] == "Price":
            yield_at[label] = i + 1
            i += 2
        else:
            yield_at[label] = i
            i += 1
    latest = max(dated, key=lambda r: datetime.strptime(r[0], "%d %b %Y"))
    observed = datetime.strptime(latest[0], "%d %b %Y").date()
    values = latest[1:]
    by_tenor = {MAS_TENORS[label]: values[idx] for label, idx in yield_at.items() if label in MAS_TENORS and idx < len(values)}
    rates: dict[str, float] = {}
    for tenor in tenors:
        if tenor not in by_tenor:
            raise RefreshError(f"MAS: the table carries no {tenor} benchmark")
        rates[tenor] = _percent(by_tenor[tenor], f"MAS {tenor}")
    return Fetched(as_of=observed, rates=rates, notes=[f"MAS Daily SGS Prices, closing yields of the benchmark issues for {observed.isoformat()}"])


def fetch_mas_sgs_html(rule: reference.RateSource) -> Fetched:
    """(77) Singapore. MAS's API gateway needs a registered corporate account and its portal
    is closed to a foreign individual, but MAS's own statistics page renders the benchmark
    closing yields server-side, keyless; that page is the official source."""
    requested = [t for t in rule.tenors if not any(t == r for r, _ in rule.substitute)]
    return _substituted(parse_mas_sgs_html(_get(rule.url), requested), rule)


HKGB_TENORS = {"1-year": "1y", "3-year": "3y", "5-year": "5y", "7-year": "7y", "10-year": "10y", "15-year": "15y", "20-year": "20y"}


def hkgb_benchmark_rows(body: bytes, sheet: str) -> list[list[object]]:
    """(78) The Government Bond Programme's daily closing-pricings workbook, a binary Excel
    file; the benchmark sheet's cells, row by row, for the pure parser below. A date cell
    is rendered as an ISO date, everything else as the cell's own value."""
    import xlrd  # the one binary-Excel source in the registry

    book = xlrd.open_workbook(file_contents=body)
    names = book.sheet_names()
    if sheet not in names:
        raise RefreshError(f"HKGB: sheet {sheet!r} is not in the workbook ({', '.join(names)})")
    ws = book.sheet_by_name(sheet)
    rows: list[list[object]] = []
    for r in range(ws.nrows):
        row: list[object] = []
        for c in range(ws.ncols):
            cell = ws.cell(r, c)
            if cell.ctype == xlrd.XL_CELL_DATE:
                row.append(xlrd.xldate_as_datetime(float(cell.value), book.datemode).date().isoformat())
            else:
                row.append(cell.value)
        rows.append(row)
    return rows


def parse_hkgb_rows(rows: list[list[object]], tenors: list[str]) -> Fetched:
    """(78) The benchmark sheet: a `Tenor` row naming the benchmarks (each over a price
    column and a yield column), then one dated row per business day with a price and a
    yield per benchmark. The newest dated row is the observation; a requested tenor the
    sheet does not carry, or one whose yield is not a number (the one-year is a floating
    rate note quoted at par with no yield), is an error, never an interpolation."""
    tenor_row = next((r for r in rows if r and str(r[0]).strip().lower() == "tenor"), None)
    if tenor_row is None:
        raise RefreshError("HKGB: the benchmark sheet has no Tenor row")
    columns: dict[str, int] = {}
    for c, cell in enumerate(tenor_row):
        label = str(cell).strip().rstrip("*").lower()
        if label in HKGB_TENORS:
            columns[HKGB_TENORS[label]] = c + 1  # the yield sits right of the price under each tenor
    dated: list[tuple[date, list[object]]] = []
    for r in rows:
        stamp = str(r[0]).strip() if r else ""
        try:
            dated.append((date.fromisoformat(stamp[:10]), r))
        except ValueError:
            continue
    if not dated:
        raise RefreshError("HKGB: the benchmark sheet has no dated row")
    observed, latest = max(dated, key=lambda x: x[0])
    rates: dict[str, float] = {}
    for tenor in tenors:
        c = columns.get(tenor)
        if c is None or c >= len(latest):
            raise RefreshError(f"HKGB: the benchmark sheet carries no {tenor} column")
        rates[tenor] = _percent(str(latest[c]), f"HKGB {tenor}")
    return Fetched(as_of=observed, rates=rates, notes=[f"HKGB Closing Reference Pricings for {observed.isoformat()}, the Government of the Hong Kong SAR the owner"])


def fetch_hkgb_xls(rule: reference.RateSource) -> Fetched:
    """(78) Hong Kong. The Government Bond Programme publishes the institutional bonds'
    closing reference pricings daily as a workbook, keyless; the HKMA open API stops at
    three-year Exchange Fund Notes and carries no bond yields."""
    series = dict(rule.series)
    requested = [t for t in rule.tenors if not any(t == r for r, _ in rule.substitute)]
    return _substituted(parse_hkgb_rows(hkgb_benchmark_rows(_get(rule.url), series["sheet"]), requested), rule)


def fetch_dst_statbank(rule: reference.RateSource) -> Fetched:
    """(65) Denmark. Danmarks Nationalbank's statistics are served through Statistics
    Denmark's StatBank, keyless; table MPK3 carries the ten-year central government bond
    redemption yield and nothing shorter, so the seven-year is substituted and recorded,
    exactly as the OECD monthly tier does."""
    series = dict(rule.series)
    observed, rate = parse_dst_statbank(_get(rule.url), series["10y"])
    return _substituted(
        Fetched(as_of=observed, rates={"10y": rate},
                notes=[f"monthly average for {observed.strftime('%B %Y')}; as_of is that month's end"]), rule)


def fetch_boc_valet(rule: reference.RateSource) -> Fetched:
    series = dict(rule.series)
    url = rule.url.format(series=",".join(series.values()))
    return parse_boc_valet(_get(url), series)


def fetch_ecb_yc(rule: reference.RateSource) -> Fetched:
    series = dict(rule.series)
    url = rule.url.format(series="+".join(series.values()))
    return parse_ecb_yc(_get(url), series)


def fetch_bundesbank_bbsis(rule: reference.RateSource) -> Fetched:
    points = {tenor: parse_bundesbank_lines(_get(rule.url.format(series=sid)), sid) for tenor, sid in rule.series}
    dates = sorted({d for d, _ in points.values()})
    notes = (
        ["tenors observed on different dates: " + ", ".join(f"{t} {d.isoformat()}" for t, (d, _) in points.items())]
        if len(dates) > 1 else []
    )
    return Fetched(as_of=dates[0], rates={t: r for t, (_, r) in points.items()}, notes=notes)


def fetch_mof_jgb(rule: reference.RateSource) -> Fetched:
    return parse_mof_jgb(_get(rule.url), dict(rule.series))


def fetch_tesouro_direto(rule: reference.RateSource) -> Fetched:
    return parse_tesouro_direto(_get(rule.url, timeout=180), list(rule.tenors))


FETCHERS: dict[str, Callable[[reference.RateSource], Fetched]] = {
    "fred_dgs": fetch_fred_dgs,
    "fred_oecd_10y": fetch_fred_oecd_10y,
    "boc_valet": fetch_boc_valet,
    "dst_statbank": fetch_dst_statbank,
    "chinabond_czb": fetch_chinabond_czb,
    "mas_sgs_html": fetch_mas_sgs_html,
    "hkgb_xls": fetch_hkgb_xls,
    "ecb_yc": fetch_ecb_yc,
    "bundesbank_bbsis": fetch_bundesbank_bbsis,
    "mof_jgb": fetch_mof_jgb,
    "tesouro_direto": fetch_tesouro_direto,
}


# --- validation and writing -------------------------------------------------------------


def validate(fetched: Fetched, rule: reference.RateSource, today: date) -> None:
    """Reject before anything is written; the reason names the offending value."""
    if fetched.as_of > today:
        raise RefreshError(f"as_of {fetched.as_of} is in the future")
    if (today - fetched.as_of).days > MAX_OBSERVATION_AGE_DAYS:
        raise RefreshError(
            f"as_of {fetched.as_of} is {(today - fetched.as_of).days} days old; a current observation "
            f"older than {MAX_OBSERVATION_AGE_DAYS} days is a broken parser, not data"
        )
    missing = [t for t in rule.tenors if t not in fetched.rates]
    if missing:
        raise RefreshError(f"missing tenor(s) the registry claims: {', '.join(missing)}")
    for tenor, rate in fetched.rates.items():
        if not PLAUSIBLE_RATE[0] < rate < PLAUSIBLE_RATE[1]:
            raise RefreshError(f"{tenor} rate {rate:.4%} is outside the plausible range")


def to_curve(fetched: Fetched, rule: reference.RateSource) -> reference.Curve:
    ordered = sorted(fetched.rates, key=lambda t: TENOR_ORDER.index(t) if t in TENOR_ORDER else 99)
    return reference.Curve(
        source=rule.source,
        tier=rule.tier,
        as_of=fetched.as_of.isoformat(),
        rates=[(t, fetched.rates[t]) for t in ordered],
        estimated=list(fetched.estimated),
        tenor_used=sorted(fetched.tenor_used.items()),
        notes=list(fetched.notes),
    )


def write_atomically(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def refresh(country: str, rule: reference.RateSource, table: reference.RiskFreeRates,
            fetched_so_far: dict[str, reference.Curve], today: date) -> reference.Curve:
    if rule.parser == "proxy":
        base = fetched_so_far.get(rule.proxy_of) or dict(table.countries).get(rule.proxy_of)
        if base is None:
            raise RefreshError(f"proxy of {rule.proxy_of}, which has no curve")
        return reference.Curve(
            source=rule.source, tier=rule.tier, as_of=base.as_of, rates=list(base.rates),
            estimated=list(base.estimated), tenor_used=list(base.tenor_used),
            notes=[f"copied from the {rule.proxy_of} entry"])
    fetcher = FETCHERS.get(rule.parser)
    if fetcher is None:
        raise RefreshError(f"no fetcher for parser {rule.parser!r}")
    fetched = fetcher(rule)
    validate(fetched, rule, today)
    return to_curve(fetched, rule)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--country", action="append", default=[], help="a country in the registry; repeatable")
    parser.add_argument("--all", action="store_true", help="every non-manual country in the registry")
    args = parser.parse_args(argv)
    wanted: list[str] = list(args.country)
    do_all: bool = args.all
    registry = reference.RateSources.from_json_string(REGISTRY_PATH.read_text())
    table = (reference.RiskFreeRates.from_json_string(RATES_PATH.read_text()) if RATES_PATH.exists()
             else reference.RiskFreeRates(max_age_days=registry.max_age_days, tenors=registry.tenors, aliases=registry.aliases, countries=[],
                                          notes=["written by python/refresh_rates.py from the sources in rate_sources.json; fetched data, never tracked"]))
    rules = dict(registry.countries)
    if do_all:
        wanted = list(rules)
    if not wanted:
        parser.error("give --country NAME (repeatable) or --all")
    unknown = [c for c in wanted if c not in rules]
    if unknown:
        parser.error(f"not in {REGISTRY_PATH}: {', '.join(unknown)}")

    today = date.today()
    fetched: dict[str, reference.Curve] = {}
    failures: list[str] = []
    # proxies last, so they can copy a fresh base
    for country in sorted(wanted, key=lambda c: rules[c].parser == "proxy"):
        rule = rules[country]
        if rule.parser == "manual":
            existing = dict(table.countries).get(country)
            age = f"as_of {existing.as_of}" if existing else "no entry"
            print(f"{country:24s} manual       {age}; {rule.notes[0] if rule.notes else 'refresh by hand'}")
            continue
        try:
            curve = refresh(country, rule, table, fetched, today)
        except RefreshError as e:
            failures.append(country)
            print(f"{country:24s} FAILED       {rule.parser}: {e}", file=sys.stderr)
            continue
        fetched[country] = curve
        subs = ", ".join(f"{r}<-{u}" for r, u in curve.tenor_used)
        print(
            f"{country:24s} {curve.tier:12s} as_of {curve.as_of}  "
            + ", ".join(f"{t} {r:.2%}" for t, r in curve.rates)
            + (f"  [{subs}]" if subs else "")
            + ("  (interpolated)" if curve.estimated else "")
        )

    if fetched:
        kept = [(c, v) for c, v in table.countries if c not in fetched]
        table.countries = sorted(fetched.items()) + kept
        table.countries.sort(key=lambda cv: (cv[0] != "United States", cv[0]))
        text = table.to_json_string(indent=2, allow_nan=False, ensure_ascii=False)
        reference.RiskFreeRates.from_json_string(text)  # parse-time type check of what we write
        RATES_PATH.parent.mkdir(parents=True, exist_ok=True)
        write_atomically(RATES_PATH, text + "\n")
        print(f"\nwrote {len(fetched)} curve(s) to {RATES_PATH}")
    if failures:
        print(f"\n{len(failures)} country(ies) failed and were left untouched: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
