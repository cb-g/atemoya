"""DART filings (74): the annual reports Korean issuers file with the Financial Supervisory
Service, served by OpenDART as the full set of consolidated statement lines with their
XBRL account ids, read for a name on the Korea Exchange (a `.KS` or `.KQ` ticker) when
the operator holds an OpenDART key. The key is free on registration and lives in `.env`
as DART_API_KEY, read from the environment first as every other key is; without it the
name stays on the vendor and the record says so.

OpenDART's own corporation register maps the six-digit stock code to the eight-digit
corporation code the statements are filed under, so nothing is declared: the map is the
regulator's, cached for a day. The single-company statements endpoint serves one
business year per call, the annual report (11011) on a consolidated basis (CFS), every
line of the balance sheet, income statement, comprehensive income and cash flow with its
account id, its current-year amount and the period it covers, and the receipt number of
the report it came from, whose first eight digits are the day it was filed. The lines are
read into the companyfacts shape and go through the same period reader under the
ifrs-full definitions: one period per report, the tag behind every number, the
restatement scan, the vendor cross-checked beside. A line whose account id is not a
standard ifrs-full concept (DART's own `dart_` extensions, and the marker for a line
filed under no standard code) is counted and left unread until a measured rule says what
it is.

Nothing fetched is tracked: the register and each year's lines are cached for a day
under data/dart/, since an amended report replaces the year's lines under a new receipt.

OpenDART's terms of use (opendart.fss.or.kr/intro/terms.do), read 2026-09-30: anyone may
register, individuals included, with no nationality or residency limit; the key is
personal, one per member, and not to be used by a third party, which is why it is read
only from the operator's own environment or env file and never written, printed or
committed; the request allowance is posted on the site and a call over it answers status
020, raised here as an error and never retried; excessive network access is a ground for
suspension, so requests are paced and cached. The terms say nothing about redistribution
and the tool does none: every user fetches with their own key under a gitignored path."""

from __future__ import annotations

import io
import json
import os
import time
import urllib.error
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "data" / "dart"
DOTENV_PATH = REPO_ROOT / ".env"
KEY_NAME = "DART_API_KEY"
HOST = "https://opendart.fss.or.kr"
CACHE_SECONDS = 86400
PROVIDER = "DART filings (opendart.fss.or.kr)"
TAXONOMY = "ifrs-full"
FORM = "DART"  # the form name the adapted lines carry; the fetch extends annual_forms with it on this path alone
ANNUAL_REPORT = "11011"
CONSOLIDATED = "CFS"
STANDARD_PREFIX = "ifrs-full_"
NO_DATA = "013"
SUFFIXES = (".KS", ".KQ")


@dataclass(frozen=True)
class Report:
    year: int
    receipt: str          # rcept_no: the filing's receipt number, its first eight digits the day filed
    period_end: date
    filed: date


@dataclass
class Adapted:
    gaap: dict[str, object]
    currency: str | None
    reports: list[Report]           # newest first
    notes: list[str] = field(default_factory=lambda: [])
    unread: Counter[str] = field(default_factory=lambda: Counter())


class DartError(RuntimeError):
    """OpenDART answered with a status that is not data and not 'no data'."""


# --- the key, the network edge and the cache ------------------------------------------------

def api_key(env: Mapping[str, str] | None = None, *, dotenv: Path = DOTENV_PATH) -> str | None:
    """DART_API_KEY from the environment, else from the env file at the repo root; None when
    neither has it. Never printed."""
    source = os.environ if env is None else env
    key = source.get(KEY_NAME, "").strip()
    if not key and dotenv.is_file():
        for line in dotenv.read_text().splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and name.strip() == KEY_NAME:
                key = value.strip().strip("'\"")
    return key or None


def stock_code(symbol: str) -> str | None:
    """`005930.KS` -> `005930`; None for a ticker that is not a Korea Exchange line."""
    upper = symbol.upper()
    for suffix in SUFFIXES:
        if upper.endswith(suffix):
            code = upper[: -len(suffix)]
            return code if code.isdigit() and len(code) == 6 else None
    return None


_last_request = 0.0


def _get(url: str, timeout: int = 120) -> bytes:
    """One request, paced; the URL carries the key and is never echoed."""
    global _last_request
    wait = 0.25 - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "atemoya fetch_dart (https://github.com/cb-g/atemoya)"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return cast(bytes, response.read())
    except urllib.error.HTTPError as e:
        raise DartError(f"OpenDART answered HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise DartError(f"OpenDART unreachable: {e.reason}") from e
    finally:
        _last_request = time.monotonic()


def _cached(path: Path, url: str) -> bytes:
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_SECONDS:
        return path.read_bytes()
    body = _get(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def parse_corp_codes(body: bytes) -> dict[str, str]:
    """The register's zip: one XML file, a `list` element per corporation with corp_code,
    corp_name, stock_code and modify_date; listed companies carry a six-digit stock code."""
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".xml")]
        if not names:
            raise DartError("the corporation register carries no XML")
        root = ET.fromstring(z.read(names[0]))
    out: dict[str, str] = {}
    for item in root.iter("list"):
        code = (item.findtext("stock_code") or "").strip()
        corp = (item.findtext("corp_code") or "").strip()
        if len(code) == 6 and code.isdigit() and corp:
            out[code] = corp
    return out


