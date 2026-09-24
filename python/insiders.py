"""Form 4 (66): what the people with the most information did about the price.

Open-market purchases (code `P`) and sales (code `S`) from the non-derivative table of
SEC's Form 4 filings, counted and listed. An award, an exercise, a tax withholding or a
gift is counted by its code and never summed: an exercise-and-sell is not a sale of
conviction. No score, no weight and no signal lives here.

Everything is cut on the FILING date, not the transaction date, so the point-in-time panel
reads only what was public on its date. The filing date is not in the document — SEC's
submissions index carries it, and the signature date disagrees with it often enough to
matter, so the index is the only source for it.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, cast

import boundary

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "insiders"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
FORMS = ("4", "4/A")
PURCHASE, SALE = "P", "S"
CLUSTER_DAYS = 14          # the standard window, kept because it is the standard one
CLUSTER_BUYERS = 2
WINDOWS = (90, 365)
CHIEF = re.compile(r"chief\s+(executive|financial)|(^|\b)(ceo|cfo)(\b|$)", re.IGNORECASE)

NO_CIK = "no CIK: Form 4 covers SEC registrants, and this name is on the vendor path"
NO_FILINGS = "no insider transactions filed in the year to the date"
SCOPE_LIMITS = [
    "Form 4 covers directors, officers and ten-percent owners of SEC registrants only; a foreign private issuer files none",
    "a purchase or sale under a rule 10b5-1 plan is scheduled, not decided, and is marked on the transaction where the filing says so",
    "open-market purchases and sales only: awards, exercises, tax withholding and gifts are counted by code and never summed",
]


@dataclass(frozen=True)
class Transaction:
    """One non-derivative line of one filing, already filtered to a purchase or a sale."""
    owner: str
    owner_cik: str
    relationship: str
    transaction_date: date
    code: str
    shares: float
    price_per_share: float
    accession: str
    filed: date
    shares_owned_after: float | None
    plan_10b5_1: bool

    @property
    def dollars(self) -> float:
        return self.shares * self.price_per_share

    def to_boundary(self) -> boundary.InsiderTransaction:
        return boundary.InsiderTransaction(
            owner=self.owner, relationship=self.relationship,
            transaction_date=self.transaction_date.isoformat(), code=self.code,
            shares=self.shares, price_per_share=self.price_per_share, dollars=self.dollars,
            shares_owned_after=self.shares_owned_after, accession=self.accession,
            filed=self.filed.isoformat(), plan_10b5_1=self.plan_10b5_1)


def _text(node: ET.Element | None, path: str) -> str | None:
    """A field's text, whether or not the schema wraps it in <value>. The wrapper is on
    some fields and not others in the same document -- transactionCode has none, the
    shares beside it do -- so a parser that always appends it, or never does, is wrong."""
    if node is None:
        return None
    found = node.find(path)
    if found is None:
        return None
    inner = found.find("value")
    raw = (inner.text if inner is not None else found.text) or ""
    return raw.strip() or None


def _number(node: ET.Element | None, path: str) -> float | None:
    raw = _text(node, path)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _flag(node: ET.Element | None, path: str) -> bool:
    """A filing agent may emit only the flag that is true, so absent is false; and the two
    spellings live side by side in one schema version."""
    raw = _text(node, path)
    return raw is not None and raw.strip().lower() in ("1", "true")


def relationship_of(owner: ET.Element) -> str:
    rel = owner.find("reportingOwnerRelationship")
    parts: list[str] = []
    if _flag(rel, "isDirector"):
        parts.append("director")
    if _flag(rel, "isOfficer"):
        title = _text(rel, "officerTitle")
        parts.append(f"officer: {title}" if title else "officer")
    if _flag(rel, "isTenPercentOwner"):
        parts.append("ten-percent owner")
    if _flag(rel, "isOther"):
        other = _text(rel, "otherText")
        parts.append(f"other: {other}" if other else "other")
    return "; ".join(parts) or "not stated"


def parse_form4(body: bytes, accession: str, filed: date, issuer_cik: str | None = None) -> tuple[list[Transaction], Counter[str]]:
    """One filing's open-market purchases and sales, and a count of every other code seen.

    [filed] comes from the submissions index: the document carries no filing date, and its
    signature date is a different thing.

    [issuer_cik] is the name being valued. A CIK's index lists the Form 4s it filed in BOTH
    capacities: as the issuer, where its own insiders report trades in its stock, and as a
    reporting owner, where it reports its own trades in somebody else's. Only the first is
    about this name, and the two are told apart by the document's issuerCik -- nothing in
    the index distinguishes them per filing."""
    excluded: Counter[str] = Counter()
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return [], excluded
    if issuer_cik is not None:
        filed_for = _text(root, "issuer/issuerCik")
        if filed_for is None or int(filed_for) != int(issuer_cik):
            excluded["reported as an owner of another issuer"] += 1
            return [], excluded
    plan = _flag(root, "aff10b5One")          # a document-level marking, not a per-line one
    owners = root.findall("reportingOwner")   # more than one owner in a filing is ordinary
    if not owners:
        return [], excluded
    who = "; ".join(sorted({_text(o, "reportingOwnerId/rptOwnerName") or "" for o in owners} - {""})) or "not stated"
    cik = "; ".join(sorted({_text(o, "reportingOwnerId/rptOwnerCik") or "" for o in owners} - {""}))
    relationship = "; ".join(sorted({relationship_of(o) for o in owners}))
    out: list[Transaction] = []
    for t in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = _text(t, "transactionCoding/transactionCode")    # no <value> wrapper here
        if code is None:
            continue
        if code not in (PURCHASE, SALE):
            # counted, never summed: an award and a gift file a price of zero, so a summer
            # that filtered after the arithmetic would inflate the buyer and seller counts
            excluded[code] += 1
            continue
        when = _text(t, "transactionDate")
        shares = _number(t, "transactionAmounts/transactionShares")
        price = _number(t, "transactionAmounts/transactionPricePerShare")
        if when is None or shares is None or price is None:
            excluded[f"{code} (incomplete)"] += 1
            continue
        try:
            transaction_date = date.fromisoformat(when)
        except ValueError:
            excluded[f"{code} (unparsed date)"] += 1
            continue
        out.append(Transaction(
            owner=who, owner_cik=cik, relationship=relationship, transaction_date=transaction_date,
            code=code, shares=shares, price_per_share=price, accession=accession, filed=filed,
            shares_owned_after=_number(t, "postTransactionAmounts/sharesOwnedFollowingTransaction"),
            plan_10b5_1=plan))
    return out, excluded


def form4_filings(index: Mapping[str, object]) -> list[tuple[str, date, str]]:
    """(accession, filing date, primary document) per Form 4 and 4/A, newest first.

    Takes either a submissions index, whose filings are under `filings.recent`, or one of the
    older pages beside it, whose arrays are at the top level.

    **`recent` is a year, not a history.** It holds the most recent thousand filings or one
    year, whichever is more, so for a heavy filer it is barely the year: JPMorgan's reaches
    back twelve months and Meta's fifteen. A 365-day window (66) never needs more; anything
    that walks further (67) must read the older pages, or it reads an empty window and calls
    it no insider activity."""
    filings = cast(Mapping[str, object], index.get("filings") or {})
    recent = cast(Mapping[str, Any], filings.get("recent") or index)
    forms = cast(list[str], recent.get("form") or [])
    accessions = cast(list[str], recent.get("accessionNumber") or [])
    dates = cast(list[str], recent.get("filingDate") or [])
    documents = cast(list[str], recent.get("primaryDocument") or [])
    out: list[tuple[str, date, str]] = []
    for i, form in enumerate(forms):
        if form not in FORMS or i >= min(len(accessions), len(dates), len(documents)):
            continue
        try:
            filed = date.fromisoformat(dates[i])
        except ValueError:
            continue
        out.append((accessions[i], filed, documents[i]))
    return sorted(out, key=lambda x: (x[1], x[0]), reverse=True)


def document_url(cik: str, accession: str, primary_document: str) -> str:
    """The raw XML. The index's primaryDocument carries an XSL rendering prefix that serves
    HTML if it is left on, and the accession loses its dashes in the path."""
    return ARCHIVE.format(cik=str(int(cik)), accession=accession.replace("-", ""),
                          document=primary_document.rsplit("/", 1)[-1])


def deduplicate(transactions: list[Transaction]) -> list[Transaction]:
    """An amendment restates a transaction the original already reported, and nothing in
    the index links the two: their accessions share only the filing agent and the year. So
    the same line is recognised by what it says -- owner, date, code and shares -- and the
    later filing wins."""
    best: dict[tuple[str, str, str, float], Transaction] = {}
    for t in sorted(transactions, key=lambda x: (x.filed, x.accession)):
        best[(t.owner_cik or t.owner, t.transaction_date.isoformat(), t.code, t.shares)] = t
    return sorted(best.values(), key=lambda t: (t.transaction_date, t.accession))


def window(transactions: list[Transaction], as_of: date, days: int) -> boundary.InsiderWindow:
    """One window's counts and dollars. Public because the through-time study (67) reads one
    window from a cache filled for that window alone, and must not claim the other."""
    start = as_of - timedelta(days=days)
    inside = [t for t in transactions if start <= t.transaction_date <= as_of]
    buys = [t for t in inside if t.code == PURCHASE]
    sells = [t for t in inside if t.code == SALE]
    bought = sum(t.dollars for t in buys)
    sold = sum(t.dollars for t in sells)
    largest = max(buys, key=lambda t: t.dollars, default=None)
    return boundary.InsiderWindow(
        days=days, buyers=len({t.owner for t in buys}), sellers=len({t.owner for t in sells}),
        dollars_bought=bought, dollars_sold=sold, net_dollars=bought - sold,
        largest_purchase=None if largest is None else largest.to_boundary(),
        ceo_or_cfo_bought=any(CHIEF.search(t.relationship) for t in buys))


def cluster(transactions: list[Transaction], as_of: date, days: int = 90) -> boundary.InsiderCluster | None:
    """Two DISTINCT insiders buying on the open market inside one fourteen-day window. One
    insider buying twice is not a cluster, which is the whole point of the rule."""
    start = as_of - timedelta(days=days)
    buys = sorted((t for t in transactions if t.code == PURCHASE and start <= t.transaction_date <= as_of),
                  key=lambda t: t.transaction_date)
    for i, anchor in enumerate(buys):
        end = anchor.transaction_date + timedelta(days=CLUSTER_DAYS)
        inside = [t for t in buys[i:] if t.transaction_date <= end]
        owners = sorted({t.owner for t in inside})
        if len(owners) >= CLUSTER_BUYERS:
            return boundary.InsiderCluster(
                window_start=anchor.transaction_date.isoformat(),
                window_end=max(t.transaction_date for t in inside).isoformat(), buyers=owners)
    return None


def compute(transactions: list[Transaction], excluded: Counter[str], as_of: date, cik: str,
            filings_read: int) -> tuple[boundary.Insiders | None, str | None]:
    """The block, or the reason there is none. Everything here counts and lists."""
    if not transactions and not excluded and filings_read == 0:
        return None, NO_FILINGS
    kept = deduplicate(transactions)
    found = cluster(kept, as_of)
    return boundary.Insiders(
        as_of=as_of.isoformat(), cik=cik,
        window_90=window(kept, as_of, 90), window_365=window(kept, as_of, 365),
        cluster_buy=found is not None, cluster=found, filings_read=filings_read,
        excluded_by_code=sorted(excluded.items()), scope_limits=list(SCOPE_LIMITS)), None
