"""The trailing period: the last four filed quarters as one fiscal period, beside the annual ones.

Every model reads the last annual period, and nothing filed after the annual report reaches
a fair value; the recency block (84) says how far behind that is, on revenue alone. This
module reads the whole period the quarters describe, so the four-quarter shadow can value it
with the same model the headline runs on the annual base. The models keep the annual base.

Contract. `of_record(...)` returns (period, basis, None) or (None, None, reason). The period
is a `boundary.FiscalPeriod` whose `period_end` is the latest quarter end at which the filer
reports a fiscal year-to-date net income and a book equity, and whose lines are read by the
same recipes as an annual period's (`fetch_sec`, `reference/field_definitions.json`), from
facts that are:

- for a duration, the fiscal year-to-date figure ending at that quarter, plus the prior
  fiscal year's annual figure, less the prior year's year-to-date figure ending about a year
  earlier: trailing = year-to-date + prior year - prior year-to-date. The prior year is the
  annual period the models read; the two year-to-date figures come from the quarterly
  filing's own accession where it carries both, since a 10-Q presents the prior year's
  comparative in its own presentation;
- for an instant, the balance at that quarter end, from the latest filing that carries it.

A line missing any of its facts is null, never estimated or scaled. Lines no quarterly
filing carries as this tool reads them (restatements, the working-capital reconciliation,
the distributions-filed test, the BDC lines, FFO) are left null or at their defaults, and
the period says so in its notes. Only a filer of Form 10-Q has one: a 20-F filer, a name on
vendor statements, a filer whose latest quarter end is not after the annual base, and one
without an anchoring net income and book equity at a quarter end carry the reason instead.
The point-in-time path passes `as_of`, and every fact is then one filed on or before it.
Nothing here moves an annual period, a model, a belief or a signal."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Mapping

from pydantic import ValidationError

import boundary
import fetch_sec
import reference
from fetch_sec import Fact

QUARTERLY_FORMS = ("10-Q", "10-Q/A")
YEAR_TO_DATE_SPAN_DAYS = {"Q1": (70, 110), "Q2": (160, 200), "Q3": (250, 295)}   # one, two, three quarters
NEAR_DAYS = 10                 # a 52/53-week year moves a quarter end by up to a week
YEAR_DAYS = 365

NO_FACTS = "no filed facts: the statements come from another provider"
NO_QUARTERLY_IFRS = "no quarterly filings in the filed facts: a 20-F filer reports half-years on Form 6-K, which companyfacts does not carry"
NO_ANCHOR = "no quarterly filing carries a fiscal year-to-date net income and a book equity at the same quarter end"
NO_ANNUAL = "no annual period to complete the trailing year with"
NOT_AFTER_BASE = "the latest quarter end is not after the annual base the models read: the trailing year is the annual period"
NO_PRIOR_YEAR = "the annual period before the fiscal year of the latest quarter is not among the periods the models read"

NOTES = [
    "the last four filed quarters as one period: each duration is the fiscal year-to-date figure plus the prior year's annual figure less the prior year's year-to-date figure; each balance is the quarter end's",
    "read for the four-quarter shadow only; the models read the annual periods",
    "not read on a trailing period: restatements, the working-capital reconciliation, the distributions-filed test, the BDC lines, FFO",
]


def _validated(entries: Iterable[object], as_of: date | None) -> list[Fact]:
    out: list[Fact] = []
    for raw in entries:
        try:
            fact = Fact.model_validate(raw)
        except ValidationError:
            continue
        if as_of is not None and fact.filed > as_of:
            continue
        out.append(fact)
    return out


def _latest(facts: list[Fact], *, prefer_accession: str | None = None) -> Fact | None:
    """The latest filed; with [prefer_accession], that filing's fact where it has one."""
    if prefer_accession is not None:
        own = [f for f in facts if f.accn == prefer_accession]
        if own:
            return max(own, key=lambda f: f.filed)
    return max(facts, key=lambda f: f.filed) if facts else None


class Anchor:
    """The latest quarter end the trailing period ends at, and the spans around it."""

    def __init__(self, quarter_end: date, year_start: date, prior_year_end: date, prior_year_start: date,
                 prior_year_to_date_end: date, filed: date, accession: str, quarters: int) -> None:
        self.quarter_end = quarter_end
        self.year_start = year_start
        self.prior_year_end = prior_year_end
        self.prior_year_start = prior_year_start
        self.prior_year_to_date_end = prior_year_to_date_end
        self.filed = filed
        self.accession = accession
        self.quarters = quarters


