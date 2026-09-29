"""The universe file, loaded strictly: each entry is exactly ticker, entity_class, why and
optionally scope_limits, cik, lei (73, the Legal Entity Identifier whose ESEF reports are
the statements, twenty characters), adr_ratio (42, ordinary shares per depositary
receipt, a positive number) and the two build-out declarations (60); anything else is an
error, so nothing that remembers an outcome or a finding can creep back into a declaration."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, cast

import reference

ALLOWED = ("ticker", "entity_class", "why", "scope_limits", "cik", "lei", "adr_ratio",
           "build_out_return", "build_out_lag_years")
REQUIRED = ("ticker", "entity_class", "why")
# (60) A build-out declaration is exactly a value, the evidence for it and a date. A number
# with no why is not a declaration, which is the whole point of the readout being declared.
DECLARATION = ("value", "why", "as_of")
LEI = re.compile(r"[A-Z0-9]{18}[0-9]{2}")  # ISO 17442: eighteen alphanumerics and two check digits


class UniverseError(ValueError):
    """A universe entry that is more, or less, than a declaration."""


def _check_entry(index: int, entry: object) -> None:
    if not isinstance(entry, dict):
        raise UniverseError(f"universe entry {index} is not an object")
    fields: dict[str, object] = {str(k): v for k, v in cast(dict[Any, Any], entry).items()}
    ticker = fields.get("ticker")
    name = ticker if isinstance(ticker, str) else f"entry {index}"
    unknown = [k for k in fields if k not in ALLOWED]
    if unknown:
        raise UniverseError(
            f"universe entry {name} carries unknown field(s) {', '.join(unknown)}; "
            f"a universe entry is exactly {', '.join(ALLOWED)}"
        )
    missing = [k for k in REQUIRED if not isinstance(fields.get(k), str) or not str(fields[k]).strip()]
    if missing:
        raise UniverseError(f"universe entry {name} lacks {', '.join(missing)}")
    lei = fields.get("lei")
    if lei is not None and (not isinstance(lei, str) or not LEI.fullmatch(lei)):
        raise UniverseError(f"universe entry {name}: lei must be a twenty-character Legal Entity Identifier (letters and digits), not {lei!r}")
    ratio = fields.get("adr_ratio")
    if ratio is not None and (isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or ratio <= 0):
        raise UniverseError(f"universe entry {name}: adr_ratio must be a positive number (ordinary shares per receipt)")
    for field in ("build_out_return", "build_out_lag_years"):
        _check_declaration(name, field, fields.get(field))
    declared = [k for k in ("build_out_return", "build_out_lag_years") if fields.get(k) is not None]
    if len(declared) == 1:
        raise UniverseError(
            f"universe entry {name}: {declared[0]} is declared without the other; the build-out readout needs both a return and a lag")


def _check_declaration(name: object, field: str, value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise UniverseError(f"universe entry {name}: {field} is not an object")
    fields: dict[str, object] = {str(k): v for k, v in cast(dict[Any, Any], value).items()}
    unknown = [k for k in fields if k not in DECLARATION]
    if unknown:
        raise UniverseError(
            f"universe entry {name}: {field} carries unknown field(s) {', '.join(unknown)}; "
            f"a declaration is exactly {', '.join(DECLARATION)}")
    number = fields.get("value")
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        raise UniverseError(f"universe entry {name}: {field} lacks a numeric value")
    if field == "build_out_lag_years" and (number < 0 or float(number) != int(number)):
        raise UniverseError(f"universe entry {name}: build_out_lag_years must be a whole number of years, not {number}")
    for text in ("why", "as_of"):
        if not isinstance(fields.get(text), str) or not str(fields[text]).strip():
            raise UniverseError(f"universe entry {name}: {field} lacks {text}")
    as_of = str(fields["as_of"])
    try:
        date.fromisoformat(as_of)
    except ValueError:
        raise UniverseError(f"universe entry {name}: {field} as_of {as_of!r} is not an ISO date") from None


def load_text(text: str) -> reference.Universe:
    raw: object = json.loads(text)
    entries = cast(dict[Any, Any], raw).get("tickers") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        raise UniverseError("universe: no tickers list")
    for i, entry in enumerate(cast(list[object], entries), 1):
        _check_entry(i, entry)
    return reference.Universe.from_json_string(text)


def load(path: Path) -> reference.Universe:
    return load_text(path.read_text())
