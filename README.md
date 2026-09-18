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
the key after `FRED_API_KEY=`. `.env` is gitignored and the pre-commit hook refuses it;
nothing else needs it.

## Run

```sh
uv run python/fetch.py AAPL MSFT            # yfinance -> data/financials/<TICKER>.json
dune exec atemoya -- data/financials/*.json # one valuation record per line on stdout
uv run python/refresh_rates.py              # U.S. curve from FRED -> reference/risk_free_rates.json
```

`dune exec atemoya` reads parameters from `reference/` (`--reference DIR` to override) and
measures their age against today's UTC date (`--today YYYY-MM-DD` to override). A record
is either `Ok` with a fair value, or `Failed` with a reason; it never carries a guessed
number. `data/` and `output/` are generated and gitignored; versioned inputs live in
`reference/`.

Build, test, type-check:

```sh
dune build        # also regenerates python/boundary.py and python/reference.py from schema/*.atd
dune test
uv run pyright
```
