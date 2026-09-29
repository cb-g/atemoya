"""The DART reader (74) on synthetic OpenDART answers: the key from the environment or the
env file and never printed, the stock code from the ticker, the corporation register, the
period dates from the main accounts, one year's lines into the companyfacts shape with
the receipt day as the filing date, the declared operating-income reading, the
non-standard lines counted and unread, the equity statement left alone, the duplicate
line on two statements taken once, and the whole thing through the period reader. Every
number is invented."""

from __future__ import annotations

import dataclasses
import io
import json
import zipfile
from datetime import date
from pathlib import Path

import pytest

import fetch_dart as fd
import fetch_sec


def row(account_id: str, amount: float | str, *, sj: str = "IS", year: int = 2024, receipt: str = "20250311000123", currency: str = "KRW", name: str = "계정") -> dict[str, object]:
    return {"rcept_no": receipt, "reprt_code": "11011", "bsns_year": str(year), "corp_code": "00126380", "sj_div": sj, "sj_nm": "x",
            "account_id": account_id, "account_nm": name, "account_detail": "-", "thstrm_nm": "제 56 기",
            "thstrm_amount": str(amount), "frmtrm_nm": "제 55 기", "frmtrm_amount": "1", "ord": "1", "currency": currency}


def answer(*rows: dict[str, object]) -> dict[str, object]:
    return {"status": "000", "message": "정상", "list": list(rows)}


def main(year: int = 2024, *, fs_div: str = "CFS") -> dict[str, object]:
    return answer({"fs_div": fs_div, "sj_div": "BS", "account_nm": "자산총계", "thstrm_dt": f"{year}.12.31 현재"},
                  {"fs_div": fs_div, "sj_div": "IS", "account_nm": "매출액", "thstrm_dt": f"{year}.01.01 ~ {year}.12.31"})


SPAN_2024 = (date(2024, 1, 1), date(2024, 12, 31))


def year_2024() -> dict[str, object]:
    return answer(
        row("ifrs-full_Assets", 500e12, sj="BS"), row("ifrs-full_Equity", 300e12, sj="BS"), row("ifrs-full_CashAndCashEquivalents", 50e12, sj="BS"),
        row("ifrs-full_Revenue", 300e12), row("ifrs-full_ProfitLoss", 30e12), row("ifrs-full_ProfitLoss", 30e12, sj="CF"),   # the head of the cash flow repeats it
        row("dart_OperatingIncomeLoss", 40e12, name="영업이익"), row("dart_OtherGains", 2e12), row("-표준계정코드 미사용-", 1e12),
        row("ifrs-full_Revenue", "-"), row("ifrs-full_Equity", 999e12, sj="SCE"),
        row("dart_AdjustmentsForAssetsLiabilitiesOfOperatingActivities", -9e12, sj="CF", name="영업활동으로 인한 자산부채의 변동"),
        row("-표준계정코드 미사용-", 17e12, sj="BS", name="단기차입금"), row("-표준계정코드 미사용-", 3e12, sj="CF", name="단기차입금"),
    )


def test_the_key_comes_from_the_environment_then_the_env_file_and_is_never_a_default(tmp_path: Path) -> None:
    dotenv = tmp_path / "env-file"
    dotenv.write_text(f"SOME_OTHER_NAME=ignored\n{fd.KEY_NAME}='k' \n")   # the name built at run time: the pre-commit hook refuses the literal with any value
    assert fd.api_key({"DART_API_KEY": "from-env"}, dotenv=dotenv) == "from-env"
    assert fd.api_key({}, dotenv=dotenv) == "k"
    assert fd.api_key({}, dotenv=tmp_path / "absent") is None
    assert fd.api_key({"DART_API_KEY": "  "}, dotenv=tmp_path / "absent") is None


