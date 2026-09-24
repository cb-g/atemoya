"""Form 4 (66): the parser on synthetic filings, the cluster rule, the point-in-time cut
and the null reasons. Every fixture here is invented; nothing observed is written down."""

from __future__ import annotations

from collections import Counter
from datetime import date

import insiders


def form4(*, owner: str = "Doe Jane", owner_cik: str = "0000000009", director: str = "1",
          officer: str = "0", title: str | None = None, ten_percent: str = "0",
          plan: str | None = None, transactions: str = "", document: str = "4") -> bytes:
    title_xml = f"<officerTitle>{title}</officerTitle>" if title is not None else ""
    plan_xml = f"<aff10b5One>{plan}</aff10b5One>" if plan is not None else ""
    return f"""<?xml version="1.0"?>
<ownershipDocument>
  <schemaVersion>X0609</schemaVersion>
  <documentType>{document}</documentType>
  <periodOfReport>2026-05-04</periodOfReport>
  <issuer><issuerCik>0000000001</issuerCik><issuerName>Test</issuerName></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>{owner_cik}</rptOwnerCik><rptOwnerName>{owner}</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>{director}</isDirector><isOfficer>{officer}</isOfficer>
      <isTenPercentOwner>{ten_percent}</isTenPercentOwner>{title_xml}
    </reportingOwnerRelationship>
  </reportingOwner>
  {plan_xml}
  <nonDerivativeTable>{transactions}</nonDerivativeTable>
</ownershipDocument>""".encode()


def line(code: str, when: str, shares: float, price: str | None, after: float | None = 1000.) -> str:
    price_xml = f"<transactionPricePerShare><value>{price}</value></transactionPricePerShare>" if price is not None \
        else "<transactionPricePerShare><footnoteId id=\"F1\"/></transactionPricePerShare>"
    after_xml = f"<postTransactionAmounts><sharesOwnedFollowingTransaction><value>{after}</value></sharesOwnedFollowingTransaction></postTransactionAmounts>" if after is not None else ""
    return f"""
    <nonDerivativeTransaction>
      <securityTitle><value>Common</value></securityTitle>
      <transactionDate><value>{when}</value></transactionDate>
      <transactionCoding><transactionFormType>4</transactionFormType><transactionCode>{code}</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>{shares}</value></transactionShares>
        {price_xml}
        <transactionAcquiredDisposedCode><value>{'A' if code in ('P', 'A', 'M') else 'D'}</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      {after_xml}
    </nonDerivativeTransaction>"""


FILED = date(2026, 5, 6)


def test_the_parser_keeps_purchases_and_sales_and_counts_the_rest() -> None:
    """A purchase and a sale are summed; an award, an exercise, a withholding and a gift
    are counted by their code and never summed, because an exercise-and-sell is not a sale
    of conviction. An award files a price of zero, so the filter is on the code, before the
    arithmetic, or the buyer counts inflate where the dollars do not."""
    body = form4(officer="1", director="0", title="Chief Financial Officer",
                 transactions=line("P", "2026-05-04", 100, "10.5") + line("S", "2026-05-04", 50, "12")
                 + line("A", "2026-05-04", 900, "0") + line("M", "2026-05-04", 400, "0")
                 + line("F", "2026-05-04", 30, "12") + line("G", "2026-05-04", 5, "0"))
    kept, excluded = insiders.parse_form4(body, "acc-1", FILED)
    assert [t.code for t in kept] == ["P", "S"]
    assert kept[0].shares == 100 and kept[0].price_per_share == 10.5 and kept[0].dollars == 1050
    assert kept[0].relationship == "officer: Chief Financial Officer"
    assert kept[0].filed == FILED and kept[0].accession == "acc-1"
    assert kept[0].shares_owned_after == 1000
    assert excluded == Counter({"A": 1, "M": 1, "F": 1, "G": 1})


