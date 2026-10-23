# Running the batch

```sh
uv run python/fetch.py AAPL MSFT SAP        # statements from SEC XBRL (10-K or 20-F filers, us-gaap or ifrs-full) or yfinance -> data/financials/<TICKER>.json
dune exec atemoya -- data/financials/*.json # one valuation record per line on stdout
uv run python/refresh_rates.py --all        # sovereign curves per reference/rate_sources.json -> data/reference/risk_free_rates.json (never tracked)
uv run python/refresh_fx.py --all           # FX via FRED H.10 -> data/reference/fx_rates.json (never tracked)

uv run python/fetch_all.py                  # every ticker in reference/universe.json -> data/snapshots/<date>/, data/financials -> the latest
dune exec atemoya -- data/financials --out output   # -> output/valuations.jsonl, summary.txt, provider_diff.txt, the same three under output/runs/<date>/ (never overwritten), and output/maps/<ticker>.json per belief map
uv run python/plot_map.py AAPL                   # -> output/maps/AAPL.png: the belief map's surface, the price contour, the observed starting growth
dune exec atemoya -- data/financials --out output --baseline previous/valuations.jsonl   # plus this run against that one
dune exec atemoya -- data/snapshots/<new> --out output --baseline previous/valuations.jsonl --baseline-snapshot data/snapshots/<old>   # plus stability_<old>_<new>.txt
uv run python/fetch_all.py --as-of 2025-06-30   # point-in-time: data/pit/2025-06-30/ from what was known on that date, with its reference/
dune exec atemoya -- data/pit/2025-06-30 --reference data/pit/2025-06-30/reference --fetched data/pit/2025-06-30/reference --today 2025-06-30 --out output/pit/2025-06-30
dune exec atemoya -- --entity-class OperatingCompany --out output data/financials/NEW.json   # a name not in the universe, declared on the command line
uv run python/build_panel.py                    # every quarter-end 2022-03-31 .. 2026-06-30 -> output/pit/panel.jsonl, panel_summary.txt
uv run python/build_panel.py --no-insiders      # (80) the same without the Form 4 read, hours of paced fetching the anchor study does not need; the per-name vendor fetch is cached for the day under data/pit/names/
uv run python/anchor_study.py --as-of 2026-09-30  # (80) what the panel's judgments preceded: excess over SPY at +63/+126/+252 trading days, by signal, quintile, belief, model, class and refusal family -> output/anchor_study/
uv run python/baseline_study.py --as-of 2026-09-30  # the same rows sorted by earnings yield, book-to-price and EBIT/EV beside the margin of safety -> output/baseline_study/
uv run python/consensus.py                     # (82) today's consensus bar for every name, the release history, output/consensus/; at each sitting or daily
```

## The words

The tool's vocabulary, one line each, grouped by layer; each term is explained in full where
the pointer says.

