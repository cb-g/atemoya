"""The broad panel and its study on invented figures: the fiscal year's fields matched by
end date, the cover-page count and its split basis, the market value on today's basis, the
forward return, the nine signals, the peer-implied gap, and the tables. No network."""

from __future__ import annotations

from typing import cast

import broad_panel as bp
import broad_study as bs

Json = dict[str, object]


def test_a_fiscal_year_takes_only_fields_filed_for_its_own_end() -> None:
    frames: dict[str, list[Json]] = {
        "NetIncomeLoss": [{"cik": 1, "end": "2019-09-30", "val": 10.0}],
        "Revenues": [{"cik": 1, "end": "2019-12-31", "val": 999.0}],   # another period's: not taken
        "RevenueFromContractWithCustomerExcludingAssessedTax": [{"cik": 1, "end": "2019-09-30", "val": 100.0}],
        "NetCashProvidedByUsedInOperatingActivities": [{"cik": 1, "end": "2019-09-30", "val": 12.0}, {"cik": 2, "end": "2019-09-30", "val": 5.0}],
    }
    assert bp.flows_of(frames) == {1: {"fiscal_year_end": "2019-09-30", "net_income": 10.0, "revenue": 100.0, "operating_cash_flow": 12.0}}
    stocks = bp.stocks_of({"Assets": [{"cik": 1, "end": "2019-09-30", "val": 500.0}], "LongTermDebtNoncurrent": [{"cik": 1, "end": "2019-09-30", "val": 50.0}],
                           "LongTermDebt": [{"cik": 1, "end": "2019-09-30", "val": 70.0}]})
    assert stocks == {(1, "2019-09-30"): {"total_assets": 500.0, "long_term_debt": 50.0}}   # the first element in order wins


def test_the_cover_count_is_the_newest_in_the_first_half_and_its_split_basis_is_reconciled() -> None:
    rows: list[Json] = [{"cik": 1, "end": "2020-02-10", "val": 100.0}, {"cik": 1, "end": "2020-05-01", "val": 110.0},
                        {"cik": 1, "end": "2020-07-17", "val": 440.0}, {"cik": 2, "end": "2019-12-20", "val": 9.0}]
    assert bp.cover_count(rows, 2020) == {1: ("2020-05-01", 110.0)}
    # splits after the cover month move the count onto today's basis; one in the cover month is ambiguous
    assert bp.split_factor({"2020-08": 4.0, "2024-06": 10.0, "2019-01": 2.0}, "2020-05-01") == (40.0, None)
    factor, why = bp.split_factor({"2020-05": 4.0}, "2020-05-01")
    assert factor is None and why is not None and "which came first" in why


def test_a_row_carries_market_value_on_todays_basis_and_the_next_twelve_months() -> None:
    flow: Json = {"fiscal_year_end": "2019-12-31", "net_income": 10.0, "revenue": 100.0}
    stocks: dict[tuple[int, str], Json] = {(1, "2019-12-31"): {"total_assets": 500.0}, (1, "2018-12-31"): {"total_assets": 400.0}}
    prices: dict[str, Json] = {
        "TKR": {"close": {"2020-06": 25.0, "2021-06": 30.0}, "adjusted": {"2020-06": 20.0, "2021-06": 26.0}, "splits": {"2020-08": 4.0}},
        "SPY": {"close": {}, "adjusted": {"2020-06": 100.0, "2021-06": 110.0}, "splits": {}},
    }
    row = bp.row_of(1, "TKR", "Test Co", 2020, flow, {"fiscal_year_end": "2018-12-31", "net_income": 8.0}, stocks, ("2020-05-01", 110.0), prices)
    # 110 shares before a 4-for-1 split are 440 on today's basis, at June's split-adjusted close of 25
    assert row["market_cap"] == 110.0 * 4.0 * 25.0 and row["split_factor"] == 4.0
    assert abs(cast(float, row["forward_12m"]) - 0.3) < 1e-12 and abs(cast(float, row["spy_12m"]) - 0.1) < 1e-12
    assert row["total_assets"] == 500.0 and cast(Json, row["prior"])["total_assets"] == 400.0
    none = bp.row_of(1, "TKR", "Test Co", 2020, flow, None, stocks, None, prices)
    assert "market_cap" not in none and none["market_cap_reason"] == "no cover-page share count dated January to June of 2020"
    gone = bp.row_of(1, "GONE", "Gone Co", 2020, flow, None, stocks, ("2020-05-01", 110.0), prices)
    assert gone["forward_reason"] == "the vendor carries no monthly bars for the ticker"
    # the same count tagged in thousands: 110,000 "shares" would be worth 22,000 times the filer's assets, and 1,000 times its own count the June before
    wrong = bp.row_of(1, "TKR", "Test Co", 2020, flow, None, stocks, ("2020-05-01", 110_000.0), prices, (("2019-05-01", 110.0),))
    assert "market_cap" not in wrong and wrong["cover_shares"] == 110_000.0 and "forward_12m" in wrong
    assert wrong["market_cap_reason"] == ("the cover-page share count of 2020-05-01 gives a market value 22,000 times the larger of revenue and total assets "
                                          "and is 1,000 times the smallest count the filer filed for another June: a count filed in the wrong unit")
    by_weighted = bp.row_of(1, "TKR", "Test Co", 2020, {**flow, "weighted_shares": 400.0}, None, stocks, ("2020-05-01", 110_000.0), prices)
    assert "1,100 times the fiscal year's weighted share count" in cast(str, by_weighted["market_cap_reason"])
    # a company the market prices at 22,000 times its assets, its count agreeing with its own filings, keeps its market value
    priced = bp.row_of(1, "TKR", "Test Co", 2020, {**flow, "weighted_shares": 420_000.0}, None, stocks, ("2020-05-01", 110_000.0), prices, (("2019-05-01", 100_000.0),))
    assert priced["market_cap"] == 110_000.0 * 4.0 * 25.0 and "market_cap_reason" not in priced
    # and a count a thousand times the others on a market value under the ceiling is left alone too: one sign is not two
    small = bp.row_of(1, "TKR", "Test Co", 2020, {**flow, "revenue": 1e9}, None, stocks, ("2020-05-01", 110_000.0), prices, (("2019-05-01", 110.0),))
    assert "market_cap" in small
    assert bp.wrong_unit(100.0, None, []) is None and bp.wrong_unit(100.0, 2.0, [50.0]) is None