def year_to_date_facts(entries: Iterable[object], as_of: date | None) -> list[Fact]:
    """The quarterly filings' fiscal year-to-date durations: a 10-Q fact marked Q1 to Q3
    whose span is one, two or three quarters by its mark. A three-month figure in a Q2 or
    Q3 filing is not one."""
    out: list[Fact] = []
    for fact in _validated(entries, as_of):
        if fact.form not in QUARTERLY_FORMS or fact.start is None or fact.fp not in YEAR_TO_DATE_SPAN_DAYS:
            continue
        lo, hi = YEAR_TO_DATE_SPAN_DAYS[fact.fp]
        if lo <= (fact.end - fact.start).days <= hi:
            out.append(fact)
    return out


def anchor_of(gaap: Mapping[str, object], tags: reference.XbrlTags, unit: str, annual_periods: list[boundary.FiscalPeriod],
              as_of: date | None) -> tuple[Anchor | None, str | None]:
    """The latest quarter end with a year-to-date net income and a book equity, and the
    annual period before its fiscal year, or the reason there is none."""
    table = dict(tags.fields)
    income_tags = table["net_income"].tags if "net_income" in table else []
    equity_tags = table["book_equity"].tags if "book_equity" in table else []
    candidates: list[Fact] = []
    for tag in income_tags:
        candidates.extend(year_to_date_facts(fetch_sec._entries(gaap.get(tag), unit), as_of))  # pyright: ignore[reportPrivateUsage]
    equity_ends: set[date] = set()
    for tag in equity_tags:
        for fact in _validated(fetch_sec._entries(gaap.get(tag), unit), as_of):  # pyright: ignore[reportPrivateUsage]
            if fact.start is None:
                equity_ends.add(fact.end)
    anchored = [f for f in candidates if f.end in equity_ends]
    if not anchored:
        return None, NO_ANCHOR
    latest_end = max(f.end for f in anchored)
    fact = max((f for f in anchored if f.end == latest_end), key=lambda f: f.filed)
    assert fact.start is not None
    if not annual_periods:
        return None, NO_ANNUAL
    ends = sorted(date.fromisoformat(p.period_end) for p in annual_periods)
    if latest_end <= ends[-1]:
        return None, NOT_AFTER_BASE
    before = [e for e in ends if e < fact.start]
    if not before or (fact.start - before[-1]).days > NEAR_DAYS:
        return None, NO_PRIOR_YEAR
    prior_year_end = before[-1]
    prior_year_start = _annual_start(gaap, income_tags, tags, unit, prior_year_end, as_of)
    if prior_year_start is None:
        return None, NO_PRIOR_YEAR
    quarters = round((latest_end - fact.start).days / 91)
    return Anchor(latest_end, fact.start, prior_year_end, prior_year_start,
                  latest_end - timedelta(days=YEAR_DAYS), fact.filed, fact.accn, max(1, min(3, quarters))), None


def _annual_start(gaap: Mapping[str, object], income_tags: list[str], tags: reference.XbrlTags, unit: str, end: date,
                  as_of: date | None) -> date | None:
    lo, hi = tags.annual_span_days
    for tag in income_tags:
        for fact in _validated(fetch_sec._entries(gaap.get(tag), unit), as_of):  # pyright: ignore[reportPrivateUsage]
            if fact.form in tags.annual_forms and fact.fp == "FY" and fact.start is not None and fact.end == end \
                    and lo <= (fact.end - fact.start).days <= hi:
                return fact.start
    return None