**The record and its anchor.**
- *record* — one JSON line per name: `Ok` with a fair value or `Failed` with a reason, plus
  inputs, readouts and provenance ([The record](#the-record)).
- *anchor*, *fair value*, *margin of safety*, *signal* — the model's value per share, its
  distance from the price, and Buy/Hold/Sell at declared thresholds; "the anchor" is the
  fair value as the thing the readouts stand beside and never move.
- *class*, *lens*, *model*, *admissibility* — the kind of business a person declares for a
  name (OperatingCompany, Cyclical, Bank, …), the one way that kind is read, the model that
  does it, and the table saying which model a class admits; a class without one is refused
  with the lens named (`docs/flow.md`).
- *Failed reason* — the exact string a refusal carries; every one is a terminal node of the
  flow chart and a test holds the code to that list (`docs/flow.md`).
- *provenance* — `model_version` (the commit), the provider of every figure, the definition
  and tags behind it, the version of every declaration read.

**What goes in.**
- *statements*, *periods*, *base* — the filed annual periods a model reads; the *annual base*
  is the latest, the one the base cash flow and growth history start from.
- *trailing period* — the last four filed quarters as one period beside the annual ones, read
  by the four-quarter shadow and nothing else ([The four-quarter shadow](#the-four-quarter-shadow)).
- *snapshot* — one dated fetch of the universe under `data/snapshots/<date>/`; `data/financials`
  points at the latest.
- *reference vs data* — `reference/` holds what a person declares (universe, parameters,
  tables); `data/` and `output/` hold what was fetched or produced, never tracked
  ([Inputs and declarations](#inputs-and-declarations)).
- *declaration* — a value a person sets, dated, with a why: a class, a scope limit, a belief, a
  required return, a build-out's return and lag, a parameter table. Revised by a new dated
  declaration, never because of what a number looks like.
- *universe entry* — a name's declaration in `reference/universe.json`: ticker, class, why,
  scope limits and codes, and any per-name declarations.
- *scope limit*, *scope code* — what the model cannot see for a name, in prose and as a stable
  code a reader can act on by rule ([Scope limit codes](#scope-limit-codes)).
- *parameter*, *vintage* — a rate, premium or growth figure with its source, date and age; a
  table's vintage is the edition transcribed, and a stale one fails the record.
- *required return*, *cost of equity*, *CAPM* — the discount rate's equity side: CAPM (rate plus
  beta times premium) unless a premium is declared (`docs/required-return.md`).

**What stands beside the anchor.**
- *readout* — a block that describes the statements, the tape or the filings and never moves
  a value: quality, recency, stretch, insiders, base rate, build-out, runway, capital intensity,
  goodwill, earnings ([Readouts and diffs](#readouts-and-diffs)).
- *shadow* — the same model run once more under one changed thing, beside the headline: the
  *growth shadow* on the other growth estimate, the *four-quarter shadow* on the trailing
  period, the *declared growth* on a reader's own growth or future free cash flow
  ([The growth shadow](#the-growth-shadow), [The four-quarter shadow](#the-four-quarter-shadow),
  [The declared growth](#the-declared-growth)).
- *headline* — the record's own value and inputs, as against a shadow's.
- *limits*, *measured sentence* — every block's `scope_limits` say what it cannot see; the last
  of them says what the block was measured against on `docs/studies.md` and what came of it,
  or that no study reads it ([The record](#the-record)).
- *implied readouts* — the growth the price needs, how long it must last, and how often
  companies of that size grew that fast ([Readouts and diffs](#readouts-and-diffs)).
- *belief*, *belief map*, *probability overpaid* — a declared view on growth, the surface of
  value over growth and years, and the probability the price exceeds the value under the
  belief (`docs/beliefs.md`).
- *market-implied block*, *options store* — the risk-neutral distribution and expected return
  from the name's option chains, read as the market's risk pricing and not a forecast
  (`docs/market-implied.md`).
- *recency*, *base_limits* — how far the filed quarters have moved on from the annual base,
  and the sentence saying what that costs the fair value ([Recency](#recency)).
- *build-out*, *contour* — capital spending on capacity not yet earning, declared on the entry;
  the readout maps the return the price requires per lag ([The build-out readout](#the-build-out-readout)).

**How the tool is tested on itself.**
- *panel* — one row per name per date valued from what was known then, with what followed;
  three of them: *point-in-time* (the universe, quarter-ends since 2022), *broad* (every SEC
  filer, each June since 2010, no model), *rule* (the five hundred largest each June since 2013
  under the generic DCF) (`docs/studies.md`, The panels).
- *study* — a script reading a panel and printing descriptive tables: medians, counts, fifths
  within the date, a rank correlation where a date carries enough rows, no statistic the sample
  cannot carry (`docs/studies.md`).
- *holdout* — the names and dates no study reads until the rule is fixed, declared in
  `reference/holdout.json`.
- *point-in-time (pit)* — a fetch cut at a date: facts filed by then, the close and rates
  observed by then ([Share counts and point-in-time](#share-counts-and-point-in-time)).
- *kink* — where the terminal-growth hold meets the rate: below the table's figure a point of
  rate moves a fair value about one per cent, above it the full duration
  ([Terminal growth is held to the risk-free rate](#terminal-growth-is-held-to-the-risk-free-rate)).
- *tried* — what was built, measured and taken out again (`docs/tried.md`).

## Inputs and declarations

`dune exec atemoya` reads declared parameters from `reference/` (`--reference DIR` to
override) and the fetched curves and FX from `data/reference/` (`--fetched DIR`), and
measures their age against today's UTC date (`--today YYYY-MM-DD` to override). Inputs may
be files or directories.

Every ticker needs a declared `entity_class`, from its entry in `reference/universe.json`
or from `--entity-class CLASS` for an ad-hoc run; without one the record fails as
undeclared. `reference/admissibility.json` says which models may run on which class
(today the FCFF DCF on `OperatingCompany` and `HighGrowthSoftware`, the same engine on
through-cycle earning power for `Cyclical`, residual income on `Bank`, residual income on
AOCI-adjusted book from filed statements on `Insurer`, and the FFO-covered dividend on
`Reit`) and what each other class is judged on instead; an inadmissible class fails with
that lens named.

A universe entry may declare the SEC filer to read by `cik` when the ticker map points
elsewhere; the fetch keeps as many annual periods as the class's model needs.
`docs/flow.md` charts every stage from ticker to record. The universe file declares only:
ticker, class, why, what no model can see, and the receipt ratio; it is loaded strictly.
Whether a change moved anything is answered by the run diff against the previous run,
never by a stored expectation.

## The record

An `Unprofitable` record carries a `runway` block beside its refusal (76): cash against
the burn from the cash-flow statement's own lines, the years of runway and the releases
inside it, or a `runway_reason`. It is a state, never a value or a signal.

A record is either `Ok` with a fair value, or `Failed` with a reason; it never carries a
guessed number. Every record carries a `floor` (present, absent by definition, or not
assessable here, with its basis) that gates nothing, and `model_version` names the code
that produced it (the git short hash, `-dirty` when the tree had uncommitted edits).

The cost of equity is CAPM unless a required return is declared: the risk-free rate at the
projection tenor plus the industry's beta from `reference/industry_betas.json` times the
country's equity risk premium. Beside the rate, `cost_of_equity_limits` says what that beta
is and is not (decided 2026-10-18 on the betas study, `docs/studies.md`): an industry's
number keyed on the vendor's industry string, held flat through every projection year and
the terminal value where the names' own betas converge toward one, so a rate above the
market's charges the far years more than the names kept and one below less; and why it
stays, which is that on the tool's own panel beta was paid and no beta in the fair value
sorted returns better than one, while a name's own beta would read its risk from its price
history. A name without an industry in the table is valued at one and the field says so;
under a declared return the field is empty, a declared premium carrying no beta. Beside
both, `rate_pass_through_limits` says how the fair value moves with the risk-free rate,
which passes into the discount rate one for one on every path: which regime the hold of
terminal growth puts the record in, what a point of rate does there and how that leans
(decided 2026-10-18; below under [Terminal growth is held to the risk-free
rate](#terminal-growth-is-held-to-the-risk-free-rate)). `base_limits` says which annual
period the models read and what the quarters filed since cost the fair value, and
`four_quarter_shadow` values the generic DCF once more on the last four quarters, beside the
headline (below under [The four-quarter shadow](#the-four-quarter-shadow)).
`capital_intensity` and `goodwill` read what the capital is doing, spending against
depreciation and the return on capital with and without acquired goodwill (below under
[Capital intensity and goodwill](#capital-intensity-and-goodwill)).

**Every readout says what was measured about it (decided 2026-10-18).** A readout, the quality
block, the two shadows, the base rate, stretch, insiders, earnings, the build-out and the
runway, describes the statements, the tape or the filings and need not predict; that is the
tool's standing principle and it stays. Two studies had measured the quality block and found
the composite score sorting nothing before 2022 while the levels and the share count sorted,
and the question was whether a readout that does not sort returns stays. It stays, and the
record now says so honestly: the last of every readout block's limits is one dated sentence
(`ocaml/lib/measured.ml`) saying what the block was measured against on `docs/studies.md` and
what came of it, or that no study reads it, so a reader can tell a tested readout from an
untested one and a finding from a description. Weighed and not taken: prediction as the test
for a readout, which applied evenly would remove the anchor, since the fair value did not sort
returns among large companies either; and reshaping or pruning the quality block to the three
signals that sorted, a per-field change fitted on one panel of survivors. The upkeep is a
rule, stated at the top of `docs/studies.md`: a study that measures a readout owes its block
the sentence in the same commit, as a `Failed` string owes the flow chart, and a test holds
every sentence that names a heading to a heading that exists.

A name whose statements and price are in different currencies is converted at one
recorded FX rate (statement totals, never per-share fields) and valued in the trading
currency with that currency's country's rates plus the domicile's country risk premium;
prices quoted in pence or cents are converted to the major unit at the fetch.

The curve follows the currency of the cash flows, not the address. A name whose statements
and price are both in a currency that is not its domicile's own (Teva in dollars from
Israel, Sea in dollars from Singapore) takes that currency's curve and terminal growth and
keeps the domicile's country risk premium and tax rate, the risk-free parameter's source
saying so. `reference/fx_sources.json` declares each domicile's own currency under
`country_currencies`; a domicile it does not name fails the record naming it.

## Providers and definitions

Filed statements come in the taxonomy the filer uses (us-gaap or ifrs-full, each a
section of `reference/xbrl_tags.json`) and in the currency the facts carry, which the
record names as its statement currency and which must agree with the vendor's, else the
record fails. SEC's submissions index is read for every CIK-resolved name and its newest
10-K or 20-F recorded; when that filing is newer than the newest annual facts and those
facts are past the filing-age gate, the vendor's statements are used by a decision
written into the record's provider reason (companyfacts lags submissions), never as a
fallback from the gate.

A name with no SEC filer whose universe entry declares an `lei` (73) reads its ESEF
annual reports, the Inline XBRL every issuer on an EU, EEA or UK regulated market must
file, from filings.xbrl.org, keyless: the index is cached for a day and each report's
facts and definition linkbase for ever under `data/esef/`. The facts arrive in the
companyfacts shape and go through the same period reader under the ifrs-full definitions,
one period per report, the vendor cross-checked beside; interim reports are skipped and
named, and where a report tags an extension anchored to one standard concept the
definitions read and no standard line for it, the extension stands in and the note says
so. The LEI is read from the filer's own report cover and declared, never resolved from
the vendor. An issuer the aggregator does not carry (Allianz, on the German register)
stays on the vendor and the reason says so; and where the aggregator's newest report is
past the filing-age gate while the vendor carries a newer annual, the vendor's statements
are used by a decision written into the provider reason, as the companyfacts lag is.

A Korea Exchange line (`.KS`, `.KQ`) reads its annual reports from OpenDART (74) when
`DART_API_KEY` is set, in the environment or on its line of the env file at the repo
root: the regulator's own register maps the stock code to the filer, and each business
year's consolidated lines arrive with their ifrs-full account ids and go through the same
period reader, one period per report, the receipt day as the filing date. Lines under
DART's own account ids or under no standard code are counted and left unread. The key is
free on registration at opendart.fss.or.kr, open to individuals of any nationality under
its terms of use, personal and one per member, which is why it lives only in your own env
file; without it the name stays on the vendor and the reason says so.

Both providers assemble cash, total debt, the change in working capital and ebit per
`reference/field_definitions.json`, the one definition per field with its reasoning; every
period records the components summed, and a record fetched under another definition fails
rather than being valued under this one. A derived ebit (no operating income filed) runs
the DCF only when the cross-check finds it within threshold of the vendor's operating
income. Where it misses, a third recipe stands in if it passes the same check: revenues
less the filer's own total of costs and expenses, plus interest where the interest is inside
those costs, carried on the period as `ebit_alternative` with its composition and named on
the record as `revenues_less_costs_and_expenses` when used. It is a fallback and never a
first choice. The refinement policy in that file allows two refinements of a recipe and
names the `Failed` reason for a miss.

## The equity bridge

A DCF values the business; the share count divides the common equity. Between the two stand
net debt and every other claim the cash flow does not already settle, and every asset it does
not already earn on. `equity_bridge`, on the inputs of every generic and mid-cycle DCF record,
carries those items one by one: the value as read, the row, whether it applied and why, and
the total, so `equity_value` is the enterprise value less net debt less that total
(`ocaml/lib/equity_bridge.ml`, `reference/field_definitions.json` equity_bridge). The implied
readouts, the shadows, the sensitivity and the belief map value on the same claims.

The rule for every item is that it pairs with the cash flow. An item is applied where the cash
flow leaves it out and never where it already holds it:

- **Minority interests** are deducted where the cash flow starts from consolidated operating
  income, which carries the minority holders' share of the subsidiaries it consolidates, and
  not on the mid-cycle path built from net income attributable to the parent, which leaves it
  out already. A universe entry may declare `share_count_includes_minority`, with the filing
  cited, where the share count the price is quoted on already holds the units the minority
  interest stands for: Blackstone's 10-K counts 748,688,068 shares of common stock beside
  445,586,312 participating Blackstone Holdings partnership units at 2025-12-31, and the
  minority interest in Blackstone Holdings is those units' claim, so deducting it as well
  would divide it twice.
- **Minority buyouts since the base** are deducted beside them: what the latest 10-Q's
  year-to-date cash flow statement shows paid to buy minority interests out, less the book the
  purchases removed where filed. The minority interest is carried at its base-date book, and a
  purchase settles it at a price, which the base's net debt still holds as cash; Intel's 10-Q
  for the quarter to 2026-06-27 files 14,339 million of `PaymentsToMinorityShareholders` for
  the half-year after its base. Dividends to minority holders and contributions
  from them are not read: each moves the cash and the minority's own book alike, and since the
  bridge reads neither after the base, taking the cash alone would count a contribution's cash
  without the claim that came with it.
- **Associates and joint ventures** are added at book where the cash flow starts from operating
  income, which leaves their earnings out, and not where it is built from net income, which
  holds them already, nor where the filing shows them inside operating income: operating
  income less revenue less costs and expenses is the line between them, and where it equals
  the equity-method line the investees' earnings sit inside (BWXT's 75 million for 2025),
  where it is nil they do not (Caterpillar, CME, Kinder Morgan, McDonald's, Uber). Book is not market, and the item says so: a listed stake can be worth
  several times its carrying amount.
- **Lease liabilities** outside the debt rows are deducted on IFRS statements and on the
  vendor's statements of a filer outside the United States. There the lease cost is
  depreciation, added back with the rest, and interest, and the principal is paid in financing,
  so the cash flow never pays it. A US GAAP operating lease's cost is inside operating income,
  and its liability stays out, as `total_debt`'s why has always said. A filer's IFRS
  Borrowings may carry its leases already: where the debt less the lease liabilities is the
  vendor's debt within the threshold and the debt itself is not, the leases are inside it and
  are not deducted again (Shell's 75.643 billion of Borrowings holds its 28.933 billion of
  leases).
- **Contingent consideration** is deducted wherever filed: an acquisition's deferred price,
  paid outside the capex and working-capital lines the cash flow reads.
- **Long-term financial investments** are added at their carrying value where the cash flow
  starts from operating income, which leaves out their interest, dividends and changes in
  value, and not where it is built from net income, which holds them. They are the debt
  securities classified noncurrent, those held to maturity, and the equity securities outside
  the equity method, the largest element filed where a filer tags one line under two (Nvidia
  tags its 22,251 million of non-marketable securities under both), beside the filer's
  long-term investment line. Such a line holds the parts where it is at least their sum, and
  the associates too where it still covers the parts without them, and the associates, which
  the bridge adds on their own, are then taken out of it: Microsoft's 36,348 million of equity
  and other investments less its 12,000 million of associates, Sea's long-term investments
  less theirs. A line below the parts' sum is a line of its own beside them: ServiceNow's
  1,542 million of strategic investments beside its 3,771 million of long-term marketable
  securities. The unclassified equity-securities total is not read, since Cisco's and
  Workday's sit inside the short-term investments cash already holds. No tax on a gain not yet
  realised is deducted; Alphabet's 68,687 million of non-marketable securities carry 44,485
  million of cumulative upward adjustments.
- **The defined-benefit plans' net liability** is deducted after tax at the statutory rate, and
  a surplus added the same way, where the cash flow starts from operating income: operating
  income carries the plans' service cost, and the interest on the obligation and the return on
  the assets fall below it, while contributions are deductible. Not on the path built from net
  income, which carries that interest and return. Pension and retiree health are read as one
  line where the filer files one (Caterpillar's 3,838 million of postemployment benefits), else
  summed apart (BWXT prints 78 million of each on two lines), less the plan assets recognised
  (Northrop Grumman's 3,167 million beside 1,110 million owed); on IFRS statements the net
  defined-benefit line, else its two sides; on the vendor's statements the noncurrent
  liability row less the surplus row. The current portion sits in accrued liabilities and is
  not read, nor the vendor's current pension row, which for some filers carries other
  payables.
- **Preferred stock** is deducted at carrying value wherever filed, every cash flow here being
  before the preferred dividend: the first element filed above nil, since a par line of nil is
  not a carrying value, and redeemable preferred outside equity beside it. A redeemable
  minority interest joins the minority interest above.
- **Distributions since the base** are deducted where the valued period is the annual base the
  figures run from: buybacks and common dividends less shares issued, from the latest 10-Q's
  year-to-date cash flow statement (`distributions_since_base` on the financials). The share
  count is today's, and the base's net debt still holds the cash those payments spent; before
  this a name buying back stock was valued on its pre-buyback cash divided by its post-buyback
  share count. Buybacks after the quarter end are in the share count and not here, a quarter's
  residue at most. Shares issued since the base add their cash back, the new shares being in
  today's count; Alphabet's 10-Q for the half to 2026-06-30 files 30,499 million of common stock
  issued and no buybacks. A preferred issue since the base is not read: its cash came with a
  senior claim of the same size, and the bridge reads neither.

**Decided (2026-10-19), after a survey and a downstream project's evidence.** The record's
bridge was net debt alone. A survey of every item between enterprise and equity value across
the 104 records the generic and mid-cycle DCF valued on the run of 2026-10-19 found most items
negligible on most names and the six above material on some, and a downstream project that
runs a clone sent the filing lines for thirteen names, which agreed with the survey wherever
both measured the same thing. Weighed and not taken: the latest quarter's balance sheet with
the share count of its date, in place of the distributions line, which on an annual base also
brings in acquisitions paid since, whose cash flows the base does not hold, seasonal working
capital, and the part of the first projected year already earned; the textbook bridge applied
whole, which would have added associates whose earnings a net-income recipe already holds and
deducted a minority interest whose units the share count already divides; and diluted shares,
since stock compensation is already a cost inside operating income and the shares for awards
already granted need a rule that does not count the cost twice.

Not read, each a stated limit: the distributions of a filer whose quarterly cash flow is not in
the sources read (a 20-F filer's half-years, and every name on vendor statements, where the
vendor's quarterly rows were missing or nil where the half-year reports print the payments);
the distributions on units the share count holds by declaration; a captive finance arm's debt,
a lender's loan book and customer deposits classified in financing, which no filer tags alike
and which need a declaration per name. The four-quarter shadow reads the bridge's lines at the
quarter end where the 10-Q files them, and no distributions, its balance sheet being the
quarter's own.

**Decided (2026-10-23): the textbook items.** The first survey had called pension deficits
negligible because it read the funded-status element, which six filers tag without a plan
dimension; read from the balance-sheet lines they reach a few points of the equity value on
Delta, Caterpillar and Lockheed Martin. A second survey took every standard item between
enterprise and equity value across the same records, and the long-term financial
investments, the plans' net liability and preferred stock are read from it, preferred being
negligible on today's bases but standing on Alphabet's next: its 10-Q files 19,063 million of
convertible preferred issued in the half after its base. Not read, each a stated limit: what
an investment line under the filer's own element holds beyond the standard elements beneath it
(the rest of Intel's equity investments, the marketable part of Uber's, the associates inside
Delta's), the unclassified equity-securities total, and IFRS other financial assets, which
hold loans and derivatives beside the stakes; assets held for sale, whose earnings stay inside
operating income unless the disposal is a discontinued operation; tax losses carried forward,
which the tax rate the record derives already reads in part. A decommissioning trust held
under the filer's investment line would be added while the obligation it funds is not
deducted; no valued record holds one (Vistra's, refused by class).

## Terminal growth is held to the risk-free rate

A country's terminal growth comes from `reference/params.json`, one figure per country.
Where that figure is above the risk-free rate the valuation discounts at, the model uses
the rate, and the record's `terminal_growth_rate` parameter says so in its `source` with
both figures ("held to the risk-free rate (rate) ((country)/7y): the table's (figure) is
above it"). A company cannot outgrow its economy for ever, and the risk-free rate is the
market's own reading of long-run nominal growth. Without the rule the gap between the
discount rate and the terminal growth closes whenever rates fall, and on the rule panel the
typical large company read as worth double its price through the low-rate years
(`docs/studies.md`, Why the anchor's level moves with rates). With the
dollar rate above the dollar figure the rule binds no dollar record today; it is there for
the day it does.

**Above the table's figure, the full pass-through stays (decided 2026-10-18).** The hold
gives the model two regimes, meeting at a kink where the rate equals the table's figure.
Below it terminal growth follows the rate, the gap between the discount rate and the growth
does not move, and a point of rate moves a fair value by about one per cent, the projection
years alone; above it the hold ends, the growth stands at the table's figure and a point of
rate moves a fair value by its full duration, a fifth to a quarter (`docs/studies.md`, The
rule panel under shifted rates). The dollar rate crossed the dollar figure between June 2022
and June 2023, so every dollar record today is in the second regime. Against the market's
own measure that regime overstates: only the part of a rate move that is time preference
passes to equity prices, about a third of the US move 1990 to 2023 and little of it after
2000, the rest read as news on growth or inflation and not discounted; the model discounts
the whole move. It is decided that the full pass-through stays: the rate is the one observed
input the model has on the time value of money, taken at face value as a bond takes it, and
every damping of it is a share that would have to be asserted, the paper that measured the
split finding it not constant and not readable for a given move in real time. What the
choice is worth is a level, and the data cannot choose a level: under every reading the
within-date rank of the margins is the run's at one, the return sort is unchanged, and the
market's return has not followed the margin in either stretch. The record says which regime
it is in and how that leans: `rate_pass_through_limits`, beside the rate, carries one
sentence, held to the rate or above the table's figure, with what a point of rate does there;
on the residual-income paths, which have no terminal value, the pass-through into the cost of
equity alone; the NAV path discounts nothing and carries none.

The alternatives weighed and not taken are on the studies page: a partial pass-through, the
WACC taking the long-run mean rate plus a share of the day's distance from it, which halves
the level's swing with the rate and keeps its sign, at the price of a share and an anchor
fitted on one country over one span and a fair value that would depend on the rate's history
rather than the rate; a premium that moves against the rate, built on the market's earnings
yield, which reverses the swing by importing the market's pricing of the panel into every
name's rate; a flat rate, the long-run mean on every date; and the hold both ways, terminal
growth equal to the rate above the table's figure too, which has no parameter and no kink
and makes equity values blind to rates against the market's measured response to time
preference. Each is a level shift above the table's figure and nothing below it, so it would
leave every stored record from 2023 incomparable with the next; none sorts returns
differently.

Should the philosophy change, each path is one place. The rate enters through
`Params.resolve`'s `risk_free` and `Dcf.cost_of_equity`; a partial pass-through or a flat
rate is a step after the curve is read, the rate moved toward a declared anchor by a declared
share, both of which would have to be declared in `reference/`, since the panel's mean and
the paper's share are measurements and not declarations; `python/rule_discount.py` already
reruns the panel under any such reading. The hold both ways is `Params.hold_to_risk_free`
with its comparison removed. A moving premium would replace the table's equity risk premium
in `Dcf.cost_of_equity_capm` with a series per currency, an aggregate earnings yield over a
declared universe, which the model does not have. `Dcf.rate_pass_through_limits` says on the
record which regime a record is in and would change with any of them. Whatever the path,
every stored record values under the present rule, so the panels are rebuilt and the studies
rerun before the new fair values are compared with anything that came before.

## Readouts and diffs

Every `Ok` record also carries two implied readouts solved on its own inputs, headline
untouched: the starting growth (or ROE) the price needs, and the reversion half-life the
observed start would need, and the whole number of explicit years the observed start
would have to persist (an integer scan to 40 years, the risk-free rate held at its
recorded point), the last two only where the start lies above its target; a rule on the
record says which one to read, and every null carries its reason.

With `--baseline`, `provider_diff.txt` opens with every record against the previous run
and lists the inputs behind every moved fair value; with `--baseline-snapshot` as well,
every moved input of every record is classified (price, new filing, restatement, vendor
row, rate or FX, unexplained) in a stability report, so two fetches with nothing having
happened can be shown to agree.

## Quality

`quality` on a record is quality from the filed statements alone, independent of every
model here: Piotroski's nine yes-or-no signals of profitability, balance-sheet strength and
operating efficiency, with the accruals ratio and gross profitability beside them. It reads
the latest two fiscal years and nothing else, so it is the same on a valued record and a
refused one, and nothing reads it. It is on every record whose statements are filed;
`quality_reason` says why there is none (the statements come from another provider, fewer
than two fiscal periods, or two periods that are not consecutive years).

The signals, latest year against the year before, assets at each year's end: return on
assets positive; operating cash flow positive; return on assets higher; operating cash flow
above net income; debt over assets lower; current ratio higher; no more shares; gross
margin higher; asset turnover higher. Each carries the two figures it compared. A signal
whose lines are not all filed is null, never guessed; `f_score` is the count passed and is
null unless all nine are available, and `signals_passed` with `signals_available` say what
is there. `accruals_ratio` is net income less operating cash flow over average total
assets, high meaning earnings ahead of cash; `gross_profitability` is gross profit over
total assets.

The fetch reads five filed lines per fiscal year beside the statements (`quality_lines` on
the boundary record: total assets, current assets, current liabilities, gross profit, cost
of revenue, each with its element; cut at the date on the point-in-time path) and moves no
statement field. Its limits ride on the block: nine yes-or-no signals carry no magnitudes;
assets are year-end figures and leverage reads the record's financial debt, where the
original reads the opening balance and long-term debt; a share count up by more than a
quarter is null, a split and an issue not being told apart; and a bank or an insurer files
no current section and no gross profit, so three signals are null there and no score is
formed. `baseline_study.py` reads the block on the panel's rows. The run summary carries
three plain lines from it, a description and never a signal: the names not profitable on
the latest year, those with operating cash flow not positive (banks, insurers and lenders
left out, where it is not a business reading), and those with more shares than the year
before, counted in full and named where the rise is above two per cent. These three, and
not the composite score, are what the broad study found to sort returns.

**Measured on the panel (2026-10-03), and it is a description, not a signal.** 2,361 rows on
141 names over eighteen quarter-ends carry the block, 989 with all nine signals, the holdout
unread. A score of seven to nine ran four points below SPY at a year and a score of four to
six three below, so the score separated nothing; the fifty-nine rows scoring three or less,
on ten names, ran well above, a handful of speculative names in a market that paid for
them. The interaction the literature documents did not appear: cheap and high-scoring ran
eight points below at a year, cheap and low-scoring six below, and dear and low-scoring was
the best cell. Gross profitability sorted nothing. The accruals ratio was the one measure
on its documented side, the lowest fifth about four points ahead of the highest at a year,
which is small on this sample. So quality is on the record as a reading of the statements
and feeds no model, belief or signal.

## Recency

`recency` on a record (84) says how far the filed quarters have moved on from the annual
base the models read. Every model's base cash flow and growth history start from the last
annual period, and nothing filed after the last annual report reaches a fair value, so a
name that changes fast is read on figures up to a year old and a whole year's change
arrives in one step when the next annual report lands. The downstream reader compares the
growth the price implies with the growth observed, and a stale base misreads both on
exactly the names that move fastest. The block does not move the base; it says how far
behind it is.

It reads revenue alone, the one line every quarterly filing carries on the same element as
the annual one, from the same companyfacts the statements come from: the quarterly filings'
revenue (Form 10-Q, the first three fiscal quarters, a duration of about a quarter) and the
annual filings' (Form 10-K), under the revenue chain's elements, one element throughout:
the element the annual base was read from where its quarters reach the base, else another
that files the base's own annual revenue and whose quarters do (a filer that moved its
quarters to another element years ago, as General Dynamics did, is read on the current
one; a narrower element files a smaller year and is never taken), and where the base's
element has quarters that stop short and no other qualifies, no block, with the reason;
the fourth quarter of each fiscal year is the year less its three filed quarters, marked
`derived`. Then: `latest_quarter_end` and its revenue against
`year_earlier_quarter_revenue`, giving `quarter_yoy`; the four latest consecutive quarters
summed as `trailing_four_quarters_revenue` against `annual_base_revenue` at
`annual_base_end`, giving `trailing_over_annual`; `quarters_since_base`, the filed quarters
ending after the base; and `base_stale`, true when the trailing figure is beyond the
declared `divergence` (`reference/params.json`, `recency_divergence`, a tenth) either way,
since a collapse is as much a stale base as a surge. Where the quarters do not chain the
trailing figure is absent with `trailing_reason`; a 20-F filer reports half-years on Form
6-K, which companyfacts does not carry, and has `recency_reason` instead of a block, as does
a name on the vendor's statements. companyfacts can lag the filings by months: where the
filer's submissions list a 10-Q or 10-K, filed by the fetch date, for a period after the
latest quarter the block reads, `facts_lag` names it, and `base_limits` repeats it, since
the four-quarter shadow then stops short of the filings too. On the point-in-time path the filings are cut at the
date. The summary lists the names whose base is stale, with the trailing figure over the
base.

Nothing reads the block: the models keep the annual base. What the annual base costs the fair
value is said beside it in `base_limits`, and the four-quarter shadow below values the same
model on the last four quarters, beside the headline (decided 2026-10-18, under [The
four-quarter shadow](#the-four-quarter-shadow)). The quarters compared are those of the
element the annual base's revenue was read from; a filer tagging a wider total and a
narrower contract revenue has quarters on both, and a ratio across the two measures the gap
between the elements and not the quarters' distance from the base (corrected 2026-10-18:
MercadoLibre read as a collapse of fifteen per cent where its quarters ran a fifth ahead).

## The growth shadow

The generic DCF picks its starting growth by a switch. With positive after-tax operating
profit and positive net reinvestment it takes the fundamental estimate, the return on
capital times the reinvestment rate; otherwise it takes the historical revenue growth, held
to the return on capital. The switch sits at zero net reinvestment, so a company reinvesting
slightly more than nothing takes a growth near zero and one reinvesting slightly less takes
its whole revenue history: two nearly identical companies, two very different values.

`growth_shadow` on every record whose generic DCF completed says what the value would be
without the switch: the starting growth is the higher of the two estimates where both exist,
the historical one still held to the return on capital, and everything else, the clamp, the
decay, the cash flow and the discount rate, is the headline's own. The block carries both
estimates, the headline's growth and source beside the shadow's, and the shadow's
`fair_value` and `margin_of_safety`, which are what the headline would be. Where the rule
picks the same estimate the shadow equals the headline. The record's `fair_value`,
`margin_of_safety` and `signal` are never moved by it.

It is a shadow so that it can be measured before anything changes: `baseline_study.py` puts
the shadow's margin of safety beside the headline's on the panel's rows. Its limits ride on
the block: what the headline is and how it leans, that the higher of two estimates is a rule
and not a forecast, and that revenue history still reads a rebound or an acquisition as growth.

**The headline stays the fundamental estimate (decided 2026-10-18).** The growth study on the
rule panel (`docs/studies.md`, growth on the rule panel) found that no starting estimate
forecasts the growth that followed, the fundamental one least of all, and that it reads a
median three points below what the names it heads then did. The data could not choose a
headline, so the choice is what the headline means. It means the statements' reading: what
the return on capital and the reinvestment now being made can fund, projected from here,
rather than the past rate carried forward on the assumption that it continues, which is the
one assumption a valuation should not make. Where the fundamental estimate cannot be read,
because operating profit or net reinvestment is not positive, the record falls back to the
revenue history held to the return on capital, and there it does extrapolate. Both facts, and
the lean, are now the block's first limit, so a reader of the fair value knows which way it
errs. The alternatives weighed and not taken are on the studies page: the historical estimate
as headline, a shrunk estimate on the panel's fitted line, a faster fade, the terminal rate
alone. Each is a level shift that would leave every stored record incomparable with the next;
none sorts returns differently; and the fitted line would put a parameter estimated on one
decade of one country's largest survivors on every record, which nothing else on the record is.

Should the philosophy change, each path is one place. The headline's choice is
`Growth.select` in `ocaml/lib/growth.ml`, the switch on positive operating profit and
reinvestment: the historical estimate as headline is a reordering there, the terminal rate
alone a constant there. The fade is `mean_reversion_lambda` in `reference/params.json`, a
declared scalar: a faster fade is a larger value and no code. A shrunk estimate is a step after
the selection, the chosen growth moved toward a target by a declared share, and its target
and share would have to be declared in `reference/`, since the fitted line's intercept and
slope are a panel's and not a declaration; `docs/studies.md` records the line, 5.7 per cent
plus 0.38 of the path, as what that step would have fitted. The growth shadow's `rule` and
`scope_limits` in `ocaml/lib/growth_shadow.ml` say on the record what the headline is and
would change with it. Whatever the path, every stored record values under the old rule, so
the panels are rebuilt and the studies rerun before the new fair values are compared with
anything that came before.

**Measured, and it stays a shadow (the user's decision, 2026-10-03).** On the panel, 644
generic-DCF rows on 42 names over eighteen quarter-ends with the holdout unread, the
shadow's margin of safety ranked names as the headline's did: a rank correlation within the
date of 0.97 at the median, 105 rows changing quintile, the cheapest fifth less the dearest
10.5 points below at a year against 12.3 for the headline and 9.9 for the earnings yield.
It moves levels, a third of the valued names by a fifth to two fifths, and not the order.
So it is not promoted: a rule that only ever raises values, with no evidence it sorts
better, does not replace the headline. It stays on the record because it shows how much a
name's value rests on the growth rule. The holdout was not opened for it.

## The four-quarter shadow

The models read the last annual period, and nothing filed after the annual report reaches
a fair value; the recency block above says how far behind that is, on revenue alone.
`four_quarter_shadow`, on every record whose generic DCF completed and whose statements
carry a trailing period, is the same DCF run once more with the last four filed quarters as
its base. The fetcher reads that period beside the annual ones (`trailing_period` on the
financials, `trailing_basis` naming the filings and spans): each duration is the fiscal
year-to-date figure plus the prior year's annual figure less the prior year's year-to-date
figure, the two year-to-date figures from the quarterly filing's own accession where it
carries both, each balance the quarter end's, and every line is read by the same recipes as
an annual period's (`python/trailing.py`). A recipe that sums components reads what is
present, and on a trailing period a line the 10-K tags may have no 10-Q facts, so a line is
kept only where the trailing recipe is whole against the annual base's: for debt a filer
total or a complete pair, else every row the annual read, and zero by absence only where the
annual was zero; for cash every role the annual assembled unless the quarter reads the
inclusive total; for the working-capital change the aggregate or every row; a line that is
not whole is null and the basis notes name the row, never a partial sum (Crocs's trailing
working capital read the asset side alone before this rule). The valuer puts the trailing period in front of
the annual ones and runs `Dcf.value` unchanged (`ocaml/lib/four_quarter_shadow.ml`). The
block carries the shadow's `fair_value` and `margin_of_safety`, the headline's fair value
beside them, the trailing revenue over the annual base's, and the shadow's complete `inputs`,
so a reader has the second valuation whole. The record's `fair_value`, `margin_of_safety`
and `signal` are the headline's and are never moved by it. Where there is none,
`four_quarter_shadow_reason` says why: no trailing period in the statements (a 20-F filer
reports half-years companyfacts does not carry, a name on vendor statements has no facts, the
latest quarter end is not after the annual base, or no quarter end carries both a
year-to-date net income and a book equity), a derived ebit on the trailing period (the
headline's policy checks a derived ebit against the vendor's annual figure, and nothing
checks a trailing one), or the DCF's own refusal on the trailing base, prefixed.

`base_limits`, on every Ok record with a recency block, is one sentence saying what the
annual base costs: which period the models read, how many quarters have been filed since,
how far the last four quarters' revenue has moved from it against the declared divergence,
which way the fair value leans for it if margins held, and whether a shadow stands beside it;
on the mid-cycle, residual-income, REIT and NAV paths, that no model here reads the quarters.

**Decided (2026-10-18): built as a shadow beside the annual headline, to be measured; the
annual base stays the headline.** When the recency block was built the four-quarter base
was weighed and held back on three grounds, each still standing and now on the shadow's
limits: only US filers report quarterly, so a four-quarter headline would be two bases in
one universe; the quarters are reviewed and not audited and a quarter's one-off lands in a
trailing base in full; and a base on the latest quarters moves when the quarters move, as
the price already has, so on a surging or collapsing name it capitalises the latest
run-rate. On the run of 2026-10-18, 146 of 250 names carried a recency block and 46 of them
read stale beyond a tenth, twenty of ninety valued records among them, the largest by a
fifth to two fifths; the headline on those names describes a business up to a year old and
takes the whole year's change in one step when the next annual report lands, and a reader
comparing what the price implies with what was observed is misread on exactly those names.
The shadow answers "what does the business as currently filed support" beside the headline's
"what do the audited statements support", and the two bracket what a year of lag is worth;
neither is the other's correction, which is why neither replaces the other until measured.
Weighed and not taken: promoting the four-quarter base to the headline on US filers, which
is the three grounds above and every stored US record incomparable with the next, unmeasured;
scaling the annual flows by the recency ratio, which invents cash flows from a revenue ratio
on the assumption every margin held, the plausible default the module contract forbids; and
leaving the annual base with its staleness on the block alone, which says the figure and not
what it does to the fair value. The sentence and the shadow together are the record saying
both.

Should the philosophy change, each path is one place. Promotion is the valuer reading the
trailing period as the latest: one line in `Valuation.run` placing `trailing_period` in
front of `periods` before the models run, after which every stored record values on another
base and the panels are rebuilt before anything is compared. The measurement is the
point-in-time path, which now writes the trailing period cut at the date, so the panels
carry the shadow once rebuilt, and a study putting the shadow's margin beside the headline's
as `baseline_study.py` does for the growth shadow: whether it sorts the returns that followed
differently, whether it anticipates the next annual headline, how often the two disagree on
direction. That study was run the next day on both panels rebuilt (`docs/studies.md`, The
owed measurements on the rule panel): the shadow's margin ranks with the headline's at 0.92
to 0.93 within the date, sorts the returns that followed no better, and is nearer the next
June's headline than the headline itself on two thirds of name-years, a quarter closer in log
distance; a fresher base and not a better sort, so it stays what the statements say, beside
the headline, and the block's last limit says so. The residual-income, REIT and mid-cycle paths read annual periods and
have no shadow: a trailing base for them is a declared recipe each (book equity at the
quarter end with trailing income and payouts; trailing FFO; a window that cannot be
trailing), none written.

## The declared growth

`--growth FILE` puts a reader's own view of growth beside the headline of each name the file
declares: the generic or mid-cycle DCF valued once more with a starting growth the reader
gives, or with the starting growth at which the headline's own path reaches a free cash flow
the reader gives for a year inside the projection. The record's `fair_value`,
`margin_of_safety` and `signal` are the headline's and are never moved by it.

```json
{
  "notes": ["what these declarations rest on"],
  "tickers": {
    "TEST": {"fcff": 1200000000, "currency": "USD", "fiscal_year_ending": 2030,
             "steady_fcff": 1500000000, "g_after": 4, "why": "...", "as_of": "2026-10-19"},
    "GEN":  {"g0": 8, "why": "...", "as_of": "2026-10-19"}
  }
}
```

Each entry is exactly one of two declarations, loaded strictly like `--beliefs`: an unknown
or missing field, both or neither, a non-positive free cash flow, an empty why or a
malformed date stops the run naming the entry.

- `g0`, the starting growth in percentage points. It decays to terminal growth at the
  headline's speed and runs through the headline's arithmetic as declared, not held to the
  clamp the headline's own estimate is held to.
- `fcff`, a free cash flow for the fiscal year ending in `fiscal_year_ending`, in
  `currency`, its major unit. The year is the calendar year the fiscal year ends in, read
  against the record's `fiscal_period_end`, and must lie from the base year plus one to the
  projection's last year, the base year plus `projection_years`; a year the statements
  already carry, or one past the projection, is refused with the reason. The currency must
  be the record's, the one its price and `inputs.fcff` are in, which on a converted record
  is the trading currency and not the statements'. The starting growth is then solved by
  bisection over the implied block's domain, -50% to 300%, so the headline's path from its
  base free cash flow reaches the declared one in that year; the flow there rises with the
  starting growth, so the answer is unique, and past either end the record says which.
- `steady_fcff`, beside `fcff` only: what the declared year's free cash flow would be with
  capex back at a steady level. Every flow after the declared year and the terminal value are
  then scaled by `steady_fcff / fcff`, so the years after it grow along the path from the
  steady figure; declared in the projection's last year, the step is the terminal value's
  alone. Without it, the declared year's capex is carried into every later year and the
  terminal value, and the record says so: a year still building out is valued as if it built
  out forever.
- `g_after`, beside `fcff` only, in percentage points: the growth of the first year after the
  declared one, the years after that fading to terminal growth at the headline's speed, in
  place of the solved path's growth; set to the terminal rate it is a straight drop. Without
  it the years after the declared one keep the solved path's growth, which on a high solved
  starting growth is still well above terminal; with a declared year that is the
  projection's last there are no years for it to apply to, and the record refuses it with the
  reason.

`declared_growth` carries the declaration and its version, the base period and free cash
flow, the starting growth used beside the headline's, whether it lies outside the
headline's clamp or above the return on capital, the growth and the free cash flow in each
projection year, and the shadow's `fair_value` and `margin_of_safety` beside the headline's
fair value. Its limits say what the path is: the years before the declared one are the
headline's path and not a forecast of their own, and the years after it keep the path's
growth, which is still above terminal where the declared year comes early, or grow from a
declared `g_after`. On the mid-cycle path the base is the through-cycle free cash flow on
today's capital, so a declared free cash flow is read as the through-cycle level in its year, and one for a peak or a trough
year is carried as the normal level into the years after it; the block says so on every
mid-cycle record. Where a declared name has no block, `declared_growth_reason` says why:
the declaration's own refusal, a model with no free cash flow path (the residual-income,
REIT and NAV paths), or a model that did not complete. An undeclared name's record carries
neither field and is the record without the flag.

**Decided (2026-10-19), on a request from a downstream project that runs a clone.** The
headline's growth is the statements' reading and stays so (the growth shadow above); a
reader who holds a view of a name's cash flow had no way to put it beside the headline
without editing the code. The declaration is the reader's, like a belief or a required
return, so it is dated, carries a why, is never derived from anything here, and stays a
shadow. Everything but the starting growth, and what the reader declares for the years after
the declared one, is the headline's own: the discount rate (a declared required return included), the fade, terminal
growth, net debt, the equity bridge and shares. Weighed and not taken: a declared free cash flow for a year the
statements carry, which is a restatement of the base and not a view; and a declared starting
growth and free cash flow together, which over-determines the path. The growth after the
declared year is the headline's path unless the reader declares `g_after`, added the same day
when the same project found on its own cash flows that the growth left over from the solve
carried a material part of the value on many names, most where build-out capex holds the
base down and so lifts the solved starting growth: the years it did not declare are then
something it can declare rather than a remainder of the solve.

## Capital intensity and goodwill

Two readouts from the statements on what the capital is doing, beside the fair value and
never inside it (`ocaml/lib/capital.ml`).

`capital_intensity`, on every record whose latest period carries capex and a positive
depreciation: the two figures, capex over depreciation, and `growth_capex`, capex less
depreciation where positive. The split is the build-out readout's own rule, stated:
depreciation is maintenance and the excess is growth spending, because no filer discloses
the split. On a generic DCF record the block also carries `fcff_maintenance`, the headline's
free cash flow with maintenance capex in place of the capex spent, what the standing business
throws off if the growth spending stopped: a figure, not a value, and not the headline's
base. `capital_intensity_reason` names the missing line otherwise. The block declares no
build-out; whether the capital is one, and what it will earn, stays the universe entry's
judgment (`build_out`, `build_out_return`, `build_out_lag_years`), which the build-out
readout maps where it is declared.

`goodwill`, on a record whose generic DCF completed and whose latest period files goodwill
under the `Goodwill` element (now read by the fetcher as `goodwill` on every filed period):
the filed balance, the headline's invested capital (book equity plus debt), the same less
goodwill, goodwill's share of it, and the return on capital both ways, `roic` as the
headline reads it and `roic_ex_goodwill` on the thinner base. `goodwill_reason` says why
there is none. The headline keeps the return with goodwill, so an acquirer's fundamental
growth estimate leans low, and the block says so.

**Decided (2026-10-18): the last open model question, four declared limits, is settled as
two readouts and two declarations.** The universe marks ten names `build_out` by hand;
measured on the run, forty of the hundred and eighty-four names with the two lines spend at
or above twice their depreciation, and the uncoded ones include the largest build-outs in
the universe by dollars, Alphabet, Meta, Microsoft, Micron, Texas Instruments, Nvidia, all
valued records whose headline free cash flow is after that spending with nothing on the
record saying so, since the build-out readout appears only on refusals. So the condition is
now measured on every record and the code stays what it was, a judgment. Goodwill was a code
on seven names and the figure was not fetched; now it is, and the claim the code makes is a
number a reader can see; measured the next day on the rule panel rebuilt (`docs/studies.md`,
The owed measurements on the rule panel), capex over depreciation sorted the returns that
followed by nothing, the margin at maintenance capex sorted worse than the headline's, and the
fundamental estimate on the return without goodwill forecast realised growth no better and a
shade worse at three and five years, so the headline keeps both its base and its return and
each block's last limit says what was found. The measurement of the code found
two definition defects on the way, Accenture's depreciation and Lilly's capex, corrected in
the commit before this one. The other two of the four stay declared: a rebound, trough or
one-off year inside the growth window, whose remedies are a year in the universe entry
(against the rule that entries carry none), a fitted detector, or a scope code read as a
model input, each breaking a rule the tool keeps; and the growth rule's cliff at zero
reinvestment, already carried by the growth shadow and the `growth_without_reinvestment`
code, whose remedies are a blend weight nobody declared or a per-name choice of estimate,
which is what a belief is for and the anchor is not. Weighed and not taken for the two built:
promoting the maintenance free cash flow to a headline for build-outs, which capitalises a
declared return on growth capex as if every dollar became earning capital, the fallback the
contract forbids; and switching the headline's return to the one without goodwill, a
definition change on every acquirer's record before it is measured. Should the philosophy
change: the headline's base is `Dcf.fcff` and its return `Growth.estimate`, one place each;
the eight undeclared build-outs want their return and lag declared on the entry, which is the
user's judgment and the readout's only input.

## Scope limit codes

A record's `scope_limits` say in prose what the model cannot see for the name. Beside them,
`scope_limit_codes` carries one stable code per limit, in the same order, so a reader can
act on a limit by rule (skip the valuation layer for every `build_out` name, say) and still
read the text. The field is absent when the record carries no limit. The codes are declared
with their meanings in `reference/universe.json` under `scope_codes`; each universe entry
gives `scope_limit_codes` beside its `scope_limits`, each class its
`scope_limit_codes_default` in `reference/admissibility.json`, and both loaders refuse a
code outside the vocabulary or a count that does not match the limits. A code is added to
the vocabulary and never renamed. `uncoded` is reserved for a declaration that gives no
codes, as a `--universe` file from before them does; no tracked limit reads it.

| code | a limit under it says |
|---|---|
| `build_out` | capital spending runs well above depreciation on capacity that is not yet earning, so the free cash flow or the return the model starts from understates the business |
| `growth_without_reinvestment` | the fundamental growth estimate, reinvestment times the return on capital, reads far below the revenue history because the business grows with little reinvestment, so the headline value stands on the lower estimate and the growth shadow carries the other (84) |
| `rebound_window` | the growth window opens on a recovery from a collapse, so the derived starting growth reads the rebound as growth |
| `trough_window` | a reset or trough year sits inside the growth window, so the derived starting growth reads the trough |
| `product_transition` | a product transition inside the growth window: a franchise in decline or a launch not yet in the statements |
| `goodwill_heavy` | acquired goodwill is a large part of invested capital or sits inside the latest earnings, so the return on capital reads the price paid for a business rather than what it earns |
| `acquired_history` | acquisitions or a change of ownership inside the window, or one after the latest statements: the filed history is not the business ahead |
| `carve_out_history` | a spin-off, carve-out, divestiture or fresh-start accounting inside the window: part of the filed history is another entity's |
| `short_history` | the filed history is short or young, so what the model reads as a through-cycle figure is a few years |
| `structural_break` | a declared break in the business, so a through-cycle figure may not recur |
| `backward_looking` | the through-cycle average looks backward by construction |
| `captive_finance` | a captive finance arm: its interest is an operating cost and its debt funds a lending book, and the model reads both as the company's financing |
| `pass_through_balances` | balances held for customers, members or managed funds pass through the statements and are not the company's own cash, debt or working capital |
| `one_off_in_window` | a one-time charge, write-down or non-operating loss sits inside the window and is read as an operating year |
| `leases_excluded` | operating leases are outside the debt definition, so a lease-heavy estate carries less debt here than its obligations imply |
| `vendor_statements` | no filed statements are read: they come from the vendor, with fewer years and no tag behind a number |
| `mixed_business` | a material part of the business is of another kind than the class's lens reads |
| `market_marks` | earnings carry unrealised marks or performance fees that move with markets, which the model reads as a level |
| `investment_book` | a large book of investments sits on the balance sheet at values the model does not read |
| `filer_marks` | the value rests on the filer's own marks of unquoted assets, recorded and not verified, with losses visible late |
| `policy_dependent` | earnings rest on a policy rate, a tax credit or a government agreement that the company does not control |
| `commodity_exposure` | part of revenue or cost moves with a commodity price |
| `concentration` | a few customers or products carry a large share of revenue |
| `contract_terms` | a large cost or revenue share is set by contracts the statements do not separate |
| `balance_sheet` | the balance sheet's own shape, heavy debt or negative book equity, limits what the model can read |
| `ownership_structure` | the listed line owns only part of the business, counts only part of the shares, or ranks behind other claims |
| `country_basis` | the country that chooses the risk premium is not the legal domicile |
| `filer_tagging` | the filer's own tagging puts a line under an element that means something else, so a field the record reads is not what its name says |
| `leases_in_debt` | the vendor does not separate lease liabilities from borrowings, so the debt read includes the leases |
| `loss_making` | loss-making on the latest filed years |

## The studies

What the tool found when turned on its own work is on `docs/studies.md`: the three panels
and what each can and cannot answer, the anchor and baseline studies on the point-in-time
panel, the broad panel's cheapness and quality sorts, the rule panel's DCF on the five
hundred largest filers with its rates, betas, growth and duration, stretch and insiders
through time, the surprise study, and the model questions the studies left open. This page
is the manual for the tool; that one is what the tool found.

## Three side tools on the run's own outputs

Each reads what a run and the consensus tool already wrote, fetches nothing, and writes a
table. None is on a valuation record and none feeds a model, a belief or a signal.

    uv run python/implied_cost.py           # -> output/consensus/implied_cost.txt and .jsonl
    uv run python/earnings_reactions.py     # -> output/earnings_reactions/table.txt and rows.jsonl
    uv run python/watch.py                  # -> output/watch/<valued_on>.txt

**The consensus-implied cost of capital** (`implied_cost.py`) is a third required return
beside CAPM and the options-implied one: the discount rate at which the price equals the
earnings the analysts forecast, by Easton's PEG model, the square root of the next fiscal
year's consensus EPS less the current year's, over the price. It needs only what the daily
consensus snapshot carries. A name gets a figure or the reason there is none: no snapshot,
a forecast missing or not positive, the next year not above this one, forecasts in another
currency than the price, or a price in a minor unit. The table puts the record's CAPM and
options-implied figures beside it. The forecasts are the Street's adjusted earnings and run
optimistic, and the model ignores dividends, so it reads low for a payer.

**Earnings reactions** (`earnings_reactions.py`) joins two things already on disk: the
record's last eight releases with the move across each against the benchmark, and the
consensus tool's bar and reported figure for each. Per name it gives the median excess move
on beats and on misses with their counts (a side with fewer than three is a count alone),
the beats the price fell on and the misses it rose on, and beside them the next release,
the days to it, and the implied move against the realised median where the run was made
with the options store. A pooled line covers every matched release in the universe. Eight
releases are a handful, and a beat on the Street's adjusted figure is not a beat on
guidance.

**The watch** (`watch.py`) compares two runs' records and lists what changed, one line a
name, for reading a day where the batch's own `--baseline` diff is for auditing a change
to the code. Without `--previous` it takes the newest archived run under `output/runs/`
valued on an earlier day. Its sections: a ticker that no longer names its declared filer;
status changed; signal changed; the price crossed the fair value; a new fiscal year was
read; the fair value moved by more than five per cent with no new year; the price moved by
more than ten; stretch newly at three on a side; an insider buying cluster newly present;
releases due within seven days; names in one run and not the other. It ranks nothing and
recommends nothing.

These replace three things the first version of this project had and leave out what made
them recommendations: its earnings scanner sized positions and named trades, and its
watchlist scored a thesis and raised price alerts. What is kept is the descriptive core.

## Share counts and point-in-time

Two share counts live in `reference/field_definitions.json` and are never interchanged: a
flow per share for a historical period (the REIT model's FFO growth) uses that period's
weighted-average diluted count, and a point count (market cap) is effective shares live or
a filed count point-in-time.

A point-in-time record values a name as of a past date from what was known then: facts
filed by the date, the close on the last trading day on or before it (split-corrected),
the share count nearest the filed period carried through the vendor's split record and
divided by the declared receipt ratio, rates and FX observed by then, and the vendor's
live column for the same fiscal period as a cross-check only;

ERP, tax rates, betas and the assumptions are held at the current vintage and every one
whose vintage postdates the date is named on the record. Vendor-path names have no
filing dates and fail, named. The panel builder writes one row per name and quarter-end
with the forward 12-month return and one descriptive table, and no statistic.

Valuation never fetches, so running it twice on the same inputs with `--today` pinned
gives byte-identical output. `data/` and `output/` are generated and gitignored;
versioned inputs live in `reference/`.

## Stretch

Every record whose name has 250 closes on or before its date carries a `stretch` block:
six measures from split-corrected closes and volume, `dd_120` (close over the 120-day
high, minus one), `above_120_low`, `vs_ma50`, `vs_ma200`, Wilder's `rsi_14`, `rv_20` with
`rv_ratio` against the name's own one-year median, and `vol_5_60`, each with its
percentile of the name's own trailing two years, so "tail" is the name's. Two counts
follow, never a blend: `stretch_low`, how many of `dd_120`, `vs_ma50`, `vs_ma200` and
`rsi_14` sit at or beyond the low thresholds, and `stretch_high` with `above_120_low` in
place of `dd_120`.

The thresholds live in `reference/stretch.json`, dated with a why: set to fire on two
remembered episodes and to be rare; changing them is a dated declaration. The summary
names every record at or above 3 on either side and prints a line for each with the
measures, the percentiles and the anchor's fair value, margin of safety and
`probability_overpaid` beside it. Whose thesis a stretched name corroborates is the
reader's to know; the tool holds no thesis and no flag. It says "stretched" and nothing
more: no signal, no claim about what follows.

The block is computed at fetch time and point-in-time from closes on or before the date
(`python/stretch.py --ticker PLTR --as-of 2026-06-25` prints it; `--snapshot DIR` adds it
to a snapshot's records), and `python/plot_stretch.py PLTR` draws two years of closes with
the averages, shaded where either count reached 3, to `output/stretch/PLTR.png`.

## The build-out readout

A name whose reported cash flow is negative because it is investing more than it earns, and
whose earning history at scale is too short for the mid-cycle window, refuses honestly and
today says nothing else. The build-out readout (60) says the one thing that can be said: for
a `Cyclical` or `OperatingCompany` record that failed the observation guard or the
non-positive-free-cash-flow guard, whose latest capex exceeds its depreciation and whose
latest operating income is positive, `build_out` carries the surface of value per share
across what the new capital earns and how long it takes to earn it, with the price drawn as
a contour per lag.

It is a map of what the price requires, not a value. The record stays `Failed` with its own
reason; the block adds no fair value, no margin of safety and no signal, nothing downstream
reads it, and it never fails a record.

The two declarations live on the universe entry, both or neither, each exactly a value, the
evidence for it and a date:

```json
{
  "ticker": "AMZN",
  "entity_class": "Cyclical",
  "why": "retail and cloud; a capacity build-out ...",
  "build_out_return":    { "value": 0.22, "why": "...", "as_of": "2026-09-23" },
  "build_out_lag_years": { "value": 2,    "why": "...", "as_of": "2026-09-23" }
}
```

`build_out_return` is the after-tax **accounting** return on the new capital once earning,
after depreciation — the units a filing states and a reader reasons in, directly comparable
to the name's own recent return on capital, which the `why` cites as evidence (63). The
readout converts it to the cash yield it needs, adding the same depreciation-to-capital ratio
it then charges as maintenance, and carries both figures with the ratio on the record; a
tranche's free cash flow is therefore the declared return on its cost. `build_out_lag_years`
is whole years from spend to first earning (a data-centre campus one to two, an LNG train
four). A name with one and not the other fails the universe loader; a name with neither
carries `build_out_reason: "build-out return and lag not declared"`.

On the record: the two declarations, the cash return they convert to with the sentence saying
how, the maintenance sentence, the last three years' capex,
depreciation and growth capex as tranches, the standing business alone per share, the WACC,
tax rate, terminal growth and depreciation-to-capital ratio the map runs on, the return axis
(31 values in accounting terms, as the declaration is, the declaration in the middle, ±15
points in 1-point steps), the surface (one row per lag 0..6) and the price contour, whose
`return_required` is an accounting return too. A lag whose contour is null says why — no return in
the range reaches the price, or the price is below the whole range — with the figure at that
end, and that is itself the readout.

```sh
uv run python/plot_build_out.py AMZN --out output   # -> output/build_out/AMZN.png
```

The picture is the surface with the contour, a vertical line at the declared return and a
horizontal one at the declared lag; where the contour is empty the legend says the price is
outside the map at every lag.

## Insiders

Stretch says the price has run from its own path; Form 4 says what the people with the most
information did about it (66). Every CIK-resolved record carries an `insiders` block, read
from SEC's own filings index and archive, keyless and timestamped. A name without a CIK
carries `insiders_reason` instead, because Form 4 covers SEC registrants only.

**Open-market purchases and sales only.** From the non-derivative table, transaction code
`P` (purchase) and `S` (sale). An award (`A`), an exercise (`M`), a tax withholding (`F`), a
gift (`G`) and every other code are **counted by their code and never summed** — an
exercise-and-sell is not a sale of conviction, and an award files a price of zero, so the
filter runs before the arithmetic or the buyer counts inflate where the dollars do not. The
codes seen and not summed are listed on the block as `excluded_by_code`.

The block carries, over the trailing 90 and 365 days: distinct buyers, distinct sellers,
dollars bought, dollars sold, net dollars, the largest single purchase with its owner and
relationship as filed, and whether any buyer's filed title names a chief executive or
financial officer. `cluster_buy` is true when **two distinct insiders** bought on the open
market inside any fourteen-day window in the trailing ninety days — one insider buying twice
is not a cluster, which is the point of the rule — with the window's dates and buyers listed.

**Telling routine sales from unusual ones.** Most insider selling is stock pay being sold
on a schedule, so each window also says how much of its selling was scheduled and how much
of a holding each seller let go. `plan_sales`, `plan_sellers` and `plan_dollars_sold` count
the sale lines, the sellers and the dollars on filings that mark a Rule 10b5-1 plan, the
form's own checkbox. `sellers_detail` lists every seller in the window, largest dollars
first: the sales, shares and dollars, the part under a marked plan, and
`fraction_of_holdings_sold`, the shares sold over what the seller's ownership lines held
before the sales began. Holdings are filed per ownership line (direct, each trust), so the
balance is read per line from its last sale in the window and summed over the lines sold
from; a line with no figure leaves the share absent. Three limits ride on the block: the
checkbox is in use on forms filed from April 2023 and covers the whole filing, so an earlier
sale reads unmarked; lines with no sale in the window, options and unvested awards are not
in the holdings, so the share overstates what was sold of everything the seller owns; and
nothing here weighs or scores a sale.

**Routine traders and opportunistic ones (83).** A reader who cannot tell scheduled
selling from the other kind ignores all of it, and most of it is scheduled. The block
therefore tells them apart by the rule in Cohen, Malloy and Pomorski, "Decoding Inside
Information", NBER Working Paper 16454, October 2010, doi:10.3386/w16454: an insider who
placed a trade in the same calendar month in each of the three preceding years is a
routine trader, every other insider with a trade in each of those three years is
opportunistic, and the designation is made from past history alone and inherited by the
trades that follow it. In their data the trades of opportunistic insiders carried the
information and those of routine insiders none: after an opportunistic sale the stock
ran lower in the month that followed, after a routine one it did not. Here the three
years are the calendar years before the as-of year, the trades are this name's
open-market purchases and sales with buys and sells pooled for the timing test, which
the paper leaves open, and an insider with fewer than three such years is unclassified
with the reason, never defaulted. Each window carries `routine_buyers`,
`opportunistic_buyers`, `routine_sellers` and `opportunistic_sellers` with the dollars
each way, the rest of the buyers and sellers being unclassified; each seller in
`sellers_detail` carries `trader` and, when unclassified, `trader_reason`; and
`trader_history` says what the classification read, the years, the documents parsed, the
documents and pages the cache lacked, and whether it was complete. The plan marking stays
a separate axis: a scheduled seller whose months shift by one reads opportunistic, and the
two are meant to be read together.

**The history is fetched once and never by the valuation path.** Three years of Form 4 is
tens of thousands of documents across the universe, so `uv run python/insider_history.py`
fills the cache (the older submissions pages whose span meets the three years, then every
Form 4 and 4/A filed in them, paced), hours the first time and the index reads after. The
run reads only what is on disk: where a page or a document the index lists is missing,
every trader in the window is unclassified with `trader_history_reason` naming the command,
and the counts by kind are nil, because a quiet year that was never read must not become a
routine one. A name without a filer, or a foreign private issuer, has no history to read,
as it has no block.

**What the classification preceded on these names (2026-10-07).**

    uv run python/insider_study.py                 # -> output/insider_study/tables.txt

`insider_study.py` reads, for every universe name with a filer at every quarter-end from
March 2024 to the last before the holdout, the trailing ninety days of Form 4 from the
cache and classifies each seller and buyer from the three years before the date's year, as
the block does; a name and date is then one row in one of four groups on each side, an
opportunistic seller present, routine sellers only, unclassified sellers only, no seller,
and its excess over SPY at 63, 126 and 252 trading days after is read from the anchor
study's closes. Ten quarter-ends, 1,670 name-dates on 167 names, every history complete.
Of the sellers in the windows 17 per cent read opportunistic, 23 routine and 59
unclassified, their history shorter than three years.

| sellers in the window | rows | names | +63d median excess | +126d | +252d (positive share) |
|---|---|---|---|---|---|
| an opportunistic seller present | 408 | 83 | −0.023 | −0.035 | −0.053 (113/252) |
| routine sellers only | 232 | 59 | −0.006 | −0.009 | −0.026 (64/134) |
| unclassified sellers only | 329 | 102 | −0.018 | −0.016 | +0.004 (89/176) |
| no seller | 701 | 120 | −0.008 | −0.025 | −0.025 (179/406) |

So on these names, in these ten quarters, the names where an opportunistic insider had
sold ran about three points behind the names with routine sellers only at a year, and
behind the names with no seller, on the side the paper found and by about a third of its
size; the routine sellers' names ran with the rest. That is a lean, read on one market
over two and a half years with cells of a few hundred, and the study claims nothing more
than that it is on the paper's side rather than against it. The buying side has too few
classified buyers to read: 23 rows with an opportunistic buyer, 15 with routine ones.
Nothing feeds back: the block carries the kinds and the reader weighs them.

**The cut is on the filing date, not the transaction date.** A Form 4 carries no filing date
in its XML and its signature date disagrees with the index often enough to matter, so the
index is the only source for it. The point-in-time path reads the same index with everything
filed after `D` already removed, so the panel's block is the one a reader had on the day.

Documents are immutable once filed and are cached under `data/insiders/<CIK>/<accession>.xml`
for ever; the index is what ages. Amendments are read too: nothing in the index links a `4/A`
to the `4` it amends — their accessions share only the filing agent and the year — so the same
line is recognised by owner, date, code and shares, and the later filing wins.

The summary prints, beside every name already listed at `stretch_low >= 3` or
`stretch_high >= 3`, that name's ninety-day buyer and seller counts and net dollars, and then
a second list, **"stretched with insiders on the other side"**: stretched low with a cluster
buy or a chief executive or financial officer buying, and stretched high with net selling by
two or more distinct sellers. Counting, never weighting.

```sh
uv run python/plot_insiders.py PLTR                     # -> output/stretch/PLTR.png
uv run python/plot_insiders.py PLTR --as-of 2026-06-25  # as it stood on that day
```

The picture is the stretch chart with every open-market purchase and sale drawn at its price
on its transaction date, sized by dollars against the largest in the window, so the reader
sees where insiders acted relative to the path. It replaces the stretch-only chart.

**Scope limits, on every block:** Form 4 covers directors, officers and ten-percent owners of
SEC registrants, so a foreign private issuer files none; a purchase or sale under a rule
10b5-1 plan is scheduled rather than decided, and the filing's plan marking is carried on the
transaction where it has one.

What the stretch marks and the insiders' windows preceded, across everything the store holds,
is a study: `docs/studies.md`, Stretch and insiders through time.

## Consensus and surprise

`uv run python/consensus.py` (82) records the Street's bar for every universe name and how
each name has met it. It is a side output: nothing in a valuation record reads it, no model,
belief or signal moves with it, and it never fails a record. Consensus is an input for a
reader who uses it as the market's bar; it settles nothing.

**The daily snapshot** writes `data/consensus/days/<day>/<TICKER>.json`: for this quarter,
next quarter and both fiscal years, each period's end date, the EPS bar (mean, low, high,
analyst count, the year-ago figure), the revenue bar with the same keys, and the EPS
consensus as it stood 7, 30, 60 and 90 days earlier. The fetch day is the as-of date of
every figure in the file, and a figure the vendor does not carry is null. A run is
idempotent per day: an ok record is never fetched or overwritten again, a failed one is
retried, and `manifest.json` says complete or partial with the names that failed. A name
the vendor answers with no consensus at all, a fund for instance, is `none` rather than
failed: listed apart in the manifest and not retried that day. A day with no run gets a
manifest of its own saying it is a gap, because a bar cannot be taken after the fact. Run
it at each sitting or daily by cron; the more days it runs, the fresher the bar each
revenue pair can use, and every pair says how many days before the release its bar was
taken. Nothing here is tracked, so each clone builds its own history from its first run.

**The release history** writes `data/consensus/history/<TICKER>.json` once a day: every
past release in the vendor's dated earnings table with its final EPS estimate and the
reported figure, both on the **Street-adjusted basis** the vendor carries and not GAAP,
the estimate being the last consensus before the release with no earlier date given; each
release matched to the latest filed fiscal period ending 1 to 120 days before it, or null
with the reason; and, for a name with SEC filings, quarterly revenue as first filed, a
three-month figure where one is filed and otherwise the fourth quarter as the fiscal year
less the nine months to the third quarter, labelled so. The revenue tags are the shared
`total_revenue` list plus one element the shared list does not yet name, written in the
module with the reason.

**The summary** is `output/consensus/summary.jsonl`, `pooled.json` and `summary.txt`,
regenerated from `data/` alone. Per name and per window of the last 8 and 12 releases:
the count, beats (reported above the estimate), meets and misses, the beat rate, and the
median and quartiles of the surprise in percent of the estimate, a zero estimate counted in
the rate and left out of the percentages with the reason. Revenue gets the same windows,
in percent and absolute, over the pairs of a snapshotted bar taken on a day before the
release and the filed quarter, so it starts empty and fills one release at a time. The
pooled rate is the beats and releases summed across every name with a window; pulling a
name's own rate toward it is the reader's decision, not the tool's.

**Scope limits.** The surprise history measures the Street's adjusted EPS against the
Street's own estimate, so it says nothing about GAAP EPS. The revenue bar is the
consensus's own definition of revenue, which can differ from the filed line, gross against
net or with pass-through costs, and a pair across such a gap reads as a surprise. A name
with no SEC filer has releases and bars but no filed quarters, and says so. Sources: the
vendor's earnings-trend module, reached through a private surface of yfinance 1.7.0, so a
change in the library is a failed record with the reason; the vendor's dated earnings
table; SEC companyfacts.

What the surprise history preceded, whether a beat follows a beat and what the price did
after, is a study: `docs/studies.md`, What the surprise history preceded.

## Build, test, type-check

```sh
dune build        # also regenerates python/boundary.py and python/reference.py from schema/*.atd
dune test
uv run pyright
uv run pytest
```

Every figure in every test and fixture is invented. The tickers are `TEST`, `GEN`, `BNK`,
`NIL` and the like, the statements are round numbers chosen so the arithmetic can be checked
by hand, and the fixture files under `ocaml/test/fixtures/` say so in their `notes`. Nothing
under test was ever fetched: a fixture written from a snapshot would be fetched data in the
tree, which the data policy forbids, and a filer's real figures, public as they are, would
read as a claim about that filer rather than a check on the code. A record a reader holds
was produced from their own fetch and carries its provenance on itself; no test figure
reaches one.
