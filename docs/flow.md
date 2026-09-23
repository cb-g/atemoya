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
6. **Debt components are summed when no aggregate or complete pair is filed.** A filer
   with fewer instruments is not missing data: one component per kind, recorded;
   absent-is-zero applies only when no component and no interest tag is present.
7. **AOCI by components.** When the aggregate is absent the filed components are summed,
   recorded as `sum_of_components` with each component.
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
   under the largest-total rule and cannot displace a filed total; it is read only when
   the filer files no total and none of the components, where it is demonstrably the whole
   line. Capitalised internal-use software is read as capex on the same footing, last in
   the tag order, so a filer tagging purchases of property, plant and equipment is
   untouched.
10. **Interest stand-ins on the mid-cycle path only.** When no interest-expense line is
   filed, a net non-operating interest figure negated, else cash interest paid, stands
   in, recorded as `net_nonoperating_interest` or `interest_paid_stands_in` on the period
   and on every observation; the DCF path's EBIT policy never reads a stand-in.

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