class TrailingFacts(fetch_sec.Facts):
    """A filer's facts read at the anchor's quarter end: a duration is the trailing four
    quarters, an instant the balance at the quarter end. Every recipe in `fetch_sec` reads
    through `annual`, so the same recipes build the trailing period unchanged."""

    def __init__(self, gaap: Mapping[str, object], tags: reference.XbrlTags, notes: list[str], *, unit: str,
                 anchor: Anchor, as_of: date | None) -> None:
        super().__init__(gaap, tags, notes, unit=unit)
        self.anchor = anchor
        self.as_of = as_of

    def annual(self, tag: str, *, instant: bool, unit: str | None = None) -> dict[date, Fact]:
        key = (tag, instant, unit or self._unit)
        if key not in self._memo:
            entries = fetch_sec._entries(self._gaap.get(tag), unit or self._unit)  # pyright: ignore[reportPrivateUsage]
            fact = self.instant_at_end(entries) if instant else self.trailing(entries)
            self._memo[key] = {} if fact is None else {self.anchor.quarter_end: fact}
        return self._memo[key]

    def instant_at_end(self, entries: Iterable[object]) -> Fact | None:
        a = self.anchor
        return _latest([f for f in _validated(entries, self.as_of) if f.start is None and f.end == a.quarter_end])

    def trailing(self, entries: Iterable[object]) -> Fact | None:
        """year-to-date + prior year - prior year-to-date, or None when any is missing."""
        a = self.anchor
        facts = _validated(entries, self.as_of)
        lo, hi = self._tags.annual_span_days
        current = _latest([f for f in facts if f.form in QUARTERLY_FORMS and f.start == a.year_start and f.end == a.quarter_end],
                          prefer_accession=a.accession)
        prior_year = _latest([f for f in facts if f.form in self._tags.annual_forms and f.fp == "FY" and f.start is not None
                              and f.end == a.prior_year_end and lo <= (f.end - f.start).days <= hi])
        prior_ytd = _latest([f for f in facts if f.form in QUARTERLY_FORMS and f.start == a.prior_year_start
                             and abs((f.end - a.prior_year_to_date_end).days) <= NEAR_DAYS],
                            prefer_accession=a.accession)
        if current is None or prior_year is None or prior_ytd is None:
            return None
        return Fact(end=a.quarter_end, start=a.prior_year_to_date_end + timedelta(days=1),
                    val=current.val + prior_year.val - prior_ytd.val,
                    form=current.form, fp=current.fp, filed=current.filed, accn=current.accn)


def _rows(composition: boundary.Composition | None, row: str | None) -> set[str]:
    """The tags a derived line was assembled from: the composition's, else the row itself."""
    if composition is not None and composition.components:
        return {c.row for c in composition.components}
    return {row} if row else set()


def _roles(composition: boundary.Composition | None) -> set[str]:
    """The parts a derived line was assembled from, by the recipe's name for each."""
    return set() if composition is None else {c.name for c in composition.components}


DEBT_WHOLE = ("aggregate", "total_including_current")   # a filer's own total: a complete recipe on its own
DEBT_PAIRS = ({"noncurrent", "current_total"}, {"noncurrent", "current_long_term"})   # a complete pair


def _complete(field: str, base_value: float | None, base_composition: boundary.Composition | None, base_row: str | None,
              derived: fetch_sec.Derived, notes: list[str]) -> fetch_sec.Derived:
    """[derived] when the trailing recipe is whole against the annual base's, else null with a
    note. Whole means: for total_debt, a filer total or a complete pair (the recipes the
    annual reads first), or a component sum carrying every row the annual's did, or zero by
    absence only where the annual was zero too; for cash, every role the annual's recipe
    assembled (equivalents, the restricted deductions, short-term investments) unless the
    trailing reads the inclusive total; for delta_nwc, the aggregate, or every row the
    annual's component sum read."""
    value, row, composition = derived
    if value is None:
        return derived
    roles, base_roles = _roles(composition), _roles(base_composition)
    missing: list[str]
    if field == "total_debt":
        if any(r in roles for r in DEBT_WHOLE) or any(pair <= roles for pair in DEBT_PAIRS):
            return derived
        if not roles:   # zero by absence: no debt line and no interest, which the annual must also have found
            if base_value == 0.0:
                return derived
            missing = sorted(_rows(base_composition, base_row)) or ["the annual period's debt"]
        else:
            missing = sorted(_rows(base_composition, base_row) - _rows(composition, row))
    elif field == "cash":
        missing = [] if "cash_and_investments" in roles else sorted(base_roles - roles)
    else:
        missing = [] if "aggregate" in roles else sorted(_rows(base_composition, base_row) - _rows(composition, row))
    if not missing:
        return derived
    notes.append(f"{field}: the annual period's recipe reads {', '.join(missing)}, which ha{'s' if len(missing) == 1 else 've'} no trailing fact; left null rather than a partial sum")
    return None, None, None


