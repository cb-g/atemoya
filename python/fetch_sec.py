"""SEC XBRL companyfacts as a statements provider: filed 10-K or 20-F facts under us-gaap
or ifrs-full, canonical tags chosen per fiscal period from that taxonomy's section of
reference/xbrl_tags.json; cash, total debt, the change in working capital and ebit
assembled per reference/field_definitions.json, the one definition both providers follow,
with the components recorded on every period. The statement currency is the unit the
facts carry (recorded as financial_currency; the vendor's is recorded beside it and the
valuation refuses a disagreement).

    uv run python/fetch_sec.py ALL MET PGR       ->  the same routed fetch as fetch.py

fetch.py decides per ticker whether a name is XBRL-primary (its CIK resolves exactly in
SEC's ticker map and its facts carry annual net income and equity on an annual form under
us-gaap, else under ifrs-full) and calls into here for the statements. companyfacts JSON is cached under
data/sec/ for a day; requests are spaced to stay well under SEC's rate guidance; the whole
SEC_EDGAR_IDENTITY string is sent verbatim as the User-Agent.
"""

from __future__ import annotations

import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import cast

from pydantic import BaseModel, ConfigDict, ValidationError

import boundary
import reference

REPO_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = REPO_ROOT / ".env"
CACHE_DIR = REPO_ROOT / "data" / "sec"
TAGS_PATH = REPO_ROOT / "reference" / "xbrl_tags.json"
DEFINITIONS_PATH = REPO_ROOT / "reference" / "field_definitions.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ANNUAL_SUBMISSION_FORMS = ("10-K", "20-F")  # the original annual filings; amendments and 40-Fs are not
PROVIDER = "SEC XBRL companyfacts"
TAXONOMIES = ("us-gaap", "ifrs-full")  # in order of preference when a filer carries both
CACHE_SECONDS = 86400
MIN_SPACING_SECONDS = 0.25  # 4 requests per second, under SEC's 10/s guidance
PERIODS = 5

_last_request = 0.0


class Fact(BaseModel):
    """One companyfacts entry, untrusted until validated."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    end: date
    start: date | None = None
    val: float
    form: str
    fp: str
    filed: date
    accn: str


def identity() -> str:
    value = os.environ.get("SEC_EDGAR_IDENTITY", "")
    if not value and DOTENV_PATH.is_file():
        for line in DOTENV_PATH.read_text().splitlines():
            name, sep, rest = line.strip().partition("=")
            if sep and name.strip() == "SEC_EDGAR_IDENTITY":
                value = rest.strip().strip("'\"")
    if "@" not in value:
        sys.exit(
            "SEC_EDGAR_IDENTITY is not set or has no contact email. Put "
            '"<name> <email>" in .env at the repo root (see .env.example); nothing was fetched.'
        )
    return value


def load_tags() -> reference.XbrlTags:
    return reference.XbrlTags.from_json_string(TAGS_PATH.read_text())


def load_definitions() -> reference.FieldDefinitions:
    return reference.FieldDefinitions.from_json_string(DEFINITIONS_PATH.read_text())


def _get(url: str, user_agent: str) -> bytes:
    global _last_request
    wait = MIN_SPACING_SECONDS - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read()
            return gzip.decompress(body) if response.headers.get("Content-Encoding") == "gzip" else body
    finally:
        _last_request = time.monotonic()


def _cached(path: Path, url: str, user_agent: str) -> bytes:
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_SECONDS:
        return path.read_bytes()
    body = _get(url, user_agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def tickers_table(user_agent: str) -> dict[str, object]:
    return json.loads(_cached(CACHE_DIR / "company_tickers.json", TICKERS_URL, user_agent))


def cik_for(symbol: str, table: Mapping[str, object]) -> str | None:
    """Exact ticker match on SEC's company_tickers.json; "ALV.DE" is not "ALV" (Autoliv)."""
    for entry in table.values():
        if isinstance(entry, dict) and str(entry.get("ticker", "")).upper() == symbol.upper():  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            return str(entry["cik_str"]).zfill(10)  # pyright: ignore[reportUnknownArgumentType]
    return None


