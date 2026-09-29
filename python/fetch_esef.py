"""ESEF filings (73): the annual reports that issuers listed on an EU, EEA or UK regulated
market must file in Inline XBRL under the European Single Electronic Format, aggregated
keyless at filings.xbrl.org and read here for a name with no SEC filer whose universe entry
declares its Legal Entity Identifier. Declared, never resolved: the vendor's ISIN lookup
returns nothing for half the names and a wrong code for one, and an LEI is a fact about
the filer that a human reads once from the filer's own report.

The index (`/api/filings`, JSON:API, filtered on the LEI) names every report with its
period end, country, the date it was added, the xBRL-JSON facts and the report package.
An annual report is one whose facts carry a duration of about a year ending at its period
end; interim reports (Novo Nordisk files quarterlies in the same format) are left out and
named. Two reports for one period end (a dual listing files twice, AstraZeneca in GB and
SE) resolve to the earlier-added one, the other named.

The facts are read into the shape companyfacts uses, so fetch_sec.periods_from_facts
reads them under the ifrs-full section of the definitions with no second reader: one
period per fiscal year from its own report (61), the tag behind every number, the
restatement scan, the cross-check against the vendor beside it. A fact with any
dimension beyond the core five is a breakdown, not a statement line, and is skipped; a
fact in a unit that is not a currency is skipped; an extension concept is skipped unless
it is anchored. ESEF requires an issuer that extends the taxonomy to anchor the extension
to the closest wider standard concept (arcrole wider-narrower in its definition
linkbase), and that declaration is read from the report package: where a report tags no
standard fact for a concept a chain reads and does tag an extension anchored to that one
concept as narrower, the extension's value is read under the standard concept and the
substitution is written into the record's notes, because a narrower line is at most the
wider one and the reader is told which line stood in. An extension anchored to several
wider concepts, or to none, is left unread; a standard fact present in the same report
always wins.

Nothing fetched is tracked: the index is cached for a day and each report's facts and
definition linkbase for ever, under data/esef/. The package (tens of megabytes of
rendered report) is streamed to a temporary file for its linkbase and removed."""

from __future__ import annotations

import json
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "data" / "esef"
HOST = "https://filings.xbrl.org"
CACHE_SECONDS = 86400
USER_AGENT = "atemoya fetch_esef (https://github.com/cb-g/atemoya)"
PROVIDER = "ESEF filings (filings.xbrl.org)"
TAXONOMY = "ifrs-full"
FORM = "ESEF"  # the form name the facts carry, listed in xbrl_tags.json's annual_forms
CORE_DIMENSIONS = frozenset({"concept", "entity", "period", "unit", "language"})
WIDER_NARROWER = "http://www.esma.europa.eu/xbrl/esef/arcrole/wider-narrower"
XLINK = "{http://www.w3.org/1999/xlink}"
CURRENCY_PREFIX = "iso4217:"
STANDARD_PREFIX = TAXONOMY + ":"


@dataclass(frozen=True)
class Filing:
    fxo_id: str
    period_end: date
    country: str
    date_added: date
    json_url: str | None
    package_url: str | None


@dataclass
class Adapted:
    """The facts in companyfacts shape, the currency they are in, the reports they came
    from newest first, and every note a reader should see."""
    gaap: dict[str, object]
    currency: str | None
    filings: list[Filing]
    notes: list[str] = field(default_factory=lambda: [])
    substitutions: int = 0


# --- the network edge and the cache -----------------------------------------------------

_last_request = 0.0


