# atemoya

Fundamentals-based fair-value anchoring for equities: Python collects vendor data into a
schema-checked boundary, OCaml values it.

## Setup

Requires git, [opam](https://opam.ocaml.org) 2.1+, [uv](https://docs.astral.sh/uv/), and
optionally [direnv](https://direnv.net).

```sh
git clone <this repo> && cd atemoya

# OCaml: a local switch in ./_opam, pinned by atemoya.opam.locked (compiler included)
opam switch create . --deps-only --locked

# Python: the venv in ./.venv, pinned by uv.lock (downloads Python 3.14 if needed)
uv sync --locked

# Everything else, once per clone
direnv allow
```

`direnv allow` runs `.envrc` on every `cd` into the repo: it activates the opam switch and
the venv, loads `.env` if present, and points git at the tracked hooks in `.githooks/`
(a pre-commit secret scan and a commit-msg trailer strip). Without direnv, do those by hand:

```sh
eval "$(opam env --switch=. --set-switch)"
git config core.hooksPath .githooks
```

`uv run` works without activating the venv either way.

The U.S. risk-free curve is refreshed from FRED and needs an API key, free from
<https://fred.stlouisfed.org/docs/api/api_key.html>. Copy `.env.example` to `.env` and put
the key after `FRED_API_KEY=`. Statements for U.S. filers come from SEC XBRL, which
requires every request to identify its sender: put `"<name> <email>"` after
`SEC_EDGAR_IDENTITY=`, quoted.
`.env` is gitignored and the pre-commit hook refuses it.

Options data (the market-implied readout) comes from ThetaData through its terminal, run
from this repository with your own subscription:

1. Download `ThetaTerminalv3.jar` from ThetaData into `tools/thetaterminal/` (gitignored
   entirely: the jar, its config, its logs and the momentary creds file live there).
2. Put your ThetaData login in `.env` as `THETADATA_EMAIL` and `THETADATA_PASSWORD`.
3. `uv run python/theta_terminal.py start` (then `status`, `stop`). The script reads the
   two variables from the environment, writes a creds file with mode 600, launches the
   jar with `--creds-file`, and removes the file once the terminal's port answers. It
   never prints a credential.

## Data policy and first run

**Nothing obtained from a data provider is ever committed.** Rates, FX, filings, snapshots,
runs: all under gitignored `data/` or `output/`. `reference/` holds declarations and
hand-transcribed, attributed vintage tables only. Every user of a clone provides their own
FRED key and runs the refreshers before the first valuation; a missing fetched file fails
each record that needs it with the refresher to run, never a shipped default.

First run, in this order:

1. `cp .env.example .env`.
2. Obtain a FRED API key (free, at fred.stlouisfed.org) and set `FRED_API_KEY` in `.env`.
3. Set `SEC_EDGAR_IDENTITY` in `.env` (name and email, sent as the User-Agent).
4. `uv run python/refresh_rates.py --all` and `uv run python/refresh_fx.py --all`, which write
   `data/reference/risk_free_rates.json` and `data/reference/fx_rates.json`.
5. `uv run python/fetch_all.py`.
6. `dune exec atemoya -- data/financials --out output`.

## Run

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
```

`dune exec atemoya` reads declared parameters from `reference/` (`--reference DIR` to
override) and the fetched curves and FX from `data/reference/` (`--fetched DIR`), and
measures their age against today's UTC date (`--today YYYY-MM-DD` to override). Inputs may
be files or directories. Every ticker needs a declared `entity_class`, from its entry in
`reference/universe.json` or from `--entity-class CLASS` for an ad-hoc run; without one the
record fails as undeclared. `reference/admissibility.json` says which models may run on
which class (today the FCFF DCF on `OperatingCompany` and `HighGrowthSoftware`, the same
engine on through-cycle earning power for `Cyclical`, residual income on `Bank`, residual
income on AOCI-adjusted book from filed statements on `Insurer`, and the FFO-covered
dividend on `Reit`) and what each other class is judged on instead; an inadmissible class
fails with that lens named. A universe entry may declare the SEC filer to read by `cik`
when the ticker map points elsewhere; the fetch keeps as many annual periods as the
class's model needs. `docs/flow.md` charts every branch from ticker to record. A record is either
`Ok` with a fair value, or `Failed` with a reason; it never carries a guessed number.
Every record carries a `floor` (present, absent by definition, or not assessable here,
with its basis) that gates nothing. A name whose statements and price are in different
currencies is converted at one recorded FX rate (statement totals, never per-share
fields) and valued in the trading currency with that currency's country's rates plus the
domicile's country risk premium; prices quoted in pence or cents are converted to the
major unit at the fetch. The universe file declares only: ticker, class, why, and what no
model can see; it is loaded strictly. Whether a change moved anything is answered by the
run diff against the previous run, never by a stored expectation.
Filed statements come in the taxonomy the filer uses (us-gaap or ifrs-full, each a
section of `reference/xbrl_tags.json`) and in the currency the facts carry, which the
record names as its statement currency and which must agree with the vendor's, else the
record fails. SEC's submissions index is read for every CIK-resolved name and its newest 10-K or 20-F
recorded; when that filing is newer than the newest annual facts and those facts are past
the filing-age gate, the vendor's statements are used by a decision written into the
record's provider reason (companyfacts lags submissions), never as a fallback from the
gate. Both providers assemble cash, total debt, the change in working capital and ebit per
`reference/field_definitions.json`, the one definition per field with its reasoning; every
period records the components summed, and a record fetched under another definition fails
rather than being valued under this one. A derived
ebit (no operating income filed) runs the DCF only when the cross-check finds it within
threshold of the vendor's operating income; the refinement policy in that file allows one
refinement of a recipe and names the `Failed` reason for a miss. Every `Ok` record also
carries two implied readouts solved on its own inputs, headline untouched: the starting
growth (or ROE) the price needs, and the reversion half-life the observed start would need,
and the whole number of explicit years the observed start would have to persist (an
integer scan to 40 years, the risk-free rate held at its recorded point), the last two only
where the start lies above its target; a rule on the record says which one to read, and
every null carries its reason, and `model_version` names the code that produced it (the
git short hash, `-dirty` when the tree had uncommitted edits). With `--baseline`, `provider_diff.txt` opens with
every record against the previous run and lists the inputs behind every moved fair value;
with `--baseline-snapshot` as well, every moved input of every record is classified (price,
new filing, restatement, vendor row, rate or FX, unexplained) in a stability report, so two
fetches with nothing having happened can be shown to agree.
Two share counts live in `reference/field_definitions.json` and are never interchanged: a
flow per share for a historical period (the REIT model's FFO growth) uses that period's
weighted-average diluted count, and a point count (market cap) is effective shares live or
a filed count point-in-time. A point-in-time record values a name as of a past date from
what was known then: facts filed by the date, the close on the last trading day on or
before it (split-corrected), shares from the newest cover page filed by then (else the
balance-sheet count at the newest period end filed by then), rates and FX observed by
then, and the vendor's live column for the same fiscal period as a cross-check only; ERP, tax
rates, betas and the assumptions are held at the current vintage and every one whose
vintage postdates the date is named on the record. Vendor-path names have no filing dates
and fail, named. The panel builder writes one row per name and quarter-end with the forward
12-month return and one descriptive table, and no statistic.
Valuation never fetches, so running it twice on the same inputs with `--today` pinned gives
byte-identical output. `data/` and `output/` are generated and gitignored; versioned inputs
live in `reference/`.

Build, test, type-check:

```sh
dune build        # also regenerates python/boundary.py and python/reference.py from schema/*.atd
dune test
uv run pyright
uv run pytest
```

## Beliefs

The declared belief on long-run growth, and the probability of overpaying under it, follow
Smith and Smith's value-surplus idea read as written: the investor states their own
uncertainty about long-run growth; the output is the distribution of the value surplus,
which is the margin of safety here; the risk measure is the probability that it is
negative. Nothing is sampled: fair value is monotone in terminal growth below the discount
rate, so the probability is the belief's CDF at the implied long-run growth, in closed
form. The rules of use, in this order:

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

Run with a further beliefs file:

```sh
dune exec atemoya -- data/financials --out output --beliefs my_beliefs.json
```

## Market-implied

The market's own belief beside yours. `python/fetch_options.py <ticker>... [--as-of D]`
writes the full end-of-day option chain for a date, every expiry and strike unfiltered,
with the underlying's close, to `data/options/<date>/<TICKER>.json` (gitignored, like all
fetched data). A run with `--options data/options` then reads, on every Ok record, the
name's chain on the latest snapshot date at or before the valuation date and records
`market_implied`:

- the expiry: the longest at least 365 days out with at least eight out-of-the-money
  strikes quoted with a positive bid on each side of spot, and `horizon_years`;
- the smile: implied volatilities from out-of-the-money mids whose spread is no wider
  than the mid, an SVI fit per expiry under the no-arbitrage constraints (Lee's wing
  bound and no butterfly arbitrage), checked again after the fit; on failure the block is
  null with `smile fit failed: <why>`. The put-call implied-vol gap at the forward is
  recorded: US single-stock options are American and the inversion is European, so a
  long-dated put's early-exercise premium shows there as a positive gap, a diagnostic that
  is never corrected;
- `price_quantiles`: the 5/25/50/75/95 quantiles of the price at expiry, by
  Breeden-Litzenberger on the fitted smile in closed form;
- `p_below_anchor_path`: the risk-neutral probability that the price at expiry is below
  fair value grown at the required return used, `V (1 + ke)^T`. It sits directly beside
  `probability_overpaid`, and the summary compares the two medians;
- `implied_growth_quantiles`: each price quantile discounted at `ke` to today and
  inverted through the implied-terminal-growth solver, the market's belief on the growth
  axis, labelled `approximate` with the reason: a horizon of one to two years stands in
  for the long run. Null with the reason on the residual-income paths.

Through time, `uv run python/build_panel.py --options data/options` values every panel
date with the store under the no-lookahead rule (`--options-max-age 7`: the latest
snapshot on or before the date and no older than seven days, else the reason), using that
date's own fair value and required return for the anchor path; the panel rows gain the
block's numbers beside `probability_overpaid` on the date, `output/pit/market_summary.txt`
holds one descriptive line per date (no statistic), and
`uv run python/plot_market_through_time.py` draws the two medians over the dates that
have a block.

Every field is risk-neutral: it embeds the market's risk pricing and is not a forecast.
Without `--options` a record carries neither `market_implied` nor `market_implied_reason`;
with it, a name without a chain says `no options data`, a chain without a usable expiry
says so. Nothing here feeds the headline, the beliefs or the frontier.

```sh
uv run python/theta_terminal.py start
uv run python/fetch_options.py AAPL MSFT PG                  # today's chain, or --as-of 2026-09-17
dune exec atemoya -- data/financials --out output --options data/options
```

## Hedging

`python/hedge.py <holdings.json>` hedges one holding at a time from the options store,
with quotes and a declared constraint, never a model price or a hidden weighting. The
holdings file is untracked (`data/holdings/` is ignored) and each entry is a ticker, a
share count, a horizon in days and exactly one constraint: `{"max_cost_pct": x}`,
`{"min_floor_pct": y}` or `{"floor": "anchor"}`; an optional `as_of` picks the store
date, the latest snapshot at or before it.

Four structures, per share held and evaluated held to expiry: a protective put, a collar
(long put, short call above it), a put spread (long put, short lower put) and a covered
call. For every expiry at least the horizon out and within 120 days beyond it and every
quoted strike with a positive bid, the cost is the ask for what is bought and the bid for
what is sold, the mid reported beside it. A structure whose leg has no quote is not a
candidate; a leg whose mid sits more than five vol points off the fitted smile is a stale
or junk quote and is excluded. The three numbers on every candidate:

- `cost_pct`: the net premium over today's value, negative for a credit;
- `floor_pct`: the worst outcome at expiry, premium included, over today's value. A put
  spread's worst is at zero, since the protection ends at the short strike; a covered
  call's floor is the premium alone;
- `cap_pct`: the best outcome where a short call binds, null for a put or put spread.

The frontier is the exact Pareto set over lower cost, higher floor and higher or null
cap, no weights and no optimiser; the whole candidate table sits beside it. The
constraint selects: `max_cost_pct` gives the frontier points at or below it, highest
floor first; `min_floor_pct` the points at or above it, cheapest first; `floor: "anchor"`
takes the name's fair value from the latest run as the floor and picks the cheapest point
at or above it, and says "the anchor is above the price; nothing above it to insure" when
the fair value exceeds spot. The first eligible point is the selection; without a
constraint nothing is recommended. A cap on the upside is something the holder declares,
never something a rule chooses for them: an entry may carry `min_cap_pct`, the lowest
best outcome at expiry the holder accepts, and without it only protective puts and put
spreads are selectable, collars and covered calls staying in the table and the frontier;
the output states which set was selectable. One risk-neutral readout goes with the selection: the
market's probability, from the same smile, that the price at expiry is at or below the
floor's strike. Position Greeks (holding plus structure) come from the smile at the quoted
strikes.

Scope limits, on every output: short calls carry assignment risk before expiry (American
exercise), stated and not modelled; the structure is evaluated held to expiry; dividends
inside the horizon are not modelled; commissions beyond the bid-ask are not included; the
floor probability embeds the market's risk pricing and is not a forecast. Output goes to
`output/hedge/<holdings-file-name>/<TICKER>.json` and `.png` (cost against floor, every
candidate faint, the frontier as a line with capped points coloured by cap, the selection
starred). Two runs are byte-identical; nothing is sampled.

```sh
uv run python/hedge.py data/holdings/mine.json      # {"holdings": [{"ticker": "AAPL", "shares": 100, "horizon_days": 180, "constraint": {"max_cost_pct": 0.03}}]}
```

A book is hedged with one index product the same way, sized by declared betas.
`python/hedge_book.py <book.json>` takes a file with `index`, `horizon_days`, one
`constraint`, optional `min_cap_pct`, and holdings that each declare `beta`, `beta_why`
and `beta_as_of`; a holding without a declared beta is listed and excluded, and an index
not in the store is refused with the fetch command named. `python/beta.py <book.json>`
writes `betas.txt`, a two-year weekly regression beta to the index beside each
declaration with its standard error and R-squared: evidence for the holder, which the
hedge never reads. Each holding's index-equivalent exposure is shares times spot times
beta, the book's is the sum, and the contracts are the nearest whole number to the
exposure over the index spot times the multiplier, the residual reported and never
covered by a fraction. The structures, quotes, Pareto set, constraint and risk-neutral
floor probability are the single-name tool's on the index's chain; the book's floor and
cap come from the index payoff on the declared betas, the book floored at zero, so the
worst outcome sits at a strike or where the book reaches zero, and a cap is hard only
when the short call covers the exposure. Exact for the declared betas, and wrong exactly
when the holdings' co-movement with the index breaks. Output: `book.json`, `book.png`
and `betas.txt` under `output/hedge/<file>/`.

```sh
uv run python/beta.py data/holdings/book.json
uv run python/hedge_book.py data/holdings/book.json
```

## FX hedging

A holder of a name whose value moves with a foreign currency sells that currency forward
for the horizon. `python/hedge_fx.py <holdings.json>` does it with CME FX futures only,
standard or micro, and the reason is stated here: forwards are over the counter and not
something a clone can assume its account can trade; options on FX futures are listed and
tradable, but this tool prices structures from quotes and no source it has carries CME
options quotes, so they enter when a quote source is declared, as the equity terminal was,
and not before. Pricing them with Black-76 at an assumed volatility is exactly what the
hedging tools refuse.

Exposure is declared per holding, no default: `exposure_currency`, `exposure_fraction` in
[0, 1] of the holding's value that moves with the currency, `exposure_why` and
`exposure_as_of`; the file's `horizon_days` and `hedge_fraction` (of the exposure to hedge,
written even at 1.0). A holding without a declared exposure is listed and excluded.
`reference/fx_futures.json` is a dated, hand-transcribed table of the contracts per
currency (EUR, JPY, GBP, CHF, CAD, AUD, MXN, BRL): product, size, tick, the exchange's
published maintenance margin and its speculative initial margin, loaded strictly; a
currency not in it is refused by name, a proxy being a declaration for a later brief.
The fair forward is covered interest parity on the fetched curves at the tenor nearest
the horizon (`F = S (1 + r_usd T) / (1 + r_ccy T)`, tenors recorded), the carry is
`(F - S) / S`, positive when the hedged currency yields less than the dollar, and a
missing curve fails the holding with the refresher named. The vendor's front futures
quote is fetched and compared with the parity forward, the residual recorded and flagged
beyond 0.5%, never used as the input (`--no-vendor` skips it offline). Contracts are
whole: the standard-plus-micro combination leaving the smallest residual, the count and
the residual reported, the margin tied up as a percent of the holding's value. The output
is a deterministic payoff grid, currency moves from -20% to +20% in 1% steps, the
holding's dollar value at the horizon unhedged and hedged, drawn as two lines with the
residual's slope visible, under `output/hedge/<file>/fx.json` and `fx.png`. Scope limits
on every output: expiry and rolling, margin calls before expiry, and the declared
fraction are not modelled or estimated.

```sh
uv run python/hedge_fx.py data/holdings/fx.json
```

## Frontier

`python/frontier.py <candidates.json>` is Smith and Smith's endgame: for an untracked
candidate set, the distribution of the portfolio's value surplus (the margin of safety)
under the declared beliefs, and the long-only weightings that minimise downside risk at
each level of expected surplus. It needs a batch run whose records carry a belief and its
41-point surplus curve, the correlation section of `reference/beliefs.json` (one declared
common-factor number, per-pair overrides optional, never estimated), and the draws and
seed in `reference/params.json`. Each name's marginal is its truncated normal; the joint is
a Gaussian copula. Risk is downside-only: the probability of a negative surplus, LPM1 at
zero and CVaR at 95%; the standard deviation is reported beside them and never optimised.
The frontier minimises CVaR95 at each target mean by the Rockafellar and Uryasev linear
programme; the minimum-p_negative, minimum-CVaR and minimum-std portfolios are reported
side by side, with the current weights when given. Names that are Failed, absent or
without a belief are listed with the reason and excluded; the universe is never the
candidate set. Output goes to `output/frontier/<candidates-file-name>/` as a JSON, a text
summary and a two-panel plot, expected surplus against p_negative and against CVaR95.
When every candidate's p_negative is one, the summary says the frontier is not
informative at these prices and the output is still written.

```sh
uv run python/frontier.py data/candidates/mine.json      # {"names": [{"ticker": "O", "weight": 0.5}, ...]}
```

## Required return

The cost of equity is CAPM by default: the risk-free rate plus beta times the equity risk
premium, plus a country premium on the cross-currency path, blended into a WACC on the DCF
paths and used directly on the residual-income and REIT paths. The sensitivity block shows
it binds on every DCF name, and it is the one input that is a chain of parameters rather
than an observation or a declaration. A declared required return sits beside it, exactly
like a belief. The rules of use:

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

```sh
dune exec atemoya -- data/financials --out output --required-returns my_required_returns.json
```