def companyfacts(cik: str, user_agent: str) -> dict[str, object] | None:
    """The filer's facts, cached for a day; None when SEC has no companyfacts for the CIK."""
    try:
        return json.loads(_cached(CACHE_DIR / f"CIK{cik}.json", FACTS_URL.format(cik=cik), user_agent))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def submissions(cik: str, user_agent: str) -> dict[str, object] | None:
    """The filer's submissions index, cached for a day; None when SEC has none for the CIK."""
    try:
        return json.loads(_cached(CACHE_DIR / f"submissions-CIK{cik}.json", SUBMISSIONS_URL.format(cik=cik), user_agent))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def latest_annual_submission(index: Mapping[str, object] | None) -> tuple[boundary.Submission | None, str | None]:
    """The newest 10-K or 20-F in filings.recent, or None with the reason."""
    if index is None:
        return None, "submissions: not found (HTTP 404)"
    recent = _as_dict(_as_dict(index.get("filings")).get("recent"))
    columns = {name: cast(list[object], recent[name]) for name in ("form", "filingDate", "accessionNumber", "reportDate") if isinstance(recent.get(name), list)}
    if len(columns) < 4:
        return None, "submissions: filings.recent carries no form, filingDate, accessionNumber and reportDate columns"
    best: boundary.Submission | None = None
    for form, filed, accession, report in zip(columns["form"], columns["filingDate"], columns["accessionNumber"], columns["reportDate"]):
        if str(form) not in ANNUAL_SUBMISSION_FORMS:
            continue
        try:
            _ = (date.fromisoformat(str(filed)), date.fromisoformat(str(report)))
        except ValueError:
            continue
        candidate = boundary.Submission(form=str(form), filing_date=str(filed), accession=str(accession), report_date=str(report))
        if best is None or candidate.filing_date > best.filing_date:
            best = candidate
    if best is None:
        return None, f"submissions: no {' or '.join(ANNUAL_SUBMISSION_FORMS)} in filings.recent"
    return best, None


# --- annual facts and per-period tag selection ------------------------------------------


def annual_facts(entries: Iterable[object], *, instant: bool, tags: reference.XbrlTags, notes: list[str], tag: str) -> dict[date, Fact]:
    """The latest-filed annual fact per fiscal year end: annual-form facts marked FY whose
    duration spans about a year (or, for balances, carry no start)."""
    lo, hi = tags.annual_span_days
    out: dict[date, Fact] = {}
    rejected = 0
    for raw in entries:
        try:
            fact = Fact.model_validate(raw)
        except ValidationError:
            rejected += 1
            continue
        if fact.form not in tags.annual_forms or fact.fp != "FY":
            continue
        if instant:
            if fact.start is not None:
                continue
        elif fact.start is None or not (lo <= (fact.end - fact.start).days <= hi):
            continue
        if fact.end not in out or fact.filed > out[fact.end].filed:
            out[fact.end] = fact
    if rejected:
        notes.append(f"{tag}: {rejected} companyfacts entries rejected at validation")
    return out


def taxonomy_fields(tags: reference.XbrlTags, taxonomy: str) -> list[tuple[str, reference.XbrlField]]:
    return tags.ifrs_full_fields if taxonomy == "ifrs-full" else tags.fields


def select(gaap: Mapping[str, object], tags: reference.XbrlTags, notes: list[str], *, taxonomy: str = "us-gaap", unit: str = "USD") -> dict[str, dict[date, tuple[Fact, str]]]:
    """Per canonical field, per fiscal year end: the first candidate tag with an annual fact
    in the filer's unit."""
    out: dict[str, dict[date, tuple[Fact, str]]] = {}
    for field, spec in taxonomy_fields(tags, taxonomy):
        per_end: dict[date, tuple[Fact, str]] = {}
        for tag in spec.tags:
            entries = _entries(gaap.get(tag), unit)
            if not entries:
                continue
            for end, fact in annual_facts(entries, instant=spec.kind == "instant", tags=tags, notes=notes, tag=tag).items():
                per_end.setdefault(end, (fact, tag))
        out[field] = per_end
    return out


Selected = Mapping[str, Mapping[date, tuple[Fact, str]]]