def select_trailing(facts: TrailingFacts, tags: reference.XbrlTags, taxonomy: str) -> dict[str, dict[date, tuple[Fact, str]]]:
    """Per canonical field, the first candidate tag with a trailing (or quarter-end) fact."""
    out: dict[str, dict[date, tuple[Fact, str]]] = {}
    for field, spec in fetch_sec.taxonomy_fields(tags, taxonomy):
        per_end: dict[date, tuple[Fact, str]] = {}
        for tag in spec.tags:
            for end, fact in facts.annual(tag, instant=spec.kind == "instant").items():
                per_end.setdefault(end, (fact, tag))
        out[field] = per_end
    return out


def of_record(facts: Mapping[str, object] | None, taxonomy: str, unit: str | None, tags: reference.XbrlTags,
              defs: reference.FieldDefinitions, params: reference.Params, annual_periods: list[boundary.FiscalPeriod],
              *, as_of: date | None = None) -> tuple[boundary.FiscalPeriod | None, boundary.TrailingBasis | None, str | None]:
    """The trailing period with its basis, or None with the reason."""
    if facts is None or not taxonomy or unit is None:
        return None, None, NO_FACTS
    if taxonomy == "ifrs-full":
        return None, None, NO_QUARTERLY_IFRS
    gaap = fetch_sec._as_dict(fetch_sec._as_dict(facts.get("facts")).get(taxonomy))  # pyright: ignore[reportPrivateUsage]
    anchor, reason = anchor_of(gaap, tags, unit, annual_periods, as_of)
    if anchor is None:
        return None, None, reason
    notes: list[str] = []
    t = TrailingFacts(gaap, tags, notes, unit=unit, anchor=anchor, as_of=as_of)
    selected = select_trailing(t, tags, taxonomy)
    end = anchor.quarter_end
    v: dict[str, float | None] = {}
    r: dict[str, str | None] = {}
    for field, _ in fetch_sec.taxonomy_fields(tags, taxonomy):
        v[field], r[field] = fetch_sec.value_of(selected, field, end)
    dna, dna_row, dna_candidates, dna_recipe, dna_composition = fetch_sec.depreciation(t, selected, tags, defs, end, taxonomy=taxonomy)
    v["capex"], r["capex"] = fetch_sec.capex_with_software(t, tags, end, v["capex"], r["capex"])
    v["net_income"], r["net_income"] = fetch_sec.parent_net_income(t, tags, end, v["net_income"], r["net_income"])
    cash_value, cash_row, cash_composition = fetch_sec.cash(t, defs, end)
    debt, debt_row, debt_composition = fetch_sec.total_debt(t, defs, params, end)
    nwc, nwc_row, nwc_composition = fetch_sec.delta_nwc(t, defs, end, notes)
    ebit_value, ebit_row, ebit_recipe, ebit_composition = fetch_sec.ebit(t, defs, end, v["pretax_income"], r["pretax_income"], taxonomy=taxonomy)
    alt_value, alt_composition = (fetch_sec.ebit_alternative(t, defs, end, v["total_revenue"], r["total_revenue"], taxonomy=taxonomy)
                                  if ebit_recipe is not None and ebit_recipe != "operating_income" else (None, None))
    shares = fetch_sec.weighted_shares(t, defs, end, taxonomy=taxonomy)
    interest_value, interest_row, interest_recipe = fetch_sec.interest_expense(t, defs, end, taxonomy=taxonomy)
    aoci_value, aoci_row, aoci_recipe, aoci_composition = fetch_sec.aoci(t, defs, end, (v["aoci"], r["aoci"]))
    preferred_value, preferred_row = fetch_sec.preferred_equity_of(v["preferred_equity"], r["preferred_equity"])
    common_dividends, common_dividends_row = fetch_sec.common_dividends_of(
        v["common_dividends_paid"], r["common_dividends_paid"], v["dividends_paid"], v["preferred_dividends"])
    bridge = fetch_sec.bridge_lines(t, defs, end, taxonomy=taxonomy)
    # Completeness: a recipe that sums components, or takes the largest of several totals,
    # reads what is present, and on an annual period what is present is what the filer
    # tags that year. On a trailing period a line the 10-K tags may have no 10-Q facts (a
    # liability the quarterly filing folds into another tag), and the sum would silently be
    # the asset side alone (Crocs, 2026-10-18). So every row the annual base's recipe used
    # must be in the trailing recipe's, else the line is null and the notes say which row.
    base = next((p for p in annual_periods if p.period_end == anchor.prior_year_end.isoformat()), None)
    if base is not None:
        cash_value, cash_row, cash_composition = _complete("cash", base.cash, base.cash_composition, base.cash_row, (cash_value, cash_row, cash_composition), notes)
        debt, debt_row, debt_composition = _complete("total_debt", base.total_debt, base.total_debt_composition, base.total_debt_source, (debt, debt_row, debt_composition), notes)
        nwc, nwc_row, nwc_composition = _complete("delta_nwc", base.delta_nwc, base.delta_nwc_composition, base.delta_nwc_row, (nwc, nwc_row, nwc_composition), notes)
        if dna is not None and base.depreciation_amortization_row is not None and dna_row is not None \
                and base.depreciation_amortization_row not in dna_row \
                and not any(c.row == base.depreciation_amortization_row for c in (dna_candidates or [])):
            notes.append(f"depreciation_amortization: the annual period reads {base.depreciation_amortization_row}, which has no trailing fact; left null rather than a smaller total")
            dna, dna_row, dna_candidates, dna_recipe, dna_composition = None, None, None, None, None
    investees = fetch_sec.investees_in_operating_income(t, defs, end, v["total_revenue"])
    due, due_row = fetch_sec.debt_due_within_year(t, defs, end, debt_composition)
    period = boundary.FiscalPeriod(
        period_end=end.isoformat(),
        ebit=ebit_value, pretax_income=v["pretax_income"], tax_provision=v["tax_provision"],
        total_revenue=v["total_revenue"], net_interest_income=v["net_interest_income"],
        premiums_earned=v["premiums_earned"], premiums_earned_row=r["premiums_earned"],
        depreciation_amortization=dna, depreciation_amortization_row=dna_row, depreciation_amortization_candidates=dna_candidates,
        depreciation_amortization_recipe=dna_recipe, depreciation_amortization_composition=dna_composition,
        capex=v["capex"], delta_nwc=nwc, cash=cash_value,
        total_debt=debt, total_debt_source=debt_row,
        book_equity=v["book_equity"], net_income=v["net_income"],
        goodwill=v["goodwill"], goodwill_row=r["goodwill"],
        **fetch_sec.bridge_fields(bridge),
        investees_in_operating_income=investees, debt_due_within_year=due, debt_due_within_year_row=due_row,
        dividends_paid=v["dividends_paid"], dividends_paid_row=r["dividends_paid"],
        operating_cash_flow=v["operating_cash_flow"], operating_cash_flow_row=r["operating_cash_flow"],
        net_income_to_common=v["net_income_to_common"], net_income_to_common_row=r["net_income_to_common"],
        preferred_equity=preferred_value, preferred_equity_row=preferred_row,
        preferred_dividends=v["preferred_dividends"], preferred_dividends_row=r["preferred_dividends"],
        preferred_outside_equity=None,
        common_dividends_paid=common_dividends, common_dividends_paid_row=common_dividends_row,
        provision_for_credit_losses=None, provision_for_credit_losses_row=None,
        net_loans=None, net_loans_row=None,
        filed=anchor.filed.isoformat(), accession=anchor.accession,
        restated_from=[], no_distributions_filed=None,
        working_capital_reconciled=None, working_capital_gap=None,
        aoci=aoci_value, aoci_row=aoci_row, aoci_recipe=aoci_recipe, aoci_composition=aoci_composition,
        claims_incurred=v["claims_incurred"], claims_incurred_row=r["claims_incurred"],
        benefits_losses_and_expenses=v["benefits_losses_and_expenses"], benefits_losses_and_expenses_row=r["benefits_losses_and_expenses"],
        policy_acquisition_expense=v["policy_acquisition_expense"], policy_acquisition_expense_row=r["policy_acquisition_expense"],
        operating_expense=v["operating_expense"], operating_expense_row=r["operating_expense"],
        future_policy_benefits=v["future_policy_benefits"], future_policy_benefits_row=r["future_policy_benefits"],
        claims_liability=v["claims_liability"], claims_liability_row=r["claims_liability"],
        total_revenue_row=r["total_revenue"], ebit_row=ebit_row, pretax_income_row=r["pretax_income"],
        tax_provision_row=r["tax_provision"], capex_row=r["capex"], delta_nwc_row=nwc_row,
        cash_row=cash_row, book_equity_row=r["book_equity"], net_income_row=r["net_income"],
        net_interest_income_row=r["net_interest_income"],
        ebit_recipe=ebit_recipe, ebit_composition=ebit_composition,
        ebit_alternative=alt_value, ebit_alternative_composition=alt_composition,
        interest_expense=interest_value, interest_expense_row=interest_row, interest_recipe=interest_recipe,
        cash_composition=cash_composition,
        total_debt_composition=debt_composition, delta_nwc_composition=nwc_composition,
        ffo=None, ffo_composition=None, ffo_unavailable="not read on a trailing period",
        net_asset_value_per_share=None, net_asset_value_per_share_row=None, net_asset_value_composition=None,
        net_investment_income=None, net_investment_income_row=None, net_investment_income_composition=None,
        distributions_per_share=None, distributions_per_share_row=None,
        weighted_shares=None if shares is None else shares[0], weighted_shares_tag=None if shares is None else shares[1],
    )
    basis = boundary.TrailingBasis(
        quarter_end=end.isoformat(), year_to_date_start=anchor.year_start.isoformat(),
        prior_year_end=anchor.prior_year_end.isoformat(), prior_year_to_date_end=anchor.prior_year_to_date_end.isoformat(),
        quarters_in_year_to_date=anchor.quarters, filed=anchor.filed.isoformat(), accession=anchor.accession,
        notes=NOTES + notes)
    return period, basis, None


