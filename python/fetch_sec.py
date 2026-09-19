"""SEC XBRL companyfacts as a statements provider: filed 10-K facts, canonical us-gaap tags
chosen per fiscal period from reference/xbrl_tags.json.

    uv run python/fetch_sec.py ALL MET PGR       ->  the same routed fetch as fetch.py

fetch.py decides per ticker whether a name is XBRL-primary (its CIK resolves exactly in
SEC's ticker map and its facts carry annual 10-K net income and stockholders' equity under
us-gaap) and calls into here for the statements. companyfacts JSON is cached under
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
from datetime import date
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, ValidationError

import boundary
import reference

REPO_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = REPO_ROOT / ".env"
CACHE_DIR = REPO_ROOT / "data" / "sec"
TAGS_PATH = REPO_ROOT / "reference" / "xbrl_tags.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
PROVIDER = "SEC XBRL companyfacts"
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


def select(gaap: Mapping[str, object], tags: reference.XbrlTags, notes: list[str]) -> dict[str, dict[date, tuple[Fact, str]]]:
    """Per canonical field, per fiscal year end: the first candidate tag with an annual fact."""
    out: dict[str, dict[date, tuple[Fact, str]]] = {}
    for field, spec in tags.fields:
        per_end: dict[date, tuple[Fact, str]] = {}
        for tag in spec.tags:
            node = gaap.get(tag)
            if not isinstance(node, dict):
                continue
            for end, fact in annual_facts(_usd_entries(node), instant=spec.kind == "instant", tags=tags, notes=notes, tag=tag).items():
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


def total_debt(selected: Selected, tags: reference.XbrlTags, end: date) -> tuple[float | None, str | None]:
    for recipe in tags.debt_recipes:
        parts = [value_of(selected, field, end) for field in recipe]
        if any(v is None for v, _ in parts):
            continue
        total = sum(v for v, _ in parts if v is not None)
        rows = [r or f for (_, r), f in zip(parts, recipe)]
        for field in tags.debt_optional_add:
            v, r = value_of(selected, field, end)
            if v is not None:
                total += v
                rows.append(r or field)
        return total, " + ".join(rows)
    return None, None


def working_capital(selected: Selected, tags: reference.XbrlTags, end: date) -> tuple[float | None, str]:
    """(current assets - cash) - (current liabilities - current debt where filed); the label says which."""
    wc = dict(tags.working_capital)
    assets, a_row = value_of(selected, wc["assets"], end)
    liabilities, l_row = value_of(selected, wc["liabilities"], end)
    cash, c_row = value_of(selected, wc["cash"], end)
    debt, d_row = value_of(selected, wc["debt_current"], end)
    if assets is None or liabilities is None or cash is None:
        return None, ""
    label = f"({a_row} - {c_row}) - ({l_row}" + (f" - {d_row})" if debt is not None else ")")
    return (assets - cash) - (liabilities - (debt or 0.0)), label


def periods_from_facts(gaap: Mapping[str, object], tags: reference.XbrlTags, notes: list[str]) -> list[boundary.FiscalPeriod]:
    selected = select(gaap, tags, notes)
    ends = sorted(set(selected["net_income"]) & set(selected["book_equity"]), reverse=True)[: PERIODS + 1]
    nwc = {end: working_capital(selected, tags, end) for end in ends}
    periods: list[boundary.FiscalPeriod] = []
    for i, end in enumerate(ends[:PERIODS]):
        anchor = selected["net_income"][end][0]
        v: dict[str, float | None] = {}
        r: dict[str, str | None] = {}
        for field, _ in tags.fields:
            v[field], r[field] = value_of(selected, field, end)
        dna, dna_row = depreciation(selected, tags, end)
        debt, debt_row = total_debt(selected, tags, end)
        delta_nwc: float | None = None
        delta_row: str | None = None
        if i + 1 < len(ends):
            this_nwc, label = nwc[end]
            prev_nwc, _ = nwc[ends[i + 1]]
            if this_nwc is not None and prev_nwc is not None:
                delta_nwc, delta_row = this_nwc - prev_nwc, f"change in {label} from {ends[i + 1]}"
        periods.append(
            boundary.FiscalPeriod(
                period_end=end.isoformat(),
                ebit=v["ebit"], pretax_income=v["pretax_income"], tax_provision=v["tax_provision"],
                total_revenue=v["total_revenue"], net_interest_income=v["net_interest_income"],
                premiums_earned=v["premiums_earned"], premiums_earned_row=r["premiums_earned"],
                depreciation_amortization=dna, depreciation_amortization_row=dna_row,
                capex=v["capex"], delta_nwc=delta_nwc, cash=v["cash"],
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
                total_revenue_row=r["total_revenue"], ebit_row=r["ebit"], pretax_income_row=r["pretax_income"],
                tax_provision_row=r["tax_provision"], capex_row=r["capex"], delta_nwc_row=delta_row,
                cash_row=r["cash"], book_equity_row=r["book_equity"], net_income_row=r["net_income"],
                net_interest_income_row=r["net_interest_income"],
            )
        )
    return periods


# --- the provider decision ---------------------------------------------------------------


def _as_dict(obj: object) -> dict[str, object]:
    """An untrusted JSON object as a typed dict; anything else is empty."""
    if isinstance(obj, dict):
        return {str(k): v for k, v in obj.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return {}


def _usd_entries(node: object) -> list[object]:
    units = _as_dict(_as_dict(node).get("units"))
    entries = units.get("USD")
    return cast(list[object], entries) if isinstance(entries, list) else []


def decide(facts: Mapping[str, object] | None, tags: reference.XbrlTags) -> tuple[bool, str, Mapping[str, object]]:
    """(xbrl_primary, reason, us-gaap facts). XBRL-primary iff annual net income and
    stockholders' equity exist under us-gaap on the annual forms; otherwise the vendor, with
    the reason: IFRS filer, facts on other forms only, or no annual anchors at all."""
    if facts is None:
        return False, "SEC companyfacts: not found (HTTP 404)", {}
    all_facts = _as_dict(facts.get("facts"))
    gaap = _as_dict(all_facts.get("us-gaap"))
    ifrs = _as_dict(all_facts.get("ifrs-full"))
    scratch: list[str] = []
    selected = select(gaap, tags, scratch) if gaap else {}
    if selected and selected.get("net_income") and selected.get("book_equity"):
        return True, f"us-gaap annual filer ({', '.join(tags.annual_forms)})", gaap
    if ifrs:
        return False, "ifrs filer, not in scope", gaap
    forms: set[str] = set()
    for e in _usd_entries(gaap.get("NetIncomeLoss")):
        entry = _as_dict(e)
        if "form" in entry:
            forms.add(str(entry["form"]))
    if forms:
        return False, f"us-gaap facts filed on {', '.join(sorted(forms))} only; {' or '.join(tags.annual_forms)} required", gaap
    return False, f"us-gaap facts carry no annual net income and stockholders' equity ({len(gaap)} tags)", gaap


def latest_filing(periods: list[boundary.FiscalPeriod]) -> str | None:
    filed = [p.filed for p in periods if p.filed]
    return max(filed) if filed else None


if __name__ == "__main__":
    import fetch

    sys.exit(fetch.main(sys.argv[1:]))