def value_of(selected: Selected, field: str, end: date) -> tuple[float | None, str | None]:
    hit = selected.get(field, {}).get(end)
    return (hit[0].val, hit[1]) if hit else (None, None)


def depreciation(selected: Selected, tags: reference.XbrlTags, end: date) -> tuple[float | None, str | None]:
    value, row = value_of(selected, "depreciation_amortization", end)
    if value is not None:
        return value, row
    parts: list[tuple[float, str]] = []
    for i, field in enumerate(tags.depreciation_components):
        v, r = value_of(selected, field, end)
        if v is None:
            if i == 0:
                return None, None
            continue
        parts.append((v, r or field))
    if not parts:
        return None, None
    return sum(v for v, _ in parts), " + ".join(r for _, r in parts)


class Facts:
    """A filer's us-gaap facts with annual selection per tag, memoised, for the fields
    reference/field_definitions.json assembles from more than one tag."""

    def __init__(self, gaap: Mapping[str, object], tags: reference.XbrlTags, notes: list[str], *, unit: str = "USD") -> None:
        self._gaap = gaap
        self._tags = tags
        self._notes = notes
        self._unit = unit
        self._memo: dict[tuple[str, bool], dict[date, Fact]] = {}

    def annual(self, tag: str, *, instant: bool) -> dict[date, Fact]:
        key = (tag, instant)
        if key not in self._memo:
            entries = _entries(self._gaap.get(tag), self._unit)
            self._memo[key] = annual_facts(entries, instant=instant, tags=self._tags, notes=self._notes, tag=tag)
        return self._memo[key]

    def at(self, tag: str, end: date, *, instant: bool) -> float | None:
        fact = self.annual(tag, instant=instant).get(end)
        return None if fact is None else fact.val

    def first(self, candidates: Iterable[str], end: date, *, instant: bool) -> tuple[float, str] | None:
        for tag in candidates:
            value = self.at(tag, end, instant=instant)
            if value is not None:
                return value, tag
        return None

    def duration_tags_with_prefix(self, prefix: str, end: date) -> list[str]:
        """Every tag with the prefix that carries an annual duration fact at [end]."""
        return sorted(tag for tag in self._gaap if tag.startswith(prefix) and self.at(tag, end, instant=False) is not None)

    def sum_present(self, name: str, tags: Iterable[str], end: date, *, instant: bool) -> list[boundary.Component]:
        """Every tag of the alternative that is present, as components."""
        return [boundary.Component(name=name, value=v, row=t) for t in tags if (v := self.at(t, end, instant=instant)) is not None]


def _composition(definition: str, parts: list[boundary.Component]) -> boundary.Composition:
    return boundary.Composition(definition=definition, components=parts)


SUBTRACTED = frozenset({"restricted_cash", "liability_components", "interest_income", "other_nonoperating", "equity_method", "cash_flow_signed_components", "gain_on_property_sales"})  # components summed with their sign flipped


def _label(parts: list[boundary.Component]) -> str:
    """The row label: tags joined with the sign each entered the sum with."""
    out = ""
    for i, part in enumerate(parts):
        sign = "-" if part.name in SUBTRACTED else "+"
        if i == 0:
            out = ("-" if sign == "-" else "") + part.row
        else:
            out += f" {sign} {part.row}"
    return out


Derived = tuple[float | None, str | None, boundary.Composition | None]


def cash(facts: Facts, defs: reference.FieldDefinitions, end: date) -> Derived:
    """Cash and equivalents (less the restricted components when only the restricted-inclusive
    total is tagged) plus the first present short-term investments tag."""
    d = defs.cash.xbrl
    equivalents = facts.first(d.cash_equivalents, end, instant=True)
    if equivalents is None:
        return None, None, None
    value, tag = equivalents
    parts = [boundary.Component(name="cash_equivalents", value=value, row=tag)]
    if tag in d.restricted_inclusive:
        for alternative in d.restricted_cash:
            found = [(facts.at(t, end, instant=True), t) for t in alternative]
            if all(v is not None for v, _ in found):
                parts.extend(boundary.Component(name="restricted_cash", value=-v, row=t) for v, t in found if v is not None)
                break
    investments = facts.first(d.short_term_investments, end, instant=True)
    if investments is not None:
        parts.append(boundary.Component(name="short_term_investments", value=investments[0], row=investments[1]))
    return sum(p.value for p in parts), _label(parts), _composition(defs.cash.name, parts)