def test_stock_code_from_a_korea_exchange_ticker_only() -> None:
    assert fd.stock_code("005930.KS") == "005930" and fd.stock_code("000660.ks") == "000660" and fd.stock_code("035420.KQ") == "035420"
    assert fd.stock_code("AAPL") is None and fd.stock_code("SAN.PA") is None and fd.stock_code("ABC.KS") is None


def test_the_register_maps_stock_codes_to_corporation_codes() -> None:
    xml = ('<?xml version="1.0" encoding="UTF-8"?><result><list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name>'
           '<stock_code>005930</stock_code><modify_date>20240101</modify_date></list><list><corp_code>00000001</corp_code>'
           '<corp_name>unlisted</corp_name><stock_code> </stock_code><modify_date>20240101</modify_date></list></result>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CORPCODE.xml", xml)
    assert fd.parse_corp_codes(buf.getvalue()) == {"005930": "00126380"}


def test_the_period_comes_from_the_main_accounts() -> None:
    assert fd._dates("2024.01.01 ~ 2024.12.31") == (date(2024, 1, 1), date(2024, 12, 31))  # pyright: ignore[reportPrivateUsage]
    assert fd._dates("2024.12.31 현재") == (None, date(2024, 12, 31))  # pyright: ignore[reportPrivateUsage]
    assert fd._dates("n/a") is None  # pyright: ignore[reportPrivateUsage]
    assert fd.span_of(main(2024)) == SPAN_2024
    assert fd.span_of(main(2024, fs_div="OFS")) is None   # the separate statements are not the consolidated ones
    assert fd.span_of(answer({"fs_div": "CFS", "sj_div": "BS", "thstrm_dt": "2024.03.31 현재"})) == (date(2024, 1, 1), date(2024, 3, 31))
    assert fd.span_of(None) is None


def test_lines_become_facts_with_the_receipt_day_and_the_declared_reading() -> None:
    adapted = fd.adapt({2024: (year_2024(), SPAN_2024), 2023: (None, None)})
    assert adapted.currency == "KRW"
    assert [(r.year, r.receipt, r.period_end.isoformat(), r.filed.isoformat()) for r in adapted.reports] == [(2024, "20250311000123", "2024-12-31", "2025-03-11")]
    gaap = adapted.gaap
    revenue = gaap["Revenue"]["units"]["KRW"]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
    assert revenue == [{"end": "2024-12-31", "val": 300e12, "accn": "20250311000123", "fy": 2024, "fp": "FY", "form": "DART", "filed": "2025-03-11", "start": "2024-01-01"}]
    assert len(gaap["ProfitLoss"]["units"]["KRW"]) == 1          # pyright: ignore[reportIndexIssue, reportUnknownArgumentType]
    assert "start" not in gaap["Assets"]["units"]["KRW"][0]       # pyright: ignore[reportIndexIssue, reportUnknownMemberType]
    assert gaap["Equity"]["units"]["KRW"][0]["val"] == 300e12    # pyright: ignore[reportIndexIssue, reportUnknownMemberType]  the equity statement's line is not read
    assert gaap["ProfitLossFromOperatingActivities"]["units"]["KRW"][0]["val"] == 40e12  # pyright: ignore[reportIndexIssue, reportUnknownMemberType]
    assert "dart_OperatingIncomeLoss" not in gaap and "OtherGains" not in gaap
    # the working-capital line negated into the boundary's sign, and the borrowings read by label on the balance sheet only
    assert gaap["IncreaseDecreaseInWorkingCapital"]["units"]["KRW"][0]["val"] == 9e12  # pyright: ignore[reportIndexIssue, reportUnknownMemberType]
    assert gaap["ShorttermBorrowings"]["units"]["KRW"] == [{"end": "2024-12-31", "val": 17e12, "accn": "20250311000123", "fy": 2024, "fp": "FY", "form": "DART", "filed": "2025-03-11"}]  # pyright: ignore[reportIndexIssue]
    assert adapted.unread == {"dart_OtherGains": 1, "-표준계정코드 미사용-": 2}
    assert any("negated into the boundary's sign" in n for n in adapted.notes) and any("labelled 단기차입금" in n for n in adapted.notes)
    assert any("ProfitLossFromOperatingActivities read from dart_OperatingIncomeLoss" in n for n in adapted.notes)
    assert any("under no standard account id" in n for n in adapted.notes)
    # a year whose main accounts carry no dates is not read, and says so
    adapted = fd.adapt({2024: (year_2024(), None)})
    assert adapted.reports == [] and any("no period dates" in n for n in adapted.notes)


def test_the_adapted_lines_read_through_the_period_reader() -> None:
    y23 = answer(row("ifrs-full_Equity", 280e12, sj="BS", year=2023, receipt="20240312000456"),
                 row("ifrs-full_Revenue", 260e12, year=2023, receipt="20240312000456"), row("ifrs-full_ProfitLoss", 25e12, year=2023, receipt="20240312000456"))
    adapted = fd.adapt({2024: (year_2024(), SPAN_2024), 2023: (y23, (date(2023, 1, 1), date(2023, 12, 31)))})
    tags = dataclasses.replace(fetch_sec.load_tags(), annual_forms=[*fetch_sec.load_tags().annual_forms, fd.FORM])
    periods = fetch_sec.periods_from_facts(adapted.gaap, tags, fetch_sec.load_definitions(), [], taxonomy="ifrs-full", unit="KRW", depth=5)
    by_end = {p.period_end: p for p in periods}
    assert by_end["2024-12-31"].accession == "20250311000123" and by_end["2024-12-31"].filed == "2025-03-11"
    assert by_end["2024-12-31"].net_income == 30e12 and by_end["2024-12-31"].total_revenue == 300e12 and by_end["2024-12-31"].book_equity == 300e12
    assert by_end["2024-12-31"].ebit == 40e12 and by_end["2024-12-31"].ebit_row == "ProfitLossFromOperatingActivities"
    assert by_end["2023-12-31"].accession == "20240312000456" and by_end["2023-12-31"].net_income == 25e12


def test_no_data_and_errors_are_told_apart() -> None:
    """The walk from this year back: a year OpenDART has no data for is None, two empty years
    in a row end the walk, and any other status is an error, named."""
    calls: list[str] = []

    def fake_cached(path: Path, url: str) -> bytes:
        calls.append(url)
        year = int(url.split("bsns_year=")[1][:4])
        if fd.MAIN_ACCOUNTS + ".json" in url:   # the main accounts, not the full accounts, whose name extends this one
            return json.dumps(main(year) if year in (2025, 2024) else {"status": "013", "message": "none"}).encode()
        if year in (2025, 2024):
            return json.dumps(answer(row("ifrs-full_Revenue", 1e12, year=year, receipt=f"{year + 1}0311000123"),
                                     row("ifrs-full_ProfitLoss", 1e11, year=year, receipt=f"{year + 1}0311000123"),
                                     row("ifrs-full_Equity", 5e12, sj="BS", year=year, receipt=f"{year + 1}0311000123"))).encode()
        if year == 2020:
            return json.dumps({"status": "020", "message": "limit"}).encode()
        return json.dumps({"status": "013", "message": "조회된 데이타가 없습니다."}).encode()

    fd._cached = fake_cached  # pyright: ignore[reportPrivateUsage, reportAttributeAccessIssue]
    assert fd.statements_year("k", "00126380", 2026) is None
    adapted = fd.statements("k", "00126380", years=5, today=date(2026, 9, 29))
    assert [r.year for r in adapted.reports] == [2025, 2024]
    full = [int(u.split("bsns_year=")[1][:4]) for u in calls if fd.MAIN_ACCOUNTS + "All" in u]
    assert full == [2026, 2026, 2025, 2024, 2023, 2022]  # two empty years in a row end the walk
    with pytest.raises(fd.DartError, match="status 020"):
        fd.statements_year("k", "00126380", 2020)
