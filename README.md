# atemoya

A disciplined description of what a listed company is worth, one name at a time, with its
limits written on the record.

Give it a ticker and a declared class, and it fetches the company's filed statements, the
sovereign curve and the FX it needs, values the company with the one model its class
admits, and writes a record: a fair value, what the price needs to be true, the inputs
with their provenance, and a set of readouts beside the anchor. Where it cannot value a
name honestly it says so, with the reason, and refuses. A wrong fair value is worse than
none, because it gets acted on.

Python collects the data into a schema-checked boundary; OCaml does the valuing. Nothing
fetched is ever committed, every number carries its basis, and nothing the models need is
estimated by the tool: the class, the belief, a required return, a beta, a view are all
declared by a person, dated, with a why.

## What a record says

One line of JSON per name, `Ok` with a fair value or `Failed` with a reason.

- **The anchor.** A fair value from the model the declared class admits: a free-cash-flow
  DCF for an operating company, a mid-cycle DCF for a cyclical, a residual-income model for
  a bank or an insurer, an FFO-covered dividend for a REIT. A class without an admissible
  model is refused with the right lens named, so the reader learns what the measurement
  should have been.
- **What the price needs.** The growth the market price implies, how long it must last,
  and how often companies of that size have grown that fast, from filed history.
- **A belief beside the anchor, never inside it.** A declared belief on growth gives a
  probability that the price overpays; the record names the belief's source. A fresh
  clone ships six textbook class defaults and no view on any company.
- **The market's own belief.** From the options store, the risk-neutral price distribution
  and an options-implied expected return, read as the market's risk pricing and not as a
  forecast.
- **Readouts.** Quality signals from the statements alone, a growth shadow, price stretch
  against the name's own history, insider transactions with each trader told routine from
  opportunistic by their own timing, the Street's consensus and the name's surprise history.
- **Provenance.** The provider of every figure, the definition and the tags summed, and
  the version of the code and of every declaration it read.

`docs/flow.md` draws every stage from ticker to record and lists every `Failed` reason
against the stage that emits it; a test holds the code to that list.

## The universe

247 names across fifteen declared classes, most of them US filers read from SEC XBRL, with
Swiss, European, Asian and other lines read from filed reports where a filed source
exists and from the vendor's statements where it does not, that limit stated on the entry.
Every entry is a declaration: the class, confirmed by a person, the scope limits the model
should be read under, and nothing fetched. `reference/universe.json` is the list.

## What the studies found

The tool tests its own outputs, and the results are kept whether or not they flatter it:

- **The anchor does not sort returns among large companies.** On a point-in-time panel of
  the tool's own records, and on the five hundred largest US filers each June since 2013
  chosen by a rule, the cheapest fifth by margin of safety did no better than the dearest
  over the next twelve months, and no better than the plain earnings yield. The same
  holds after the market's part is taken out by regression.
- **Cheapness worked where the names were smaller.** On every SEC filer with a ticker,
  about three thousand, earnings yield sorted returns from 2022 while among the largest it
  did not.
- **Beta was paid.** Sorted on a one-year beta, the largest US companies earned the
  market's premium per unit of beta over 2013–2025, so the tool's own data give no ground
  for taking beta out of its cost of equity.
- **The model's level moves with rates.** With a terminal growth that did not come down
  with the risk-free rate, most large companies read as worth double their price in the
  low-rate years; the model now holds terminal growth to the risk-free rate.

`docs/run.md` has each study with its figures and limits; `docs/tried.md` records what was
built, measured and taken out again. The reading that informs changes is cited where it is
used, by the version that was read.

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

### Keys

Every user brings their own keys; `.env` is gitignored and the pre-commit hook refuses it.

- **FRED**, for the U.S. risk-free curve and FX: a free key from
  <https://fred.stlouisfed.org/docs/api/api_key.html> on the `FRED_API_KEY` line of `.env`.
- **SEC EDGAR** requires every request to name its sender: `SEC_EDGAR_IDENTITY` as
  `"<name> <email>"`, quoted, as `.env.example` shows.
- **OpenDART**, for Korean filers' annual reports: a free key on `DART_API_KEY`; without it
  the Korean names stay on the vendor.
- **ThetaData**, for options: its terminal and your own login; `docs/market-implied.md`
  has the steps. European filers' ESEF reports come keyless from filings.xbrl.org.

### First run

Nothing obtained from a data provider is ever committed: rates, FX, filings, snapshots and
runs live under gitignored `data/` and `output/`, and a missing fetched file fails the
record naming the refresher to run.