def cash_ifrs(facts: Facts, defs: reference.FieldDefinitions, end: date) -> Derived:
    """Cash and cash equivalents plus the first investment alternative with any tag present,
    summed (IFRS filers split current financial assets by measurement category)."""
    d = defs.cash.ifrs
    equivalents = facts.first(d.cash_equivalents, end, instant=True)
    if equivalents is None:
        return None, None, None
    parts = [boundary.Component(name="cash_equivalents", value=equivalents[0], row=equivalents[1])]
    for alternative in d.short_term_investments:
        found = facts.sum_present("short_term_investments", alternative, end, instant=True)
        if found:
            parts.extend(found)
            break
    return sum(p.value for p in parts), _label(parts), _composition(defs.cash.name, parts)


def total_debt_ifrs(facts: Facts, defs: reference.FieldDefinitions, end: date) -> Derived:
    """Borrowings, the taxonomy's financial-debt aggregate, when tagged; else the groups
    present summed (noncurrent borrowings and bonds, current bonds, and current borrowings
    as one tag or as short-term borrowings plus the current portion of long-term debt),
    at least one noncurrent group required. Lease liabilities are never read."""
    d = defs.total_debt.ifrs

    def part(name: str, hit: tuple[float, str] | None) -> list[boundary.Component]:
        return [] if hit is None else [boundary.Component(name=name, value=hit[0], row=hit[1])]

    total = facts.first(d.total, end, instant=True)
    if total is not None:
        parts = part("total", total)
        return sum(p.value for p in parts), _label(parts), _composition(defs.total_debt.name, parts)
    noncurrent = part("noncurrent_borrowings", facts.first(d.noncurrent_borrowings, end, instant=True)) + part("noncurrent_bonds", facts.first(d.noncurrent_bonds, end, instant=True))
    if not noncurrent:
        return None, None, None
    current = part("current_total", facts.first(d.current_total, end, instant=True))
    if not current:
        current = part("short_term_borrowings", facts.first(d.short_term_borrowings, end, instant=True)) + part("current_portion_of_long_term", facts.first(d.current_portion_of_long_term, end, instant=True))
    parts = noncurrent + part("current_bonds", facts.first(d.current_bonds, end, instant=True)) + current
    return sum(p.value for p in parts), _label(parts), _composition(defs.total_debt.name, parts)


def delta_nwc_ifrs(facts: Facts, defs: reference.FieldDefinitions, end: date, notes: list[str]) -> Derived:
    """The working-capital adjustment family, cash-flow-signed for assets and liabilities
    alike, every component flipped by the definition's sign into the boundary's; a family
    tag classified neither as a component nor as excluded leaves the field null."""
    d = defs.delta_nwc.ifrs
    present = [tag for prefix in d.family_prefixes for tag in facts.duration_tags_with_prefix(prefix, end)]
    unclassified = sorted(t for t in present if t not in d.components and t not in d.excluded)
    if unclassified:
        notes.append(f"delta_nwc {end}: left null, unclassified working-capital tags: {', '.join(unclassified)}")
        return None, None, None
    parts: list[boundary.Component] = []
    for tag in d.components:
        value = facts.at(tag, end, instant=False)
        if value is not None:
            parts.append(boundary.Component(name="cash_flow_signed_components", value=value * d.sign, row=tag))
    if not parts:
        return None, None, None
    return sum(p.value for p in parts), _label(parts), _composition(defs.delta_nwc.name, parts)


def net_interest_income_recipe(facts: Facts, recipe: reference.NiiRecipe, end: date) -> tuple[float | None, str | None]:
    """First present interest revenue less first present interest expense, as A - B."""
    revenue = facts.first(recipe.interest_revenue, end, instant=False)
    expense = facts.first(recipe.interest_expense, end, instant=False)
    if revenue is None or expense is None:
        return None, None
    return revenue[0] - expense[0], f"{revenue[1]} - {expense[1]}"


