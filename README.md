# atemoya

Fundamentals-based fair-value anchoring for equities. Python collects vendor and filed
data into a schema-checked boundary; OCaml values every name with the model its declared
class admits, states what the price needs to be true, and puts a declared belief and the
market's own risk-neutral belief beside the anchor. Tools for hedging, expressing a view
and portfolio choice hang off the records and never move them.

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

The U.S. risk-free curve comes from FRED and needs an API key, free from
<https://fred.stlouisfed.org/docs/api/api_key.html>: copy `.env.example` to `.env` and put
the key on the `FRED_API_KEY` line. SEC XBRL requires every request to name its sender: set
the `SEC_EDGAR_IDENTITY` key to `"<name> <email>"`, quoted, as `.env.example` shows with
its example.com placeholder. `.env` is gitignored and the pre-commit hook refuses it.
Options data needs ThetaData's terminal and your own login: the terminal's jar is fetched
from ThetaData's open download on the first `start`, and `docs/market-implied.md` has the
steps.
European filers' ESEF annual reports come keyless from filings.xbrl.org for the names
whose universe entry declares an `lei`; nothing to set up. Korean filers' annual reports
come from OpenDART, which needs a free key on the `DART_API_KEY` line of the env file;
without it the Korean names stay on the vendor.

## Data policy and first run

Nothing obtained from a data provider is ever committed: rates, FX, filings, snapshots and
runs live under gitignored `data/` and `output/`, and a missing fetched file fails the
record naming the refresher to run. First run, in this order:

1. `cp .env.example .env`.
2. Obtain a FRED API key and set `FRED_API_KEY` in `.env`.
3. Set `SEC_EDGAR_IDENTITY` in `.env` (name and email, sent as the User-Agent).
4. `uv run python/refresh_rates.py --all`, `uv run python/refresh_fx.py --all` and `uv run python/base_rates.py`.
5. `uv run python/fetch_all.py`.
6. `dune exec atemoya -- data/financials --out output`.

**The beliefs a fresh clone runs on are not yours.** `reference/beliefs.json` ships six
class defaults, each a textbook starting point (long-run growth near the economy's, with a
wide band) and none a view on any company; it ships no belief on any name. Every
`probability_overpaid` on a first run comes from one of them, and the record says so in
`belief.source` ("class default for ..."). Read the six before relying on a number built on
them, and either keep them knowingly or declare your own in a file of the same format
passed with `--beliefs`, which overrides them and never needs committing; `docs/beliefs.md`
has the rules.

## What it produces

| output | what it is | command |
|---|---|---|
| valuation record | one line per name: fair value or a `Failed` reason, inputs, readouts, floor | `dune exec atemoya -- data/financials --out output` |
| summary | counts, failures by reason, cross-checks, the readout medians | the same run, `output/summary.txt` |
| run diff and stability | this run against a previous one, every moved input classified | `... --baseline prev/valuations.jsonl --baseline-snapshot data/snapshots/<old>` |
| point-in-time panel | every name at every quarter-end from what was known then, no statistic | `uv run python/build_panel.py --options data/options` |
| market-implied block | the risk-neutral price distribution beside the anchor, from the options store | `... --options data/options` |
| frontier | the value-surplus distribution and the downside-minimising weights of a candidate set | `uv run python/frontier.py data/candidates/mine.json` |
| hedge | a single name, a book on an index, or FX exposure, from quotes under a declared constraint | `uv run python/hedge.py`, `hedge_book.py`, `hedge_fx.py` |
| view | every vertical on a declared view's side, ranked by EV per dollar at risk | `uv run python/express.py data/views/mine.json` |
| fills | empirical fill positions from the trade tape, read back into the view tool | `uv run python/fill_model.py AAPL` |
| stretch | six price measures with own-history percentiles and two counts on every record; the summary lists every name at or above 3 on either side | the same run, `output/summary.txt` |
| quality | Piotroski's nine signals, the accruals ratio and gross profitability from the filed statements alone, on valued and refused records alike | the same run, `quality` on the record |
| growth shadow | what the generic DCF would say on the higher of its two growth estimates, without the switch at zero reinvestment; beside the headline, never replacing it | the same run, `growth_shadow` on the record |
| base rate | how often companies of the same size grew as fast as the record assumes and as the price needs, from filed history | the same run, `base_rate` on the record; `uv run python/base_rates.py` builds the table |
| options-implied expected return | a required return read from option prices alone (Martin and Wagner), beside CAPM and the declared one | `... --options data/options`, `options_expected_return` on the record |
| studies | what the records' own judgments preceded against SPY, and the same rows sorted by plain cheapness; descriptive, a declared holdout unread | `uv run python/anchor_study.py`, `baseline_study.py` |
| broad panel | every SEC filer with a ticker today, each June since 2010, and what cheapness, quality and a peer-implied gap did before 2022 and since; survivors only, descriptive | `uv run python/broad_panel.py --retry-missing`, `broad_study.py` |
| consensus | the Street's dated bar per name and each name's surprise history; never on a record | `uv run python/consensus.py`, daily |

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
  point-in-time.
- `docs/flow.md`: the stages from ticker to record as one chart, and every `Failed`
  reason against its stage.
- `docs/tried.md`: what was built, measured and taken out again, and what would have to be
  different for it to be worth building again.
- `docs/beliefs.md`, `docs/required-return.md`, `docs/market-implied.md`,
  `docs/frontier.md`, `docs/hedging.md`: each tool in full.
