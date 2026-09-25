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
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel, ConfigDict, ValidationError

import boundary
import reference

if TYPE_CHECKING:
    import insiders as insiders_mod

REPO_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = REPO_ROOT / ".env"
CACHE_DIR = REPO_ROOT / "data" / "sec"
# (66) A transaction may be reported up to two business days after it happens, so a
# filing a little older than the window can still carry a transaction inside it.
INSIDER_FILING_LAG_DAYS = 10
TAGS_PATH = REPO_ROOT / "reference" / "xbrl_tags.json"
DEFINITIONS_PATH = REPO_ROOT / "reference" / "field_definitions.json"
PARAMS_PATH = REPO_ROOT / "reference" / "params.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"
ANNUAL_SUBMISSION_FORMS = ("10-K", "20-F")  # the original annual filings; amendments and 40-Fs are not
PROVIDER = "SEC XBRL companyfacts"
TAXONOMIES = ("us-gaap", "ifrs-full")  # in order of preference when a filer carries both
CACHE_SECONDS = 86400
MIN_SPACING_SECONDS = 0.25  # 4 requests per second, under SEC's 10/s guidance
PERIODS_DEFAULT = 5  # annual periods kept for every model but the mid-cycle DCF (22), whose window is a parameter

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


def load_params() -> reference.Params:
    """(65) The fetcher reads one declared parameter, interest_evidence_floor; the rest are
    the models'. Loaded here so a period can be built without threading the whole file."""
    return reference.Params.from_json_string(PARAMS_PATH.read_text())


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


def submissions_pages(index: Mapping[str, object] | None, first: date, last: date) -> list[str]:
    """(67) The older submission pages that could carry a filing in [first, last].

    `filings.recent` is a year or a thousand filings, whichever is more, and `filings.files`
    lists the pages behind it with the span each covers. Only the pages whose span meets the
    window are named, so walking four years of one filer does not pull twenty years of its
    index."""
    if index is None:
        return []
    files = cast(list[Mapping[str, object]], cast(Mapping[str, object], index.get("filings") or {}).get("files") or [])
    out: list[str] = []
    for page in files:
        try:
            covers_from = date.fromisoformat(str(page["filingFrom"]))
            covers_to = date.fromisoformat(str(page["filingTo"]))
        except (KeyError, ValueError):
            out.append(str(page.get("name", "")))        # a page we cannot date is a page we must read
            continue
        if covers_from <= last and covers_to >= first:
            out.append(str(page["name"]))
    return [name for name in out if name]


def submissions_page(name: str, user_agent: str) -> dict[str, object]:
    """One older page, cached for a day as the index itself is."""
    return json.loads(_cached(CACHE_DIR / name, SUBMISSIONS_PAGE_URL.format(name=name), user_agent))


def form4_filings_cached(cik: str, index: Mapping[str, object] | None, first: date, last: date,
                         ) -> tuple[list[tuple[str, date, str]], list[str]]:
    """(67) Every Form 4 filed in [first, last] across `recent` and the older pages ON DISK,
    with the names of the pages that are not.

    Fetches nothing. A page that is absent is returned rather than passed over, because an
    unread page is indistinguishable from a quiet quarter and the difference is the whole
    question."""
    import insiders as insiders_mod  # noqa: PLC0415

    if index is None:
        return [], []
    seen = dict.fromkeys(insiders_mod.form4_filings(index))
    absent: list[str] = []
    for name in submissions_pages(index, first, last):
        path = CACHE_DIR / name
        if not path.exists():
            absent.append(name)
            continue
        seen.update(dict.fromkeys(insiders_mod.form4_filings(json.loads(path.read_bytes()))))
    inside = [f for f in seen if first <= f[1] <= last]
    return sorted(inside, key=lambda x: (x[1], x[0]), reverse=True), absent


