"""Declared beliefs on long-run growth (24), loaded strictly: six fields per belief and
nothing else (mean, sd, floor, ceiling, why, as_of), so no file can ask the tool to
estimate one. The batch is the consumer; this loader keeps the Python side honest about
the same file (the tracked class defaults and per-name entries) and any further
per-name file given as --beliefs."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, cast

import reference

FIELDS = ("mean", "sd", "floor", "ceiling", "why", "as_of")


class BeliefError(ValueError):
    """A belief that is more, or less, than its six fields."""


def _check(name: str, entry: object) -> None:
    if not isinstance(entry, dict):
        raise BeliefError(f"belief {name} is not an object")
    fields = {str(k): v for k, v in cast(dict[Any, Any], entry).items()}
    unknown = [k for k in fields if k not in FIELDS]
    if unknown:
        raise BeliefError(f"belief {name} carries unknown field(s) {', '.join(unknown)}; a belief is exactly {', '.join(FIELDS)}")
    missing = [k for k in FIELDS if k not in fields]
    if missing:
        raise BeliefError(f"belief {name} lacks {', '.join(missing)}")
    numbers = {k: fields[k] for k in ("mean", "sd", "floor", "ceiling")}
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in numbers.values()):
        raise BeliefError(f"belief {name}: mean, sd, floor and ceiling must be numbers")
    sd = float(cast(float, numbers["sd"]))
    floor = float(cast(float, numbers["floor"]))
    ceiling = float(cast(float, numbers["ceiling"]))
    if sd <= 0:
        raise BeliefError(f"belief {name}: sd {sd:g} is not positive")
    if floor >= ceiling:
        raise BeliefError(f"belief {name}: floor {floor:g} is not below ceiling {ceiling:g}")
    why = fields["why"]
    if not isinstance(why, str) or not why.strip():
        raise BeliefError(f"belief {name}: why is empty")
    try:
        date.fromisoformat(str(fields["as_of"]))
    except ValueError as e:
        raise BeliefError(f"belief {name}: as_of: {e}") from e


def _table(text: str, key: str) -> None:
    raw: object = json.loads(text)
    entries = cast(dict[Any, Any], raw).get(key) if isinstance(raw, dict) else None
    if not isinstance(entries, dict):
        raise BeliefError(f"beliefs: no {key} object")
    for name, entry in cast(dict[Any, Any], entries).items():
        _check(str(name), entry)


def _correlation(raw: dict[Any, Any]) -> None:
    """The correlation section (35): exactly common, why, as_of and an optional pairs list
    of exactly a, b, rho, why, as_of; common in [0, 1), rho in (-1, 1)."""
    section = raw.get("correlation")
    if section is None:
        return
    if not isinstance(section, dict):
        raise BeliefError("correlation must be an object")
    kv = {str(k): v for k, v in cast(dict[Any, Any], section).items()}
    unknown = [k for k in kv if k not in ("common", "why", "as_of", "pairs")]
    missing = [k for k in ("common", "why", "as_of") if k not in kv]
    if unknown:
        raise BeliefError(f"correlation section carries unknown field(s) {', '.join(unknown)}")
    if missing:
        raise BeliefError(f"correlation section lacks {', '.join(missing)}")
    common = kv["common"]
    if not isinstance(common, (int, float)) or isinstance(common, bool) or not 0 <= common < 1:
        raise BeliefError(f"correlation common {common} is not in [0, 1)")
    for pair in cast(list[Any], kv.get("pairs", [])):
        if not isinstance(pair, dict):
            raise BeliefError("correlation pair is not an object")
        pkv = {str(k): v for k, v in cast(dict[Any, Any], pair).items()}
        if set(pkv) != {"a", "b", "rho", "why", "as_of"}:
            raise BeliefError(f"correlation pair fields are {sorted(pkv)}, not exactly a, b, rho, why, as_of")
        rho = pkv["rho"]
        if not isinstance(rho, (int, float)) or isinstance(rho, bool) or not -1 < rho < 1:
            raise BeliefError(f"correlation pair rho {rho} is not in (-1, 1)")


def load_classes_text(text: str) -> reference.ClassBeliefs:
    _table(text, "classes")
    raw: object = json.loads(text)
    if isinstance(raw, dict):
        if "names" in cast(dict[Any, Any], raw):
            _table(text, "names")
        _correlation(cast(dict[Any, Any], raw))
    return reference.ClassBeliefs.from_json_string(text)


def load_names_text(text: str) -> reference.NameBeliefs:
    _table(text, "tickers")
    return reference.NameBeliefs.from_json_string(text)


def load_classes(path: Path) -> reference.ClassBeliefs:
    return load_classes_text(path.read_text())


def load_names(path: Path) -> reference.NameBeliefs:
    return load_names_text(path.read_text())
