# atemoya

Fundamentals-based fair-value anchoring for equities: Python collects vendor data into a
schema-checked boundary, OCaml values it.

## Setup

Requires git, [opam](https://opam.ocaml.org) 2.1+, [uv](https://docs.astral.sh/uv/), and
optionally [direnv](https://direnv.net).

```sh
git clone <this repo> && cd atemoya_new_paradigm

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

## Run

```sh
uv run python/fetch.py AAPL MSFT SAP        # statements from SEC XBRL (10-K or 20-F filers, us-gaap or ifrs-full) or yfinance -> data/financials/<TICKER>.json
dune exec atemoya -- data/financials/*.json # one valuation record per line on stdout
uv run python/refresh_rates.py --all        # sovereign curves per reference/rate_sources.json
uv run python/refresh_fx.py --all           # FX via FRED H.10 -> reference/fx_rates.json

uv run python/fetch_all.py                  # every ticker in reference/universe.json -> data/snapshots/<date>/, data/financials -> the latest
dune exec atemoya -- data/financials --out output   # -> output/valuations.jsonl, summary.txt, provider_diff.txt, and the same three under output/runs/<date>/ (never overwritten)
dune exec atemoya -- data/financials --out output --baseline previous/valuations.jsonl   # plus this run against that one
dune exec atemoya -- data/snapshots/<new> --out output --baseline previous/valuations.jsonl --baseline-snapshot data/snapshots/<old>   # plus stability_<old>_<new>.txt
uv run python/fetch_all.py --as-of 2025-06-30   # point-in-time: data/pit/2025-06-30/ from what was known on that date, with its reference/
dune exec atemoya -- data/pit/2025-06-30 --reference data/pit/2025-06-30/reference --today 2025-06-30 --out output/pit/2025-06-30
uv run python/fetch_all.py --universe data/universe.private.json --snapshots data/snapshots-private   # a second universe file, same format, never tracked
dune exec atemoya -- data/snapshots-private/<date> --universe data/universe.private.json --out output/private
uv run python/build_panel.py                    # every quarter-end 2022-03-31 .. 2026-06-30 -> output/pit/panel.jsonl, panel_summary.txt
```

`dune exec atemoya` reads parameters from `reference/` (`--reference DIR` to override) and
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
