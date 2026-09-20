"""The options store (36): a vendor row maps to a quote field for field, the chain is
sorted and stamped, and the path is data/options/<date>/<TICKER>.json."""

from __future__ import annotations

import json
from pathlib import Path

import boundary
import fetch_options as fo

ROW = {
    "symbol": '"TEST"', "expiration": '"2028-06-16"', "strike": "100.000", "right": '"CALL"',
    "created": "2026-09-01T21:00:00.000", "last_trade": "2026-09-01T20:00:00.000",
    "open": "9.00", "high": "10.00", "low": "9.00", "close": "9.50", "volume": "3", "count": "2",
    "bid_size": "5", "bid_exchange": "1", "bid": "9.40", "bid_condition": "0",
    "ask_size": "7", "ask_exchange": "1", "ask": "9.60", "ask_condition": "0",
}


def test_quote_of_row_keeps_every_field() -> None:
    q = fo.quote_of_row(ROW)
    assert (q.expiration, q.strike, q.right) == ("2028-06-16", 100.0, "call")
    assert (q.bid, q.ask, q.mid, q.bid_size, q.ask_size) == (9.4, 9.6, 9.5, 5, 7)
    assert (q.last, q.volume, q.count) == (9.5, 3, 2)


def test_chain_is_sorted_stamped_and_written(tmp_path: Path) -> None:
    put = {**ROW, "right": '"PUT"', "strike": "50.000"}
    chain = fo.chain_of_rows("TEST", [ROW, put], snapshot_date="2026-09-01", underlying_close=95.0, fetched_at="2026-09-02T00:00:00+00:00")
    assert [q.strike for q in chain.quotes] == [50.0, 100.0]
    assert chain.snapshot_timestamp == "2026-09-01T21:00:00.000" and chain.underlying_close == 95.0
    path = fo.write_chain(chain, tmp_path)
    assert path == tmp_path / "2026-09-01" / "TEST.json"
    again = boundary.OptionChain.from_json(json.loads(path.read_text()))
    assert again == chain


def test_symbols() -> None:
    assert fo.option_symbol("BRK-B") == "BRKB" and fo.stock_symbol("BRK-B") == "BRK.B"
    assert fo.compact("2026-09-17") == "20260917"


def test_spans_never_exceed_the_endpoint_limit() -> None:
    assert fo.spans("2026-09-17", "2026-09-17") == [("2026-09-17", "2026-09-17")]
    assert fo.spans("2025-04-16", "2026-09-17") == [("2025-04-16", "2026-04-15"), ("2026-04-16", "2026-09-17")]
    assert fo.spans("2025-04-16", "2026-04-16") == [("2025-04-16", "2026-04-15"), ("2026-04-16", "2026-04-16")]
