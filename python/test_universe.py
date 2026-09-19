"""The strict universe loader: exactly four fields, why required, nothing remembered."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import universe

ROOT = Path(__file__).resolve().parent.parent


def test_tracked_universe_is_a_declaration_only() -> None:
    text = (ROOT / "reference" / "universe.json").read_text()
    u = universe.load_text(text)
    raw = json.loads(text)["tickers"]
    assert len(u.tickers) == len(raw) == 34
    for entry in raw:
        assert set(entry) <= set(universe.ALLOWED) and all(k in entry for k in universe.REQUIRED)
        # no number followed by a unit, no percentage or multiple, no four-digit year, in a why
        assert not re.search(r"\d+(\.\d+)?\s*(bn|m|%|x)\b|\b(19|20)\d\d\b", entry["why"]), entry


def test_loader_rejects_anything_beyond_the_declaration() -> None:
    ok = {"tickers": [{"ticker": "X", "entity_class": "Bank", "why": "a bank"}]}
    assert universe.load_text(json.dumps(ok)).tickers[0].why == "a bank"
    with pytest.raises(universe.UniverseError, match="unknown field\\(s\\) outcome"):
        universe.load_text(json.dumps({"tickers": [{**ok["tickers"][0], "outcome": "Ok"}]}))
    with pytest.raises(universe.UniverseError, match="unknown field\\(s\\) note, finding"):
        universe.load_text(json.dumps({"tickers": [{**ok["tickers"][0], "note": "n", "finding": "f"}]}))
    with pytest.raises(universe.UniverseError, match="lacks why"):
        universe.load_text(json.dumps({"tickers": [{"ticker": "X", "entity_class": "Bank"}]}))
    with pytest.raises(universe.UniverseError, match="lacks why"):
        universe.load_text(json.dumps({"tickers": [{"ticker": "X", "entity_class": "Bank", "why": " "}]}))
    with pytest.raises(universe.UniverseError, match="no tickers list"):
        universe.load_text(json.dumps({"names": []}))
