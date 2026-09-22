# Frontier

`python/frontier.py <candidates.json>` is Smith and Smith's endgame: for an untracked
candidate set, the distribution of the portfolio's value surplus (the margin of safety)
under the declared beliefs, and the long-only weightings that minimise downside risk at
each level of expected surplus.

## What it needs

A batch run whose records carry a belief and its 41-point surplus curve, the correlation
section of `reference/beliefs.json` (one declared common-factor number, per-pair overrides
optional, never estimated), and the draws and seed in `reference/params.json`.

## How it measures risk

Each name's marginal is its truncated normal; the joint is a Gaussian copula. Risk is
downside-only: the probability of a negative surplus, LPM1 at zero and CVaR at 95%; the
standard deviation is reported beside them and never optimised. The frontier minimises
CVaR95 at each target mean by the Rockafellar and Uryasev linear programme; the
minimum-p_negative, minimum-CVaR and minimum-std portfolios are reported side by side,
with the current weights when given.

## What it excludes and writes

Names that are Failed, absent or without a belief are listed with the reason and
excluded; the universe is never the candidate set. Output goes to
`output/frontier/<candidates-file-name>/` as a JSON, a text summary and a two-panel plot,
expected surplus against p_negative and against CVaR95. When every candidate's p_negative
is one, the summary says the frontier is not informative at these prices and the output
is still written.

```sh
uv run python/frontier.py data/candidates/mine.json      # {"names": [{"ticker": "O", "weight": 0.5}, ...]}
```
