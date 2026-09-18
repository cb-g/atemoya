"""Fetch a U.S. filer's statements from SEC XBRL companyfacts and emit boundary JSON.

    uv run python/fetch_sec.py ALL MET PGR       ->  data/financials/<TICKER>.json

Same record as fetch.py, with provider "SEC XBRL companyfacts": every statement number is
from a filed 10-K (annual duration facts only; instant facts at the fiscal year end), the
canonical us-gaap tag matched per field is recorded as the row label, and each period
carries its filing date and accession number. Price, market cap, currency, country and
industry still come from the vendor quote, as in fetch.py. A ticker SEC does not know
yields a record with no periods and `statements_unavailable` saying why, so the valuation
refuses with the reason rather than skipping the name.

SEC's fair-access policy requires every request to identify its sender. The whole string
in SEC_EDGAR_IDENTITY ("<name> <contact email>", from the environment or .env) is sent
verbatim as the User-Agent; nothing is composed here. Missing or without an @: exit
non-zero, fetch nothing.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from pathlib import Path

import yfinance as yf
from pydantic import BaseModel, ConfigDict, ValidationError

import boundary
import fetch

REPO_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = REPO_ROOT / ".env"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
PROVIDER = "SEC XBRL companyfacts"
ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "20-F", "40-F"})
ANNUAL_DAYS = (350, 380)  # a duration fact that spans about a year; fp=FY also marks quarters
PERIODS = 5

# Canonical field -> candidate us-gaap tags, first present per fiscal period wins. Duration
# tags are flows over the year; instant tags are balances at the year end.
DURATION_TAGS: dict[str, tuple[str, ...]] = {
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "total_revenue": ("Revenues",),
    "premiums_earned": ("PremiumsEarnedNet", "PremiumsEarnedNetPropertyAndCasualty", "PremiumsEarnedNetLife"),
    "claims_incurred": ("PolicyholderBenefitsAndClaimsIncurredNet", "IncurredClaimsPropertyCasualtyAndLiability"),
    "benefits_losses_and_expenses": ("BenefitsLossesAndExpenses",),
    "policy_acquisition_expense": ("DeferredPolicyAcquisitionCostAmortizationExpense",),
    "operating_expense": ("OperatingExpenses", "OtherCostAndExpenseOperating"),
    "dividends_paid": ("PaymentsOfDividendsCommonStock", "PaymentsOfDividends"),
}
INSTANT_TAGS: dict[str, tuple[str, ...]] = {
    "book_equity": ("StockholdersEquity",),
    "aoci": ("AccumulatedOtherComprehensiveIncomeLossNetOfTax",),
    "future_policy_benefits": ("LiabilityForFuturePolicyBenefits",),
    "claims_liability": ("LiabilityForClaimsAndClaimsAdjustmentExpense",),
}
NON_NEGATIVE = frozenset(
    {"premiums_earned", "claims_incurred", "benefits_losses_and_expenses", "policy_acquisition_expense",
     "operating_expense", "dividends_paid", "future_policy_benefits", "claims_liability"}
)


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


def _get(url: str, user_agent: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(request, timeout=90) as response:
        body = response.read()
        return gzip.decompress(body) if response.headers.get("Content-Encoding") == "gzip" else body


def cik_for(symbol: str, table: Mapping[str, object]) -> str | None:
    """Exact ticker match on SEC's company_tickers.json; "ALV.DE" is not "ALV" (Autoliv)."""
    for entry in table.values():
        if isinstance(entry, dict) and str(entry.get("ticker", "")).upper() == symbol.upper():  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            return str(entry["cik_str"]).zfill(10)  # pyright: ignore[reportUnknownArgumentType]
    return None


def annual_facts(entries: Iterable[object], *, instant: bool, notes: list[str], tag: str) -> dict[date, Fact]:
    """The latest-filed annual fact per fiscal year end: 10-K facts marked FY whose duration
    spans about a year (or, for balances, carry no start)."""
    out: dict[date, Fact] = {}
    rejected = 0
    for raw in entries:
        try:
            fact = Fact.model_validate(raw)
        except ValidationError:
            rejected += 1
            continue
        if fact.form not in ANNUAL_FORMS or fact.fp != "FY":
            continue
        if instant:
            if fact.start is not None:
                continue
        else:
            if fact.start is None or not (ANNUAL_DAYS[0] <= (fact.end - fact.start).days <= ANNUAL_DAYS[1]):
                continue
        if fact.end not in out or fact.filed > out[fact.end].filed:
            out[fact.end] = fact
    if rejected:
        notes.append(f"{tag}: {rejected} companyfacts entries rejected at validation")
    return out


def select(
    gaap: Mapping[str, object], candidates: Mapping[str, tuple[str, ...]], *, instant: bool, notes: list[str]
) -> dict[str, dict[date, tuple[Fact, str]]]:
    """Per canonical field, per fiscal year end: the first candidate tag with an annual fact."""
    out: dict[str, dict[date, tuple[Fact, str]]] = {}
    for field, tags in candidates.items():
        per_end: dict[date, tuple[Fact, str]] = {}
        for tag in tags:
            node = gaap.get(tag)
            if not isinstance(node, dict):
                continue
            usd = node.get("units", {}).get("USD", [])  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            for end, fact in annual_facts(usd, instant=instant, notes=notes, tag=tag).items():  # pyright: ignore[reportUnknownArgumentType]
                per_end.setdefault(end, (fact, tag))
        out[field] = per_end
    return out


def _value(selected: Mapping[str, Mapping[date, tuple[Fact, str]]], field: str, end: date) -> tuple[float | None, str | None]:
    hit = selected.get(field, {}).get(end)
    return (hit[0].val, hit[1]) if hit else (None, None)