def _get(url: str, timeout: int = 300) -> bytes:
    """One request, paced to two a second; filings.xbrl.org asks for nothing more."""
    global _last_request
    wait = 0.5 - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/zip, */*"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return cast(bytes, response.read())
    finally:
        _last_request = time.monotonic()


def _cached(path: Path, url: str, *, max_age: float | None) -> bytes:
    """[max_age] None: immutable once written (a report never changes); a number: refetched
    after that many seconds (the index grows)."""
    if path.exists() and (max_age is None or time.time() - path.stat().st_mtime < max_age):
        return path.read_bytes()
    body = _get(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def index_url(lei: str) -> str:
    query = json.dumps([{"name": "entity.identifier", "op": "eq", "val": lei}], separators=(",", ":"))
    return f"{HOST}/api/filings?filter={urllib.parse.quote(query)}&page%5Bsize%5D=100"


def parse_index(body: bytes) -> list[Filing]:
    """Every report the index lists for the filer, oldest first; a row missing its period
    end or its date is skipped."""
    raw = cast(Mapping[str, object], json.loads(body))
    out: list[Filing] = []
    for row in cast(list[Mapping[str, object]], raw.get("data") or []):
        a = cast(Mapping[str, object], row.get("attributes") or {})
        try:
            period_end = date.fromisoformat(str(a["period_end"])[:10])
            added = date.fromisoformat(str(a["date_added"])[:10])
        except (KeyError, ValueError):
            continue
        out.append(Filing(fxo_id=str(a.get("fxo_id") or ""), period_end=period_end, country=str(a.get("country") or ""),
                          date_added=added, json_url=cast(str | None, a.get("json_url")), package_url=cast(str | None, a.get("package_url"))))
    return sorted(out, key=lambda f: (f.period_end, f.date_added))


def index(lei: str) -> list[Filing]:
    return parse_index(_cached(CACHE_DIR / f"index-{lei}.json", index_url(lei), max_age=CACHE_SECONDS))


def report(filing: Filing) -> Mapping[str, object] | None:
    """The report's xBRL-JSON, cached for ever; None when the index names no facts file."""
    if not filing.json_url:
        return None
    body = _cached(CACHE_DIR / f"{filing.fxo_id}.json", HOST + filing.json_url, max_age=None)
    return cast(Mapping[str, object], json.loads(body))


def definition_linkbase(filing: Filing) -> bytes | None:
    """The report package's definition linkbase, extracted once and cached for ever; the
    package itself is streamed to a temporary file and removed. None when the index names
    no package or the package carries no definition linkbase."""
    if not filing.package_url:
        return None
    path = CACHE_DIR / f"{filing.fxo_id}.def.xml"
    if path.exists():
        return path.read_bytes() or None
    body = _get(HOST + filing.package_url)
    found = b""
    with tempfile.NamedTemporaryFile(suffix=".zip") as tmp:
        tmp.write(body)
        tmp.flush()
        try:
            with zipfile.ZipFile(tmp.name) as z:
                names = [n for n in z.namelist() if n.lower().endswith("_def.xml") and "/reports/" not in n]
                if names:
                    found = z.read(names[0])
        except zipfile.BadZipFile:
            found = b""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(found)  # an empty file records that the package had none
    return found or None


# --- the readings ------------------------------------------------------------------------

def _qname(href: str) -> str:
    """`...#ifrs-full_ProfitLossBeforeTax` -> `ifrs-full:ProfitLossBeforeTax`; the id joins
    prefix and name with the first underscore."""
    ident = href.rsplit("#", 1)[-1]
    prefix, sep, name = ident.partition("_")
    return f"{prefix}:{name}" if sep else ident


def anchors(linkbase: bytes | None) -> dict[str, str]:
    """Extension concept -> the one standard concept (name without prefix) it is anchored to
    as narrower. An extension with two wider standard parents, or none, is absent."""
    if not linkbase:
        return {}
    try:
        root = ET.fromstring(linkbase)
    except ET.ParseError:
        return {}
    wider_of: dict[str, set[str]] = {}
    for link in root.iter():
        locs: dict[str, str] = {}
        for el in link:
            if el.tag.endswith("}loc"):
                label, href = el.get(XLINK + "label"), el.get(XLINK + "href")
                if label and href:
                    locs[label] = _qname(href)
        for el in link:
            if not el.tag.endswith("Arc") or el.get(XLINK + "arcrole") != WIDER_NARROWER:
                continue
            wider = locs.get(el.get(XLINK + "from") or "")
            narrower = locs.get(el.get(XLINK + "to") or "")
            if wider and narrower and wider.startswith(STANDARD_PREFIX) and not narrower.startswith(STANDARD_PREFIX):
                wider_of.setdefault(narrower, set()).add(wider[len(STANDARD_PREFIX):])
    return {ext: next(iter(w)) for ext, w in wider_of.items() if len(w) == 1}


def _period(text: str) -> tuple[date | None, date]:
    """xBRL-JSON periods: `start/end` for a duration, one instant otherwise; an end at
    midnight is the exclusive end of the day before."""
    def day(stamp: str) -> date:
        d = date.fromisoformat(stamp[:10])
        clock = stamp[11:19] if len(stamp) >= 19 else "00:00:00"
        return d - timedelta(days=1) if clock == "00:00:00" else d
    if "/" in text:
        start, end = text.split("/", 1)
        return date.fromisoformat(start[:10]), day(end)
    return None, day(text)


def _lines(doc: Mapping[str, object]) -> list[tuple[str, str, date | None, date, float]]:
    """(concept qname, currency, start, end, value) for every monetary statement line: no
    dimension beyond the core, a currency unit, a numeric value."""
    out: list[tuple[str, str, date | None, date, float]] = []
    for fact in cast(Mapping[str, Mapping[str, object]], doc.get("facts") or {}).values():
        dims = cast(Mapping[str, object], fact.get("dimensions") or {})
        if any(k not in CORE_DIMENSIONS for k in dims):
            continue
        unit = str(dims.get("unit") or "")
        if not unit.startswith(CURRENCY_PREFIX) or "/" in unit:
            continue
        try:
            value = float(cast(str, fact.get("value")))
            start, end = _period(str(dims.get("period") or ""))
        except (TypeError, ValueError):
            continue
        out.append((str(dims.get("concept") or ""), unit[len(CURRENCY_PREFIX):], start, end, value))
    return out


def is_annual(lines: list[tuple[str, str, date | None, date, float]], period_end: date, span: tuple[int, int]) -> bool:
    lo, hi = span
    return any(start is not None and end == period_end and lo <= (end - start).days <= hi for _, _, start, end, _ in lines)


def choose(filings: list[Filing], reports: Mapping[str, Mapping[str, object] | None], span: tuple[int, int], notes: list[str]) -> list[Filing]:
    """The annual reports, one per period end, newest first."""
    by_end: dict[date, Filing] = {}
    for f in filings:
        doc = reports.get(f.fxo_id)
        if doc is None:
            notes.append(f"ESEF {f.fxo_id}: no facts file in the index; skipped")
            continue
        if not is_annual(_lines(doc), f.period_end, span):
            notes.append(f"ESEF {f.fxo_id}: no annual duration ends at its period end; an interim report, skipped")
            continue
        if f.period_end in by_end:
            notes.append(f"ESEF {f.fxo_id}: a second report for {f.period_end}; the earlier-added {by_end[f.period_end].fxo_id} is read")
            continue
        by_end[f.period_end] = f
    return [by_end[end] for end in sorted(by_end, reverse=True)]


def adapt(chosen: list[Filing], reports: Mapping[str, Mapping[str, object] | None], anchor_of: Mapping[str, Mapping[str, str]],
          *, read_tags: frozenset[str] | None = None) -> Adapted:
    """The companyfacts shape: {tag: {"units": {currency: [entry, ...]}}}, an entry per
    fact with end, start, val, accn (the report's id), fy, fp FY, form ESEF and filed.
    [read_tags] limits the anchored substitution to the concepts the definitions read (the
    harvest fetch_sec.read_tag_names makes), so a line nothing reads is never renamed and
    the notes name only substitutions that can reach a record; None substitutes for any."""
    gaap: dict[str, dict[str, dict[str, list[dict[str, object]]]]] = {}
    currencies: Counter[str] = Counter()
    notes: list[str] = []
    substitutions = 0
    named: set[tuple[str, str, str]] = set()
    for f in chosen:
        doc = reports.get(f.fxo_id)
        if doc is None:
            continue
        lines = _lines(doc)
        standard = {(c[len(STANDARD_PREFIX):], s, e) for c, _, s, e, _ in lines if c.startswith(STANDARD_PREFIX)}
        anchored = anchor_of.get(f.fxo_id) or {}
        for concept, currency, start, end, value in lines:
            if concept.startswith(STANDARD_PREFIX):
                tag = concept[len(STANDARD_PREFIX):]
            else:
                wider = anchored.get(concept)
                if wider is None or (wider, start, end) in standard or (read_tags is not None and wider not in read_tags):
                    continue
                tag = wider
                substitutions += 1
                if (f.fxo_id, tag, concept) not in named:
                    named.add((f.fxo_id, tag, concept))
                    notes.append(f"ESEF {f.fxo_id}: {tag} read from the extension {concept}, anchored to it as narrower, on the periods the report tags no standard line for")
            entry: dict[str, object] = {"end": end.isoformat(), "val": value, "accn": f.fxo_id, "fy": f.period_end.year,
                                        "fp": "FY", "form": FORM, "filed": f.date_added.isoformat()}
            if start is not None:
                entry["start"] = start.isoformat()
            gaap.setdefault(tag, {"units": {}})["units"].setdefault(currency, []).append(entry)
            currencies[currency] += 1
    currency = currencies.most_common(1)[0][0] if currencies else None
    if len(currencies) > 1:
        notes.append("ESEF: monetary facts in more than one currency, " + ", ".join(f"{c} {n}" for c, n in currencies.most_common()) + f"; {currency} is read")
    return Adapted(gaap=cast(dict[str, object], gaap), currency=currency, filings=chosen, notes=notes, substitutions=substitutions)


def statements(lei: str, *, span: tuple[int, int], read_tags: frozenset[str] | None = None) -> Adapted:
    """The filer's annual reports as facts. An empty [filings] means the index carries no
    annual report for the LEI, and the caller says so on the record."""
    listed = index(lei)
    reports = {f.fxo_id: report(f) for f in listed}
    notes: list[str] = []
    chosen = choose(listed, reports, span, notes)
    anchor_of = {f.fxo_id: anchors(definition_linkbase(f)) for f in chosen}
    adapted = adapt(chosen, reports, anchor_of, read_tags=read_tags)
    adapted.notes = notes + adapted.notes
    if listed and not chosen:
        adapted.notes.append(f"ESEF: the index lists {len(listed)} report(s) for LEI {lei} and none is annual")
    return adapted


