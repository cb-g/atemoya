"""The CME FX futures table (43), loaded strictly: transcribed public specifications and the
exchange's published margins, dated; an unknown field anywhere is an error, so nothing
fetched or estimated can creep into it."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, cast

import reference

TOP = ("source", "as_of", "max_age_days", "notes", "contracts")
PRODUCT = ("quote", "vendor_symbol", "standard", "micro")
CONTRACT = ("product", "size", "tick", "tick_value_usd", "maintenance_margin_usd", "initial_margin_usd")
QUOTES = ("usd_per_unit", "units_per_usd")


class FxFuturesError(ValueError):
    """A table entry that is more, or less, than a transcription."""


def _fields(what: str, entry: object, allowed: tuple[str, ...], required: tuple[str, ...]) -> dict[str, object]:
    if not isinstance(entry, dict):
        raise FxFuturesError(f"{what} is not an object")
    fields = {str(k): v for k, v in cast(dict[Any, Any], entry).items()}
    unknown = [k for k in fields if k not in allowed]
    if unknown:
        raise FxFuturesError(f"{what} carries unknown field(s) {', '.join(unknown)}; exactly {', '.join(allowed)}")
    missing = [k for k in required if k not in fields]
    if missing:
        raise FxFuturesError(f"{what} lacks {', '.join(missing)}")
    return fields


def _contract(what: str, entry: object) -> None:
    f = _fields(what, entry, CONTRACT, CONTRACT)
    for k in ("size", "tick", "tick_value_usd", "maintenance_margin_usd", "initial_margin_usd"):
        v = f[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            raise FxFuturesError(f"{what}: {k} must be a positive number")


def load_text(text: str) -> reference.FxFutures:
    raw: object = json.loads(text)
    top = _fields("fx_futures", raw, TOP, ("source", "as_of", "max_age_days", "contracts"))
    date.fromisoformat(str(top["as_of"]))
    contracts = top["contracts"]
    if not isinstance(contracts, dict):
        raise FxFuturesError("fx_futures: contracts must be an object keyed by currency")
    for ccy, entry in cast(dict[Any, Any], contracts).items():
        f = _fields(f"fx_futures {ccy}", entry, PRODUCT, ("quote", "vendor_symbol", "standard"))
        if f["quote"] not in QUOTES:
            raise FxFuturesError(f"fx_futures {ccy}: quote must be one of {', '.join(QUOTES)}")
        _contract(f"fx_futures {ccy} standard", f["standard"])
        if "micro" in f:
            _contract(f"fx_futures {ccy} micro", f["micro"])
    return reference.FxFutures.from_json_string(text)


def load(path: Path) -> reference.FxFutures:
    return load_text(path.read_text())
