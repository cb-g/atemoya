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

## The earnings gate

An expiry picked without knowing whether a results release sits inside it is picked blind, and
a spread or a hedge held across one is a different instrument (68). Every record carries an
`earnings` block, Ok or Failed: it never fails a record, adds no `Failed` string, and nothing
in the valuation reads it.

**The calendar, filed and keyless.** Every 8-K carrying item 2.02, Results of Operations and
Financial Condition, from SEC's own submissions index, over the last five years. The form gate
is not optional: `items` is an N.NN-shaped comma-joined string on other forms too, and form
ABS-15G numbers its own items 1.01 to 2.03, so a shape-only match would eventually read an
asset-backed due-diligence item as an earnings release. An 8-K/A is left out, because it
restates a release the original already dated. `filings.recent` is a year or a thousand
filings, whichever is more, so the older pages are read as brief 67 reads them, or the five
biggest banks would give one year of cadence instead of five.

A filer with no item 2.02 at all falls back to the vendor's dates, and that case is wider than
a name without a filer: a foreign private issuer files 6-K and a trust files neither. The
fallback is therefore keyed on the absence of a filed release rather than the absence of a
CIK, and `past_source_why` says which silence it was.

**The next date** is the vendor's where it carries one — its calendar first, its dated table
second, and the record says which — and a projection from the filed cadence otherwise, the
last release plus the median interval of the last eight, recorded as `filed cadence,
projected`. Never both silently: a projection presented as a filed or vendor date would be a
forecast wearing a filing's clothes. `cadence_days` is on the block either way, because it is
the reader's check that the cadence is quarterly — a filer that reports operating statistics
under item 2.02 as well as results has twice the releases and half the interval, and the
number says so.

**The realised move** per release is close to close across it, and the benchmark's over the
same two dates, with the median absolute excess over the last eight. Which two closes bracket
a release is read, not assumed: the index carries the acceptance time, and a release after the
close on a day moves that day to the next while one before the open moves the previous day to
that one. The vendor's closes are already split-adjusted, so their ratio is the corrected move
and applying a split factor here would put the jump back in.

**The implied event move** is the later of the two bracketing expiries' total variance less
the earlier's, and its square root. SVI parameterises *total* implied variance, so `w(0)` at
the forward is exactly "implied volatility squared times years" with no round trip through a
volatility, and both legs take the same put-call-parity forward — the event variance is a
difference of two close numbers, and mixing conventions between them is noise exactly where
the answer is. An expiry on the release date is the later leg, since a release is dated by its
filing day and an option expiring that day is still exposed to one made before the open.
`null` with the reason where no expiry precedes the date, where a smile at one of them will
not fit, or where the subtraction comes out negative — a term structure with no event premium,
which is a reading and not a gap.

**The mark.** The `market_implied` expiry carries `spans_earnings` and the implied move beside
it. The expiry is not reselected and no number in the readout moves; a reader is told whether
the horizon they are being shown carries the release.

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