def periods_from_facts(gaap: Mapping[str, object], notes: list[str]) -> list[boundary.FiscalPeriod]:
    flows = select(gaap, DURATION_TAGS, instant=False, notes=notes)
    balances = select(gaap, INSTANT_TAGS, instant=True, notes=notes)
    ends = sorted(set(flows["net_income"]) & set(balances["book_equity"]), reverse=True)[:PERIODS]
    periods: list[boundary.FiscalPeriod] = []
    for end in ends:
        anchor = flows["net_income"][end][0]
        v: dict[str, float | None] = {}
        r: dict[str, str | None] = {}
        for field in list(DURATION_TAGS) + list(INSTANT_TAGS):
            v[field], r[field] = _value(flows if field in DURATION_TAGS else balances, field, end)
            if field in NON_NEGATIVE and v[field] is not None and v[field] < 0:  # pyright: ignore[reportOptionalOperand]
                notes.append(f"{end}: {field} filed negative under {r[field]}; dropped")
                v[field], r[field] = None, None
        periods.append(
            boundary.FiscalPeriod(
                period_end=end.isoformat(),
                ebit=None, pretax_income=None, tax_provision=None,
                total_revenue=v["total_revenue"], net_interest_income=None,
                premiums_earned=v["premiums_earned"], premiums_earned_row=r["premiums_earned"],
                depreciation_amortization=None, depreciation_amortization_row=None,
                capex=None, delta_nwc=None, cash=None, total_debt=None, total_debt_source=None,
                book_equity=v["book_equity"], net_income=v["net_income"],
                dividends_paid=v["dividends_paid"], dividends_paid_row=r["dividends_paid"],
                provision_for_credit_losses=None, provision_for_credit_losses_row=None,
                net_loans=None, net_loans_row=None,
                filed=anchor.filed.isoformat(), accession=anchor.accn,
                aoci=v["aoci"], aoci_row=r["aoci"],
                claims_incurred=v["claims_incurred"], claims_incurred_row=r["claims_incurred"],
                benefits_losses_and_expenses=v["benefits_losses_and_expenses"],
                benefits_losses_and_expenses_row=r["benefits_losses_and_expenses"],
                policy_acquisition_expense=v["policy_acquisition_expense"],
                policy_acquisition_expense_row=r["policy_acquisition_expense"],
                operating_expense=v["operating_expense"], operating_expense_row=r["operating_expense"],
                future_policy_benefits=v["future_policy_benefits"], future_policy_benefits_row=r["future_policy_benefits"],
                claims_liability=v["claims_liability"], claims_liability_row=r["claims_liability"],
            )
        )
    return periods


def fetch_filed(symbol: str, as_of: datetime, user_agent: str, tickers: Mapping[str, object]) -> boundary.Financials:
    notes: list[str] = []
    quote, profile = fetch._info(yf.Ticker(symbol), notes)  # pyright: ignore[reportPrivateUsage]
    cik = cik_for(symbol, tickers)
    periods: list[boundary.FiscalPeriod] = []
    unavailable = ""
    if cik is None:
        unavailable = f"no SEC filings for {symbol}: not in company_tickers.json"
    else:
        try:
            facts = json.loads(_get(FACTS_URL.format(cik=cik), user_agent))
            gaap = facts.get("facts", {}).get("us-gaap", {})
            periods = periods_from_facts(gaap, notes)
            notes.append(f"CIK {cik}: {facts.get('entityName', '')}; {len(gaap)} us-gaap tags")
            if not periods:
                unavailable = f"SEC companyfacts for CIK {cik} carry no annual net income and stockholders' equity"
        except urllib.error.HTTPError as e:
            unavailable = f"SEC companyfacts for CIK {cik}: HTTP {e.code}"
        except (urllib.error.URLError, ValueError) as e:
            unavailable = f"SEC companyfacts for CIK {cik}: {type(e).__name__}: {e}"
    return boundary.Financials(
        ticker=symbol,
        as_of=as_of.isoformat(timespec="seconds"),
        currency=fetch._single_currency(quote, notes) if quote else None,  # pyright: ignore[reportPrivateUsage]
        price=quote.price if quote else None,
        market_cap=quote.market_cap if quote else None,
        country=profile.country if profile else None,
        industry=profile.industry if profile else None,
        periods=periods,
        notes=notes,
        provider=PROVIDER,
        statements_unavailable=unavailable,
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="+", help="symbols as the vendor spells them; SEC's map is matched exactly")
    parser.add_argument("--out", type=Path, default=fetch.DEFAULT_OUT)
    args = parser.parse_args(argv)
    tickers: list[str] = [str(t).upper() for t in args.tickers]
    out: Path = args.out
    user_agent = identity()
    out.mkdir(parents=True, exist_ok=True)
    as_of = datetime.now(timezone.utc)
    table = json.loads(_get(TICKERS_URL, user_agent))
    for symbol in tickers:
        financials = fetch_filed(symbol, as_of, user_agent, table)
        text = financials.to_json_string(indent=2, allow_nan=False)
        boundary.Financials.from_json_string(text)
        path = out / f"{symbol}.json"
        path.write_text(text + "\n")
        latest = financials.periods[0] if financials.periods else None
        summary = (
            f"{symbol}: {len(financials.periods)} filed period(s)"
            + (f" through {latest.period_end} (filed {latest.filed}, {latest.accession})" if latest else "")
            + f", price={financials.price}, country={financials.country}"
            + (f"; {financials.statements_unavailable}" if financials.statements_unavailable else "")
        )
        print(f"{summary} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