def corp_codes(key: str) -> dict[str, str]:
    return parse_corp_codes(_cached(CACHE_DIR / "corp_codes.zip", f"{HOST}/api/corpCode.xml?crtfc_key={key}"))


def statements_year(key: str, corp: str, year: int) -> Mapping[str, object] | None:
    """The annual report's consolidated lines for one business year; None when OpenDART
    says it has no data for that year (status 013)."""
    url = f"{HOST}/api/fnlttSinglAcntAll.json?crtfc_key={key}&corp_code={corp}&bsns_year={year}&reprt_code={ANNUAL_REPORT}&fs_div={CONSOLIDATED}"
    raw = cast(Mapping[str, object], json.loads(_cached(CACHE_DIR / f"{corp}-{year}-{ANNUAL_REPORT}-{CONSOLIDATED}.json", url)))
    status = str(raw.get("status", ""))
    if status == NO_DATA:
        return None
    if status != "000":
        raise DartError(f"OpenDART status {status}: {raw.get('message', '')}")
    return raw


MAIN_ACCOUNTS = "fnlttSinglAcnt"


def main_accounts(key: str, corp: str, year: int) -> Mapping[str, object] | None:
    """The main-accounts endpoint for the same year: the same report's headline lines, each
    with the period it covers (`2025.12.31 현재`, `2025.01.01 ~ 2025.12.31`), which the
    full-accounts endpoint does not carry. None when OpenDART has no data (013)."""
    url = f"{HOST}/api/{MAIN_ACCOUNTS}.json?crtfc_key={key}&corp_code={corp}&bsns_year={year}&reprt_code={ANNUAL_REPORT}"
    raw = cast(Mapping[str, object], json.loads(_cached(CACHE_DIR / f"{corp}-{year}-{ANNUAL_REPORT}-main.json", url)))
    status = str(raw.get("status", ""))
    if status == NO_DATA:
        return None
    if status != "000":
        raise DartError(f"OpenDART status {status}: {raw.get('message', '')}")
    return raw


def span_of(main: Mapping[str, object] | None) -> tuple[date, date] | None:
    """(start, end) of the business year from the main accounts' consolidated income-statement
    lines, the balance-sheet date as the end where only that is given; None when absent."""
    if main is None:
        return None
    start: date | None = None
    end: date | None = None
    for row in cast(list[Mapping[str, object]], main.get("list") or []):
        if str(row.get("fs_div") or "") not in (CONSOLIDATED, ""):
            continue
        parsed = _dates(str(row.get("thstrm_dt") or ""))
        if parsed is None:
            continue
        s, e = parsed
        if s is not None and start is None:
            start, end = s, e
        elif end is None:
            end = e
    if end is None:
        return None
    return (start or date(end.year, 1, 1)), end


# Declared readings of lines the standard has no element for, each measured on Samsung
# Electronics and SK hynix before it was written; every other line stays unread and counted.
#
# DART's own account ids: operating income, which K-IFRS 1001 requires every filer to
# present as revenue less cost of sales less selling and administrative expense, is the
# operating income the ebit recipe reads; and the cash-flow reconciliation's one-line
# change in operating assets and liabilities is the working-capital aggregate the delta_nwc
# recipe reads where no component is tagged, in the cash-flow sign, so it is negated into
# the boundary's (Samsung FY2023-FY2025: -5,459, -1,568 and -9,614bn won filed against the
# vendor's +5,459, +1,568 and +9,614).
DART_STANDARD: dict[str, tuple[str, float]] = {
    "dart_OperatingIncomeLoss": ("ProfitLossFromOperatingActivities", 1.0),
    "dart_AdjustmentsForAssetsLiabilitiesOfOperatingActivities": ("IncreaseDecreaseInWorkingCapital", -1.0),
}
# Balance-sheet lines a filer files under no standard code at all, read by the K-IFRS
# standard label the regulator prints for them: short-term borrowings, which Samsung
# files that way (17,575bn won at FY2025 beside 1,178 of current long-term debt under the
# standard id), so that a debt recipe summing the tagged components does not read a
# borrower of that size as owing a fifteenth of it.
DART_LABELS: dict[tuple[str, str], str] = {("BS", "단기차입금"): "ShorttermBorrowings"}
STATEMENTS_READ = ("BS", "IS", "CIS", "CF")   # the statement of changes in equity is not read


# --- the reading ---------------------------------------------------------------------------

