# Market-implied

The market's own belief beside yours. `python/fetch_options.py <ticker>... [--as-of D]`
writes the full end-of-day option chain for a date, every expiry and strike unfiltered,
with the underlying's close, to `data/options/<date>/<TICKER>.json` (gitignored, like all
fetched data). A run with `--options data/options` then reads, on every Ok record, the
name's chain on the latest snapshot date at or before the valuation date and records
`market_implied`.

## The block

- the expiry: the longest at least 365 days out with at least eight out-of-the-money
  strikes quoted with a positive bid on each side of spot, and `horizon_years`;
- the smile: implied volatilities from out-of-the-money mids whose spread is no wider
  than the mid, an SVI fit per expiry under the no-arbitrage constraints (Lee's wing
  bound and no butterfly arbitrage), checked again after the fit; on failure the block is
  null with `smile fit failed: <why>`. The put-call implied-vol gap at the forward is
  recorded: US single-stock options are American and the inversion is European, so a
  long-dated put's early-exercise premium shows there as a positive gap, a diagnostic that
  is never corrected;
- `price_quantiles`: the 5/25/50/75/95 quantiles of the price at expiry, by
  Breeden-Litzenberger on the fitted smile in closed form;
- `p_below_anchor_path`: the risk-neutral probability that the price at expiry is below
  fair value grown at the required return used, `V (1 + ke)^T`. It sits directly beside
  `probability_overpaid`, and the summary compares the two medians;
- `implied_growth_quantiles`: each price quantile discounted at `ke` to today and
  inverted through the implied-terminal-growth solver, the market's belief on the growth
  axis, labelled `approximate` with the reason: a horizon of one to two years stands in
  for the long run. Null with the reason on the residual-income paths.

## Through time

`uv run python/build_panel.py --options data/options` values every panel date with the
store under the no-lookahead rule (`--options-max-age 7`: the latest snapshot on or before
the date and no older than seven days, else the reason), using that date's own fair value
and required return for the anchor path. The panel rows gain the block's numbers beside
`probability_overpaid` on the date, `output/pit/market_summary.txt` holds one descriptive
line per date (no statistic), and `uv run python/plot_market_through_time.py` draws the
two medians over the dates that have a block.

## What it is not

Every field is risk-neutral: it embeds the market's risk pricing and is not a forecast.
Without `--options` a record carries neither `market_implied` nor `market_implied_reason`;
with it, a name without a chain says `no options data`, a chain without a usable expiry
says so. Nothing here feeds the headline, the beliefs or the frontier.

## The terminal and the store

Options data comes from ThetaData through its terminal, run from this repository with your
own subscription. Download `ThetaTerminalv3.jar` from ThetaData into `tools/thetaterminal/`
(gitignored entirely: the jar, its config, its logs and the momentary creds file live
there); put your ThetaData login in `.env` as `THETADATA_EMAIL` and `THETADATA_PASSWORD`;
then `uv run python/theta_terminal.py start` (then `status`, `stop`). The script reads the
two variables from the environment, writes a creds file with mode 600, launches the jar
with `--creds-file`, and removes the file once the terminal's port answers. It never
prints a credential.

```sh
uv run python/theta_terminal.py start
uv run python/fetch_options.py AAPL MSFT PG                  # today's chain, or --as-of 2026-09-17
dune exec atemoya -- data/financials --out output --options data/options
```
