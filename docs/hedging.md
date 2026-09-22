# Hedging

Four tools hang off the options store and the latest run, none of them touching a
valuation record: a single-name hedge, a book hedged with one index product, an FX hedge
with futures, and the expression of a declared view, with a fill model beside it. Each
prices from quotes, selects only under a declared constraint, and states its scope limits
on every output.

## Single-name hedging

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
or junk quote and is excluded.

The three numbers on every candidate:

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
constraint nothing is recommended.

A cap on the upside is something the holder declares, never something a rule chooses for
them: an entry may carry `min_cap_pct`, the lowest best outcome at expiry the holder
accepts, and without it only protective puts and put spreads are selectable, collars and
covered calls staying in the table and the frontier; the output states which set was
selectable. One risk-neutral readout goes with the selection: the market's probability,
from the same smile, that the price at expiry is at or below the floor's strike. Position
Greeks (holding plus structure) come from the smile at the quoted strikes.

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

## A book, with one index product

A book is hedged with one index product the same way, sized by declared betas.
`python/hedge_book.py <book.json>` takes a file with `index`, `horizon_days`, one
`constraint`, optional `min_cap_pct`, and holdings that each declare `beta`, `beta_why`
and `beta_as_of`; a holding without a declared beta is listed and excluded, and an index
not in the store is refused with the fetch command named. `python/beta.py <book.json>`
writes `betas.txt`, a two-year weekly regression beta to the index beside each
declaration with its standard error and R-squared: evidence for the holder, which the
hedge never reads.

Each holding's index-equivalent exposure is shares times spot times beta, the book's is
the sum, and the contracts are the nearest whole number to the exposure over the index
spot times the multiplier, the residual reported and never covered by a fraction. The
structures, quotes, Pareto set, constraint and risk-neutral floor probability are the
single-name tool's on the index's chain;

the book's floor and cap come from the index payoff on the declared betas, the book
floored at zero, so the worst outcome sits at a strike or where the book reaches zero,
and a cap is hard only when the short call covers the exposure. Exact for the declared
betas, and wrong exactly when the holdings' co-movement with the index breaks. Output:
`book.json`, `book.png` and `betas.txt` under `output/hedge/<file>/`.

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

The spot the hedge trades against is the ECB's daily reference rate, a dollar cross of two
ECB rates, fetched keyless by `python/refresh_fx.py --daily` into
`data/reference/fx_spot_daily.json`; a missing file or currency fails the holding naming
the refresher, and the weekly H.10 rate the valuation uses is recorded beside it with
both dates (the valuation path never reads the daily file, its weekly series and age gate
being immaterial there).

The fair forward is covered interest parity on the fetched curves at the tenor nearest
the horizon (`F = S (1 + r_usd T) / (1 + r_ccy T)`, tenors recorded), the carry is
`(F - S) / S`, positive when the hedged currency yields less than the dollar, and a
missing curve fails the holding with the refresher named. The vendor's front futures
quote is fetched and compared with the parity forward, the residual recorded and flagged
beyond 0.5%, never used as the input (`--no-vendor` skips it offline).

Contracts are whole: the standard-plus-micro combination leaving the smallest residual,
the count and the residual reported, the margin tied up as a percent of the holding's
value. The table's margins are the exchange's published minimums and brokers charge more,
so a holding may declare its broker's initial margin per contract with `margin_why`
naming the broker and the date; when it does, that figure is used and the exchange
minimum reported beside it, and the output states which was used on every holding.

The output is a deterministic payoff grid, currency moves from -20% to +20% in 1% steps,
the holding's dollar value at the horizon unhedged and hedged, drawn as two lines with
the residual's slope visible, under `output/hedge/<file>/fx.json` and `fx.png`. Scope
limits on every output: expiry and rolling, margin calls before expiry, and the declared
fraction are not modelled or estimated.

```sh
uv run python/hedge_fx.py data/holdings/fx.json
```

## Expressing a view

