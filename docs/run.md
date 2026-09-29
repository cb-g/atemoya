# Running the batch

```sh
uv run python/fetch.py AAPL MSFT SAP        # statements from SEC XBRL (10-K or 20-F filers, us-gaap or ifrs-full) or yfinance -> data/financials/<TICKER>.json
dune exec atemoya -- data/financials/*.json # one valuation record per line on stdout
uv run python/refresh_rates.py --all        # sovereign curves per reference/rate_sources.json -> data/reference/risk_free_rates.json (never tracked)
uv run python/refresh_fx.py --all           # FX via FRED H.10 -> data/reference/fx_rates.json (never tracked)

uv run python/fetch_all.py                  # every ticker in reference/universe.json -> data/snapshots/<date>/, data/financials -> the latest
dune exec atemoya -- data/financials --out output   # -> output/valuations.jsonl, summary.txt, provider_diff.txt, the same three under output/runs/<date>/ (never overwritten), and output/maps/<ticker>.json per belief map
uv run python/plot_map.py AAPL                   # -> output/maps/AAPL.png: the belief map's surface, the price contour, the observed starting growth
dune exec atemoya -- data/financials --out output --baseline previous/valuations.jsonl   # plus this run against that one
dune exec atemoya -- data/snapshots/<new> --out output --baseline previous/valuations.jsonl --baseline-snapshot data/snapshots/<old>   # plus stability_<old>_<new>.txt
uv run python/fetch_all.py --as-of 2025-06-30   # point-in-time: data/pit/2025-06-30/ from what was known on that date, with its reference/
dune exec atemoya -- data/pit/2025-06-30 --reference data/pit/2025-06-30/reference --fetched data/pit/2025-06-30/reference --today 2025-06-30 --out output/pit/2025-06-30
dune exec atemoya -- --entity-class OperatingCompany --out output data/financials/NEW.json   # a name not in the universe, declared on the command line
uv run python/build_panel.py                    # every quarter-end 2022-03-31 .. 2026-06-30 -> output/pit/panel.jsonl, panel_summary.txt
```

## Inputs and declarations

`dune exec atemoya` reads declared parameters from `reference/` (`--reference DIR` to
override) and the fetched curves and FX from `data/reference/` (`--fetched DIR`), and
measures their age against today's UTC date (`--today YYYY-MM-DD` to override). Inputs may
be files or directories.

Every ticker needs a declared `entity_class`, from its entry in `reference/universe.json`
or from `--entity-class CLASS` for an ad-hoc run; without one the record fails as
undeclared. `reference/admissibility.json` says which models may run on which class
(today the FCFF DCF on `OperatingCompany` and `HighGrowthSoftware`, the same engine on
through-cycle earning power for `Cyclical`, residual income on `Bank`, residual income on
AOCI-adjusted book from filed statements on `Insurer`, and the FFO-covered dividend on
`Reit`) and what each other class is judged on instead; an inadmissible class fails with
that lens named.

A universe entry may declare the SEC filer to read by `cik` when the ticker map points
elsewhere; the fetch keeps as many annual periods as the class's model needs.
`docs/flow.md` charts every stage from ticker to record. The universe file declares only:
ticker, class, why, what no model can see, and the receipt ratio; it is loaded strictly.
Whether a change moved anything is answered by the run diff against the previous run,
never by a stored expectation.

## The record

A record is either `Ok` with a fair value, or `Failed` with a reason; it never carries a
guessed number. Every record carries a `floor` (present, absent by definition, or not
assessable here, with its basis) that gates nothing, and `model_version` names the code
that produced it (the git short hash, `-dirty` when the tree had uncommitted edits).

A name whose statements and price are in different currencies is converted at one
recorded FX rate (statement totals, never per-share fields) and valued in the trading
currency with that currency's country's rates plus the domicile's country risk premium;
prices quoted in pence or cents are converted to the major unit at the fetch.

## Providers and definitions

Filed statements come in the taxonomy the filer uses (us-gaap or ifrs-full, each a
section of `reference/xbrl_tags.json`) and in the currency the facts carry, which the
record names as its statement currency and which must agree with the vendor's, else the
record fails. SEC's submissions index is read for every CIK-resolved name and its newest
10-K or 20-F recorded; when that filing is newer than the newest annual facts and those
facts are past the filing-age gate, the vendor's statements are used by a decision
written into the record's provider reason (companyfacts lags submissions), never as a
fallback from the gate.

