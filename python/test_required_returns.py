"""The strict required-return loader (34): three fields, nothing derived, the tracked file empty."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import required_returns as rr

ROOT = Path(__file__).resolve().parent.parent
OK = {"premium_over_rf": 3, "why": "a stated hurdle", "as_of": "2026-09-19"}


def test_tracked_file_ships_empty() -> None:
    table = rr.load_classes(ROOT / "reference" / "required_returns.json")
    assert table.classes == [] and table.names == []


def test_loader_is_strict() -> None:
    assert rr.load_classes_text(json.dumps({"classes": {"OperatingCompany": OK}})).classes[0][1].premium_over_rf == 3
    with pytest.raises(rr.RequiredReturnError, match="unknown field\\(s\\) beta"):
        rr.load_classes_text(json.dumps({"classes": {"OperatingCompany": {**OK, "beta": 1.2}}}))
    with pytest.raises(rr.RequiredReturnError, match="lacks why"):
        rr.load_classes_text(json.dumps({"classes": {"OperatingCompany": {k: v for k, v in OK.items() if k != "why"}}}))
    with pytest.raises(rr.RequiredReturnError, match="as_of"):
        rr.load_classes_text(json.dumps({"classes": {"OperatingCompany": {**OK, "as_of": "last year"}}}))
    with pytest.raises(rr.RequiredReturnError, match="no classes object"):
        rr.load_classes_text(json.dumps({"names": {}}))
    with pytest.raises(rr.RequiredReturnError, match="required return X.A carries unknown field"):
        rr.load_classes_text(json.dumps({"classes": {}, "names": {"X.A": {**OK, "sigma": 1}}}))
    further = rr.load_names_text(json.dumps({"tickers": {"X.A": OK}}))
    assert further.tickers[0][0] == "X.A"