`python/express.py <views.json>` is the hedging machinery pointed the other way. It is
not a signal, a forecast or a recommendation: the holder declares a view, six fields per
entry, `ticker`, `direction` (`up` or `down`), `level`, `horizon_days`, `probability`
(the holder's, that the price is at or beyond the level in the direction at the horizon),
`why` and `as_of`, with `slippage_per_leg` written even at 0.00 and optional
`max_risk_usd` and `as_of_snapshot`; a view without a probability or a why is refused,
since a direction alone is not something the tool can price, and the tool never supplies,
infers or adjusts a view. Views live in untracked files.

Given the view, every vertical on its side is priced from the store's quotes for each
expiry at or beyond the horizon and within 60 days past it: bull call and bull put
spreads for `up`, bear put and bear call spreads for `down`, over every pair of quoted
strikes, ask for what is bought and bid for what is sold plus slippage, with max profit,
max loss (the capital at risk), breakeven and width.

Three probabilities sit on each candidate and stay distinct. `p_market` is the risk-
neutral probability of the max-profit region from the fitted density on the candidate's
expiry, with the breakeven and max-loss regions beside it. `p_view` is the declared
probability, which applies at the level and nowhere else: only to candidates whose max-
profit region is exactly the declared one, the short strike at the quoted strike nearest
the level (ties to the near side) and the long strike where the spread's definition puts
it, any width, debit or credit alike;

every other candidate carries null with the reason and is listed, not ranked, since the
tool neither interpolates nor extrapolates the view. The ranking therefore answers two
questions and only two, how wide and debit or credit, the level itself being the
holder's. `ev_per_dollar_at_risk` is the expected value per dollar at risk under
`p_view`, the number the ranking uses.

The top ten are reported with `disagreement = p_view - p_market`, which is where the
holder is being paid for the view or paying for it, and a candidate the market prices
more strongly than the holder is shown, not hidden. One diagnostic per view says whether
the view is also a volatility bet: the nearest expiry's at-the-money implied volatility
against the realised volatility over the horizon's length and against the name's own ATM
implied volatility over the last 250 snapshot dates, as a percentile.

Output: `output/express/<file>/<TICKER>.json` and `.png` (max loss against EV per dollar,
points coloured by `p_market`, credit and debit by marker, the top one starred). Scope
limits on every output: held to expiry, assignment before expiry not modelled, the
holder's probability is theirs and the market's is risk-neutral. A fill model is not here
by default; slippage is its placeholder.

```sh
uv run python/express.py data/views/mine.json
```

## Fills

The slippage field in the view-expression tool is a placeholder for this: where option
trades actually print relative to the quoted spread, per name, so the tool can rank on
expected fills rather than on the ask and the bid. It is a data product with no model in
it. `python/fetch_tape.py <ticker>... --from D1 --to D2` stores every print for every
contract that traded, with the quote at the print, under `data/tape/<date>/<TICKER>.json`
through the terminal, paced; the endpoint needs a ThetaData subscription above the free
tier, and a refusal is reported as the vendor words it.

`python/fill_model.py <ticker>...` turns the tape into a table of empirical quantiles and
nothing fitted: per print `fill_position = (price - bid) / (ask - bid)`, 0 the bid, 1 the
ask, 0.5 the mid, clamped to [-0.5, 1.5] with the clamps counted and prints at a locked or
crossed quote excluded and counted; the 10/25/50/75/90 quantiles per (moneyness third by
|delta| from the store's chain, spread width in ticks, half-hour of day), collapsed per
(moneyness, width), per moneyness and overall, each cell with its count, to
`data/fill_model/<name>.json` with a summary under `output/fill_model/`.

Buys and sells are not distinguishable from the tape, so the table is symmetric by
construction; a holder's own fills, recorded in an untracked `data/fills/<file>.json`, are
the asymmetric truth, and `python/fills_vs_model.py` reports each fill's position against
the model's quantiles. `python/express.py --fill-model data/fill_model` then prices each
leg at its cell's median fill, a bought leg at bid + q50 x spread and a sold leg at
bid + (1 - q50) x spread, recording the cell and the quantile; the flat slippage stays the
fallback and the two are never combined on one leg. The batch never reads the tape.

```sh
uv run python/fetch_tape.py AAPL NVDA --from 2026-06-25 --to 2026-09-17
uv run python/fill_model.py AAPL NVDA
uv run python/express.py data/views/mine.json --fill-model data/fill_model
uv run python/fills_vs_model.py data/fills/mine.json
```