def insider_document(cik: str, accession: str, document: str, user_agent: str) -> bool:
    """(67) Put one Form 4 document in the cache if it is not there. True when it was fetched.

    A document is immutable once filed, so it is written once and kept for ever; the index is
    the only thing that ages. Raises on a transport error, which the caller counts and retries
    at a slower pace rather than treating as a filing that does not exist."""
    import insiders as insiders_mod  # noqa: PLC0415

    path = insiders_mod.CACHE_DIR / cik / f"{accession}.xml"
    if path.exists():
        return False
    body = _get(insiders_mod.document_url(cik, accession, document), user_agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return True


def insiders_cached(cik: str, filings: Iterable[tuple[str, date, str]],
                    ) -> tuple[list[insiders_mod.Transaction], Counter[str], int, int]:
    """(67) The Form 4 transactions in [filings] whose documents are already on disk.

    Fetches nothing. A study that walks four years of dates would otherwise become tens of
    thousands of requests, so the fetching lives in one place and this reads what that left.
    The count of documents the cache does not hold is returned rather than skipped in
    silence: a window missing one filing cannot be counted, because the missing one may be
    the only purchase."""
    import insiders as insiders_mod  # noqa: PLC0415

    transactions: list[insiders_mod.Transaction] = []
    excluded: Counter[str] = Counter()
    read = missing = 0
    for accession, filed, _document in filings:
        path = insiders_mod.CACHE_DIR / cik / f"{accession}.xml"
        if not path.exists():
            missing += 1
            continue
        found, codes = insiders_mod.parse_form4(path.read_bytes(), accession, filed, issuer_cik=cik)
        transactions += found
        excluded += codes
        read += 1
    return transactions, excluded, read, missing


def insiders_of(cik: str | None, index: Mapping[str, object] | None, as_of: date, user_agent: str) -> tuple[boundary.Insiders | None, str | None]:
    """(66) The Form 4 block for one name, from filings made on or before [as_of].

    A document is immutable once filed, so it is cached forever and never re-fetched; the
    index is what ages. The cut is on the FILING date, which the index carries and the
    document does not, so the point-in-time panel reads only what was public on its date."""
    import insiders as insiders_mod  # noqa: PLC0415

    if cik is None:
        return None, insiders_mod.NO_CIK
    if index is None:
        return None, "SEC submissions index unavailable"
    oldest = as_of - timedelta(days=max(insiders_mod.WINDOWS))
    wanted = [(accession, filed, document)
              for accession, filed, document in insiders_mod.form4_filings(index)
              if filed <= as_of and filed >= oldest - timedelta(days=INSIDER_FILING_LAG_DAYS)]
    transactions: list[insiders_mod.Transaction] = []
    excluded: Counter[str] = Counter()
    read = 0
    for accession, filed, document in wanted:
        path = insiders_mod.CACHE_DIR / cik / f"{accession}.xml"
        try:
            body = path.read_bytes() if path.exists() else _get(insiders_mod.document_url(cik, accession, document), user_agent)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            continue
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        found, codes = insiders_mod.parse_form4(body, accession, filed, issuer_cik=cik)
        transactions += found
        excluded += codes
        read += 1
    return insiders_mod.compute(transactions, excluded, as_of, cik, read)


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


class Accessions:
    """(61) Which filing a fiscal period's statement is read from.

    A period's values come from ONE accession, and the choice is the filing whose own
    fiscal year it is: the latest filing whose newest annual duration fact ends at that
    period. Comparative columns in a later filing are regrouped to that later year's
    presentation, and the tag map is per period, so taking the latest fact per tag
    independently mixes two presentations and double counts a line the newer filing
    folded into another (Apple FY2021: the FY2023 10-K's combined other-liabilities line
    taken beside the standalone contract-liability line the FY2022 10-K still carried).

    A period no filing reports as its own year -- a quarter end that leaks in as an
    instant, or a year whose filing is not in companyfacts -- falls back to the latest
    filing that carries it at all, which is the behaviour this replaces.

    [primary] is computed from duration facts only: a fact spanning about a year and
    ending at the period end belongs unambiguously to that year, while an instant may be
    dated after it (a subsequent event, a cover page).
    """

    def __init__(self, taxonomy_facts: Mapping[str, object], tags: reference.XbrlTags) -> None:
        lo, hi = tags.annual_span_days
        primary: dict[str, date] = {}          # accession -> the newest year it reports
        carried: dict[date, dict[str, str]] = {}   # period end -> accession -> filing date
        for node in taxonomy_facts.values():
            for entries in _as_dict(_as_dict(node).get("units")).values():
                for raw in cast(list[object], entries):
                    e = _as_dict(raw)
                    if str(e.get("form", "")) not in tags.annual_forms or e.get("fp") != "FY":
                        continue
                    try:
                        end = date.fromisoformat(str(e["end"]))
                        accn, filed = str(e["accn"]), str(e["filed"])
                    except (KeyError, ValueError):
                        continue
                    carried.setdefault(end, {})[accn] = filed
                    start = e.get("start")
                    if start is None:
                        continue
                    try:
                        span = (end - date.fromisoformat(str(start))).days
                    except ValueError:
                        continue
                    if lo <= span <= hi and (accn not in primary or end > primary[accn]):
                        primary[accn] = end
        self._primary = primary
        self._carried = carried
        self._chosen: dict[date, str] = {}
        self._fallback: set[date] = set()
        for end, accns in carried.items():
            own = [a for a in accns if primary.get(a) == end]
            if own:
                self._chosen[end] = max(own, key=lambda a: accns[a])
            else:
                self._chosen[end] = max(accns, key=lambda a: accns[a])
                self._fallback.add(end)

    def chosen(self, end: date) -> str | None:
        return self._chosen.get(end)

    def is_fallback(self, end: date) -> bool:
        """True when no filing reports the period as its own year, so the latest that
        carries it was taken instead."""
        return end in self._fallback

    def later_than(self, end: date) -> list[tuple[str, str]]:
        """Every accession filed after the chosen one that also carries the period, oldest
        first, as (accession, filing date)."""
        chosen = self._chosen.get(end)
        if chosen is None:
            return []
        at = self._carried[end]
        return sorted(((a, f) for a, f in at.items() if f > at[chosen]), key=lambda x: x[1])


def annual_facts(entries: Iterable[object], *, instant: bool, tags: reference.XbrlTags, notes: list[str], tag: str,
                 accessions: "Accessions | None" = None) -> dict[date, Fact]:
    """The annual fact per fiscal year end: annual-form facts marked FY whose duration spans
    about a year (or, for balances, carry no start). (61) With [accessions], the fact from
    that period's chosen filing and no other, so one period's values never mix two
    presentations; without it, the latest filed wins per end, which is what point-in-time
    passes when it has already narrowed the facts to a date."""
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
        if accessions is not None and accessions.chosen(fact.end) != fact.accn:
            continue
        if fact.end not in out or fact.filed > out[fact.end].filed:
            out[fact.end] = fact
    if rejected:
        notes.append(f"{tag}: {rejected} companyfacts entries rejected at validation")
    return out


def taxonomy_fields(tags: reference.XbrlTags, taxonomy: str) -> list[tuple[str, reference.XbrlField]]:
    return tags.ifrs_full_fields if taxonomy == "ifrs-full" else tags.fields


def select(gaap: Mapping[str, object], tags: reference.XbrlTags, notes: list[str], *, taxonomy: str = "us-gaap", unit: str = "USD", accessions: "Accessions | None" = None) -> dict[str, dict[date, tuple[Fact, str]]]:
    """Per canonical field, per fiscal year end: the first candidate tag with an annual fact
    in the filer's unit."""
    out: dict[str, dict[date, tuple[Fact, str]]] = {}
    for field, spec in taxonomy_fields(tags, taxonomy):
        per_end: dict[date, tuple[Fact, str]] = {}
        for tag in spec.tags:
            entries = _entries(gaap.get(tag), unit)
            if not entries:
                continue
            for end, fact in annual_facts(entries, instant=spec.kind == "instant", tags=tags, notes=notes, tag=tag, accessions=accessions).items():
                per_end.setdefault(end, (fact, tag))
        out[field] = per_end
    return out


Selected = Mapping[str, Mapping[date, tuple[Fact, str]]]


def value_of(selected: Selected, field: str, end: date) -> tuple[float | None, str | None]:
    hit = selected.get(field, {}).get(end)
    return (hit[0].val, hit[1]) if hit else (None, None)


DnaResult = tuple[float | None, str | None, list[boundary.Component] | None, str | None, boundary.Composition | None]


class CoverPage:
    """The newest cover-page share count filed on or before a date: ordinary shares, the tag,
    the cover page's own date and the filing date."""

    def __init__(self, shares: float, tag: str, as_of: str, filed: str) -> None:
        self.shares, self.tag, self.as_of, self.filed = shares, tag, as_of, filed


def cover_page_shares(facts: Mapping[str, object], on_or_before: date, tags: Iterable[str]) -> CoverPage | None:
    """(19, 42) The newest cover page filed on or before the date; a filer with several share
    classes files one entry per class under the same date, and distinct values on that date
    are summed."""
    dei = _as_dict(_as_dict(facts.get("facts")).get("dei"))
    for tag in tags:
        node = _as_dict(dei.get(tag))
        entries = [_as_dict(e) for e in cast(list[object], _as_dict(node.get("units")).get("shares", []))]
        dated = [(str(e["filed"]), str(e["end"]), float(cast(float, e["val"]))) for e in entries
                 if "filed" in e and "end" in e and "val" in e and str(e["filed"]) <= on_or_before.isoformat()]
        if dated:
            newest = max((filed, end) for filed, end, _ in dated)
            values = sorted({v for filed, end, v in dated if (filed, end) == newest})
            return CoverPage(sum(values), tag, newest[1], newest[0])
    return None


def depreciation_ifrs(facts: "Facts", defs: reference.FieldDefinitions, end: date) -> DnaResult:
    """IFRS D&A excluding impairment (32): the pure tag; else the inclusive tag less the
    impairment filed (total, else components) plus the reversal filed (total, else
    components), recorded as a recipe with every tag; else the plain adjustment tag as a
    total; else (40) the sum of the components, every one required.
    (value, row, candidates, recipe, composition)."""
    definition = defs.depreciation_amortization
    assert definition is not None
    d = definition.ifrs
    pure = facts.first(d.pure, end, instant=False)
    if pure is not None:
        return pure[0], pure[1], [boundary.Component(name="total", value=pure[0], row=pure[1])], "pure", None
    inclusive = facts.first(d.inclusive, end, instant=False)
    if inclusive is not None:
        parts = [boundary.Component(name="inclusive", value=inclusive[0], row=inclusive[1])]
        impairment = facts.first(d.impairment, end, instant=False)
        if impairment is not None:
            parts.append(boundary.Component(name="impairment", value=-impairment[0], row=impairment[1]))
        else:
            parts += [boundary.Component(name="impairment_component", value=-v, row=tag) for tag in d.impairment_components if (v := facts.at(tag, end, instant=False)) is not None]
        reversal = facts.first(d.reversal, end, instant=False)
        if reversal is not None:
            parts.append(boundary.Component(name="reversal", value=reversal[0], row=reversal[1]))
        else:
            parts += [boundary.Component(name="reversal_component", value=v, row=tag) for tag in d.reversal_components if (v := facts.at(tag, end, instant=False)) is not None]
        return sum(p.value for p in parts), _label(parts), None, "inclusive_less_impairment", _composition(definition.name, parts)
    candidates = [boundary.Component(name="total", value=v, row=tag) for tag in d.totals if (v := facts.at(tag, end, instant=False)) is not None]
    if candidates:
        taken = max(candidates, key=lambda c: c.value)
        return taken.value, taken.row, candidates, "total", None
    # (40) the component sum, every tag required: TSMC files DepreciationExpense and
    # AmortisationExpense and no total; the right-of-use depreciation is inside the former
    # (verified against the vendor's row, see the definition's notes) and is not added.
    parts = [boundary.Component(name="component", value=v, row=tag) for tag in d.components if (v := facts.at(tag, end, instant=False)) is not None]
    if d.components and len(parts) == len(d.components):
        return sum(p.value for p in parts), _label(parts), None, "sum_of_components_ifrs", _composition(definition.name, parts)
    return None, None, None, None, None


def depreciation(facts: "Facts", selected: Selected, tags: reference.XbrlTags, defs: reference.FieldDefinitions, end: date, *, taxonomy: str = "us-gaap") -> DnaResult:
    """D&A per the definition (27): every total tag present for the period is a candidate and
    the field is the largest, candidates recorded; under IFRS the recipe excludes impairment
    (32). (62) Below the totals, the filer's own cash-flow reconciliation before its notes,
    and the note pair only where it is complete or the filer has no intangibles to amortise.
    (value, row, candidates, recipe, composition)."""
    definition = defs.depreciation_amortization
    if definition is None:
        raise ValueError("field_definitions.json carries no depreciation_amortization definition")
    if taxonomy == "ifrs-full":
        return depreciation_ifrs(facts, defs, end)
    d = definition.xbrl
    candidates = [boundary.Component(name="total", value=v, row=tag) for tag in d.totals if (v := facts.at(tag, end, instant=False)) is not None]
    if candidates:
        taken = max(candidates, key=lambda c: c.value)
        return taken.value, taken.row, candidates, None, None
    # (62) with no total filed, the filer's own cash-flow reconciliation before its notes:
    # the combined depreciation-and-amortisation line, with the amortisation line beside it
    # when that is filed separately. Never a candidate under the largest rule, so it cannot
    # displace a total.
    amortization_line = facts.first(d.amortization_line, end, instant=False)
    combined = facts.first(d.combined_line, end, instant=False)
    if combined is not None:
        cash_flow = [boundary.Component(name="combined_line", value=combined[0], row=combined[1])]
        if amortization_line is not None:
            cash_flow.append(boundary.Component(name="amortization_line", value=amortization_line[0], row=amortization_line[1]))
        return sum(p.value for p in cash_flow), _label(cash_flow), None, "cash_flow_lines", _composition(definition.name, cash_flow)
    # The note pair. Depreciation alone is the whole field only for a filer with no
    # intangibles to amortise: with a finite-lived intangibles balance filed and no
    # amortisation tagged anywhere, the line exists and is untagged, and the period fails.
    declared = list(tags.depreciation_components)
    depreciation_field = declared[0] if declared else ""
    amortization_field = declared[1] if len(declared) > 1 else ""
    value, row = value_of(selected, depreciation_field, end) if depreciation_field else (None, None)
    if value is None:
        return None, None, None, None, None
    parts = [boundary.Component(name="depreciation", value=value, row=row or depreciation_field)]
    note = value_of(selected, amortization_field, end) if amortization_field else (None, None)
    if amortization_line is not None:
        parts.append(boundary.Component(name="amortization_line", value=amortization_line[0], row=amortization_line[1]))
    elif note[0] is not None:
        parts.append(boundary.Component(name="amortization", value=note[0], row=note[1] or amortization_field))
    elif facts.first(d.finite_lived_intangibles, end, instant=True) is not None:
        return None, None, None, None, None
    # The note pair carries no recipe: the row names both elements and there is nothing a
    # recipe would add, and a period whose value does not move must not grow a field.
    return sum(p.value for p in parts), _label(parts), None, None, None


class Facts:
    """A filer's us-gaap facts with annual selection per tag, memoised, for the fields
    reference/field_definitions.json assembles from more than one tag."""

    def __init__(self, gaap: Mapping[str, object], tags: reference.XbrlTags, notes: list[str], *, unit: str = "USD",
                 accessions: "Accessions | None" = None) -> None:
        self._gaap = gaap
        self._tags = tags
        self._notes = notes
        self._unit = unit
        self._accessions = accessions   # (61) one filing per period, or None to take the latest filed
        self._memo: dict[tuple[str, bool, str], dict[date, Fact]] = {}

    def annual(self, tag: str, *, instant: bool, unit: str | None = None) -> dict[date, Fact]:
        """The tag's annual facts in the filer's currency unit, or in [unit] (e.g. shares)."""
        key = (tag, instant, unit or self._unit)
        if key not in self._memo:
            entries = _entries(self._gaap.get(tag), unit or self._unit)
            self._memo[key] = annual_facts(entries, instant=instant, tags=self._tags, notes=self._notes, tag=tag,
                                           accessions=self._accessions)
        return self._memo[key]

    def at(self, tag: str, end: date, *, instant: bool, unit: str | None = None) -> float | None:
        fact = self.annual(tag, instant=instant, unit=unit).get(end)
        return None if fact is None else fact.val

    def first(self, candidates: Iterable[str], end: date, *, instant: bool, unit: str | None = None) -> tuple[float, str] | None:
        for tag in candidates:
            value = self.at(tag, end, instant=instant, unit=unit)
            if value is not None:
                return value, tag
        return None

    @property
    def per_share_unit(self) -> str:
        """(59) The unit a per-share fact carries: the filer's currency over shares. A
        per-share tag read in the plain currency unit silently finds nothing."""
        return f"{self._unit}/shares"

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
    # (62) the aggregate that already carries the short-term investments is searched last, so
    # no period that resolves on a cash-equivalents element moves; where it supplies the
    # value the component is not added again, and the part says so.
    equivalents = facts.first(d.cash_equivalents, end, instant=True)
    inclusive = equivalents is None
    if inclusive:
        equivalents = facts.first(d.investments_inclusive, end, instant=True)
    if equivalents is None:
        return None, None, None
    value, tag = equivalents
    parts = [boundary.Component(name="cash_and_investments" if inclusive else "cash_equivalents", value=value, row=tag)]
    if tag in d.restricted_inclusive:
        for alternative in d.restricted_cash:
            found = [(facts.at(t, end, instant=True), t) for t in alternative]
            if all(v is not None for v, _ in found):
                parts.extend(boundary.Component(name="restricted_cash", value=-v, row=t) for v, t in found if v is not None)
                break
    investments = None if inclusive else facts.first(d.short_term_investments, end, instant=True)
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


DEBT_FREE = "no debt line filed and no interest expense filed; taken as 0"


def interest_evidence(facts: Facts, defs: reference.FieldDefinitions, params: reference.Params, end: date) -> tuple[bool, str]:
    """(65) Whether the interest a filer tags is evidence that it owes something, and why.

    The absent-is-zero rule (25) asks the filing to say twice that a filer owes nothing: no
    debt line, and no interest. A trace of interest is not that second saying. Interest is
    evidence only when it is an expense -- a net figure that is income never is, whatever
    its size -- and when it exceeds interest_evidence_floor of operating income. The floor
    needs a scale: with no operating income filed, or a loss, there is nothing to measure
    against and the evidence stands."""
    d = defs.total_debt.xbrl
    hit = facts.first(d.interest_evidence, end, instant=False)
    if hit is None:
        return False, DEBT_FREE
    value, tag = hit
    if value <= 0.:
        return False, f"no debt line filed and {tag} is interest income, not an expense; taken as 0"
    operating = facts.first(defs.ebit.xbrl.operating_income, end, instant=False)
    if operating is None or operating[0] <= 0.:
        return True, ""
    floor = params.interest_evidence_floor.value
    share = value / operating[0]
    if share >= floor:
        return True, ""
    return False, (
        f"no debt line filed and the only interest filed, {tag}, is {share * 100:.2f}% of "
        f"operating income, below the {floor * 100:.2f}% floor; taken as 0")


def no_distributions_filed(facts: Facts, tags: reference.XbrlTags, end: date) -> bool | None:
    """(65) Whether the filing says, for this period, that it distributed nothing.

    An absent dividend tag cannot distinguish "none" from "not filed". The cash-flow
    statement's financing subtotal is what settles it: with the section filed and no
    dividend or distribution element of any kind present, the filer has said it paid none.
    None where the financing section is not filed, so the caller keeps its existing refusal
    rather than reading silence as a statement."""
    if not tags.financing_section or not tags.dividend_evidence:
        return None
    if all(facts.at(tag, end, instant=False) is None for tag in tags.financing_section):
        return None
    # (69) preferred elements are not in this list any more: a preferred dividend goes to a
    # claim senior to common, and residual income values common equity, so its presence says
    # nothing about whether the common holder was distributed to. The elements themselves are
    # still declared, under preferred_dividend_evidence, and are read as their own field.
    if any(facts.at(tag, end, instant=False) is not None for tag in tags.dividend_evidence):
        return None
    return True


def preferred_equity_of(value: float | None, row: str | None) -> tuple[float | None, str | None]:
    """(69) The preferred carrying value inside stockholders' equity, or nothing.

    **A par-value line of zero is not a carrying value.** PNC, MET and UNH file
    `PreferredStockValue` at exactly 0.0, and PNC and MET carry real preferred: the tag is the
    par line for authorised shares, not the amount on the balance sheet. Taking the zero would
    report a deduction that did not happen, which is worse than reporting none, so a
    non-positive figure does not resolve the field and the record says the filing carries no
    carrying value."""
    return (value, row) if value is not None and value > 0. else (None, None)


def common_dividends_of(common: float | None, common_row: str | None, total: float | None,
                        preferred: float | None) -> tuple[float | None, str | None]:
    """(69) Dividends to common holders: the filed common element, else the total less the
    filed preferred dividends, the recipe recorded.

    The same shape as the income rule, and for the same reason: JPMorgan, Goldman Sachs and
    Morgan Stanley file `PaymentsOfDividends`, which is common AND preferred, so a payout
    ratio built on it over an income figure that is common-only would be a ratio of two
    different things."""
    if common is not None:
        return common, common_row
    if total is None or preferred is None:
        return None, None
    return max(0., total - preferred), "dividends_paid - preferred_dividends"


def redeemable_preferred(facts: Facts, tags: reference.XbrlTags, end: date) -> bool | None:
    """(69) Whether the filer's preferred is redeemable, and so outside stockholders' equity.

    Redeemable preferred is mezzanine equity: it sits between liabilities and equity on the
    balance sheet and was never inside the book the common holder owns. Deducting it would
    take out something that is not in there. SoFi is the case -- its only `PreferredStockValue`
    fact ever filed is a single quarterly instant from 2020 -- and its income is still the
    common holder's after the preferred dividend, so the income moves and the book does not."""
    if not tags.redeemable_preferred_evidence:
        return None
    found = any(facts.at(tag, end, instant=False) is not None
                or facts.at(tag, end, instant=True) is not None
                for tag in tags.redeemable_preferred_evidence)
    return True if found else None


def total_debt(facts: Facts, defs: reference.FieldDefinitions, params: reference.Params, end: date) -> Derived:
    """Financial debt, first complete recipe: the filer's aggregate (+ convertible notes
    beside it); noncurrent + all current debt as one tag; noncurrent + the current portion
    of long-term debt (+ short-term borrowings when tagged); long-term debt filed with its
    current portion (+ short-term borrowings); else the sum of every component present,
    one per kind (31). Operating lease tags are never read."""
    d = defs.total_debt.xbrl
    aggregate = facts.first(d.aggregate, end, instant=True)
    convertible = facts.first(d.convertible, end, instant=True)
    noncurrent = facts.first(d.noncurrent, end, instant=True)
    current_total = facts.first(d.current_total, end, instant=True)
    current_long_term = facts.first(d.current_long_term, end, instant=True)
    short_term = facts.first(d.short_term_borrowings, end, instant=True)
    total_including_current = facts.first(d.total_including_current, end, instant=True)

    def part(name: str, hit: tuple[float, str]) -> boundary.Component:
        return boundary.Component(name=name, value=hit[0], row=hit[1])

    parts: list[boundary.Component]
    if aggregate is not None:
        # (0) the filer's own aggregate, plus convertible notes carried beside it (25)
        parts = [part("aggregate", aggregate)]
        if convertible is not None:
            parts.append(part("convertible", convertible))
    elif noncurrent is not None and current_total is not None:
        parts = [part("noncurrent", noncurrent), part("current_total", current_total)]
    elif noncurrent is not None and current_long_term is not None:
        parts = [part("noncurrent", noncurrent), part("current_long_term", current_long_term)]
        if short_term is not None:
            parts.append(part("short_term_borrowings", short_term))
    elif total_including_current is not None:
        parts = [part("total_including_current", total_including_current)]
        if short_term is not None:
            parts.append(part("short_term_borrowings", short_term))
    elif any(x is not None for x in (noncurrent, current_long_term, short_term, convertible)):
        # (4) component sum (31): no aggregate and no complete pair, so every component the
        # filer tags, one per kind; a filer with fewer instruments is not missing data
        parts = [part(name, hit) for name, hit in (("noncurrent", noncurrent), ("current_long_term", current_long_term),
                                                   ("short_term_borrowings", short_term), ("convertible", convertible)) if hit is not None]
    elif all(x is None for x in (current_total, total_including_current)):
        # absent is zero only when the filing says so twice (25): no debt line, and no
        # interest that is evidence of one (65).
        evidence, source = interest_evidence(facts, defs, params, end)
        if evidence:
            return None, None, None
        return 0.0, source, _composition(defs.total_debt.name, [])
    else:
        return None, None, None
    return sum(p.value for p in parts), _label(parts), _composition(defs.total_debt.name, parts)


def delta_nwc(facts: Facts, defs: reference.FieldDefinitions, end: date, notes: list[str]) -> Derived:
    """The filed change in operating working capital: the aggregate tag, else the sum of
    the components (assets and net balances added, liabilities subtracted), attempted only
    when every IncreaseDecreaseIn tag the filer carries for the period is classified."""
    d = defs.delta_nwc.xbrl
    aggregate = facts.first(d.aggregate, end, instant=False)
    if aggregate is not None:
        parts = [boundary.Component(name="aggregate", value=aggregate[0], row=aggregate[1])]
        return aggregate[0], aggregate[1], _composition(defs.delta_nwc.name, parts)
    present = facts.duration_tags_with_prefix("IncreaseDecreaseIn", end)
    classified = set(d.aggregate) | set(d.asset_components) | set(d.liability_components) | set(d.net_components) | set(d.excluded)
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
    for tag in d.net_components:  # a net asset: asset-signed (25)
        value = facts.at(tag, end, instant=False)
        if value is not None:
            parts.append(boundary.Component(name="net_components", value=value, row=tag))
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


FINANCING_LEASES = "the filer's leases are financing receivables; NAREIT FFO does not apply"


def ffo(facts: Facts, defs: reference.FieldDefinitions, end: date, *, taxonomy: str = "us-gaap") -> tuple[float | None, str | None, boundary.Composition | None, str | None]:
    """FFO per NAREIT: net income + real-estate depreciation + impairment - gains on property
    sales; the first two required, the last two taken as 0 when not filed and recorded so.
    (54) A filer whose properties are net investments in leases files no real-estate
    depreciation to add back, so the measure does not apply and the absence carries that
    reason rather than the name of a tag. (value, row, composition, unavailable)."""
    d = defs.ffo.ifrs if taxonomy == "ifrs-full" else defs.ffo.xbrl
    net_income = facts.first(d.net_income, end, instant=False)
    # the largest filed total (27), inside the recipe as on the dcf path (31)
    candidates = [(v, tag) for tag in d.depreciation if (v := facts.at(tag, end, instant=False)) is not None]
    depreciation = max(candidates, key=lambda c: c[0]) if candidates else None
    # (54) the balance and the interest earned on it, both required: a lessor position
    # alone is something any investor may hold.
    balance = any(facts.at(tag, end, instant=True) is not None for tag in d.financing_lease_evidence)
    income = facts.first(d.financing_lease_income, end, instant=False) is not None
    if depreciation is None and balance and income:
        return None, None, None, FINANCING_LEASES
    if net_income is None or depreciation is None:
        return None, None, None, None
    parts = [boundary.Component(name="net_income", value=net_income[0], row=net_income[1]),
             boundary.Component(name="real_estate_depreciation", value=depreciation[0], row=depreciation[1])]
    impairment = facts.first(d.impairment, end, instant=False)
    parts.append(boundary.Component(name="real_estate_impairment", value=impairment[0] if impairment else 0.0, row=impairment[1] if impairment else "not filed, taken as 0"))
    gains = facts.first(d.gains, end, instant=False)
    parts.append(boundary.Component(name="gain_on_property_sales", value=-gains[0] if gains else 0.0, row=gains[1] if gains else "not filed, taken as 0"))
    return sum(p.value for p in parts), _label(parts), _composition(defs.ffo.name, parts), None


BdcLines = tuple[
    tuple[float, str, "boundary.Composition | None"] | None,   # net asset value per share
    tuple[float, str, "boundary.Composition | None"] | None,   # net investment income
    tuple[float, str] | None,                                  # distributions per share
]


def bdc_lines(facts: Facts, defs: reference.FieldDefinitions, end: date) -> BdcLines:
    """(59) The three filed lines the BDC lens reads, each taken AT the fiscal period end
    and never as the newest instant: the tag carries quarter-end instants filed under form
    10-K with fp FY, from the financial-highlights table. Net asset value per share as
    filed, else net assets over shares outstanding with both tags recorded; net investment
    income as the filer's own line, else total investment income less total expenses;
    distributions per share, declared or paid."""
    definition = defs.bdc
    if definition is None:
        return (None, None, None)
    d = definition.xbrl

    nav: tuple[float, str, boundary.Composition | None] | None = None
    filed = facts.first(d.net_asset_value_per_share, end, instant=True, unit=facts.per_share_unit)
    if filed is not None:
        nav = (filed[0], filed[1], None)
    else:
        assets = facts.first(d.net_assets, end, instant=True)
        count = facts.first(d.shares_outstanding, end, instant=True, unit="shares")
        if assets is not None and count is not None and count[0] > 0:
            parts = [boundary.Component(name="net_assets", value=assets[0], row=assets[1]),
                     boundary.Component(name="shares_outstanding", value=count[0], row=count[1])]
            nav = (assets[0] / count[0], f"{assets[1]} / {count[1]}", _composition(definition.name, parts))

    nii: tuple[float, str, boundary.Composition | None] | None = None
    line = facts.first(d.net_investment_income, end, instant=False)
    if line is not None:
        nii = (line[0], line[1], None)
    else:
        income = facts.first(d.total_investment_income, end, instant=False)
        expense = facts.first(d.total_expenses, end, instant=False)
        if income is not None and expense is not None:
            parts = [boundary.Component(name="total_investment_income", value=income[0], row=income[1]),
                     boundary.Component(name="total_expenses", value=-expense[0], row=expense[1])]
            nii = (income[0] - expense[0], f"{income[1]} - {expense[1]}", _composition(definition.name, parts))

    dps = facts.first(d.distributions_per_share, end, instant=False, unit=facts.per_share_unit)
    return (nav, nii, (dps if dps is None else (dps[0], dps[1])))


def aoci(facts: Facts, defs: reference.FieldDefinitions, end: date, filed: tuple[float | None, str | None]) -> tuple[float | None, str | None, str | None, boundary.Composition | None]:
    """AOCI (31): the filed aggregate, else the sum of the filed components with the recipe
    recorded. (value, row, recipe, composition)."""
    if filed[0] is not None:
        return filed[0], filed[1], "filed", None
    definition = defs.aoci
    if definition is None:
        return None, None, None, None
    parts = [boundary.Component(name="component", value=v, row=tag) for tag in definition.xbrl.components if (v := facts.at(tag, end, instant=True)) is not None]
    if not parts:
        return None, None, None, None
    return sum(p.value for p in parts), _label(parts), "sum_of_components", _composition(definition.name, parts)


def interest_expense(facts: Facts, defs: reference.FieldDefinitions, end: date, *, taxonomy: str = "us-gaap") -> tuple[float | None, str | None, str | None]:
    """Interest expense per period (25, 31): the ebit definition's filed line, else a net
    non-operating interest figure negated into an expense, else cash interest paid; the
    recipe recorded. (value, row, recipe)."""
    filed = facts.first(defs.ebit.ifrs.interest_expense if taxonomy == "ifrs-full" else defs.ebit.xbrl.interest_expense, end, instant=False)
    if filed is not None:
        return filed[0], filed[1], "filed"
    definition = defs.interest_expense
    if definition is None or taxonomy == "ifrs-full":
        return None, None, None
    net = facts.first(definition.xbrl.net_nonoperating, end, instant=False)
    if net is not None:
        return -net[0], net[1], "net_nonoperating_interest"
    paid = facts.first(definition.xbrl.paid, end, instant=False)
    if paid is not None:
        return paid[0], paid[1], "interest_paid_stands_in"
    return None, None, None


def weighted_shares(facts: Facts, defs: reference.FieldDefinitions, end: date, *, taxonomy: str = "us-gaap") -> tuple[float, str] | None:
    """The period's weighted-average diluted share count, else basic (its tag recorded):
    the only count a flow per share may use (shares_for_flows)."""
    tags = defs.shares_for_flows.ifrs if taxonomy == "ifrs-full" else defs.shares_for_flows.xbrl
    return facts.first(tags, end, instant=False, unit="shares")


_read_tags: frozenset[str] | None = None


def read_tag_names() -> frozenset[str]:
    """(61) Every XBRL element the two tracked reference files name, harvested once. A
    restatement is worth recording only for a tag the record actually reads, and the two
    files are where every such tag is declared, so harvesting them keeps the set correct
    as the tables grow rather than needing a third list to maintain."""
    global _read_tags
    if _read_tags is None:
        found: set[str] = set()

        def walk(node: object) -> None:
            if isinstance(node, dict):
                for v in cast(dict[str, object], node).values():
                    walk(v)
            elif isinstance(node, list):
                for v in cast(list[object], node):
                    walk(v)
            elif isinstance(node, str) and node[:1].isupper() and node.isalnum() and len(node) > 6:
                found.add(node)

        for path in (TAGS_PATH, DEFINITIONS_PATH):
            walk(cast(object, json.loads(path.read_text())))
        _read_tags = frozenset(found)
    return _read_tags


def restatements(taxonomy_facts: Mapping[str, object], accessions: Accessions, end: date, unit: str) -> list[boundary.Restatement]:
    """(61) Every tag the record reads where a filing later than the chosen one carries this
    period with a different value. Recorded, never taken."""
    later = accessions.later_than(end)
    if not later:
        return []
    filed_of = dict(later)
    chosen = accessions.chosen(end)
    out: list[boundary.Restatement] = []
    for tag in sorted(read_tag_names()):
        node = taxonomy_facts.get(tag)
        if node is None:
            continue
        taken: float | None = None
        others: dict[str, float] = {}
        for entries in _as_dict(_as_dict(node).get("units")).values():
            for raw in cast(list[object], entries):
                e = _as_dict(raw)
                if str(e.get("end", "")) != end.isoformat() or e.get("fp") != "FY":
                    continue
                try:
                    value, accn = float(cast(float, e["val"])), str(e["accn"])
                except (KeyError, TypeError, ValueError):
                    continue
                if accn == chosen:
                    taken = value
                elif accn in filed_of:
                    others[accn] = value
        if taken is None:
            continue
        for accn, value in sorted(others.items(), key=lambda kv: filed_of[kv[0]]):
            if value != taken:
                out.append(boundary.Restatement(tag=tag, taken=taken, later=value, accession=accn, filed=filed_of[accn]))
    return out


RECONCILES_EXACTLY = 0.005   # the components and the filer's own aggregate agree to within half a per cent


def reconciled_to_aggregate(facts: Facts, defs: reference.FieldDefinitions, end: date) -> tuple[bool | None, float | None]:
    """(61) Where a filer tags BOTH its own working-capital aggregate and the components
    that make it up, the two must agree. Both numbers are the filer's own, for the same
    period, out of the same filing, so the check needs no knowledge of the statement's
    structure — and it is exactly the identity a period assembled from two filings breaks,
    which is the class of defect this brief fixed.

    The record takes the aggregate where there is one, so the component sum is computed
    here only to check it and is never used as a value. Absent where the filer tags no
    aggregate, or tags no components beside it, or carries a working-capital tag the table
    does not classify. Never a gate."""
    d = defs.delta_nwc.xbrl
    aggregate = facts.first(d.aggregate, end, instant=False)
    if aggregate is None:
        return (None, None)
    present = facts.duration_tags_with_prefix("IncreaseDecreaseIn", end)
    classified = set(d.aggregate) | set(d.asset_components) | set(d.liability_components) | set(d.net_components) | set(d.excluded)
    components = [t for t in present if t not in d.aggregate and t not in d.excluded]
    if not components or any(t not in classified for t in present):
        return (None, None)
    total = 0.0
    for tag in components:
        value = facts.at(tag, end, instant=False)
        if value is None:
            continue
        total += -value if tag in d.liability_components else value
    gap = total - aggregate[0]
    return (abs(gap) <= RECONCILES_EXACTLY * max(abs(aggregate[0]), 1.0), gap)


def periods_from_facts(gaap: Mapping[str, object], tags: reference.XbrlTags, defs: reference.FieldDefinitions, notes: list[str], *, taxonomy: str = "us-gaap", unit: str = "USD", depth: int = PERIODS_DEFAULT, one_accession: bool = True, params: "reference.Params | None" = None) -> list[boundary.FiscalPeriod]:
    """[depth] is the number of annual periods kept, newest first: the model's need (periods_needed), never a constant."""
    ifrs = taxonomy == "ifrs-full"
    # (61) one filing per fiscal period, chosen before any tag is read. [one_accession] is
    # False only to reproduce the superseded latest-filed-per-tag rule for a diff.
    declared_params = params if params is not None else load_params()
    accessions = Accessions(gaap, tags) if one_accession else None
    selected = select(gaap, tags, notes, taxonomy=taxonomy, unit=unit, accessions=accessions)
    facts = Facts(gaap, tags, notes, unit=unit, accessions=accessions)
    # The fiscal year ends the filer anchors. Net income with book equity for every filer
    # that reports one; (59) a business development company's net asset value per share
    # stands in beside it, because two of the three verified stop tagging net income (and
    # one tags its realised-gain line under that element), which would otherwise leave the
    # newest years out. No other filer carries the tag, so no other filer's set moves.
    nav_tags: list[str] = list(defs.bdc.xbrl.net_asset_value_per_share) if defs.bdc is not None else []
    nav_ends: set[date] = set()
    for tag in nav_tags:
        nav_ends |= set(facts.annual(tag, instant=True, unit=facts.per_share_unit))
    anchored = set(selected["net_income"]) & set(selected["book_equity"])
    ends = sorted(anchored | (nav_ends & set(selected["book_equity"])), reverse=True)[:depth]

    def anchor_for(end: date) -> Fact:
        hit = selected["net_income"].get(end)
        if hit is not None:
            return hit[0]
        for tag in nav_tags:
            fact = facts.annual(tag, instant=True, unit=facts.per_share_unit).get(end)
            if fact is not None:
                return fact
        raise KeyError(end)  # unreachable: end came from one of the two sets

    periods: list[boundary.FiscalPeriod] = []
    for end in ends:
        anchor = anchor_for(end)
        v: dict[str, float | None] = {}
        r: dict[str, str | None] = {}
        for field, _ in taxonomy_fields(tags, taxonomy):
            v[field], r[field] = value_of(selected, field, end)
        dna, dna_row, dna_candidates, dna_recipe, dna_composition = depreciation(facts, selected, tags, defs, end, taxonomy=taxonomy)
        if ifrs:
            cash_value, cash_row, cash_composition = cash_ifrs(facts, defs, end)
            debt, debt_row, debt_composition = total_debt_ifrs(facts, defs, end)
            nwc, nwc_row, nwc_composition = delta_nwc_ifrs(facts, defs, end, notes)
            if v["net_interest_income"] is None:
                v["net_interest_income"], r["net_interest_income"] = net_interest_income_recipe(facts, tags.ifrs_full_net_interest_income, end)
        else:
            cash_value, cash_row, cash_composition = cash(facts, defs, end)
            debt, debt_row, debt_composition = total_debt(facts, defs, declared_params, end)
            nwc, nwc_row, nwc_composition = delta_nwc(facts, defs, end, notes)
        ebit_value, ebit_row, ebit_recipe, ebit_composition = ebit(facts, defs, end, v["pretax_income"], r["pretax_income"], taxonomy=taxonomy)
        ffo_value, _, ffo_composition, ffo_unavailable = ffo(facts, defs, end, taxonomy=taxonomy)
        nav_line, nii_line, dps_line = bdc_lines(facts, defs, end) if not ifrs else (None, None, None)
        # (61) what a later filing says about this period, recorded and not taken; and
        # whether the filed operating section adds up as this tool reads it
        restated = restatements(gaap, accessions, end, unit) if (not ifrs and accessions is not None) else []
        reconciled, wc_gap = reconciled_to_aggregate(facts, defs, end) if not ifrs else (None, None)
        shares = weighted_shares(facts, defs, end, taxonomy=taxonomy)
        interest_value, interest_row, interest_recipe = interest_expense(facts, defs, end, taxonomy=taxonomy)
        aoci_value, aoci_row, aoci_recipe, aoci_composition = aoci(facts, defs, end, (v["aoci"], r["aoci"]))
        preferred_value, preferred_row = preferred_equity_of(v["preferred_equity"], r["preferred_equity"])
        common_dividends, common_dividends_row = common_dividends_of(
            v["common_dividends_paid"], r["common_dividends_paid"], v["dividends_paid"], v["preferred_dividends"])
        periods.append(
            boundary.FiscalPeriod(
                period_end=end.isoformat(),
                ebit=ebit_value, pretax_income=v["pretax_income"], tax_provision=v["tax_provision"],
                total_revenue=v["total_revenue"], net_interest_income=v["net_interest_income"],
                premiums_earned=v["premiums_earned"], premiums_earned_row=r["premiums_earned"],
                depreciation_amortization=dna, depreciation_amortization_row=dna_row, depreciation_amortization_candidates=dna_candidates,
                depreciation_amortization_recipe=dna_recipe, depreciation_amortization_composition=dna_composition,
                capex=v["capex"], delta_nwc=nwc, cash=cash_value,
                total_debt=debt, total_debt_source=debt_row,
                book_equity=v["book_equity"], net_income=v["net_income"],
                dividends_paid=v["dividends_paid"], dividends_paid_row=r["dividends_paid"],
                # (69) the common-only side, read on every filed period and used by the
                # residual-income path alone; nothing above or below this line changes
                net_income_to_common=v["net_income_to_common"], net_income_to_common_row=r["net_income_to_common"],
                preferred_equity=preferred_value, preferred_equity_row=preferred_row,
                preferred_dividends=v["preferred_dividends"], preferred_dividends_row=r["preferred_dividends"],
                preferred_outside_equity=None if ifrs else redeemable_preferred(facts, tags, end),
                common_dividends_paid=common_dividends, common_dividends_paid_row=common_dividends_row,
                provision_for_credit_losses=None, provision_for_credit_losses_row=None,
                net_loans=None, net_loans_row=None,
                filed=anchor.filed.isoformat(), accession=anchor.accn,
                restated_from=restated, no_distributions_filed=None if ifrs else no_distributions_filed(facts, tags, end),
                working_capital_reconciled=reconciled, working_capital_gap=wc_gap,
                aoci=aoci_value, aoci_row=aoci_row, aoci_recipe=aoci_recipe, aoci_composition=aoci_composition,
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
                ebit_recipe=ebit_recipe, ebit_composition=ebit_composition,
                interest_expense=interest_value, interest_expense_row=interest_row, interest_recipe=interest_recipe,
                cash_composition=cash_composition,
                total_debt_composition=debt_composition, delta_nwc_composition=nwc_composition,
                ffo=ffo_value, ffo_composition=ffo_composition, ffo_unavailable=ffo_unavailable,
                net_asset_value_per_share=None if nav_line is None else nav_line[0],
                net_asset_value_per_share_row=None if nav_line is None else nav_line[1],
                net_asset_value_composition=None if nav_line is None else nav_line[2],
                net_investment_income=None if nii_line is None else nii_line[0],
                net_investment_income_row=None if nii_line is None else nii_line[1],
                net_investment_income_composition=None if nii_line is None else nii_line[2],
                distributions_per_share=None if dps_line is None else dps_line[0],
                distributions_per_share_row=None if dps_line is None else dps_line[1],
                weighted_shares=None if shares is None else shares[0], weighted_shares_tag=None if shares is None else shares[1],
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