def total_debt(facts: Facts, defs: reference.FieldDefinitions, end: date) -> Derived:
    """Financial debt, first complete recipe: noncurrent + all current debt as one tag;
    noncurrent + the current portion of long-term debt (+ short-term borrowings when
    tagged); long-term debt filed with its current portion (+ short-term borrowings);
    noncurrent alone when the filer tags nothing current at all. Operating lease tags are
    never read."""
    d = defs.total_debt.xbrl
    noncurrent = facts.first(d.noncurrent, end, instant=True)
    current_total = facts.first(d.current_total, end, instant=True)
    current_long_term = facts.first(d.current_long_term, end, instant=True)
    short_term = facts.first(d.short_term_borrowings, end, instant=True)
    total_including_current = facts.first(d.total_including_current, end, instant=True)

    def part(name: str, hit: tuple[float, str]) -> boundary.Component:
        return boundary.Component(name=name, value=hit[0], row=hit[1])

    parts: list[boundary.Component]
    if noncurrent is not None and current_total is not None:
        parts = [part("noncurrent", noncurrent), part("current_total", current_total)]
    elif noncurrent is not None and current_long_term is not None:
        parts = [part("noncurrent", noncurrent), part("current_long_term", current_long_term)]
        if short_term is not None:
            parts.append(part("short_term_borrowings", short_term))
    elif total_including_current is not None:
        parts = [part("total_including_current", total_including_current)]
        if short_term is not None:
            parts.append(part("short_term_borrowings", short_term))
    elif noncurrent is not None and short_term is None:
        parts = [part("noncurrent", noncurrent)]
    else:
        return None, None, None
    return sum(p.value for p in parts), _label(parts), _composition(defs.total_debt.name, parts)


def delta_nwc(facts: Facts, defs: reference.FieldDefinitions, end: date, notes: list[str]) -> Derived:
    """The filed change in operating working capital: the aggregate tag, else the sum of
    the components (assets added, liabilities subtracted), attempted only when every
    IncreaseDecreaseIn tag the filer carries for the period is classified."""
    d = defs.delta_nwc.xbrl
    aggregate = facts.first(d.aggregate, end, instant=False)
    if aggregate is not None:
        parts = [boundary.Component(name="aggregate", value=aggregate[0], row=aggregate[1])]
        return aggregate[0], aggregate[1], _composition(defs.delta_nwc.name, parts)
    present = facts.duration_tags_with_prefix("IncreaseDecreaseIn", end)
    classified = set(d.aggregate) | set(d.asset_components) | set(d.liability_components) | set(d.excluded)
    unclassified = [t for t in present if t not in classified]
    if unclassified:
        notes.append(f"delta_nwc {end}: left null, unclassified working-capital tags: {', '.join(unclassified)}")
        return None, None, None
    parts: list[boundary.Component] = []
    for tag in d.asset_components:
        value = facts.at(tag, end, instant=False)
        if value is not None:
            parts.append(boundary.Component(name="asset_components", value=value, row=tag))
    for tag in d.liability_components:
        value = facts.at(tag, end, instant=False)
        if value is not None:
            parts.append(boundary.Component(name="liability_components", value=-value, row=tag))
    if not parts:
        return None, None, None
    return sum(p.value for p in parts), _label(parts), _composition(defs.delta_nwc.name, parts)


def ebit(facts: Facts, defs: reference.FieldDefinitions, end: date, pretax: float | None, pretax_row: str | None, *, taxonomy: str = "us-gaap") -> tuple[float | None, str | None, str | None, boundary.Composition | None]:
    """Operating income as filed; else pretax income plus interest expense less the
    non-operating income pretax carries (interest income, other non-operating income,
    equity-method earnings: each first present, subtracted as filed), recorded as the
    recipe pretax_plus_interest_less_nonoperating. (value, row, recipe, composition)."""
    d = defs.ebit.ifrs if taxonomy == "ifrs-full" else defs.ebit.xbrl
    operating = facts.first(d.operating_income, end, instant=False)
    if operating is not None:
        parts = [boundary.Component(name="operating_income", value=operating[0], row=operating[1])]
        return operating[0], operating[1], "operating_income", _composition(defs.ebit.name, parts)
    interest = facts.first(d.interest_expense, end, instant=False)
    if pretax is None or pretax_row is None or interest is None:
        return None, None, None, None
    parts = [boundary.Component(name="pretax_income", value=pretax, row=pretax_row),
             boundary.Component(name="interest_expense", value=interest[0], row=interest[1])]
    for name, tags in (("interest_income", d.interest_income), ("other_nonoperating", d.other_nonoperating), ("equity_method", d.equity_method)):
        hit = facts.first(tags, end, instant=False)
        if hit is not None:
            parts.append(boundary.Component(name=name, value=-hit[0], row=hit[1]))
    return sum(p.value for p in parts), _label(parts), "pretax_plus_interest_less_nonoperating", _composition(defs.ebit.name, parts)


