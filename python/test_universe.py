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


def test_a_second_universe_file_is_the_same_format() -> None:
    """A private universe under data/ (21) goes through the same strict loader: the
    four fields, and an unknown field is rejected the same way."""
    private = {"tickers": [
        {"ticker": "PRIV.A", "entity_class": "OperatingCompany", "why": "a plain operating company"},
        {"ticker": "PRIV.B", "entity_class": "HighGrowthSoftware", "why": "software compounding revenue, profitable", "scope_limits": ["nothing the models see"]},
    ]}
    loaded = universe.load_text(json.dumps(private))
    assert [e.ticker for e in loaded.tickers] == ["PRIV.A", "PRIV.B"]
    assert loaded.tickers[1].scope_limits == ["nothing the models see"]
    private["tickers"][0]["position"] = "held"
    with pytest.raises(universe.UniverseError, match="universe entry PRIV.A carries unknown field\\(s\\) position"):
        universe.load_text(json.dumps(private))
