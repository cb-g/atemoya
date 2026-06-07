# factor_rank — cross-sectional value + quality factor ranking

A **complement** to the per-name absolute models (DCF / justified-P/E). Instead of
"what is this worth vs price," it answers "where does this name sit vs the universe
on **value** and **quality**," as two separate 0–100 percentiles. It needs no
correct fair value — only a consistent ordering — so it sidesteps the assumption
fragility (terminal growth, discount rate, PEG cutoffs) and the heuristics, and
keeps value and quality **unfused** (two composites, not one grade).

It does **not** replace the absolute lens: a cross-sectional rank can't tell you the
whole market is expensive. Use it alongside the DCF.

## Architecture (Python = data/IO, OCaml = computation)
- `python/fetch/fetch_panel.py` — pulls annual statements + market data for a
  universe, FX-converts statement totals to trading basis (so every factor is a
  currency-neutral ratio), sign-normalizes cash-flow lines, and writes a raw panel
  `data/factor_panel_<date>.json`.
- `ocaml/` — the ranking model: `factors.ml` (raw → oriented factor yields),
  `sector_policy.ml` (which factors apply per sector), `rank_engine.ml`
  (winsorize → within-sector percentile → composites), `bin/main.ml`
  (panel JSON → `output/factor_ranks_<date>.csv` + report). Reuses the percentile /
  sector-exclusion ideas already proven in `normalized_multiples` / `relative_valuation`.
- `python/backtest.py` — point-in-time validation (see below).

The **same OCaml binary ranks both the live panel and each backtest rebalance**, so
the backtest validates exactly what ships.

## Factors (yields; higher = better)
**Value:** ebit/EV, ebitda/EV, fcf/EV, sales/EV, earnings yield, book/price,
shareholder yield (dividends + net buybacks). EV-based factors are dropped when
EV ≤ 0; book/price keeps its sign (negative book ranks low).
**Quality:** ROIC, gross-profit/assets (Novy-Marx), gross margin, ROE,
−accruals (Sloan), −leverage (net-debt/EBITDA).

Composite = mean of the *available* sector-allowed factor percentiles, required
≥ half present else **N/A** (never imputed). Percentiles are within-sector, falling
back to the global pool for sectors with < 8 names. Banks/insurers drop EV factors;
REITs drop EV/EBIT + earnings yield (depreciation distortion).

## Run
```bash
# live ranking (sample)
uv run valuation/factor_rank/python/fetch/fetch_panel.py --tickers AAPL,MSFT,JPM,XOM,O
eval $(opam env) && dune exec valuation/factor_rank/ocaml/bin/main.exe
# full universe: drop --tickers (uses pricing/liquidity/data/liquid_tickers.txt)
# backtest (USD-reporting subset)
uv run valuation/factor_rank/python/backtest.py --universe liquid --usd-only
# tests
eval $(opam env) && dune test valuation/factor_rank/ocaml/
```

## Honest limitations
- **Relative, not absolute** — the top value-decile is still pricey in a rich
  market; pair with the DCF/justified-P/E lens.
- **Backtest is diagnostic** — yfinance statements go ~5y deep → ~3–4 non-overlapping
  annual observations; never quote one pooled IC as robust (per-period N is shown).
- **Survivorship bias** — the universe is today's liquid names; trust the
  spread / IC *ordering*, not absolute returns.
- **Level errors** — restatements (as-reported) and current-share-count × historical
  price make the **shareholder-yield** backtest indicative only.
- **Thin for financials/REITs** — quality may be N/A (flagged via `n_quality_used`).
- **Universe is options-liquidity-selected** — fit-for-purpose ("names I'd trade"),
  not a clean market-wide factor universe.
