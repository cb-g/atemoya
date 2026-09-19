"""The strict belief loader (24): six fields, nothing estimated, the tracked drafts load."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import beliefs

ROOT = Path(__file__).resolve().parent.parent
OK = {"mean": 0, "sd": 0.5, "floor": -2, "ceiling": 2, "why": "near the economy's", "as_of": "2026-09-19"}


def test_tracked_class_defaults_load() -> None:
    table = beliefs.load_classes(ROOT / "reference" / "beliefs.json")
    names = [name for name, _ in table.classes]
    assert names == ["OperatingCompany", "HighGrowthSoftware", "Cyclical", "Reit"]
    assert all(b.sd > 0 and b.floor < b.ceiling and b.why for _, b in table.classes)
    assert "Bank" not in names and "Insurer" not in names


def test_loader_is_strict() -> None:
    assert beliefs.load_classes_text(json.dumps({"classes": {"OperatingCompany": OK}})).classes[0][1].sd == 0.5
    with pytest.raises(beliefs.BeliefError, match="unknown field\\(s\\) estimated_from"):
        beliefs.load_classes_text(json.dumps({"classes": {"OperatingCompany": {**OK, "estimated_from": "history"}}}))
    with pytest.raises(beliefs.BeliefError, match="lacks ceiling"):
        beliefs.load_classes_text(json.dumps({"classes": {"OperatingCompany": {k: v for k, v in OK.items() if k != "ceiling"}}}))
    with pytest.raises(beliefs.BeliefError, match="sd 0 is not positive"):
        beliefs.load_classes_text(json.dumps({"classes": {"OperatingCompany": {**OK, "sd": 0}}}))
    with pytest.raises(beliefs.BeliefError, match="floor 2 is not below ceiling 2"):
        beliefs.load_classes_text(json.dumps({"classes": {"OperatingCompany": {**OK, "floor": 2}}}))
    with pytest.raises(beliefs.BeliefError, match="why is empty"):
        beliefs.load_classes_text(json.dumps({"classes": {"OperatingCompany": {**OK, "why": " "}}}))
    with pytest.raises(beliefs.BeliefError, match="as_of"):
        beliefs.load_classes_text(json.dumps({"classes": {"OperatingCompany": {**OK, "as_of": "last year"}}}))
    with pytest.raises(beliefs.BeliefError, match="no tickers object"):
        beliefs.load_names_text(json.dumps({"classes": {}}))
    private = beliefs.load_names_text(json.dumps({"tickers": {"PRIV.A": {**OK, "mean": 3, "floor": 1, "ceiling": 5}}}))
    assert private.tickers[0][0] == "PRIV.A" and private.tickers[0][1].mean == 3