def test_the_parser_survives_what_the_filings_do() -> None:
    """The <value> wrapper is on some fields and not others in one document: the code has
    none and the shares beside it do. Booleans come in two spellings and a filing agent may
    emit only the flag that is true. A price can be a footnote with no value at all."""
    # the code is read without a <value> wrapper, the shares with one
    kept, _ = insiders.parse_form4(form4(transactions=line("P", "2026-05-04", 10, "3")), "a", FILED)
    assert kept and kept[0].shares == 10
    # 'true'/'false' and '1'/'0' both parse, and an absent flag is false, never true
    assert insiders.parse_form4(form4(director="true", transactions=line("P", "2026-05-04", 1, "1")), "a", FILED)[0][0].relationship == "director"
    only_true = b"""<?xml version="1.0"?><ownershipDocument><documentType>4</documentType>
      <reportingOwner><reportingOwnerId><rptOwnerCik>1</rptOwnerCik><rptOwnerName>X</rptOwnerName></reportingOwnerId>
      <reportingOwnerRelationship><isDirector>true</isDirector></reportingOwnerRelationship></reportingOwner>
      <nonDerivativeTable>""" + line("P", "2026-05-04", 1, "1").encode() + b"</nonDerivativeTable></ownershipDocument>"
    kept, _ = insiders.parse_form4(only_true, "a", FILED)
    assert kept[0].relationship == "director"
    # a price that is only a footnote is not a zero-dollar trade: the line is counted, not summed
    kept, excluded = insiders.parse_form4(form4(transactions=line("P", "2026-05-04", 10, None)), "a", FILED)
    assert kept == [] and excluded == Counter({"P (incomplete)": 1})
    # the plan marking is a document-level sibling, not a field of the transaction
    kept, _ = insiders.parse_form4(form4(plan="1", transactions=line("P", "2026-05-04", 1, "1")), "a", FILED)
    assert kept[0].plan_10b5_1 is True
    assert insiders.parse_form4(form4(transactions=line("P", "2026-05-04", 1, "1")), "a", FILED)[0][0].plan_10b5_1 is False
    # rubbish in is nothing out, never an exception
    assert insiders.parse_form4(b"not xml at all", "a", FILED) == ([], Counter())


def test_an_amendment_supersedes_the_filing_it_restates() -> None:
    """Nothing in the index links a 4/A to the 4 it amends: their accessions share only the
    filing agent and the year. So the same line is recognised by what it says, and the later
    filing wins."""
    original, _ = insiders.parse_form4(form4(transactions=line("P", "2026-05-04", 100, "10")), "acc-1", date(2026, 5, 6))
    amended, _ = insiders.parse_form4(form4(document="4/A", transactions=line("P", "2026-05-04", 100, "11")), "acc-9", date(2026, 5, 20))
    kept = insiders.deduplicate(original + amended)
    assert len(kept) == 1 and kept[0].price_per_share == 11 and kept[0].accession == "acc-9"
    # two genuinely different lines are both kept
    other, _ = insiders.parse_form4(form4(owner="Roe Ann", owner_cik="8", transactions=line("P", "2026-05-04", 100, "10")), "acc-2", FILED)
    assert len(insiders.deduplicate(original + other)) == 2


def buy(owner: str, when: str, shares: float = 100, price: str = "10") -> list[insiders.Transaction]:
    return insiders.parse_form4(form4(owner=owner, owner_cik=owner, transactions=line("P", when, shares, price)),
                                f"acc-{owner}-{when}", date.fromisoformat(when))[0]


def test_a_cluster_is_two_distinct_insiders_inside_fourteen_days() -> None:
    """One insider buying twice is not a cluster, which is the whole point of the rule."""
    as_of = date(2026, 6, 1)
    two = buy("Jane", "2026-05-04") + buy("John", "2026-05-15")
    found = insiders.cluster(two, as_of)
    assert found is not None and found.buyers == ["Jane", "John"]
    assert found.window_start == "2026-05-04" and found.window_end == "2026-05-15"
    # the same person twice, however close together
    assert insiders.cluster(buy("Jane", "2026-05-04") + buy("Jane", "2026-05-05"), as_of) is None
    # two people, fifteen days apart
    assert insiders.cluster(buy("Jane", "2026-05-01") + buy("John", "2026-05-16"), as_of) is None
    # and a pair outside the ninety days does not count
    assert insiders.cluster(buy("Jane", "2026-01-04") + buy("John", "2026-01-06"), as_of) is None


def test_the_windows_count_and_never_weight() -> None:
    as_of = date(2026, 6, 1)
    sells = insiders.parse_form4(form4(owner="Sam", owner_cik="7", transactions=line("S", "2026-05-20", 10, "50")), "s", date(2026, 5, 21))[0]
    chief = insiders.parse_form4(form4(owner="Cee Oh", owner_cik="6", officer="1", director="0",
                                       title="Chief Executive Officer", transactions=line("P", "2026-05-02", 20, "25")), "c", date(2026, 5, 4))[0]
    block, reason = insiders.compute(buy("Jane", "2026-05-04") + chief + sells, Counter({"M": 3}), as_of, "0000000001", 3)
    assert reason is None and block is not None
    w = block.window_90
    assert w.buyers == 2 and w.sellers == 1
    assert w.dollars_bought == 100 * 10 + 20 * 25 and w.dollars_sold == 500
    assert w.net_dollars == w.dollars_bought - w.dollars_sold
    assert w.ceo_or_cfo_bought is True
    assert w.largest_purchase is not None and w.largest_purchase.owner == "Jane"
    assert block.cluster_buy is True and block.cluster is not None
    assert dict(block.excluded_by_code) == {"M": 3}
    assert block.filings_read == 3 and block.scope_limits
    # the year holds what the quarter does, and more
    assert block.window_365.buyers == 2
    old = buy("Older", "2025-08-01")
    wide, _ = insiders.compute(old + buy("Jane", "2026-05-04"), Counter(), as_of, "1", 2)
    assert wide is not None and wide.window_90.buyers == 1 and wide.window_365.buyers == 2


