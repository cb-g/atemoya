"""Declared required returns on equity (34), loaded strictly: three fields per entry and
nothing else (premium_over_rf, why, as_of). The batch is the consumer; this keeps the
Python side honest about the tracked file and any further --required-returns file."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, cast

import reference

FIELDS = ("premium_over_rf", "why", "as_of")


class RequiredReturnError(ValueError):
    """An entry that is more, or less, than its three fields."""


def _check(name: str, entry: object) -> None:
    if not isinstance(entry, dict):
        raise RequiredReturnError(f"required return {name} is not an object")
    fields = {str(k): v for k, v in cast(dict[Any, Any], entry).items()}
    unknown = [k for k in fields if k not in FIELDS]
    if unknown:
        raise RequiredReturnError(f"required return {name} carries unknown field(s) {', '.join(unknown)}; an entry is exactly {', '.join(FIELDS)}")
    missing = [k for k in FIELDS if k not in fields]
    if missing:
        raise RequiredReturnError(f"required return {name} lacks {', '.join(missing)}")
    premium = fields["premium_over_rf"]
    if not isinstance(premium, (int, float)) or isinstance(premium, bool):
        raise RequiredReturnError(f"required return {name}: premium_over_rf must be a number")
    why = fields["why"]
    if not isinstance(why, str) or not why.strip():
        raise RequiredReturnError(f"required return {name}: why is empty")
    try:
        date.fromisoformat(str(fields["as_of"]))
    except ValueError as e:
        raise RequiredReturnError(f"required return {name}: as_of: {e}") from e


def _table(text: str, key: str, *, required: bool) -> None:
    raw: object = json.loads(text)
    entries = cast(dict[Any, Any], raw).get(key) if isinstance(raw, dict) else None
    if entries is None and not required:
        return
    if not isinstance(entries, dict):
        raise RequiredReturnError(f"required returns: no {key} object")
    for name, entry in cast(dict[Any, Any], entries).items():
        _check(str(name), entry)


def load_classes_text(text: str) -> reference.RequiredReturns:
    _table(text, "classes", required=True)
    _table(text, "names", required=False)
    return reference.RequiredReturns.from_json_string(text)


def load_names_text(text: str) -> reference.NameRequiredReturns:
    _table(text, "tickers", required=True)
    return reference.NameRequiredReturns.from_json_string(text)


def load_classes(path: Path) -> reference.RequiredReturns:
    return load_classes_text(path.read_text())


def load_names(path: Path) -> reference.NameRequiredReturns:
    return load_names_text(path.read_text())
