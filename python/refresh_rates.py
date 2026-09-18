"""Refresh sovereign risk-free curves in reference/risk_free_rates.json from their sources.

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
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

import reference

REPO_ROOT = Path(__file__).resolve().parent.parent
RATES_PATH = REPO_ROOT / "reference" / "risk_free_rates.json"
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


def parse_fred_series(body: bytes, series_id: str) -> tuple[date, float]:
    """The newest observation with a value from one FRED observations response."""
    try:
        parsed = Observations.model_validate_json(body)
    except ValidationError as e:
        raise RefreshError(f"{series_id}: unexpected FRED response: {e}") from e
    for observation in parsed.observations:  # newest first: sort_order=desc
        if observation.value != ".":
            return observation.date, _percent(observation.value, series_id)
    raise RefreshError(f"{series_id}: none of the last {len(parsed.observations)} observations has a value")


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


def parse_bundesbank_lines(body: bytes, what: str) -> tuple[date, float]:
    """Bundesbank REST CSV: `date;value;flags` rows after a metadata block; decimal comma."""
    latest: tuple[date, float] | None = None
    for line in body.decode("utf-8-sig").splitlines():
        parts = line.split(";")
        if len(parts) >= 2 and len(parts[0]) == 10 and parts[0][:4].isdigit() and parts[1].strip():
            latest = (date.fromisoformat(parts[0]), _percent(parts[1], what))
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
    table = reference.RiskFreeRates.from_json_string(RATES_PATH.read_text())
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
        write_atomically(RATES_PATH, text + "\n")
        print(f"\nwrote {len(fetched)} curve(s) to {RATES_PATH}")
    if failures:
        print(f"\n{len(failures)} country(ies) failed and were left untouched: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
