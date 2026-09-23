# Beliefs

The declared belief on long-run growth, and the probability of overpaying under it,
follow Smith and Smith's value-surplus idea read as written: the investor states their
own uncertainty about long-run growth; the output is the distribution of the value
surplus, which is the margin of safety here; the risk measure is the probability that it
is negative.

Nothing is sampled: fair value is monotone in terminal growth below the discount rate, so
the probability is the belief's CDF at the implied long-run growth, in closed form.

## Rules of use, in this order

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
   class as offsets around the country's settled terminal growth — which since the
   terminal-growth table got a source is the IMF World Economic Outlook's last projected
   year of nominal GDP growth in the country's own currency, so a belief's centre moves
   when the vintage does — and, beside them under
   `names`, per-name absolute beliefs that override the default. A further file of
   per-name beliefs may be given as `--beliefs`; it overrides the tracked ones. Banks and
   insurers carry no belief: their model has no terminal growth.

## Running with a further beliefs file

```sh
dune exec atemoya -- data/financials --out output --beliefs my_beliefs.json
```