def ffo(facts: Facts, defs: reference.FieldDefinitions, end: date, *, taxonomy: str = "us-gaap") -> Derived:
    """FFO per NAREIT: net income + real-estate depreciation + impairment - gains on property
    sales; the first two required, the last two taken as 0 when not filed and recorded so."""
    d = defs.ffo.ifrs if taxonomy == "ifrs-full" else defs.ffo.xbrl
    net_income = facts.first(d.net_income, end, instant=False)
    depreciation = facts.first(d.depreciation, end, instant=False)
    if net_income is None or depreciation is None:
        return None, None, None
    parts = [boundary.Component(name="net_income", value=net_income[0], row=net_income[1]),
             boundary.Component(name="real_estate_depreciation", value=depreciation[0], row=depreciation[1])]
    impairment = facts.first(d.impairment, end, instant=False)
    parts.append(boundary.Component(name="real_estate_impairment", value=impairment[0] if impairment else 0.0, row=impairment[1] if impairment else "not filed, taken as 0"))
    gains = facts.first(d.gains, end, instant=False)
    parts.append(boundary.Component(name="gain_on_property_sales", value=-gains[0] if gains else 0.0, row=gains[1] if gains else "not filed, taken as 0"))
    return sum(p.value for p in parts), _label(parts), _composition(defs.ffo.name, parts)


COVER_PAGE_WINDOW_DAYS = 150  # an annual report's cover page is dated within this of its fiscal year end


def cover_shares(dei: Mapping[str, object], period_end: date, tags: reference.XbrlTags) -> tuple[float, str] | None:
    """The dei cover-page share count of the annual report for the fiscal year ending
    [period_end]: the annual-form entry dated after the year end and within the window,
    the newest filing among them, several classes summed; None when none is filed."""
    tag = "EntityCommonStockSharesOutstanding"
    entries = [_as_dict(e) for e in cast(list[object], _as_dict(_as_dict(dei.get(tag)).get("units")).get("shares", []))]
    dated: list[tuple[str, str, float]] = []
    for e in entries:
        try:
            end = date.fromisoformat(str(e["end"]))
            if str(e.get("form")) in tags.annual_forms and period_end < end <= period_end + timedelta(days=COVER_PAGE_WINDOW_DAYS):
                dated.append((str(e["filed"]), str(e["end"]), float(cast(float, e["val"]))))
        except (KeyError, ValueError):
            continue
    if not dated:
        return None
    newest = max((filed, end) for filed, end, _ in dated)
    values = sorted({v for filed, end, v in dated if (filed, end) == newest})
    return sum(values), tag


