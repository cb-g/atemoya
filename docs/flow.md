# Flow: ticker in, record out

![The stages from a universe entry to a record and the tools that hang off it](flow.svg)

The chart shows stages only; `docs/flow.mmd` is its source and the two change together.
Every `failed_reason` a record can carry is in the table below against the stage that
emits it, with variable parts in parentheses, so a line of `output/summary.txt` can be
traced to a stage. A test asserts that every reason string in the code appears in this
file.

## Every Failed reason, by stage

| stage | reason as the record carries it |
|---|---|
| read | stderr: cannot read financials; no record |
| declaration | entity_class not declared |
| declaration | entity_class not declared; statements indicate (Bank or Insurer) (evidence) |
| declaration | class disagreement: declared OperatingCompany, statements indicate (Bank or Insurer) (evidence) |
| admissibility | no admissibility row for entity class (class) in the reference table |
| admissibility | dcf not admissible for (class); lens: (lens) |
| country | country not determinable from the fetch |
| point-in-time gates | no point-in-time statements: (vendor provider carries no filing dates, or filed statements lag on the date: ...) |
| point-in-time gates | no point-in-time shares: no cover page or balance-sheet count filed by the date, or no share count within 400 days of the period |
| point-in-time gates | rate source has no history for (currency) |
| currency gate | financial currency disagreement: filing (X), vendor (Y) |
| definitions gate | field definition mismatch: (field) follows (recorded), reference/field_definitions.json defines (name); refetch the statements |
| filing age | latest annual filing is N days old, older than its max_filing_age_days 400 |
| currency gate | missing market data: financial_currency, or missing market data: trading_currency |
| FX | fx not fetched for (financial)/(trading): run python/refresh_fx.py with your FRED key |
| FX | fx not available for (financial)/(trading) |
| FX | fx for (code) (as_of date) is N days old, older than its max_age_days M |
| parameters | risk-free curve not fetched for (country): run python/refresh_rates.py with your FRED key |
| parameters | no risk-free curve for country (country) |
| parameters | *(no reason: a domicile declared in `rate_sources.json`'s `no_curve_fallback`, whose statements and price are in one currency, takes that currency's curve and keeps its own country risk premium; the risk-free parameter's source says "trading currency; domicile curve unavailable")* |
| parameters | no (equity_risk_premium, statutory_tax_rate or terminal_growth_rate) for country (country) |
| parameters | risk-free curve for (key) has no (tenor) tenor |
| parameters | (parameter) for (key) (as_of date) is N days old, older than its max_age_days M |
| parameters | (parameter) for (key) has as_of (date), later than the valuation date (today) |
| EBIT policy | operating income not filed; derived EBIT misses the cross-check ((recipe): derived (x) against the vendor's (y), (d)% beyond the 2% threshold, or: no vendor operating income to check against) |
| mid-cycle window | mid-cycle normalisation needs at least 8 annual return observations, have (k); the provider carries (n) periods |
| mid-cycle window | mid-cycle reinvestment needs at least 8 periods with capex, d&a, delta_nwc and nopat, have (k) |
| mid-cycle guards | through the cycle the business did not earn a positive return on its capital ((mean roic r over k observations) or (the sum of nopat over n periods, s, is not positive)) |
| mid-cycle guards | through the cycle the business reinvested more than it earned (reinvestment rate r) |
| DCF period | no fiscal periods in statements |
| DCF period | missing market data: (fields); missing statement fields for fiscal period ending (date): (fields) |
| DCF guards | price (p) and market cap (m) must be positive |
| DCF guards | projection horizon (N) years is negative |
| DCF guards | wacc (w) does not exceed terminal growth (g) |
| DCF guards | non-positive free cash flow (v): the DCF is not applicable; declared (class) |
| DCF growth | growth not derivable: (why) |
| DCF value | fair value is not finite (enterprise value (ev), shares (n)) |
| residual income guards | book equity (b) is not positive |
| residual income guards | roe not derivable: need 2 fiscal periods with net income and positive book equity, have (n) |
| residual income guards | payout not derivable: need 2 fiscal periods with positive net income and dividends paid, have (n) |
| residual income value | fair value is not finite (equity value (e), shares (n)) |
| insurer | insurer model requires filed-statement data; (why: no SEC filings for (ticker), or the period carries no AOCI or premiums earned) |
| BDC guards | missing statement fields for fiscal period ending (end): net_asset_value_per_share, net_investment_income, distributions_per_share, weighted_shares |
| BDC guards | net asset value per share (v) is not positive |
| BDC guards | distributions per share (d) is not positive; there is no coverage to read, and the distribution is the point of the lens |
| BDC guards | net asset value growth needs two periods carrying a filed net asset value per share, have (n) |
| REIT guards | the filer's leases are financing receivables; NAREIT FFO does not apply |
| REIT guards | ffo (f) is not positive |
| REIT guards | ffo growth needs two periods with ffo and weighted-average shares, have (n) |
| REIT guards | cost of equity (ke) does not exceed terminal growth (g) |
| conclude | non-positive fair value (v): model not applicable |
| conclude | margin of safety (m) exceeds sanity bound 5.00: likely structural break; check entity_class |

The stretch block is never a `Failed` either: on every record whose price history holds
250 closes on or before the date it carries the six measures with their own-history
percentiles and the two counts (`stretch_low`, `stretch_high`) against
`reference/stretch.json`; a shorter history carries `stretch_reason` instead. The summary
counts the names at or above 3 on each side and prints a line for each with its measures
and the anchor beside it; whose thesis it corroborates is the reader's, the tool holds
none.

The market-implied block is never a `Failed`: on an `Ok` record run with `--options` it is
either present or null with one of `no options data`, `no options snapshot within (N)
days before (D)`, `no expiry >= 365 days with >= 8 quoted strikes on each side`, or
`smile fit failed: (why)`.

## Reading the chart against a run

`output/summary.txt` lists each ticker's `failed_reason`; find the same string in the
table to see which stage produced it. Every `Failed` record still carries `floor` and
`scope_limits`, so the floor applies to every terminal, not only the drawn one.

The universe file declares and does not remember: a run's outcomes live in its records,
and the acceptance of any change is the run diff against the previous run
(`--baseline`), with every moved input classified against the previous snapshot
(`--baseline-snapshot`).

## The build-out readout

A record that refused because it is investing more than it earns says nothing else today.
The build-out readout (60) says the one thing that can be said, and **it is not a model**:
the record stays `Failed` with its own reason, gains no fair value, no margin of safety and
no signal, and nothing downstream — frontier, hedges, panel — reads it. **It adds no
`Failed` string and can never fail a record.**

It appears on a record declared `Cyclical` or `OperatingCompany` that failed the mid-cycle
observation guard or the non-positive-free-cash-flow guard, whose latest capex exceeds its
depreciation and whose latest operating income is positive; any other record carries neither
`build_out` nor `build_out_reason`. A record the readout is about but cannot draw carries
`build_out_reason` instead: the latest capex does not exceed depreciation, the latest
operating income is not positive, a field is missing, or the two declarations are absent.

**Two declarations per name, in the universe entry**, each a value, the evidence for it and
a date, both or neither: `build_out_return`, the after-tax return the new capital earns once
earning, and `build_out_lag_years`, whole years from spend to first earning. The name's own
recent return on capital is the natural citation in the `why` and is **never** the input.
**A declaration is in the units its holder reasons in** (63): the return is declared *after*
depreciation, as every filing states one, and the readout converts it to the cash yield it
needs by adding the same depreciation-to-capital ratio it then charges as maintenance. Both
figures and the ratio go on the record, the return axis and the contour are in accounting
terms, and a tranche's free cash flow is exactly the declared return on its cost.

**The split is the depreciation rule, stated.** Growth capex in a year is capex less
depreciation where positive; maintenance is depreciation, because no filer discloses the
split. The surface runs the return from fifteen points under the declaration to fifteen over
in one-point steps, and the lag from zero to six years. At each point the value is the
standing business — the latest free cash flow with maintenance capex in place of the capex
actually spent, held flat, as a perpetuity at the settled terminal growth — plus the last
three years' growth capex as tranches, each earning the converted cash return on its cost
from the lag after its spend, less its own maintenance at the company's
depreciation-to-capital ratio, as a flat perpetuity; less net debt, per effective share. The WACC, the tax rate and the
terminal growth are the ones the DCF resolves for the name, from the same functions.

The readout is the **price contour**: per lag, the return at which the value equals the
price. Where no return in the declared range reaches the price, or the price is below the
whole range, the contour is null and says which, with the figure at that end — and that is
itself the readout, not a gap.

Its scope limits go on every block: the maintenance split is a proxy; the standing business
is held flat, which understates a growing name and overstates a fading one; every dollar of
growth capex is valued as if it becomes earning capital, which no build-out achieves. It is
a map of what the price requires, not a value.

## Fetched data

Nothing obtained from a data provider is tracked. `reference/` holds declarations and
attributed vintage tables; the risk-free curves and FX rates are written by the refreshers
to `data/reference/`, gitignored at that path and at their old paths under `reference/`,
and read by the batch from `--fetched DIR` (default `data/reference`).

Point-in-time writes its own per-date copies under `data/pit/(D)/reference/` and the panel
passes that directory as both `--reference` and `--fetched`. A record that needs a curve
or a rate the user has not fetched fails naming the refresher to run.

## Market-implied

The options store and the readout beside the declared belief. The terminal is
self-contained: `tools/thetaterminal/` (gitignored entirely) holds the jar the user
downloads, its config and logs; `python/theta_terminal.py start|stop|status` reads
`THETADATA_EMAIL` and `THETADATA_PASSWORD` from the environment (direnv loads `.env`),
writes a creds file there with mode 600, launches the jar with `--creds-file`, and removes
the file once the port answers; it never prints a credential.

`python/fetch_options.py <ticker>... [--as-of D]` writes the full end-of-day chain for the
date, every expiry and strike unfiltered, with the underlying's close from the stock
endpoint, to `data/options/<date>/<TICKER>.json`. The batch reads the store only under
`--options DIR` and never requires it: without the flag a record carries neither
`market_implied` nor `market_implied_reason`.

Every number in the block is risk-neutral: it embeds the market's risk pricing and is not
a forecast, and the spot it is read from is the snapshot date's close, which may differ
from the record's price. The growth axis is approximate: a horizon of one to two years
stands in for the long run. The detail is in `docs/market-implied.md`.

## Hedging

Single-name hedging runs beside the batch and touches no record: `python/hedge.py` takes
an untracked holdings file (ticker, shares, horizon, exactly one constraint), reads the
name's chain from the store (the latest snapshot at or before `as_of`, the same rule as
everywhere), the per-expiry smiles from `atemoya-smile` (the constrained fit, expiry by
expiry) and the name's fair value and risk-free rate from the latest run.

Four structures are priced from quotes, ask for what is bought and bid for what is sold; a
missing leg or a leg more than five vol points off the smile excludes the candidate;
cost, floor and cap per candidate, distribution-free; the exact Pareto set; the declared
constraint selects and nothing is recommended without one. Capping the upside is a
declaration: a collar or covered call is selectable only when the entry declares
`min_cap_pct` and the cap is at or above it, else only puts and put spreads, the output
saying which. One risk-neutral floor probability comes from the smile's density; the
scope limits sit on every output. No model price, no sampling.

A book: `python/hedge_book.py` reuses all of it on one index's chain, each holding
declaring its beta with a why and a date (`python/beta.py` reports a regression beside it
that the hedge never reads), exposure = shares x spot x beta summed, whole contracts with
the residual reported, the book's floor and cap from the index payoff on the declared
betas, the book floored at zero; an index absent from the store is refused with the fetch
command named.

Currency exposure: `python/hedge_fx.py` sells the declared exposure forward with CME FX
futures from the dated table `reference/fx_futures.json` (strict loader), the forward by
covered interest parity on the fetched curves, the spot the ECB's daily reference rate as a
dollar cross of two ECB rates from `data/reference/fx_spot_daily.json`
(`refresh_fx.py --daily`, the valuation path never reading it; a missing file names the
refresher), the vendor's front quote as a flag, whole standard and micro contracts with
the residual, the margin, and a deterministic payoff grid; a currency not in the table is
refused by name and a missing curve names the refresher.

A declared view: `python/express.py` prices every vertical on the view's side from
quotes, applies the holder's probability only where the max-profit region is exactly the
declared one, the short strike at the quoted strike nearest the level (every other
candidate null with the reason and listed, not ranked; the ranking answers only how wide
and debit or credit), puts the risk-neutral probability of the payoff regions beside it,
ranks by expected value per dollar at risk with the disagreement shown, and states the
implied-against-realised volatility diagnostic; a view without a probability or a why, or
a name without a chain, is refused.

The fill model: `python/fetch_tape.py` stores the trade tape with the quote at each print
(a subscription-tier refusal reported as the vendor words it), `python/fill_model.py`
builds empirical quantiles of the fill position per name, moneyness third, spread width
and half-hour, nothing fitted and symmetric by construction, `--fill-model` prices each
leg of a vertical at its cell's median fill instead of the flat slippage, never both, and
`python/fills_vs_model.py` reads a holder's own fills against the table. The detail is in
`docs/hedging.md`.

## Frontier

`python/frontier.py <candidates.json>` is Smith and Smith's endgame: for an untracked
candidate set, the distribution of the portfolio's value surplus (the margin of safety)
under the declared beliefs, and the long-only weightings that minimise downside risk at
each level of expected surplus. It needs a batch run whose records carry a belief and its
41-point surplus curve, the correlation section of `reference/beliefs.json` (one declared
common-factor number, per-pair overrides optional, never estimated), and the draws and
seed in `reference/params.json`.

Each name's marginal is its truncated normal; the joint is a Gaussian copula. Risk is
downside-only: the probability of a negative surplus, LPM1 at zero and CVaR at 95%; the
standard deviation is reported beside them and never optimised. The frontier minimises
CVaR95 at each target mean by the Rockafellar and Uryasev linear programme; the
minimum-p_negative, minimum-CVaR and minimum-std portfolios are reported side by side,
with the current weights when given.

Names that are Failed, absent or without a belief are listed with the reason and
excluded; the universe is never the candidate set. Output goes to
`output/frontier/<candidates-file-name>/` as a JSON, a text summary and a two-panel
plot, expected surplus against p_negative and against CVaR95. When every candidate's
p_negative is one, the summary says the frontier is not informative at these prices and
the output is still written.

## Required return

CAPM is the default cost of equity and is never silently replaced. A declared required
return is a premium in percentage points over the country's risk-free rate, resolved per
name (a `names` entry, else the class default, else CAPM) from
`reference/required_returns.json`, both sections empty until the user declares one, or a
further `--required-returns` file. The rules of use:

1. **A required return is yours.** It is declared, dated, and carries a why: a premium in
   percentage points over the country's risk-free rate at the model's tenor. The tool
   never derives it from a beta, a prior or history. The loader accepts exactly three
   fields (`premium_over_rf`, `why`, `as_of`) and refuses anything else.
2. **Revise it by a dated declaration when evidence warrants**, never because of what a
   number looks like.
3. **The parameter is the premium over the risk-free rate**, so a declaration serves every
   currency: on the cross-currency path it replaces beta times ERP and the country
   premium, and the risk-free rate stays the trading currency's.
4. **A declaration moves the anchor**, not the signal thresholds; the readouts, the
   sensitivity step, the belief map and the probability all run on the rate used.
5. **Every record stamps `required_return_version`** when a declaration applies, and the
   run diff names every record whose version changed.
6. **Class defaults and per-name entries are tracked** in `reference/required_returns.json`;
   both sections ship empty. A further file given as `--required-returns` overrides the
   tracked entries.
7. **CAPM is the default and is never silently replaced.** Every Ok record carries
   `cost_of_equity_capm`, `cost_of_equity_used` and `required_return_source`, so the gap
   between the two rates is visible on every record a declaration touches.

## Definition rules

The rules of `reference/field_definitions.json` that decide whether a filed field exists
at all:

1. **Working capital has three kinds and a refusal.** A cash-flow `IncreaseDecreaseIn*`
   component is an asset (positive when the balance grew, an outflow, added), a liability
   (positive when the balance grew, an inflow, subtracted), or a net balance of assets
   less liabilities (added like an asset); an excluded tag sits in the operating section
   but is not working capital and is never summed. A tag in none of the four leaves the
   field null with a note naming it, never a partial number. Every tag was checked
   against its us-gaap definition and the vendor's working-capital line on a real year
   before it entered the table.
2. **Debt is zero only when the filing says so twice.** No debt tag for the period and no
   interest expense or interest paid for the period gives total debt 0, recorded as "no
   debt line filed and no interest expense filed; taken as 0". Either present without the
   other leaves the field null: a filer paying interest owes something.
3. **The mid-cycle model's NOPAT is bottom-up.** Net income plus interest expense times
   one minus the statutory rate, per period from filed lines, so no operating-income line
   is needed and the EBIT policy does not apply on that path; the through-cycle mean is
   what dampens one-offs.
4. **The latest-period gate is the model's.** `required_on_latest_period` in the
   definitions names, per model, what the latest fiscal period must carry: everything the
   DCF reads (FCFF is that year), the balance sheet only for the mid-cycle model (its
   reinvestment rate is a ratio of sums and its NOPAT applies a through-cycle return to
   today's capital). Inside the mid-cycle window a period lacking a flow is excluded from
   the sum it cannot serve, named on the record, and the guards count what remains: at
   least 8 return observations and at least 8 periods in the reinvestment sums.
   **A year the company was too small to compare leaves the return average too.** The
   through-cycle return is `NOPAT_t / IC_{t-1}`; when the business was a fraction of its
   present size that ratio describes a different firm, and the window is there to hold two
   commodity cycles, not two corporate lifetimes. A period whose opening invested capital
   is below `midcycle_scale_floor` (declared and dated in `params.json`, a tenth of the
   latest period's capital) is dropped from the average and listed on the record as
   `{period_end, sum: "roic", missing: "opening capital below the scale floor"}`, exactly
   as any other exclusion; the eight-observation guard then counts what remains, so a name
   with too little comparable history fails with the count instead of valuing on the wrong
   ratio. The reinvestment sums are untouched, because a ratio of sums over the window is
   not distorted the way a mean of ratios is: those years' flows barely enter either sum.
   Changing the floor is a dated declaration, never a tuning.
5. **D&A is the largest filed total**, inside the FFO recipe too. **Under IFRS it
   excludes impairment**: the pure tag first; where absent, the inclusive tag less the
   impairment filed (the total, else its components) plus the reversal filed, recorded as
   `inclusive_less_impairment` with every tag; an impairment the filing does not tag is
   never subtracted; the plain adjustment tag as a total when neither is filed; and when
   no total of any kind is filed, `DepreciationExpense` plus `AmortisationExpense`, both
   required, as `sum_of_components_ifrs`, the right-of-use depreciation not added because
   on TSMC the two-tag sum matched the vendor's row within the threshold. When several
   D&A total tags are filed in one period the field is the largest, since a total is
   never smaller than any of its components; every candidate is recorded with the tag
   taken. The components fallback applies only when no total is filed.

   **Below the totals the chain reads the filer's own cash-flow reconciliation, not its
   notes** (62). Brief 61's own-year rule made the difference visible: where a filer files
   no total, `Depreciation` and `AmortizationOfIntangibleAssets` are often the property and
   intangible note figures, while the reconciliation's own lines are `OtherDepreciation-
   AndAmortization` and `AdjustmentForAmortization`. So the combined line is read first,
   with the amortisation line added when it is filed separately, as `cash_flow_lines`;
   the note pair is below it, and the amortisation line is preferred inside the pair too.
   **The note pair needs both parts.** Depreciation alone is a filer's whole D&A only when
   it has no intangibles to amortise, so the pair stands when both are filed and otherwise
   only when the filing carries no finite-lived intangibles balance at all; a filer with
   intangibles that tags no amortisation anywhere has a line it did not tag, and the period
   carries no D&A rather than a depreciation figure standing in for a total.
6. **Debt components are summed when no aggregate or complete pair is filed.** A filer
   with fewer instruments is not missing data: one component per kind, recorded;
   absent-is-zero applies only when no component and no interest tag is present.
   **Interest evidence has a sign and a size** (65). A trace of interest is not the filing
   saying a second time that the filer owes something. Interest counts as evidence only
   when it is an expense — a figure that is income never does, whatever its size — and when
   it exceeds `interest_evidence_floor` of operating income, a declared parameter at half a
   per cent. The floor needs a scale, so it is applied only where operating income is filed
   and positive; with no operating income line, or a loss, the evidence stands and the
   field stays null. Both conditions are written into the debt source on the record when
   the rule fires. Only a filer that tags no debt line at all ever reaches this test.
7. **AOCI by components.** When the aggregate is absent the filed components are summed,
   recorded as `sum_of_components` with each component.

   **A filer that has never distributed anything retains everything** (65). An absent
   dividend tag cannot tell "none" from "not filed", so it alone still refuses. The
   cash-flow statement's financing subtotal settles it: a period whose filing carries that
   subtotal and no dividend or distribution element of any kind — the wider
   `dividend_evidence` list, preferred and minority included, not the common-stock payments
   the models read — has said it paid none, and the period carries `no_distributions_filed`.
   On the residual-income path, two such periods with positive net income give retention 1
   with the source on the record; either condition missing leaves the existing refusal.
8. **FFO does not apply to a financing lease.** A triple-net REIT may account for its
   properties as sales-type or direct-financing leases: they are then net investments in
   leases, they earn interest rather than rent, and there is no real-estate depreciation
   to add back, so NAREIT FFO is not the measure and net income under its name would be a
   receivable dressed as property. When the period files no depreciation total and the
   filer carries both the net-investment-in-lease balance and the interest earned on it,
   `ffo` is null with the reason "the filer's leases are financing receivables; NAREIT FFO
   does not apply", and the REIT model fails with that string instead of naming a tag it
   could not find. The balance alone is not evidence: an insurer may hold direct-financing
   leases inside an investment portfolio and never ask for FFO.
9. **A sub-line stands as a total only where nothing else is filed.** `OtherDepreciation-
   AndAmortization` is defined as D&A classified as other, so it is never a candidate
   under the largest-total rule and cannot displace a filed total; below the totals it is
   the filer's own combined line and is read there (62, rule 5 above). Capitalised
   internal-use software is read as capex on the same footing, last in the tag order, so a
   filer tagging purchases of property, plant and equipment is untouched. **An aggregate
   that already carries what a component would add is read whole**: a filer presenting one
   balance-sheet line for cash, equivalents and short-term investments tags
   `CashCashEquivalentsAndShortTermInvestments`, which is searched after the two
   cash-equivalents elements so no period that resolves moves, and the short-term
   investments component is not added again.
10. **Interest stand-ins on the mid-cycle path only.** When no interest-expense line is
   filed, a net non-operating interest figure negated, else cash interest paid, stands
   in, recorded as `net_nonoperating_interest` or `interest_paid_stands_in` on the period
   and on every observation; the DCF path's EBIT policy never reads a stand-in.

### A period's statement comes from one filing

A filer's companyfacts carry every filing that ever reported a fiscal year, and the same
period appears in the year's own 10-K and again as a comparative column in the next two or
three. Those columns are **regrouped to the later year's presentation**: a line the filer
once tagged on its own may be folded into another. Taking the newest fact per tag, tag by
tag, therefore mixes two presentations inside one period and counts a folded line twice —
Apple's FY2021 other-liabilities line reads 5,799m in its own 10-K and 7,475m in the FY2023
one, the difference being exactly the contract-liability line the FY2023 filing absorbed and
the FY2022 filing still tagged separately.

So **a period's values all come from one accession**: the filing whose own fiscal year the
period is, identified as the filing whose newest annual duration fact ends at that period.
A period no filing reports as its own year falls back to the latest filing that carries it.

A later filing that disagrees about a tag the record reads is recorded on the period as
`restated_from` — the tag, the value taken, the value not taken, and which filing it came
from — and **never used**. A restatement is a finding; which of two numbers to believe is a
judgement this tool leaves to its reader.

Where a filer tags both its own working-capital aggregate and the components that make it
up, the two must agree, and the period carries `working_capital_reconciled` with the gap.
Both numbers are the filer's own, out of the same filing, so the check needs nothing about
the statement's structure — and it is exactly the identity a period assembled from two
filings breaks. The fetch run tallies how many of those periods reconcile and names the
filers that do not. It gates nothing.

### A lens that discounts nothing

Most classes here end in a model that projects something and discounts it. The BDC lens
does not. A business development company marks a portfolio of private loans and equity
stakes to fair value every quarter and states a net asset value per share; **that mark is
the fair value**, because the alternative is for the tool to re-underwrite loans it cannot
see. So there is no discount rate, no growth rate and no country parameter on that record
at all — the parameters gate the pipeline, they are not inputs to the lens.

What the record carries instead are four ratios of filed lines, which is what makes the
mark useful: the premium or discount the market puts on it (`price_to_nav`, and the signal
follows the margin of safety as everywhere, so a premium reads Sell and a discount Buy),
what the portfolio earns against it (`nii_yield_on_nav`), what the holder is paid
(`distribution_yield`), and whether the payment is covered (`nii_coverage`, net investment
income per share over distributions per share; below one the distribution comes out of
capital and erodes the mark, which `coverage_note` says and `nav_cagr` shows over the filed
periods).

Because there is no parameter, there is nothing to invert and nothing to step: the implied
readouts, the sensitivity block, the belief and the surplus curve are all absent with the
same reason, and the name never enters the frontier.

### The belief's parameter, per path

Every belief is a declaration about the one thing the long run turns on, and which thing
that is depends on the model. On the DCF, mid-cycle and REIT paths it is long-run growth,
offset around the country's terminal growth. On the residual-income path there is no
terminal growth — by design, since a bank whose return on equity equals its cost of equity
is worth exactly book — so the belief sits on **the long-run return on equity the ROE path
reverts to**, offset around the name's cost of equity.

That reversion target is a parameter of the model, defaulting to the cost of equity, which
is why every bank and insurer number is unchanged by its arrival. The fourth readout is
`implied_roe_target`: the long-run return on equity at which fair value equals price,
everything else held, bisected over ten points under the cost of equity to thirty over it.
Fair value rises with it, because the excess return the path settles at is the target less
the cost of equity and the explicit sum carries it with nothing after. `probability_overpaid`
is the belief's CDF there, and the surplus curve sweeps the same parameter, so those names
enter the frontier like any other.

### Where terminal growth comes from

The anchor every growth path reverts to is the country's long-run nominal growth in its
own currency, because that is the currency the terminal cash flow is in. The table is
`params.json`'s `terminal_growth_rate`, transcribed from the IMF World Economic Outlook —
the nominal GDP series in national currency, percent change at the last year of the
projection horizon, deliberately not the current year, which carries the cycle. The
vintage and its release date are on the table, `max_age_days` fails it when no newer
vintage is transcribed, and **there is no default row**: a country the table does not
carry fails the record naming the field. A cross-currency name takes the row of the
trading currency's country, not its domicile's.

## Beliefs

The belief parameter is terminal growth, fixed on the merits. This choice may be revisited
only on an argument about the model, never on what it does to a number. The rules of use,
in this order:

1. **A belief is yours.** It is declared, dated, and carries a why. The tool never
   estimates it from history; history, GDP and base rates are evidence you cite in the
   why. The loader accepts exactly six fields (`mean`, `sd`, `floor`, `ceiling`, `why`,
   `as_of`) and refuses anything else.
2. **Revise it by a dated declaration when evidence warrants.** A structural event, such
   as a supply shock that changes a company's long-run demand, a lost moat, or a
   regulatory change, is exactly the moment. Never revise it because of what a number
   looks like.
3. **The belief parameter is terminal growth, fixed on the merits.** Starting growth is
   observed from filings; the reversion speed is a structural assumption with its
   sensitivity shown; long-run growth is the question every investor can answer. This
   choice may be revisited only on an argument about the model, never on what it does to
   a number.
4. **`probability_overpaid` is a statement of your belief, not a frequency.** It is the
   probability, under your truncated normal on long-run growth, that the value surplus
   (the margin of safety) is negative: that long-run growth falls short of what the price
   needs. Its calibration can only be checked years later; its revision can happen today.
5. **Every record stamps `belief_version`.** Two runs with different beliefs are
   different runs, and the run diff says so on every record whose version changed. A run
   without a belief for a name records no version and no probability, with the reason.
6. **Every belief is tracked.** `reference/beliefs.json` holds one default per entity
   class as offsets around the country's settled terminal growth and, beside them under
   `names`, per-name absolute beliefs that override the default. A further file of
   per-name beliefs may be given as `--beliefs`; it overrides the tracked ones. Banks and
   insurers carry no belief: their model has no terminal growth.

## Insiders

Form 4, on every CIK-resolved record (66). **It never fails a record and adds no `Failed`
string**: a name without a CIK, or with no Form 4 in the year, carries `insiders_reason`
instead of a block, and nothing downstream reads either.

Open-market purchases (`P`) and sales (`S`) from the non-derivative table only; awards,
exercises, withholdings and gifts are counted by their code and never summed. Over ninety and
three hundred and sixty-five days: distinct buyers and sellers, dollars each way, the net, the
largest purchase with its owner and relationship as filed, and whether a chief executive or
financial officer bought. `cluster_buy` is two **distinct** insiders buying inside a fourteen-day
window in the trailing ninety days.

Everything is cut on the **filing** date, which the index carries and the document does not, so
the point-in-time panel reads only what was public on its date. The summary prints the ninety-day
counts beside every stretched name and then lists those **stretched with insiders on the other
side**. No score, no weight and no signal: the block counts and lists, and the reader decides.

## Changelog

- entity class (05): declaration, class check, admissibility, floor.
- bank model (06): the residual-income model for `Bank`, its guards and its inputs; the
  admissibility branch now routes to the first admissible model in the row.
- risk-free fetchers (07): risk-free curves come from a source registry in three tiers; a tenor
  substitution is recorded on the parameter, never silent. No new `Failed` string.
- insurer model (08): a second statements provider (filed statements via SEC XBRL) for insurers,
  the insurer model on AOCI-adjusted book, and the `Failed` string for an insurer whose
  provider had no filed statements.
- cross-currency (09): the currency gate, the cross-currency conversion and international CAPM, the
  minor-unit price guard at the fetch, and the `Failed` strings for a missing currency
  field, a missing FX pair and a stale FX leg.
- filed statements (10): filed statements as the primary provider for us-gaap annual filers, the
  provider decision on every record, the vendor cross-check, and the filing-age `Failed`.
- field definitions (11): one definition per field on both providers (`reference/field_definitions.json`),
  the composition on every period and in the DCF inputs, the ebit recipe, and the
  field-definitions gate with its `Failed` string.
- implied readouts and bounded EBIT (12): the implied readouts on every `Ok` record (headline untouched), the one EBIT
  refinement with its refinement policy as data, and the policy's `Failed` string.
- IFRS filers (13): the ifrs-full taxonomy and the 20-F as an annual form, the statement currency
  from the facts' unit, and the currency-agreement `Failed` string.
- companyfacts lag and implied horizon (14): the companyfacts-lag routing decision from SEC's submissions index (a new
  `provider_reason`, no new `Failed` string) and the implied horizon. 
- residual income without a terminal (15): the residual-income model loses its terminal spread; the cost-of-equity-versus-
  terminal-growth `Failed` string leaves with it.
- stability pass (16): dated snapshots, the stability classification of every moved input between two
  snapshots, and the two commands for snapshot three. No new `Failed` string.
- point-in-time (17): point-in-time records and the panel; three `Failed` strings for a date without
  filed statements, cover-page shares or rate history; held vintages declared on the record.
- REIT lens (18): the REIT model on the FFO-covered dividend, FFO per NAREIT from filed tags; the
  `Failed` strings for a non-positive FFO, too few periods for FFO growth, and the cost of
  equity against terminal growth on this path.
- share counts and point-in-time recoveries (19): two share definitions (a period's weighted-average diluted count for any flow
  per share, a point count for market cap), the point-in-time balance-sheet fallback and
  the same-period vendor check. No new `Failed` string; two reworded.
- universe declares only (20): the universe entry is exactly ticker, entity_class, why and
  scope_limits, loaded strictly; the expectation check and the note echo leave the batch;
  the record loses its per-name lens text. No new `Failed` string.
- model version, dated runs, the software class, a private universe (21): `model_version`
  on every record, summary and run diff; every `--out` run also under `output/runs/`;
  `HighGrowthSoftware` admits the DCF; `--universe` and `--snapshots` for a second,
  untracked universe file. No new `Failed` string.
- the cyclical class and the mid-cycle DCF (22): `Cyclical` and `dcf_midcycle` on
  through-cycle return on invested capital; period depth per model (the mid-cycle window
  parameter for the class, five otherwise); a declared `cik` on a universe entry;
  `PreProfit` renamed `Unprofitable`; the class's default scope limits on every record.
  Three new `Failed` strings (observations, return, reinvestment); the refusal string for
  the renamed class changes its class name.
- sensitivity and the belief map (23): the deterministic sensitivity block with declared
  readability steps on every Ok record; the belief map's price contour on the
  growth-then-terminal paths, its grid to `output/maps/`, and `plot_map.py` on
  matplotlib. No new `Failed` string; no headline moves.
- declared belief and probability_overpaid (24): a six-field truncated normal on long-run
  growth per class (tracked, offsets) or per name (`--beliefs`), loaded strictly;
  `implied_terminal_growth`, `probability_overpaid` in closed form and `belief_version` on
  every Ok growth-then-terminal record; the six rules of use above. No new `Failed`
  string; no headline moves.
- definitions coverage (25): the three-kind working-capital table with a net kind, the
  debt absent-is-zero rule and the aggregate-plus-convertible recipe, capex tags widened,
  bottom-up NOPAT on the mid-cycle path (no EBIT policy there), the declared CIK honoured
  point-in-time. No new `Failed` string; the mid-cycle missing-fields list names
  net_income and interest_expense instead of ebit.
- one universe (26): the seven names that lived only in a second, untracked list join
  `reference/universe.json`; that list, its snapshot root and its output root are gone;
  per-name beliefs live under `names` in `reference/beliefs.json`; `--universe` and
  `--beliefs` stay as generic options. No new `Failed` string; no number moves.
- mid-cycle window and D&A total (27): the latest-period gate per model in the
  definitions, exclusions named inside the mid-cycle window with a guard on the
  reinvestment sums, spot fcff a nullable readout; D&A the largest filed total with
  candidates recorded. One new `Failed` string (the reinvestment guard).
- no fetched data in the repo (29): the risk-free curves and FX rates move from
  `reference/` to gitignored `data/reference/`, written by the refreshers and read with
  `--fetched`; the registry seeds the curve file; two new `Failed` strings name the
  refresher to run when a file was never fetched.
- gaps from the first growth batch (31): thirteen working-capital tags verified into the
  three kinds and the excluded list, the component-sum debt recipe, AOCI by components,
  the FFO depreciation list with the largest-total rule, interest stand-ins for the
  mid-cycle NOPAT, Shell's IFRS capex line; one new `Failed` string, the non-positive
  free-cash-flow guard on the dcf path.
- IFRS depreciation, disinvestment, captive finance, ORCL (32): the IFRS D&A recipe
  excludes impairment by filed totals or components; a negative through-cycle reinvestment
  rate fails the mid-cycle model (one new `Failed` string); Caterpillar and Ford declare
  the captive-finance scope limit and the Cyclical class text names it; Oracle is declared
  Cyclical.
- the reinvestment floor (33): the mid-cycle reinvestment rate is floored at zero with the
  measured rate recorded beside it and a flag; the disinvestment guard and its `Failed`
  string are gone.
- declared required return (34): `reference/required_returns.json` with empty class and
  name sections and strict loaders; a declaration replaces CAPM above the risk-free rate on
  every model; both rates and the source on every Ok record; readouts, sensitivity, map
  and probability on the rate used. No new `Failed` string; no number moves.
- the value-surplus frontier (35): the surplus curve on every record with a belief, the
  declared correlation section (a draft at 0.20), the frontier parameters, and
  `python/frontier.py` with its measures and plot. No new `Failed` string; no number moves.
- terminal growth gets a source (57): `params.json`'s `terminal_growth_rate` stops being
  a set of undocumented judgements and becomes a transcription of the IMF World Economic
  Outlook's nominal GDP growth in national currency at the last projected year, with the
  vintage and release date on the table; the `default` row goes, because a table with a
  source has no default, and British Virgin Islands goes with it, having no series in a
  database it is not a member of. Every row rises, because the old values sat at roughly
  half of nominal growth, so **every DCF, mid-cycle and REIT record moves and the belief
  distributions shift up with their anchor** — by design, and no belief was adjusted to
  offset it. Residual-income records are untouched: that path has carried no terminal
  growth since the terminal spread was removed. No new `Failed` string.
- declarations in the holder's units, and the bank and insurer ceilings (63): the build-out
  return is declared as an after-tax accounting return on new capital, after depreciation,
  the units a filing states and a reader compares against, and the readout converts it to the
  cash yield it charges maintenance against, both figures and the ratio on the record; the
  two drafts are confirmed at 0.22 with a two-year lag and 0.14 with four. The `Bank` belief's
  ceiling goes to eight points over the cost of equity and the `Insurer`'s to five, the centre,
  the width and the floor unchanged, on the argument that franchise banks have held five to
  eight points over for decades — not on the readout it produces. No headline moves.
- the build-out readout (60): a record that refuses because it is investing more than it
  earns gains `build_out`, the surface of value across what the new capital earns and how
  long it takes to earn it, with the price as a contour per lag. A readout, not a model: no
  fair value, no signal, no new `Failed` string, and the record stays `Failed` with its own
  reason. Two declarations per name in the universe entry, drafted for AMZN and VG and
  marked for the user to confirm; `python/plot_build_out.py` draws it. Every other record
  carries neither field and is byte-identical.
- the earnings gate for the options tools (68): every record gains an `earnings` block, Ok or
  Failed -- the next results release, where the date came from, what the last eight releases
  did, and what the option market charges for the next one. The calendar is filed and keyless,
  every 8-K carrying item 2.02 over five years from SEC's own index, with the vendor's dates
  where a filer files none; the next date is the vendor's where it carries one and a
  projection from the filed cadence otherwise, and the record always says which. The implied
  event move is the later of the two bracketing expiries' total variance less the earlier's,
  at the forward on the fitted smile, `null` with the reason where no expiry precedes the date
  or the subtraction is negative. `hedge.py`, `express.py` and the `market_implied` expiry
  carry `spans_earnings` with the implied move beside it; **no candidate is excluded and
  nothing is re-ranked** -- the flag is added where a candidate is serialised, so the Pareto
  set, the constraint and both ranking keys cannot see it. It never fails a record, adds no
  `Failed` string, and nothing in the valuation reads it.
- stretch and insiders through time (67): a study beside the batch, not in it. Every trading
  day of every name's vendor history from the third year onward is walked with the stretch
  block's own `measures_at` and `counts`; an episode starts the first day a side reaches three
  after twenty trading days below it. What followed is measured at +20, +60 and +120 trading
  days against SPY over the same dates, and what the insiders had done is brief 66's own
  window and cluster functions over the ninety days ending the day *before* the episode.
  Descriptive only: counts, medians and quartiles, a cell under ten printing its count alone,
  and no statistic the sample cannot carry. It changed the batch by nothing, adds no `Failed`
  string, and nothing downstream reads it. Two findings from building it: `filings.recent` is
  a year or a thousand filings, whichever is more, so anything that walks further must read
  the older pages `filings.files` names, and a CIK is resolved by the fetch's own resolver
  rather than read out of a record's prose.
- insiders: Form 4 as the other half of stretch (66): every CIK-resolved record gains an
  `insiders` block read from SEC's own index and archive, keyless and timestamped — open-market
  purchases and sales only, with awards, exercises, withholdings and gifts counted by code and
  never summed. Distinct buyers and sellers, dollars each way, the largest purchase, a
  chief-executive-or-financial-officer flag and a two-insider fourteen-day cluster rule, over
  ninety and three hundred and sixty-five days. Cut on the filing date, so the point-in-time
  panel carries it. The summary prints the counts beside every stretched name and lists those
  stretched with insiders on the other side; `plot_insiders.py` draws the transactions on the
  stretch chart. No score, no weight, no signal, and no new `Failed` string.
- batch three's findings as rules, and Denmark (65): four rules from the twenty names
  brief 64 added. Interest counts as evidence of debt only when it is an expense and above
  a declared floor of half a per cent of operating income, so two lease-only retailers that
  file no borrowing at all stop being refused over an undrawn facility's fees.
  `IncreaseDecreaseInLeasingReceivables` joins the working-capital exclusions, the vendor's
  line agreeing to the dollar on four years without it and missing by four fifths with it.
  A residual-income filer whose filing carries the financing subtotal and no dividend
  element of any kind retains everything, with the source on the record. And Denmark joins
  the three country tables from their own sources, with a curve probed live at Statistics
  Denmark's keyless StatBank, where Danmarks Nationalbank publishes: ten-year only, the
  seven-year substituted and recorded, no rate hand-copied. No new `Failed` string.
- the tags an own-year filing uses (62): brief 61's rule reads each period from the filer's
  own-year filing, which is internally consistent but sometimes tags less than the filings
  after it, and 136 value cells went null. Three elements answer for almost all of what
  mattered. `CashCashEquivalentsAndShortTermInvestments` is a balance-sheet line that
  already carries the investments, searched after the two cash-equivalents elements so no
  period that resolves moves; Caterpillar regains cash on seven periods and its mid-cycle
  window goes from seven observations to fourteen. Below the D&A totals the chain now reads
  the filer's own cash-flow reconciliation — `OtherDepreciationAndAmortization` with
  `AdjustmentForAmortization` beside it — before the note pair, which itself needs both
  parts or a filing with no finite-lived intangibles at all; the note figures were standing
  in for a total on filers that never tagged one. Seven records move and 126 are
  byte-identical. No new `Failed` string.
- a period's statement comes from one filing (61): the fetcher chose the newest fact per
  tag independently, so a period assembled its components from several filings whose
  presentations differ and double counted a line a later filing had folded into another;
  confirmed on Apple FY2021 and FY2022 and on Oracle. Now every tag for a period comes from
  the filing whose own fiscal year it is, a later filing's different value is recorded as
  `restated_from` and never taken, and point-in-time inherits the rule from the filings on
  or before the date, which also fixes the share count a filer's own column swap corrupted.
  Where a filer tags both the working-capital aggregate and its components the two are
  checked against each other and the gap recorded, gating nothing. No new `Failed` string.
- a BDC lens, and Valero's old years refused (59): a `Bdc` class and a `bdc_nav` model
  whose fair value is the net asset value per share the filing states, with the premium to
  it, the yield on it, the distribution yield and the coverage of the distribution beside
  it; no rate, no growth and no parameter appear on that path, so the implied readouts, the
  sensitivity block, the belief and the curve are all refused with one reason and the name
  does not enter the frontier. Four new `Failed` strings, all guards on filed lines. The
  period selection gains the net asset value per share as a second anchor beside net
  income, because two of the three filers stop tagging net income and one tags its
  realised-gain line under that element; no other filer carries the tag, so no other
  filer's period set moves. Separately, the filing's own reconciliation of net income to
  operating cash flow is admitted as a second verification for a working-capital tag on
  years the vendor does not cover — and applied to Valero it **refuses** the one tag its
  2011-2019 years leave over, because on that filer the tag is the face-line subtotal of
  the components beside it and no kind reconciles, while another filer uses the same tag as
  a real component. Valero keeps seven reinvestment periods and stays `Failed`.
- a belief for banks and insurers (58): the residual-income model's ROE reversion target
  becomes a parameter defaulting to the cost of equity, which leaves every number where it
  was and gives the path something a belief can be about; `reference/beliefs.json` gains
  Bank and Insurer as offsets over the cost of equity with a zero centre, so the long run
  grants no franchise value unless the width and the ceiling say so; `implied_roe_target`
  is the fourth readout there, `probability_overpaid` follows from the belief's CDF at it,
  and the surplus curve sweeps the same parameter so those names enter the frontier. The
  belief block names its parameter and carries the implied readout under the matching name.
  No new `Failed` string; no headline moves.
- Uruguay's rows and the mid-cycle scale rule (55): Uruguay joins the equity-risk-premium
  and statutory-tax tables from the vintages those files already cite, so MercadoLibre
  resolves its country risk premium and its tax rate and values on the dollar curve the
  no-curve declaration routes it to; the terminal-growth table gets no Uruguay row and says
  why, because it names no external source to transcribe from and MercadoLibre does not
  need one. `params.json` gains `midcycle_scale_floor`, a declared tenth: a year whose
  opening invested capital is below that fraction of the latest period's leaves the
  mid-cycle return average with an exclusion reading "opening capital below the scale
  floor", the observation guard counting what remains and the reinvestment sums untouched.
  No new `Failed` string.
- batch 2's gaps and reclassifications (54): nine working-capital component tags, the
  convertible-debt balances, interest on borrowings as debt evidence, capitalised software
  as capex and a last-resort D&A sub-line join the definitions, each classified by its
  us-gaap definition and checked against the vendor's grouping of the same tags on two
  fiscal years; a REIT whose properties are net investments in leases earning interest is
  refused with one new `Failed` string, "the filer's leases are financing receivables;
  NAREIT FFO does not apply", carried on the period by the definition and read only by the
  REIT model; `reference/rate_sources.json` gains `no_curve_fallback`, a declaration that
  a named domicile with no reachable official curve discounts at the currency its
  statements and price are both in while keeping its own country risk premium, which
  removes a `Failed` path rather than adding one; Amazon and Venture Global are
  reclassified `Cyclical` and Robinhood keeps the software lens with its interest-revenue
  scope limit declared. `InterestExpenseBorrowings` enters the debt definition's
  interest evidence only: it is a component on a deposit-taking filer, never the
  interest-expense line, so it derives no EBIT and a filer that tags nothing else
  fails on `ebit` as a filer limitation. No currently-Ok record moves.
- stretch (52): six measures from closes and volume with own-history percentiles, two
  counts against declared thresholds and the summary's lines for every name at or above
  three on either side; computed at fetch time and point-in-time, copied through by the batch. No
  `Failed` string; no pre-existing field moves.
- a fill model from the trade tape (50): the tape fetcher, the empirical quantile table,
  `--fill-model` in the expression tool and the holder's fills against it. No number moves.
- margins, the exchange minimum and the broker's override (49): a holding may declare its
  broker's initial margin, used when present with the exchange minimum reported beside it.
  No number moves.
- a daily FX spot for the FX hedge (48): the ECB's daily reference rates as the hedge's
  spot, the weekly H.10 file untouched for valuation. No number moves.
- the view applies at the level only (47): `p_view` on the spreads short at the strike
  nearest the level, debit or credit, any width; nothing else ranked. No number moves.
- expressing a view with verticals (46): `python/express.py`, the declared view, the
  quote-priced verticals, `p_view` against `p_market`, EV per dollar at risk, the vol
  diagnostic. No new `Failed` string; no number moves.
- share counts through corporate actions (44): the point-in-time count nearest the filed
  period, the cover page within 400 days, the vendor's split record applied to the count
  and to the live check's cover page. One new `Failed` string; no live number moves.
- FX hedging with futures (43): `python/hedge_fx.py`, `reference/fx_futures.json`, parity
  carry from the fetched curves, whole and micro contracts, the payoff grid. No new
  `Failed` string; no number moves.
- a book hedged with index options (41): `python/hedge_book.py` and `python/beta.py`,
  declared betas, whole contracts, the book's floor and cap on the index payoff. No new
  `Failed` string; no number moves.
- the depositary-receipt ratio (42): `adr_ratio` on the universe entry, point-in-time
  shares divided by it, and the live check flagged in the summary. No new `Failed` string;
  no live number moves.
- the IFRS component sum (40): `DepreciationExpense` plus `AmortisationExpense` when no
  total is filed, verified on TSMC against the vendor's row; TSMC recovers point-in-time
  on the dates whose filing is in facts. No new `Failed` string; no live number moves.
- capping upside is a declaration (39): `min_cap_pct` on a holding; without it only
  uncapped structures are selectable. No number moves.
- single-name hedging (38): `python/hedge.py` on the options store, four structures from
  quotes, the Pareto set, the declared constraint, the anchor as a selectable floor and
  one risk-neutral floor probability; `atemoya-smile` prints every expiry's smile on a
  chain. No new `Failed` string; no number moves.
- market-implied through time (37): `--options-max-age N` and the no-lookahead window on
  the point-in-time panel (`build_panel.py --options`, 7 days), the panel's market-implied
  columns beside `probability_overpaid` on the date, `output/pit/market_summary.txt` and
  `plot_market_through_time.py`. One new reason string; no number moves.
- market-implied distribution (36): the self-contained ThetaTerminal and its credential
  gates, the options store under `data/options/`, and under `--options` the SVI smile,
  the Breeden-Litzenberger quantiles, `p_below_anchor_path` beside `probability_overpaid`
  and the approximate growth quantiles on every Ok record with a chain, with the three
  reasons otherwise. No new `Failed` string; no number moves.

`docs/flow.svg` is rendered from `docs/flow.mmd` with `@mermaid-js/mermaid-cli` 11.17 run
through `npx` against a headless Chromium in the user's cache (nothing added to the
project's manifests), the browser launched with `--no-sandbox` because this machine
restricts user namespaces: `npx -y @mermaid-js/mermaid-cli -p puppeteer.json -c mermaid.json -i docs/flow.mmd -o docs/flow.svg -b white`
with `puppeteer.json` holding `{"args": ["--no-sandbox"]}` and `mermaid.json` holding
`{"htmlLabels": false}` (top level; the flowchart-scoped form is ignored), so the labels are SVG text rather than embedded
HTML, which image viewers and GitHub's image pipeline leave blank. The pair changes in the
same commit.