1. `cp .env.example .env` and set the keys above.
2. `uv run python/refresh_rates.py --all`, `uv run python/refresh_fx.py --all` and
   `uv run python/base_rates.py`.
3. `uv run python/fetch_all.py`.
4. `dune exec atemoya -- data/financials --out output`.

Then read `output/summary.txt`: the counts, every failure by reason, the cross-checks and
the readout medians. **The beliefs a fresh clone runs on are not yours.** Read the six
class defaults in `reference/beliefs.json` before relying on a number built on them, and
declare your own in a file of the same format passed with `--beliefs`; `docs/beliefs.md`
has the rules.

## Tools

Everything below hangs off the records and never moves them.

**The run and its readouts**

| | | |
|---|---|---|
| valuation record | one line per name: fair value or a `Failed` reason, inputs, readouts, floor | `dune exec atemoya -- data/financials --out output` |
| summary | counts, failures by reason, cross-checks, the readout medians | the same run, `output/summary.txt` |
| run diff and stability | this run against a previous one, every moved input classified | `... --baseline prev/valuations.jsonl --baseline-snapshot data/snapshots/<old>` |
| watch | what changed between two runs, one line a name | `uv run python/watch.py` |
| market-implied block | the risk-neutral price distribution and an options-implied expected return beside the anchor | `... --options data/options` |
| quality, growth shadow, base rate, stretch | readouts on every record from the statements and the name's own history | the same run, fields on the record |
| consensus and earnings reactions | the Street's dated bar, each name's surprise history, the move across each release | `uv run python/consensus.py`, `earnings_reactions.py` |
| implied cost of capital | what the price and the Street's two fiscal-year forecasts imply together | `uv run python/implied_cost.py` |

**Acting on a view, with the records as the anchor**

| | | |
|---|---|---|
| frontier | the value-surplus distribution and the downside-minimising weights of a candidate set | `uv run python/frontier.py data/candidates/mine.json` |
| hedge | a single name, a book on an index, or FX exposure, from quotes under a declared constraint | `uv run python/hedge.py`, `hedge_book.py`, `hedge_fx.py` |
| view | every vertical on a declared view's side, ranked by EV per dollar at risk | `uv run python/express.py data/views/mine.json` |
| fills | empirical fill positions from the trade tape, read back into the view tool | `uv run python/fill_model.py AAPL` |

**Testing the tool against what happened next**, descriptive, a declared holdout unread

| | | |
|---|---|---|
| point-in-time panel | every name at every quarter-end from what was known then | `uv run python/build_panel.py --options data/options` |
| anchor and baseline studies | what the records' judgments preceded against SPY, beside plain cheapness | `uv run python/anchor_study.py`, `baseline_study.py` |
| broad panel | every SEC filer with a ticker, each June since 2010: cheapness, quality, a peer-implied gap | `uv run python/broad_panel.py --retry-missing`, `broad_study.py` |
| rule panel | the tool's own DCF on the five hundred largest filers each June since 2013, chosen by rule | `uv run python/rule_panel.py`, `rule_study.py`, `rule_alpha.py`, `rule_beta.py`, `rule_rates.py` |

## Rules

- Everything the models need is declared or filed, never estimated by the tool: the
  class, the belief, the required return, a beta, an exposure, a view.
- Nothing fetched is tracked; every user brings their own keys and refreshes their own
  data.
- A belief is yours: declared, dated, with a why, revised on evidence and never on what a
  number looks like.
- CAPM is never silently replaced; a declared required return sits beside it and the
  record shows both.
- A cap on the upside is declared by the holder, never chosen by a rule.
- Every number carries its basis: the provider, the definition, the tags summed, the
  version of the code and of every declaration.
- A wrong fair value is worse than none: a record is `Ok` or `Failed` with a reason, and
  the market's probabilities are risk-neutral, not forecasts.

## Documentation

- `docs/run.md`: every command, the record, providers and definitions, readouts and diffs,
  point-in-time, and each study with its figures.
- `docs/flow.md`: the stages from ticker to record as one chart, every `Failed` reason
  against its stage, and the changelog.
- `docs/tried.md`: what was built, measured and taken out again, and what would have to be
  different for it to be worth building again.
- `docs/beliefs.md`, `docs/required-return.md`, `docs/market-implied.md`,
  `docs/frontier.md`, `docs/hedging.md`: each tool in full.