A name with no SEC filer whose universe entry declares an `lei` (73) reads its ESEF
annual reports, the Inline XBRL every issuer on an EU, EEA or UK regulated market must
file, from filings.xbrl.org, keyless: the index is cached for a day and each report's
facts and definition linkbase for ever under `data/esef/`. The facts arrive in the
companyfacts shape and go through the same period reader under the ifrs-full definitions,
one period per report, the vendor cross-checked beside; interim reports are skipped and
named, and where a report tags an extension anchored to one standard concept the
definitions read and no standard line for it, the extension stands in and the note says
so. The LEI is read from the filer's own report cover and declared, never resolved from
the vendor. An issuer the aggregator does not carry (Allianz, on the German register)
stays on the vendor and the reason says so; and where the aggregator's newest report is
past the filing-age gate while the vendor carries a newer annual, the vendor's statements
are used by a decision written into the provider reason, as the companyfacts lag is.

Both providers assemble cash, total debt, the change in working capital and ebit per
`reference/field_definitions.json`, the one definition per field with its reasoning; every
period records the components summed, and a record fetched under another definition fails
rather than being valued under this one. A derived ebit (no operating income filed) runs
the DCF only when the cross-check finds it within threshold of the vendor's operating
income; the refinement policy in that file allows one refinement of a recipe and names
the `Failed` reason for a miss.

## Readouts and diffs

Every `Ok` record also carries two implied readouts solved on its own inputs, headline
untouched: the starting growth (or ROE) the price needs, and the reversion half-life the
observed start would need, and the whole number of explicit years the observed start
would have to persist (an integer scan to 40 years, the risk-free rate held at its
recorded point), the last two only where the start lies above its target; a rule on the
record says which one to read, and every null carries its reason.

With `--baseline`, `provider_diff.txt` opens with every record against the previous run
and lists the inputs behind every moved fair value; with `--baseline-snapshot` as well,
every moved input of every record is classified (price, new filing, restatement, vendor
row, rate or FX, unexplained) in a stability report, so two fetches with nothing having
happened can be shown to agree.

## Share counts and point-in-time

