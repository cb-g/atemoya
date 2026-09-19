"""Declared beliefs on long-run growth (24), loaded strictly: six fields per belief and
nothing else (mean, sd, floor, ceiling, why, as_of), so no file can ask the tool to
estimate one. The batch is the consumer; this loader keeps the Python side honest about
the same files (a private per-name file under data/, the tracked class table)."""

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


def load_classes_text(text: str) -> reference.ClassBeliefs:
    _table(text, "classes")
    return reference.ClassBeliefs.from_json_string(text)


def load_names_text(text: str) -> reference.NameBeliefs:
    _table(text, "tickers")
    return reference.NameBeliefs.from_json_string(text)


def load_classes(path: Path) -> reference.ClassBeliefs:
    return load_classes_text(path.read_text())


def load_names(path: Path) -> reference.NameBeliefs:
    return load_names_text(path.read_text())