NO_BRIDGE_DEFINITION = "reference/field_definitions.json carries no equity_bridge definition"


def distributions_of(facts: Mapping[str, object] | None, taxonomy: str, unit: str | None, tags: reference.XbrlTags,
                     defs: reference.FieldDefinitions, annual_periods: list[boundary.FiscalPeriod],
                     *, as_of: date | None = None) -> tuple[boundary.Distributions | None, str | None]:
    """What went to shareholders between the annual base and the latest quarter: each line the
    quarterly filing's fiscal year-to-date figure from the day after the base to the quarter
    end the trailing period anchors on, first present by the equity bridge's tag lists, an
    absent line nil in the sum; or None with the reason. The same quarter end as the trailing
    period, so a filer with no trailing period has no figures here either."""
    if facts is None or not taxonomy or unit is None:
        return None, NO_FACTS
    if taxonomy == "ifrs-full":
        return None, NO_QUARTERLY_IFRS
    if defs.equity_bridge is None:
        return None, NO_BRIDGE_DEFINITION
    gaap = fetch_sec._as_dict(fetch_sec._as_dict(facts.get("facts")).get(taxonomy))  # pyright: ignore[reportPrivateUsage]
    anchor, reason = anchor_of(gaap, tags, unit, annual_periods, as_of)
    if anchor is None:
        return None, reason

    def year_to_date(candidates: Iterable[str]) -> tuple[float | None, str | None]:
        for tag in candidates:
            facts_ = _validated(fetch_sec._entries(gaap.get(tag), unit), as_of)  # pyright: ignore[reportPrivateUsage]
            hit = _latest([f for f in facts_ if f.form in QUARTERLY_FORMS and f.start == anchor.year_start and f.end == anchor.quarter_end],
                          prefer_accession=anchor.accession)
            if hit is not None:
                return hit.val, tag
        return None, None

    d = defs.equity_bridge.xbrl
    repurchases, repurchases_row = year_to_date(d.repurchases)
    dividends, dividends_row = year_to_date(d.dividends)
    issuance, issuance_row = year_to_date(d.issuance)
    buyouts, buyouts_row = year_to_date(d.minority_buyouts)
    buyouts_book, buyouts_book_row = year_to_date(d.minority_buyouts_book) if buyouts is not None else (None, None)
    return boundary.Distributions(
        since=anchor.prior_year_end.isoformat(), through=anchor.quarter_end.isoformat(),
        repurchases=repurchases, repurchases_row=repurchases_row,
        dividends=dividends, dividends_row=dividends_row,
        issuance=issuance, issuance_row=issuance_row,
        net=(repurchases or 0.0) + (dividends or 0.0) - (issuance or 0.0),
        minority_buyouts=buyouts, minority_buyouts_row=buyouts_row,
        minority_buyouts_book=buyouts_book, minority_buyouts_book_row=buyouts_book_row,
        minority_net=None if buyouts is None else max(0.0, buyouts - (buyouts_book or 0.0)),
        filed=anchor.filed.isoformat(), accession=anchor.accession), None