Two share counts live in `reference/field_definitions.json` and are never interchanged: a
flow per share for a historical period (the REIT model's FFO growth) uses that period's
weighted-average diluted count, and a point count (market cap) is effective shares live or
a filed count point-in-time.

A point-in-time record values a name as of a past date from what was known then: facts
filed by the date, the close on the last trading day on or before it (split-corrected),
the share count nearest the filed period carried through the vendor's split record and
divided by the declared receipt ratio, rates and FX observed by then, and the vendor's
live column for the same fiscal period as a cross-check only;

ERP, tax rates, betas and the assumptions are held at the current vintage and every one
whose vintage postdates the date is named on the record. Vendor-path names have no
filing dates and fail, named. The panel builder writes one row per name and quarter-end
with the forward 12-month return and one descriptive table, and no statistic.

Valuation never fetches, so running it twice on the same inputs with `--today` pinned
gives byte-identical output. `data/` and `output/` are generated and gitignored;
versioned inputs live in `reference/`.

## Stretch

Every record whose name has 250 closes on or before its date carries a `stretch` block:
six measures from split-corrected closes and volume, `dd_120` (close over the 120-day
high, minus one), `above_120_low`, `vs_ma50`, `vs_ma200`, Wilder's `rsi_14`, `rv_20` with
`rv_ratio` against the name's own one-year median, and `vol_5_60`, each with its
percentile of the name's own trailing two years, so "tail" is the name's. Two counts
follow, never a blend: `stretch_low`, how many of `dd_120`, `vs_ma50`, `vs_ma200` and
`rsi_14` sit at or beyond the low thresholds, and `stretch_high` with `above_120_low` in
place of `dd_120`.

The thresholds live in `reference/stretch.json`, dated with a why: set to fire on two
remembered episodes and to be rare; changing them is a dated declaration. The summary
names every record at or above 3 on either side and prints a line for each with the
measures, the percentiles and the anchor's fair value, margin of safety and
`probability_overpaid` beside it. Whose thesis a stretched name corroborates is the
reader's to know; the tool holds no thesis and no flag. It says "stretched" and nothing
more: no signal, no claim about what follows.

The block is computed at fetch time and point-in-time from closes on or before the date
(`python/stretch.py --ticker PLTR --as-of 2026-06-25` prints it; `--snapshot DIR` adds it
to a snapshot's records), and `python/plot_stretch.py PLTR` draws two years of closes with
the averages, shaded where either count reached 3, to `output/stretch/PLTR.png`.

## The build-out readout

A name whose reported cash flow is negative because it is investing more than it earns, and
whose earning history at scale is too short for the mid-cycle window, refuses honestly and
today says nothing else. The build-out readout (60) says the one thing that can be said: for
a `Cyclical` or `OperatingCompany` record that failed the observation guard or the
non-positive-free-cash-flow guard, whose latest capex exceeds its depreciation and whose
latest operating income is positive, `build_out` carries the surface of value per share
across what the new capital earns and how long it takes to earn it, with the price drawn as
a contour per lag.

It is a map of what the price requires, not a value. The record stays `Failed` with its own
reason; the block adds no fair value, no margin of safety and no signal, nothing downstream
reads it, and it never fails a record.

The two declarations live on the universe entry, both or neither, each exactly a value, the
evidence for it and a date:

```json
{
  "ticker": "AMZN",
  "entity_class": "Cyclical",
  "why": "retail and cloud; a capacity build-out ...",
  "build_out_return":    { "value": 0.22, "why": "...", "as_of": "2026-09-23" },
  "build_out_lag_years": { "value": 2,    "why": "...", "as_of": "2026-09-23" }
}
```

`build_out_return` is the after-tax **accounting** return on the new capital once earning,
after depreciation — the units a filing states and a reader reasons in, directly comparable
to the name's own recent return on capital, which the `why` cites as evidence (63). The
readout converts it to the cash yield it needs, adding the same depreciation-to-capital ratio
it then charges as maintenance, and carries both figures with the ratio on the record; a
tranche's free cash flow is therefore the declared return on its cost. `build_out_lag_years`
is whole years from spend to first earning (a data-centre campus one to two, an LNG train
four). A name with one and not the other fails the universe loader; a name with neither
carries `build_out_reason: "build-out return and lag not declared"`.

On the record: the two declarations, the cash return they convert to with the sentence saying
how, the maintenance sentence, the last three years' capex,
depreciation and growth capex as tranches, the standing business alone per share, the WACC,
tax rate, terminal growth and depreciation-to-capital ratio the map runs on, the return axis
(31 values in accounting terms, as the declaration is, the declaration in the middle, ±15
points in 1-point steps), the surface (one row per lag 0..6) and the price contour, whose
`return_required` is an accounting return too. A lag whose contour is null says why — no return in
the range reaches the price, or the price is below the whole range — with the figure at that
end, and that is itself the readout.

```sh
uv run python/plot_build_out.py AMZN --out output   # -> output/build_out/AMZN.png
```

The picture is the surface with the contour, a vertical line at the declared return and a
horizontal one at the declared lag; where the contour is empty the legend says the price is
outside the map at every lag.

## Insiders

Stretch says the price has run from its own path; Form 4 says what the people with the most
information did about it (66). Every CIK-resolved record carries an `insiders` block, read
from SEC's own filings index and archive, keyless and timestamped. A name without a CIK
carries `insiders_reason` instead, because Form 4 covers SEC registrants only.

**Open-market purchases and sales only.** From the non-derivative table, transaction code
`P` (purchase) and `S` (sale). An award (`A`), an exercise (`M`), a tax withholding (`F`), a
gift (`G`) and every other code are **counted by their code and never summed** — an
exercise-and-sell is not a sale of conviction, and an award files a price of zero, so the
filter runs before the arithmetic or the buyer counts inflate where the dollars do not. The
codes seen and not summed are listed on the block as `excluded_by_code`.

The block carries, over the trailing 90 and 365 days: distinct buyers, distinct sellers,
dollars bought, dollars sold, net dollars, the largest single purchase with its owner and
relationship as filed, and whether any buyer's filed title names a chief executive or
financial officer. `cluster_buy` is true when **two distinct insiders** bought on the open
market inside any fourteen-day window in the trailing ninety days — one insider buying twice
is not a cluster, which is the point of the rule — with the window's dates and buyers listed.

**The cut is on the filing date, not the transaction date.** A Form 4 carries no filing date
in its XML and its signature date disagrees with the index often enough to matter, so the
index is the only source for it. The point-in-time path reads the same index with everything
filed after `D` already removed, so the panel's block is the one a reader had on the day.

Documents are immutable once filed and are cached under `data/insiders/<CIK>/<accession>.xml`
for ever; the index is what ages. Amendments are read too: nothing in the index links a `4/A`
to the `4` it amends — their accessions share only the filing agent and the year — so the same
line is recognised by owner, date, code and shares, and the later filing wins.

The summary prints, beside every name already listed at `stretch_low >= 3` or
`stretch_high >= 3`, that name's ninety-day buyer and seller counts and net dollars, and then
a second list, **"stretched with insiders on the other side"**: stretched low with a cluster
buy or a chief executive or financial officer buying, and stretched high with net selling by
two or more distinct sellers. Counting, never weighting.

```sh
uv run python/plot_insiders.py PLTR                     # -> output/stretch/PLTR.png
uv run python/plot_insiders.py PLTR --as-of 2026-06-25  # as it stood on that day
```

The picture is the stretch chart with every open-market purchase and sale drawn at its price
on its transaction date, sized by dollars against the largest in the window, so the reader
sees where insiders acted relative to the path. It replaces the stretch-only chart.

**Scope limits, on every block:** Form 4 covers directors, officers and ten-percent owners of
SEC registrants, so a foreign private issuer files none; a purchase or sale under a rule
10b5-1 plan is scheduled rather than decided, and the filing's plan marking is carried on the
transaction where it has one.

## Stretch and insiders through time

Two episodes said insiders did not call the bottoms stretch caught (66). The study (67) asks
that question across everything the store holds, **descriptively**: counts, medians and
quartiles on the sample as it is, and nothing else. No statistic the sample cannot carry, no
fitted model, no hit rate presented as an edge, and no threshold moved after seeing a table.
Nothing in the batch reads it and no valuation record changes.

```sh
uv run python/stretch_study.py --fill               # fetch what the study reads, then stop
uv run python/stretch_study.py                      # every name in the latest snapshot
uv run python/stretch_study.py PLTR META            # or the names given
uv run python/plot_stretch_study.py                 # -> output/stretch_study/forward_excess_60.png
```

`--fill` is the only thing here that fetches, and it fetches only what the study reads: the
older submissions pages the windows reach into, then the Form 4 documents filed in those
windows. On this universe that is 19 pages and 8,559 documents. It is paced by `fetch_sec`,
it is resumable, and a 503 is SEC asking for a slower pace rather than a filing that does not
exist — it is counted, named and re-tried on the next `--fill`, never taken as an absence.
Without it the study still runs and every window it cannot read says so.

**Episodes.** For every name with at least three years of vendor closes, every trading day
from the third year onward is walked and the stretch counts computed from the block's own
`measures_at` and `counts`, on closes up to and including that day and nothing after it. An
episode starts the first day a side reaches 3 after at least 20 trading days below it, and is
dated by that day. (The percentiles the block also records play no part in a count, so they
are not recomputed; a test holds the walk's counts equal to the block's.)

The walk stops at `--as-of`, the snapshot's own date by default, and the series it walks is
cached under `data/stretch_study/`. Both are for the same reason: the vendor serves its
history to the present and the present moves, so the current day's close is still forming and
a run an hour later would give a different benchmark return at the horizons that reach it.
Fetched once, the run repeats byte for byte; delete the directory to re-fetch. Vendor
revisions to older closes are outside this and are not claimed.

**What followed.** Simple returns at +20, +60 and +120 **trading** days, `null` where the
window runs past the last close rather than a shortened horizon; the same horizons for SPY
from the same dates, and the difference, so a market-wide selloff is not read as a stock call.

**What the insiders had done.** The block's own window and cluster functions over the 90
days ending the day *before* the episode, so nothing filed on the episode's own day or after
it is read. Only that window: the Form 4 cache is filled for exactly these windows, and a
365-day figure computed from it would be a subset dressed as a total. Three states — any
open-market buyer, net selling by two or more distinct sellers, or neither — and `unknown`
whenever the window cannot be read in full, with the reason saying which: no CIK, no Form 4
on file at all, an older submissions page not on disk, or a filing the cache does not hold.
A window missing one filing may be missing the only purchase, so it is never counted as a
subset; and a window read in full that holds nothing is zero, not unknown.

**`filings.recent` is a year, not a history.** It holds the most recent thousand filings or
one year, whichever is more, so for a heavy filer it is barely the year: JPMorgan's reaches
back twelve months and Meta's fifteen. The 365-day block (66) never needs more — SEC's
`recent` covers exactly the trailing year, and the ten-day filing margin beyond it can only
hold filings reporting transactions outside the window. A study that walks four years does
need more, and reading only `recent` would have made Meta's 2023 and 2024 episodes read as no
insider activity when seven insiders had sold. `filings.files` lists the older pages with the
span each covers, and only the pages whose span meets a window are read.

The study itself fetches no filing. `fetch_sec.form4_filings_cached` and
`fetch_sec.insiders_cached` read what is on disk and report what is not, so walking four years
of dates costs disk reads rather than tens of thousands of requests; `--fill` is the one pass
that goes to SEC.

The CIK comes from SEC's ticker map and the universe's declared CIKs, the same resolver the
fetch uses — never from a record's prose, because a name whose provider reason names a
companyfacts lag rather than a CIK has a CIK all the same.

**The tables**, in `output/stretch_study/`: per side and per side-and-insider-state, for each
horizon, the count, the median excess, the interquartile range and the share positive; the
whole thing printed twice, all episodes and first-per-name-per-side-per-year, so the reader
sees whether a few names carry it; overlapping episodes within 120 days flagged and counted;
`episodes.jsonl` with every episode in full. **A cell of fewer than ten episodes prints its
count alone** — a median of eight things is a number pretending to be a measurement.

The picture is one point per episode at +60, grouped by side and insider state, with the
median drawn as a bar and the count in the label. A picture of a sample, not of a result.

## Build, test, type-check

```sh
dune build        # also regenerates python/boundary.py and python/reference.py from schema/*.atd
dune test
uv run pyright
uv run pytest
```