def periods_from_facts(gaap: Mapping[str, object], tags: reference.XbrlTags, defs: reference.FieldDefinitions, notes: list[str], *, taxonomy: str = "us-gaap", unit: str = "USD", dei: Mapping[str, object] | None = None) -> list[boundary.FiscalPeriod]:
    ifrs = taxonomy == "ifrs-full"
    selected = select(gaap, tags, notes, taxonomy=taxonomy, unit=unit)
    facts = Facts(gaap, tags, notes, unit=unit)
    ends = sorted(set(selected["net_income"]) & set(selected["book_equity"]), reverse=True)[:PERIODS]
    periods: list[boundary.FiscalPeriod] = []
    for end in ends:
        anchor = selected["net_income"][end][0]
        v: dict[str, float | None] = {}
        r: dict[str, str | None] = {}
        for field, _ in taxonomy_fields(tags, taxonomy):
            v[field], r[field] = value_of(selected, field, end)
        dna, dna_row = depreciation(selected, tags, end)
        if ifrs:
            cash_value, cash_row, cash_composition = cash_ifrs(facts, defs, end)
            debt, debt_row, debt_composition = total_debt_ifrs(facts, defs, end)
            nwc, nwc_row, nwc_composition = delta_nwc_ifrs(facts, defs, end, notes)
            if v["net_interest_income"] is None:
                v["net_interest_income"], r["net_interest_income"] = net_interest_income_recipe(facts, tags.ifrs_full_net_interest_income, end)
        else:
            cash_value, cash_row, cash_composition = cash(facts, defs, end)
            debt, debt_row, debt_composition = total_debt(facts, defs, end)
            nwc, nwc_row, nwc_composition = delta_nwc(facts, defs, end, notes)
        ebit_value, ebit_row, ebit_recipe, ebit_composition = ebit(facts, defs, end, v["pretax_income"], r["pretax_income"], taxonomy=taxonomy)
        ffo_value, _, ffo_composition = ffo(facts, defs, end, taxonomy=taxonomy)
        shares = cover_shares(dei, end, tags) if dei is not None else None
        periods.append(
            boundary.FiscalPeriod(
                period_end=end.isoformat(),
                ebit=ebit_value, pretax_income=v["pretax_income"], tax_provision=v["tax_provision"],
                total_revenue=v["total_revenue"], net_interest_income=v["net_interest_income"],
                premiums_earned=v["premiums_earned"], premiums_earned_row=r["premiums_earned"],
                depreciation_amortization=dna, depreciation_amortization_row=dna_row,
                capex=v["capex"], delta_nwc=nwc, cash=cash_value,
                total_debt=debt, total_debt_source=debt_row,
                book_equity=v["book_equity"], net_income=v["net_income"],
                dividends_paid=v["dividends_paid"], dividends_paid_row=r["dividends_paid"],
                provision_for_credit_losses=None, provision_for_credit_losses_row=None,
                net_loans=None, net_loans_row=None,
                filed=anchor.filed.isoformat(), accession=anchor.accn,
                aoci=v["aoci"], aoci_row=r["aoci"],
                claims_incurred=v["claims_incurred"], claims_incurred_row=r["claims_incurred"],
                benefits_losses_and_expenses=v["benefits_losses_and_expenses"], benefits_losses_and_expenses_row=r["benefits_losses_and_expenses"],
                policy_acquisition_expense=v["policy_acquisition_expense"], policy_acquisition_expense_row=r["policy_acquisition_expense"],
                operating_expense=v["operating_expense"], operating_expense_row=r["operating_expense"],
                future_policy_benefits=v["future_policy_benefits"], future_policy_benefits_row=r["future_policy_benefits"],
                claims_liability=v["claims_liability"], claims_liability_row=r["claims_liability"],
                total_revenue_row=r["total_revenue"], ebit_row=ebit_row, pretax_income_row=r["pretax_income"],
                tax_provision_row=r["tax_provision"], capex_row=r["capex"], delta_nwc_row=nwc_row,
                cash_row=cash_row, book_equity_row=r["book_equity"], net_income_row=r["net_income"],
                net_interest_income_row=r["net_interest_income"],
                ebit_recipe=ebit_recipe, ebit_composition=ebit_composition, cash_composition=cash_composition,
                total_debt_composition=debt_composition, delta_nwc_composition=nwc_composition,
                ffo=ffo_value, ffo_composition=ffo_composition,
                cover_shares=None if shares is None else shares[0], cover_shares_tag=None if shares is None else shares[1],
            )
        )
    return periods


# --- the provider decision ---------------------------------------------------------------


