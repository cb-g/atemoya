# Flow: ticker in, record out

Every branch that exists today, from a ticker in `reference/universe.json` (or an ad-hoc
file plus `--entity-class`) to one line in `output/valuations.jsonl`. Red terminal nodes
are the exact `failed_reason` strings, with variable parts in parentheses, so the chart is
checkable against `output/summary.txt`; a test asserts every reason string in the code
appears here. **Every change that adds a branch updates this file in the same commit.**

Nodes marked *(06)* were added by the bank model, *(07)* by the risk-free fetchers, *(08)* by the insurer model.

```mermaid
flowchart TD
    classDef failed fill:#f8d7da,stroke:#b02a37,color:#58151c
    classDef ok fill:#d1e7dd,stroke:#0f5132,color:#0a3622
    classDef new stroke-dasharray: 4 3

    IN[/"ticker: data/financials/(TICKER).json"/] --> FETCHED{"file parses as boundary financials?"}
    PROVIDER["statements provider (08): the vendor feed (fetch.py, yfinance) for every class but Insurer; filed statements (fetch_sec.py, SEC XBRL companyfacts) for Insurer, with the us-gaap tag per field, filing date and accession on each period; a ticker SEC does not know gets a record with statements_unavailable set"]:::new -.-> IN
    FETCHED -- no --> UNREAD["stderr: cannot read financials; no record"]:::failed
    FETCHED -- yes --> THR{"bank_nii_ratio_threshold fresh?"}
    THR -- "stale / future / missing" --> PFAIL

    THR -- yes --> SIG["statement signature: Bank iff NII/revenue >= threshold, else Insurer iff premium row > 0, else none"]
    SIG --> DECL{"entity_class declared? (universe entry or --entity-class)"}
    DECL -- "no, no signature" --> F_UNDECL["entity_class not declared"]:::failed
    DECL -- "no, signature fired" --> F_UNDECL_HINT["entity_class not declared; statements indicate (Bank|Insurer) (evidence)"]:::failed
    DECL -- "declared OperatingCompany, signature fired" --> F_DISAGREE["class disagreement: declared OperatingCompany, statements indicate (Bank|Insurer) (evidence)"]:::failed
    DECL -- "declared, consistent / absent / differs (recorded in class_check)" --> ROW{"admissibility row for the class?"}

    ROW -- no --> F_NOROW["no admissibility row for entity class (class) in the reference table"]:::failed
    ROW -- yes --> ADM{"first admissible model in the row"}
    ADM -- "none (RegulatedUtility, MerchantPower, Reit, Miner, Royalty, HighGrowthSoftware, PreProfit, Wrapper, ConstructionStage, UnderBid, Ballast)" --> F_INADM["dcf not admissible for (class); lens: (lens)"]:::failed
    ADM -- "dcf (OperatingCompany)" --> COUNTRY
    ADM -- "residual_income (Bank) (06)" --> COUNTRY
    ADM -- "residual_income_insurer (Insurer) (08)" --> COUNTRY

    COUNTRY{"country in the fetch?"} -- no --> F_COUNTRY["country not determinable from the fetch"]:::failed
    COUNTRY -- yes --> PARAMS["resolve parameters: projection_years, risk-free (country, 7y), ERP, statutory tax, terminal growth, debt spread, growth clamp, lambda, beta (industry table or default 1.0)"]
    PARAMS -. "risk-free curve tier (07): official (issuer or central bank) / fred_oecd_10y (the 7y taken from the OECD 10y, recorded as tenor_used) / manual (hand-copied, ages out under the 45-day gate); tier, tenor_requested and tenor_used ride on the parameter" .-> PARAMS
    PARAMS -- "country absent" --> F_NOCURVE["no risk-free curve for country (country)"]:::failed
    PARAMS -- "country absent" --> F_NOPARAM["no (equity_risk_premium|statutory_tax_rate|terminal_growth_rate) for country (country)"]:::failed
    PARAMS -- "tenor absent" --> F_NOTENOR["risk-free curve for (key) has no (tenor) tenor"]:::failed
    PARAMS -- "stale" --> PFAIL["(parameter) for (key) (as_of date) is N days old, older than its max_age_days M"]:::failed
    PARAMS -- "future as_of" --> F_FUTURE["(parameter) for (key) has as_of (date), later than the valuation date (today)"]:::failed
    PARAMS -- "resolved" --> WHICH{"routed model"}

    WHICH -- dcf --> DCF_PERIOD{"latest fiscal period, fields present? (ebit, d&a, capex, cash, total_debt, book_equity, delta_nwc over 2+ periods, price, market cap, currency)"}
    DCF_PERIOD -- "no periods" --> F_NOPERIOD["no fiscal periods in statements"]:::failed
    DCF_PERIOD -- "missing" --> F_MISSING["missing market data: (fields); missing statement fields for fiscal period ending (date): (fields)"]:::failed
    DCF_PERIOD -- ok --> DCF_GUARDS{"guards"}
    DCF_GUARDS -- "price or market cap <= 0" --> F_PRICE["price (p) and market cap (m) must be positive"]:::failed
    DCF_GUARDS -- "horizon < 0" --> F_HORIZON["projection horizon (N) years is negative"]:::failed
    DCF_GUARDS -- "wacc <= terminal growth" --> F_WACC["wacc (w) does not exceed terminal growth (g)"]:::failed
    DCF_GUARDS -- ok --> GROWTH["growth: fundamental (roic x reinvestment rate) if nopat > 0 and net reinvestment > 0, else revenue CAGR (3+ periods) capped at roic; clamp; mean-revert toward terminal at lambda"]
    GROWTH -- "neither computable" --> F_GROWTH["growth not derivable: (why)"]:::failed
    GROWTH --> DCF_EV["fcff = nopat + d&a - capex - mean delta_nwc; EV along the growth path + Gordon terminal; equity = EV - net debt; fair value = equity / (market cap / price)"]
    DCF_EV -- "not finite" --> F_NAN["fair value is not finite (enterprise value (ev), shares (n))"]:::failed
    DCF_EV --> CONCLUDE

    WHICH -- "residual_income (06)" --> RI_PERIOD{"latest fiscal period, fields present? (book_equity, net_income, price, market cap, currency) (06)"}:::new
    RI_PERIOD -- "no periods" --> F_NOPERIOD
    RI_PERIOD -- "missing" --> F_MISSING
    RI_PERIOD -- ok --> RI_GUARDS{"guards (06)"}:::new
    RI_GUARDS -- "price or market cap <= 0" --> F_PRICE
    RI_GUARDS -- "book equity <= 0" --> F_BOOK["book equity (b) is not positive (06)"]:::failed
    RI_GUARDS -- "fewer than 2 periods of net income over positive book" --> F_ROE["roe not derivable: need 2 fiscal periods with net income and positive book equity, have (n) (06)"]:::failed
    RI_GUARDS -- "fewer than 2 periods of dividends over positive net income" --> F_PAYOUT["payout not derivable: need 2 fiscal periods with positive net income and dividends paid, have (n) (06)"]:::failed
    RI_GUARDS -- "cost of equity <= terminal growth" --> F_KE["cost of equity (ke) does not exceed terminal growth (g) (06)"]:::failed
    RI_GUARDS -- "horizon < 0" --> F_HORIZON
    RI_GUARDS -- ok --> RI_EV["ROE_0 = mean net income / book; ROE_t reverts to CAPM cost of equity at lambda; book compounds by retained earnings (retention = 1 - mean payout); equity = book + PV excess returns + PV terminal (spread x ending book / (ke - g)); fair value = equity / shares; loan-loss ratios recorded, never a gate (06)"]:::new
    RI_EV -- "not finite" --> F_RINAN["fair value is not finite (equity value (e), shares (n)) (06)"]:::failed
    RI_EV --> CONCLUDE

    WHICH -- "residual_income_insurer (08)" --> INS_FILED{"filed statements with AOCI and premiums earned? (08)"}:::new
    INS_FILED -- "provider had none, or no AOCI / premiums on the latest period" --> F_FILED["insurer model requires filed-statement data; (why: no SEC filings for (ticker), or the period carries no AOCI or premiums earned) (08)"]:::failed
    INS_FILED -- yes --> INS_CORE["book per period = reported stockholders' equity - AOCI; then the residual-income core above (same guards: roe, payout, cost of equity vs terminal growth); underwriting checks recorded, never gates: combined-ratio proxy, reserves over premiums, AOCI over reported book; solvency null, basis stated (08)"]:::new
    INS_CORE -- "core guard fails" --> F_ROE
    INS_CORE -- "core guard fails" --> F_PAYOUT
    INS_CORE -- "core guard fails" --> F_KE
    INS_CORE --> CONCLUDE

    CONCLUDE{"fair value > 0?"} -- no --> F_NONPOS["non-positive fair value (v): model not applicable"]:::failed
    CONCLUDE -- yes --> BOUND{"margin of safety <= sanity bound 5.0?"}
    BOUND -- no --> F_BOUND["margin of safety (m) exceeds sanity bound 5.00: likely structural break; check entity_class"]:::failed
    BOUND -- yes --> OK["Ok: fair_value, margin_of_safety, signal (Buy >= +25%, Sell <= -25%, else Hold), inputs tagged by model, floor present = true with the model's basis"]:::ok

    F_INADM --> FLOOR
    F_COUNTRY --> FLOOR
    PFAIL --> FLOOR
    F_MISSING --> FLOOR
    F_GROWTH --> FLOOR
    F_ROE --> FLOOR
    F_PAYOUT --> FLOOR
    F_FILED --> FLOOR
    F_NONPOS --> FLOOR
    F_BOUND --> FLOOR
    OK --> RECORD
    FLOOR["floor: present = true (verified), false (PreProfit, Ballast by definition), null (not assessable here), with basis from the admissibility row; scope_limits and lens_note verbatim from the declaration"] --> RECORD[/"record: one line in output/valuations.jsonl; summary groups Failed by reason and inadmissible by class"/]
```

## Reading the chart against a run

`output/summary.txt` lists each ticker's `failed_reason`; find the same string here to see
which branch produced it. Reason text with numbers or names in it is shown with the
variable part in parentheses. Every `Failed` record still carries `floor`, `scope_limits`
and `lens_note`, so the floor node applies to all red terminals, not only the ones drawn
into it.

## Changelog

- entity class (05): declaration, class check, admissibility, floor.
- bank model (06): the residual-income model for `Bank`, its guards and its inputs; the
  admissibility branch now routes to the first admissible model in the row.
- risk-free fetchers (07): risk-free curves come from a source registry in three tiers; a tenor
  substitution is recorded on the parameter, never silent. No new `Failed` string.
- insurer model (08): a second statements provider (filed statements via SEC XBRL) for insurers,
  the insurer model on AOCI-adjusted book, and the `Failed` string for an insurer whose
  provider had no filed statements.