def year(**over: float) -> Json:
    base: Json = {"net_income": 100.0, "operating_cash_flow": 150.0, "total_assets": 1000.0, "long_term_debt": 200.0, "current_assets": 300.0,
                  "current_liabilities": 150.0, "weighted_shares": 100.0, "gross_profit": 400.0, "revenue": 1000.0}
    base.update(over)
    return base


def test_the_nine_signals_and_the_ratios() -> None:
    prior = year(net_income=80.0, long_term_debt=300.0, current_assets=280.0, current_liabilities=160.0, gross_profit=250.0, revenue=900.0)
    assert bs.f_score(year(), prior) == 9
    assert bs.f_score(year(net_income=60.0, operating_cash_flow=40.0, long_term_debt=400.0, weighted_shares=105.0), prior) == 5
    assert bs.f_score(year(weighted_shares=400.0), prior) is None            # a count up by more than a quarter is not read
    assert bs.f_score({k: v for k, v in year().items() if k != "current_assets"}, prior) is None
    raw: Json = {**year(), "market_cap": 2000.0, "book_equity": 500.0, "prior": prior}
    m = bs.measures_of(raw)
    assert m["earnings_yield"] == 0.05 and m["book_to_price"] == 0.25 and m["gross_profitability"] == 0.4
    assert abs(m["accruals_ratio"] - (-0.05)) < 1e-12 and m["f_score"] == 9.0
    assert "book_to_price" not in bs.measures_of({**raw, "book_equity": -1.0})
    derived = bs.measures_of({**{k: v for k, v in raw.items() if k != "gross_profit"}, "cost_of_revenue": 700.0})
    assert derived["gross_profitability"] == 0.3


def test_the_peer_gap_is_zero_on_a_market_that_prices_by_the_rule_and_signed_off_it() -> None:
    raws: list[Json] = []
    for i in range(120):
        assets, equity, income = 1000.0 + 10 * i, 300.0 + 3 * (i % 7), 50.0 + (i % 11)
        raws.append({"total_assets": assets, "book_equity": equity, "revenue": 800.0 + 5 * (i % 13), "net_income": income,
                     "operating_cash_flow": income + 10 + (i % 5), "market_cap": 2 * equity + 10 * income})
    gaps = bs.peer_gaps(raws)
    assert len(gaps) == 120 and max(abs(g) for g in gaps.values()) < 0.02      # the fit recovers the rule, up to the winsorised tails
    cheap = bs.peer_gaps([*raws[:-1], {**raws[-1], "market_cap": cast(float, raws[-1]["market_cap"]) / 2}])
    assert cheap[119] > 0.8                                                    # half the price the rule gives: a gap near +1
    assert bs.peer_gaps(raws[:10]) == {}                                       # too few companies to fit a year


def test_the_tables_cut_within_the_year_and_count_the_years() -> None:
    rows = [bs.Row(ticker=f"N{i:03d}", year=y, excess=0.001 * i * (1 if y < 2022 else -1), non_financial=True,
                   values={"earnings_yield": float(i), "f_score": float(i % 10)})
            for y in (2020, 2021, 2022) for i in range(100)]
    q = bs.quintiles(rows, "earnings_yield")
    assert [q[(f"N{i:03d}", 2020)] for i in (0, 19, 20, 99)] == [1, 1, 2, 5]
    before = "\n".join(bs.measure_block([r for r in rows if r.year < 2022], "earnings_yield", "before"))
    assert "200 rows over 2 formation years" in before and "positive in 2 of 2" in before and "highest less lowest, pooled: +0.080" in before
    after = "\n".join(bs.measure_block([r for r in rows if r.year >= 2022], "earnings_yield", "from"))
    assert "positive in 0 of 1" in after
    assert "no formation year carries enough rows" in "\n".join(bs.measure_block(rows[:10], "earnings_yield", "thin"))
    text = bs.report(rows, 32)
    assert "survivors only" in text and "cheap, high score" in text and "peer_gap" in text


def test_the_score_is_taken_apart_by_value_by_signal_and_by_size() -> None:
    prior = year(net_income=80.0, long_term_debt=300.0, current_assets=280.0, current_liabilities=160.0, gross_profit=250.0, revenue=900.0)
    signals = bs.signals_of(year(weighted_shares=105.0), prior)
    assert len(signals) == 9 and signals["no_more_shares"] is False and signals["return_on_assets_positive"] is True
    assert "no_more_shares" not in bs.signals_of(year(weighted_shares=400.0), prior)     # not formed, so not in the map
    rows = [bs.Row(ticker=f"N{i:03d}", year=y, excess=0.01 * (i % 10) - 0.05, non_financial=True, values={"f_score": float(i % 10)},
                   signals={"no_more_shares": i % 2 == 0}, cap=float(i)) for y in (2019, 2020) for i in range(300)]
    text = "\n".join(bs.quality_detail(rows, "test"))
    assert "600 rows carry all nine" in text and "    9: n=60 median excess +0.040" in text
    assert "seven or more less three or fewer: positive in 2 of 2 years" in text
    assert "no_more_shares: passed" in text and "third 3:" in text
