"""The universe file, loaded strictly: each entry is exactly ticker, entity_class, why and
optionally scope_limits; anything else is an error, so nothing that remembers an outcome
or a finding can creep back into a declaration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import reference

ALLOWED = ("ticker", "entity_class", "why", "scope_limits")
REQUIRED = ("ticker", "entity_class", "why")


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