def _dates(text: str) -> tuple[date | None, date] | None:
    """`2024.01.01 ~ 2024.12.31` -> (start, end); `2024.12.31 현재` -> (None, end)."""
    stamps = [t for t in text.replace("~", " ").split() if len(t) == 10 and t[4] == "." and t[7] == "."]
    try:
        days = [date(int(s[:4]), int(s[5:7]), int(s[8:10])) for s in stamps]
    except ValueError:
        return None
    if len(days) == 2:
        return days[0], days[1]
    if len(days) == 1:
        return None, days[0]
    return None


def _amount(text: object) -> float | None:
    s = str(text).replace(",", "").strip()
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def adapt(years: Mapping[int, tuple[Mapping[str, object] | None, tuple[date, date] | None]]) -> Adapted:
    """The companyfacts shape from each year's own report: a line per (tag, period), the
    receipt number as the accession, the receipt day as the filing date, form DART. The
    balance sheet's lines are instants at the year's end, the other statements' durations
    over the year; the statement of changes in equity is not read."""
    gaap: dict[str, dict[str, dict[str, list[dict[str, object]]]]] = {}
    currencies: Counter[str] = Counter()
    unread: Counter[str] = Counter()
    reports: dict[str, Report] = {}
    seen: set[tuple[str, str, str | None, str]] = set()
    notes: list[str] = []
    named: set[tuple[str, str]] = set()
    for year in sorted(years, reverse=True):
        raw, span = years[year]
        if raw is None:
            continue
        if span is None:
            notes.append(f"DART {year}: the main accounts carry no period dates, so the year is not read")
            continue
        start, end = span
        for row in cast(list[Mapping[str, object]], raw.get("list") or []):
            statement = str(row.get("sj_div") or "")
            if statement not in STATEMENTS_READ:
                continue
            account = str(row.get("account_id") or "")
            receipt = str(row.get("rcept_no") or "")
            amount = _amount(row.get("thstrm_amount"))
            if not receipt or amount is None or len(receipt) < 8 or not receipt[:8].isdigit():
                continue
            if receipt not in reports:
                reports[receipt] = Report(year=year, receipt=receipt, period_end=end, filed=date(int(receipt[:4]), int(receipt[4:6]), int(receipt[6:8])))
            label = str(row.get("account_nm") or "").strip()
            sign = 1.0
            if account.startswith(STANDARD_PREFIX):
                tag = account[len(STANDARD_PREFIX):]
            elif account in DART_STANDARD:
                tag, sign = DART_STANDARD[account]
                if (receipt, account) not in named:
                    named.add((receipt, account))
                    notes.append(f"DART {receipt}: {tag} read from {account} ({label}), the K-IFRS line the standard has no element for" + (", negated into the boundary's sign" if sign < 0 else ""))
            elif (statement, label) in DART_LABELS:
                tag = DART_LABELS[(statement, label)]
                if (receipt, label) not in named:
                    named.add((receipt, label))
                    notes.append(f"DART {receipt}: {tag} read from the line labelled {label}, filed under no standard code")
            else:
                unread[account or "(none)"] += 1
                continue
            amount *= sign
            currency = str(row.get("currency") or "KRW")
            instant = statement == "BS"
            key = (tag, currency, None if instant else start.isoformat(), end.isoformat())
            if key in seen:
                continue  # the same line on two statements (profit on the income statement and at the head of the cash flow)
            seen.add(key)
            entry: dict[str, object] = {"end": end.isoformat(), "val": amount, "accn": receipt, "fy": year, "fp": "FY", "form": FORM,
                                        "filed": reports[receipt].filed.isoformat()}
            if not instant:
                entry["start"] = start.isoformat()
            gaap.setdefault(tag, {"units": {}})["units"].setdefault(currency, []).append(entry)
            currencies[currency] += 1
    currency = currencies.most_common(1)[0][0] if currencies else None
    if unread:
        notes.append("DART: lines filed under no standard account id, counted and unread: " + ", ".join(f"{k} {n}" for k, n in unread.most_common(6)))
    return Adapted(gaap=cast(dict[str, object], gaap), currency=currency,
                   reports=sorted(reports.values(), key=lambda r: r.period_end, reverse=True), notes=notes, unread=unread)


def statements(key: str, corp: str, *, years: int, today: date) -> Adapted:
    """The last [years] annual reports, newest first; a year OpenDART has no data for ends
    the walk once two in a row are empty (a report not yet filed, then history's end)."""
    raws: dict[int, tuple[Mapping[str, object] | None, tuple[date, date] | None]] = {}
    empty = 0
    for year in range(today.year, today.year - years - 2, -1):
        raw = statements_year(key, corp, year)
        raws[year] = (raw, span_of(main_accounts(key, corp, year)) if raw is not None else None)
        empty = empty + 1 if raw is None else 0
        if empty >= 2 or len([r for r, _ in raws.values() if r is not None]) >= years:
            break
    return adapt(raws)