def _as_dict(obj: object) -> dict[str, object]:
    """An untrusted JSON object as a typed dict; anything else is empty."""
    if isinstance(obj, dict):
        return {str(k): v for k, v in obj.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return {}


def _entries(node: object, unit: str) -> list[object]:
    units = _as_dict(_as_dict(node).get("units"))
    entries = units.get(unit)
    return cast(list[object], entries) if isinstance(entries, list) else []


def currency_units(taxonomy_facts: Mapping[str, object]) -> list[tuple[str, int]]:
    """The ISO currency units the taxonomy's facts carry, most facts first."""
    counts: dict[str, int] = {}
    for node in taxonomy_facts.values():
        for unit, entries in _as_dict(_as_dict(node).get("units")).items():
            if len(unit) == 3 and unit.isalpha() and unit.isupper() and isinstance(entries, list):
                counts[unit] = counts.get(unit, 0) + len(cast(list[object], entries))
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


@dataclass(frozen=True)
class Decision:
    xbrl: bool
    reason: str
    facts: Mapping[str, object]   # the chosen taxonomy's facts, or us-gaap's for the reason
    taxonomy: str                 # us-gaap | ifrs-full; "" when the vendor
    currency: str | None          # the unit the filer's annual anchors carry
    dei: Mapping[str, object] | None = None   # the filer's dei section (cover-page shares)


def decide(facts: Mapping[str, object] | None, tags: reference.XbrlTags) -> Decision:
    """XBRL-primary iff annual net income and equity exist on the annual forms under
    us-gaap, else under ifrs-full, in some currency unit (the unit with the most facts in
    the taxonomy is the filer's statement currency; a convenience translation has fewer).
    Otherwise the vendor, with the reason: facts on other forms only, or no annual anchors."""
    if facts is None:
        return Decision(False, "SEC companyfacts: not found (HTTP 404)", {}, "", None)
    all_facts = _as_dict(facts.get("facts"))
    by_taxonomy = {name: _as_dict(all_facts.get(name)) for name in TAXONOMIES}
    # Every taxonomy with annual anchors, with the newest anchor's fiscal year end: a filer
    # that moved from us-gaap to IFRS keeps its old us-gaap facts (Sony to FY2021, Itau to
    # FY2010), so the taxonomy with the newest anchors wins, us-gaap on a tie.
    candidates: list[tuple[date, int, str, str]] = []
    for order, taxonomy in enumerate(TAXONOMIES):
        section = by_taxonomy[taxonomy]
        for unit, _ in currency_units(section):
            scratch: list[str] = []
            selected = select(section, tags, scratch, taxonomy=taxonomy, unit=unit)
            anchors = set(selected.get("net_income", {})) & set(selected.get("book_equity", {}))
            if anchors:
                candidates.append((max(anchors), -order, taxonomy, unit))
                break
    if candidates:
        newest, _, taxonomy, unit = max(candidates)
        others = [f"{t} to {e.isoformat()}" for e, _, t, _ in candidates if t != taxonomy]
        both = f" (also {', '.join(others)}; the newest anchors, {newest.isoformat()}, decide)" if others else ""
        return Decision(True, f"{taxonomy} annual filer ({', '.join(tags.annual_forms)}), statements in {unit}{both}", by_taxonomy[taxonomy], taxonomy, unit, _as_dict(all_facts.get("dei")))
    gaap = by_taxonomy["us-gaap"]
    forms: set[str] = set()
    for taxonomy in TAXONOMIES:
        for tag in dict(taxonomy_fields(tags, taxonomy))["net_income"].tags:
            for unit, _ in currency_units(by_taxonomy[taxonomy]):
                for e in _entries(by_taxonomy[taxonomy].get(tag), unit):
                    entry = _as_dict(e)
                    if "form" in entry:
                        forms.add(str(entry["form"]))
    if forms:
        return Decision(False, f"facts filed on {', '.join(sorted(forms))} only; {' or '.join(tags.annual_forms)} required", gaap, "", None)
    present = ", ".join(f"{name} {len(section)} tags" for name, section in by_taxonomy.items() if section) or "no us-gaap or ifrs-full facts"
    return Decision(False, f"facts carry no annual net income and equity ({present})", gaap, "", None)


def latest_filing(periods: list[boundary.FiscalPeriod]) -> str | None:
    filed = [p.filed for p in periods if p.filed]
    return max(filed) if filed else None


if __name__ == "__main__":
    import fetch

    sys.exit(fetch.main(sys.argv[1:]))