def test_the_null_reasons() -> None:
    """A name with no CIK has no Form 4 to read; a CIK with no filing in the year says so."""
    block, reason = insiders.compute([], Counter(), date(2026, 6, 1), "0000000001", 0)
    assert block is None and reason == insiders.NO_FILINGS
    assert "vendor path" in insiders.NO_CIK


def test_a_filing_where_the_name_is_the_owner_is_not_about_the_name() -> None:
    """A CIK's index lists the Form 4s it filed in both capacities: as the issuer, whose
    insiders report trades in its stock, and as a reporting owner of somebody else's. Only
    the first is about this name, and nothing in the index tells them apart."""
    body = form4(owner="Big Holder Inc.", transactions=line("S", "2026-05-04", 10000, "0.12"))
    kept, excluded = insiders.parse_form4(body, "a", FILED, issuer_cik="0000000001")
    assert [t.code for t in kept] == ["S"]                      # this name IS the issuer
    kept, excluded = insiders.parse_form4(body, "a", FILED, issuer_cik="0000000002")
    assert kept == [] and excluded == Counter({"reported as an owner of another issuer": 1})
    # and with no issuer named, every filing is read, as the bare parser tests above do
    assert insiders.parse_form4(body, "a", FILED)[0][0].code == "S"


def test_the_document_url_strips_the_rendering_prefix() -> None:
    """The index's primaryDocument carries an XSL prefix that serves HTML if left on, and
    the accession loses its dashes in the path."""
    assert insiders.document_url("0001321655", "0001823952-26-000022", "xslF345X06/wk-form4_1.xml") == \
        "https://www.sec.gov/Archives/edgar/data/1321655/000182395226000022/wk-form4_1.xml"
    assert insiders.document_url("0000910521", "0001593968-22-001355", "primary_01.xml") == \
        "https://www.sec.gov/Archives/edgar/data/910521/000159396822001355/primary_01.xml"


def test_the_index_selects_only_form_four_and_dates_it() -> None:
    index = {"filings": {"recent": {
        "form": ["10-K", "4", "4/A", "144", "4"],
        "accessionNumber": ["a-0", "a-1", "a-2", "a-3", "a-4"],
        "filingDate": ["2026-02-01", "2026-05-06", "2026-05-20", "2026-05-21", "not a date"],
        "primaryDocument": ["ten.htm", "xslF345X06/one.xml", "xslF345X06/two.xml", "f.htm", "three.xml"],
    }}}
    out = insiders.form4_filings(index)
    assert [a for a, _, _ in out] == ["a-2", "a-1"]      # newest first, the unparsable date dropped
    assert out[0][1] == date(2026, 5, 20)
    assert insiders.form4_filings({}) == []


def test_the_point_in_time_cut_is_on_the_filing_date() -> None:
    """A filing made after the date must not be read, whatever its transaction date: that is
    what makes the block the same one a reader had on the day."""
    import pit

    index = {"filings": {"recent": {
        "form": ["4", "4"],
        "accessionNumber": ["before", "after"],
        "filingDate": ["2026-05-06", "2026-06-30"],
        "reportDate": ["2026-05-04", "2026-05-04"],
        "primaryDocument": ["a.xml", "b.xml"],
        "acceptanceDateTime": ["2026-05-06T12:00:00.000Z", "2026-06-30T12:00:00.000Z"],
    }}}
    cut = pit.submissions_on_or_before(index, date(2026, 6, 1))
    assert cut is not None
    assert [a for a, _, _ in insiders.form4_filings(cut)] == ["before"]


def test_the_chief_test_reads_the_title_as_filed() -> None:
    for title, expected in (("Chief Executive Officer", True), ("Chief Financial Officer", True),
                            ("CFO", True), ("EVP and Chief Accounting Officer", False),
                            ("Chief Technology Officer", False), ("VP (Pres., Products Pipelines)", False)):
        assert bool(insiders.CHIEF.search(f"officer: {title}")) is expected, title
