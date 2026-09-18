"""Tag selection and the annual-fact filter on synthetic companyfacts, and the exact
ticker match against SEC's map."""

from __future__ import annotations

from datetime import date

import fetch_sec


def fact(end: str, val: float, *, start: str | None = None, filed: str = "2026-02-20", form: str = "10-K", fp: str = "FY") -> dict[str, object]:
    d: dict[str, object] = {"end": end, "val": val, "form": form, "fp": fp, "filed": filed, "accn": f"acc-{filed}"}
    if start:
        d["start"] = start
    return d


def usd(*facts: dict[str, object]) -> dict[str, object]:
    return {"units": {"USD": list(facts)}}


def test_annual_filter_drops_quarters_marked_fy_and_keeps_latest_filing() -> None:
    notes: list[str] = []
    out = fetch_sec.annual_facts(
        [fact("2025-12-31", 0.49e9, start="2025-10-01"),          # a quarter marked FY
         fact("2025-12-31", 1.58e9, start="2025-01-01", filed="2026-02-20"),
         fact("2025-12-31", 1.60e9, start="2025-01-01", filed="2026-03-01"),  # restated later: wins
         fact("2025-12-31", 9e9, start="2025-01-01", form="10-Q"),
         {"end": "bad"}],
        instant=False, notes=notes, tag="NetIncomeLoss")
    assert out[date(2025, 12, 31)].val == 1.60e9
    assert notes == ["NetIncomeLoss: 1 companyfacts entries rejected at validation"]
    balances = fetch_sec.annual_facts([fact("2025-12-31", 30e9), fact("2025-12-31", 31e9, start="2025-01-01")],
                                      instant=True, notes=notes, tag="StockholdersEquity")
    assert balances[date(2025, 12, 31)].val == 30e9


def test_pc_and_life_fixtures_resolve_their_benefits_tag_per_period() -> None:
    notes: list[str] = []
    pc = {
        "NetIncomeLoss": usd(fact("2025-12-31", 10e9, start="2025-01-01"), fact("2024-12-31", 4e9, start="2024-01-01")),
        "StockholdersEquity": usd(fact("2025-12-31", 30e9), fact("2024-12-31", 21e9)),
        "AccumulatedOtherComprehensiveIncomeLossNetOfTax": usd(fact("2025-12-31", 0.26e9), fact("2024-12-31", -0.89e9)),
        "PremiumsEarnedNet": usd(fact("2025-12-31", 61e9, start="2025-01-01"), fact("2024-12-31", 58e9, start="2024-01-01")),
        "IncurredClaimsPropertyCasualtyAndLiability": usd(fact("2024-12-31", 41e9, start="2024-01-01")),  # stops in 2024
        "BenefitsLossesAndExpenses": usd(fact("2025-12-31", 56e9, start="2025-01-01"), fact("2024-12-31", 58e9, start="2024-01-01")),
        "PaymentsOfDividendsCommonStock": usd(fact("2025-12-31", 1e9, start="2025-01-01")),
    }
    periods = fetch_sec.periods_from_facts(pc, notes)
    assert [p.period_end for p in periods] == ["2025-12-31", "2024-12-31"]
    p25, p24 = periods
    assert (p25.claims_incurred, p25.claims_incurred_row) == (None, None)
    assert (p25.benefits_losses_and_expenses, p25.benefits_losses_and_expenses_row) == (56e9, "BenefitsLossesAndExpenses")
    assert (p24.claims_incurred, p24.claims_incurred_row) == (41e9, "IncurredClaimsPropertyCasualtyAndLiability")
    assert (p25.aoci, p25.aoci_row) == (0.26e9, "AccumulatedOtherComprehensiveIncomeLossNetOfTax")
    assert p25.book_equity == 30e9 and p25.premiums_earned_row == "PremiumsEarnedNet"
    assert p25.filed == "2026-02-20" and p25.accession == "acc-2026-02-20"
    assert p25.ebit is None and p25.capex is None  # vendor-only fields stay absent

    life = {
        "NetIncomeLoss": usd(fact("2025-12-31", 3.4e9, start="2025-01-01"), fact("2024-12-31", 4.4e9, start="2024-01-01")),
        "StockholdersEquity": usd(fact("2025-12-31", 28.4e9), fact("2024-12-31", 27.5e9)),
        "AccumulatedOtherComprehensiveIncomeLossNetOfTax": usd(fact("2025-12-31", -18e9), fact("2024-12-31", -21e9)),
        "PremiumsEarnedNet": usd(fact("2025-12-31", 49.8e9, start="2025-01-01"), fact("2024-12-31", 45e9, start="2024-01-01")),
        "PolicyholderBenefitsAndClaimsIncurredNet": usd(fact("2025-12-31", 49.7e9, start="2025-01-01"), fact("2024-12-31", 44.7e9, start="2024-01-01")),
        "LiabilityForFuturePolicyBenefits": usd(fact("2025-12-31", 208.9e9)),
    }
    p25 = fetch_sec.periods_from_facts(life, notes)[0]
    assert (p25.claims_incurred_row, p25.future_policy_benefits) == ("PolicyholderBenefitsAndClaimsIncurredNet", 208.9e9)
    assert p25.benefits_losses_and_expenses is None


def test_cik_lookup_is_exact() -> None:
    table = {"0": {"cik_str": 1034670, "ticker": "ALV", "title": "AUTOLIV INC"},
             "1": {"cik_str": 1099219, "ticker": "MET", "title": "METLIFE INC"}}
    assert fetch_sec.cik_for("MET", table) == "0001099219"
    assert fetch_sec.cik_for("met", table) == "0001099219"
    assert fetch_sec.cik_for("ALV.DE", table) is None
