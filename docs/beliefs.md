# Beliefs

The declared belief on long-run growth, and the probability of overpaying under it,
follow Smith and Smith's value-surplus idea read as written: the investor states their
own uncertainty about long-run growth; the output is the distribution of the value
surplus, which is the margin of safety here; the risk measure is the probability that it
is negative.

Nothing is sampled: fair value is monotone in terminal growth below the discount rate, so
the probability is the belief's CDF at the implied long-run growth, in closed form.

## What ships, and what does not

The tracked `reference/beliefs.json` carries one default per entity class and no belief on
any name. The defaults are deliberately plain: long-run growth near the economy's, or a
long-run return on equity near the cost of equity, each with a wide band. They exist so a
fresh clone produces a complete record, not because anyone holds them about a particular
company. A record built on one says so in `belief.source`; a `probability_overpaid` under a
class default is a statement about that default and not about the reader's view. Whoever
runs a clone should read the six and either keep them knowingly or pass their own with
`--beliefs`, kept outside the repository.

## The outside view beside it

A belief is the inside view: what you hold about this company. `base_rate` on a record is
the outside view, and it is not a belief: how often companies of the same starting size
actually grew their revenue, over five years, as fast as the record's own growth path
assumes (`headline_growth`, `headline_share`) and as fast as the price needs
(`implied_growth`, `implied_share`, from `implied_g0` decaying as the model's path does).
`uv run python/base_rates.py` builds the table from SEC's frames, one request per revenue
element and calendar year since 2009, about ten thousand companies, into
`data/reference/base_rates.json`; without it the record says so. A share is held to between
one and ninety-nine per cent, the table's resolution.

Read it with its limits, which ride on the block. The record's growth is of free cash flow
and the class's is of revenue. The needed growth is solved on the record's own base cash
flow, so where that base is held down by a build-out or a trough the needed growth is
overstated. The class is survivors only, with the count of those that did not report at the
end beside it. The windows overlap and all lie in the years since 2009. Nothing reads the
block: it informs the why of a belief, as rule 1 below says history may, and never sets one.

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
   class as offsets around an anchor and, beside them under `names`, per-name absolute
   beliefs that override the default. A further file of per-name beliefs may be given as
   `--beliefs`; it overrides the tracked ones.

   On the DCF-shaped classes the anchor is the country's settled terminal growth — which
   since the terminal-growth table got a source is the IMF World Economic Outlook's last
   projected year of nominal GDP growth in the country's own currency, so a belief's
   centre moves when the vintage does.

   **Banks and insurers have a belief too, on a different parameter.** Their model has no
   terminal growth, so the belief sits on the long-run return on equity the ROE path
   reverts to, and the anchor is the name's own cost of equity. A zero centre is therefore
   the statement that the long run grants no franchise value, which is exactly what that
   model already assumed; only the width and the ceiling say a franchise might hold above
   its cost of equity. The record names which parameter it is in `belief_parameter`, and
   the fourth readout is `implied_roe_target` rather than `implied_terminal_growth`.

   **The ceilings are eight points for a bank and five for an insurer** (63). The first
   drafts were three and two, which said a large bank cannot sustain more than three points
   over its cost of equity in the long run; that is not what anyone who follows banks
   believes, since franchise banks have held five to eight points over for decades. The
   revision is made on that argument and on nothing the readout produces: a belief is
   revised because its statement about the world was wrong, never because of the
   probability it assigns to a price. The centre, the width and the floor are unchanged.

## Running with a further beliefs file

```sh
dune exec atemoya -- data/financials --out output --beliefs my_beliefs.json
```
