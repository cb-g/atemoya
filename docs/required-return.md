# Required return

The cost of equity is CAPM by default: the risk-free rate plus beta times the equity risk
premium, plus a country premium on the cross-currency path, blended into a WACC on the DCF
paths and used directly on the residual-income and REIT paths. The sensitivity block shows
it binds on every DCF name, and it is the one input that is a chain of parameters rather
than an observation or a declaration. A declared required return sits beside it, exactly
like a belief.

## Rules of use

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

## Running with a further file

```sh
dune exec atemoya -- data/financials --out output --required-returns my_required_returns.json
```
