# The studies: what the tool found about itself

The tool tests its own outputs against what happened next and keeps the result whether or
not it flatters it. Every study here is descriptive: counts, medians, quartiles, the share
positive, a rank correlation or a fitted line where a sample carries one, and no statistic
a sample cannot carry. The names on one date move together with the market, so a panel of
thousands of rows is a few dozen formations and nothing here is a test in the statistical
sense. A cell under ten rows prints its count alone. Nothing a study finds feeds a model, a
belief or a signal: a finding is weighed by a person and the change, where there is one, is
made in the open and cited. `reference/holdout.json` declares what no study reads; see
[The holdout](#the-holdout). `docs/run.md` is the manual for the tool itself; this page is
what the tool found when turned on its own work, and the questions that stayed open after
it.

## The panels

Three panels, each built for a question the others cannot answer. A study's figure means
only what its panel can mean.

| panel | built by | names and dates | what it can answer | what it cannot |
|---|---|---|---|---|
| **point-in-time** | `build_panel.py` → `output/pit/panel.jsonl`, one row per name and quarter-end valued by the real pipeline from what was known then | the tool's own universe, the names declared when it was built, every quarter-end 2022-03-31 to 2026-06-30, the held-out names and dates aside | what the records' own judgments preceded: the anchor, the belief, the model, the refusal and its reason, the quality block, the growth shadow, the options-implied return, the insiders block, the surprise history | names a person chose, in one market regime, on eighteen quarter-ends that are not eighteen independent draws; it cannot tell a measure that never worked from one that stopped |
| **broad** | `broad_panel.py` → `data/broad/panel.jsonl`, filed items from the SEC frames and a market value from the cover-page share count | every SEC filer with a ticker today, about three thousand one hundred, each June from 2010 | whether plain cheapness, quality and a peer-implied gap sorted returns over a long span and across sizes, without any model | survivors only (a filer with no ticker today is missing), restated frames, no DCF since no class is declared; it says nothing about the tool's own model |
| **rule** | `rule_panel.py` → `data/broad/rule/panel.jsonl` and `output/rule_panel/<date>/valuations.jsonl`, the real pipeline on the point-in-time fetch | the five hundred largest filers by market value each June 2013 to 2025 among those reporting current assets, chosen by a rule that reads nothing later than the date, one class for all | what the tool's own DCF does on names not picked in hindsight, and what its parameters do: the rate, the beta, the starting growth, the duration | large survivors under one lens with a beta of one and no vendor cross-check, parameter tables at the 2026 vintage except the rates; a finding here is about large US companies since 2013 |

Three studies read a store rather than a panel: the surprise study reads the consensus tool's
release history (about fifty releases a name, returns from 2020), the stretch-and-insiders
study reads the Form 4 store over the windows stretch marked, and the bound study reads the
options store (62 names, daily from April 2025).

## What stays open

The studies settled five things in the model: terminal growth is held to the risk-free rate
(2026-10-04, below under [Why the anchor's level moves with rates](#why-the-anchors-level-moves-with-rates));
the scope code `growth_without_reinvestment` names the six names whose fundamental
estimate reads far below their history (2026-10-17); the fundamental estimate stays the
headline growth of a generic DCF record, with its lean stated on the record (2026-10-18, below
under [Growth on the rule panel](#growth-on-the-rule-panel-does-the-starting-growth-forecast-what-followed)
and in `docs/run.md`, the growth shadow); and the industry beta stays in the cost of equity,
held through the projection, with its caveat stated on the record (2026-10-18, below under
[Betas on the rule panel](#betas-on-the-rule-panel-which-forecasts-and-the-fair-values-under-each));
and above the kink the rate passes through in full, with the regime and its lean stated on
the record (2026-10-18, below under
[The discount rate on the rule panel](#the-discount-rate-on-the-rule-panel-how-much-of-a-rate-move-to-take-and-a-premium-that-moves)).
A sixth was decided and built but not yet measured: a four-quarter shadow stands beside the
annual headline on every US filer's generic DCF record, the same model on the last four filed
quarters, with a sentence on every valued record saying what the annual base costs
(2026-10-18, `docs/run.md`, the four-quarter shadow); the point-in-time path writes the
trailing period, so the panels carry the shadow once rebuilt, and the study of its margin
against the headline's is owed. And a seventh, on principle: a readout that does not sort
returns stays on the record, since a readout describes and need not predict, and every
readout block now carries, last among its limits, a dated sentence saying what it was
measured against here and what came of it, or that no study reads it (2026-10-18,
`ocaml/lib/measured.ml`; the rule that a study owes its block the sentence is in
`docs/studies.md`). The quality block's two measurements, the levels and the share count sorting
and the comparisons and the accruals ratio not (under
[What the quality score is made of](#what-the-quality-score-is-made-of)), are the first such
sentence; weighed and not taken were prediction as the test for a readout, which would
remove the anchor itself, and reshaping or pruning the quality block on one panel of
survivors, a per-field change on a fitted reading.
The questions below were each measured
and not settled, because the data cannot distinguish the options or because the choice is one
of principle. They are held together and decided together, never on one study or one paper;
each line says what was measured, why it did not settle the question, and what would.

- **Build-outs, rebound windows, goodwill, and the growth rule's cliff at zero
  reinvestment.** Named on the universe entries as scope limits and on the records as
  readouts; each is a model question the tool declares rather than answers today, and none has
  a study yet.

What was built, measured and taken out again is on `docs/tried.md`.

## The anchor study

`uv run python/anchor_study.py` (80) asks what the records' own judgments preceded. For every
row of the point-in-time panel, valued on its quarter-end from what was known then, it reads
what the price did afterwards against SPY over the same calendar dates at +63, +126 and +252
trading days, and groups the rows by what the record said on the day: Ok or refused, the
signal, the margin of safety in quintiles within each date so the market's own quarter does
not masquerade as the anchor's, the belief's probability_overpaid where one existed, the
class, the model, and for the refusals the family of the reason. It writes
`output/anchor_study/records.jsonl` and `tables.txt`; `plot_anchor_study.py` draws the
year-ahead excess by margin-of-safety quintile as strip plots with the medians marked.

Descriptive only: counts, medians, quartiles and the share positive. The names on one date
move together with the market, so a hundred and seventy-eight names on eighteen quarter-ends
are not eighteen hundred independent tests and no statistic is claimed; a cell under ten
rows prints its count alone. Nothing here feeds a model, a belief or a signal. The closes
are cut at `--as-of` and cached under `data/anchor_study/` so the study repeats byte for
byte; delete the directory to re-fetch. Rebuild the panel first (`build_panel.py`) when the
code has moved since it was written, or the study reads yesterday's judgments.

### The naive baseline

`uv run python/baseline_study.py` puts three measures that need no model beside the anchor
on the same rows and the same forward windows: the earnings yield, book-to-price and EBIT
over enterprise value, each from the point-in-time boundary file the valuation itself read
(`data/pit/<date>/<TICKER>.json`), statements in another currency converted through USD at
the date's own rates. It prints each measure's quintiles within the date on every row that
carries it; on the rows the anchor valued, the measure's quintiles beside the margin of
safety's, both cut on that same set; the within-date rank correlation of the two; and the
cheapest quintile's median less the dearest's, pooled and then within each model's own rows,
since a margin of safety from one model does not rank against another's. It answers one
question the anchor study cannot: whether the anchor did anything a plain cheapness sort did
not. Further sections read blocks from each date's own valuations file: quality, by the
nine-signal score, the accruals ratio, gross profitability and the score against cheapness;
the growth shadow's margin of safety beside the headline's on the generic DCF's rows; and
the options-implied expected return in quintiles within the date on every row that carries one,
with the earnings yield and the margin of safety on the same rows and its rank correlation
with each. The options store begins in April 2025, so the second is a handful of
quarter-ends in one market and its year-ahead cells are near the small-cell floor.
Descriptive only, under the same rules; it writes `output/baseline_study/`.

### The holdout

`reference/holdout.json` declares what no study reads: the thirty-two names that joined
after the panel was built, and every date after 2026-06-30. Both studies drop those rows and
say how many in the third line of their tables. They were put aside on 2026-10-03, before
any model changed in answer to the two studies, because a change suggested by a sample
cannot be tested on it. `--holdout` on either study reads them; that is a one-time act, and
whoever does it adds the date and the tree to the file's `opened` list. The held-out names
share the 2022-2026 regime on the dates before the cut, so they are a holdout on names; only
the later dates are a holdout on time.

## The broad panel and its study

The anchor study and the naive baseline read eighteen quarter-ends on a hundred and
seventy-eight names inside one market, and every fundamentals-based sort failed there the
same way. That cannot tell a measure that never worked from one that did not work lately,
or either from a sample that was chosen. Two commands build the longer, wider sample:

    uv run python/broad_panel.py --retry-missing    # -> data/broad/panel.jsonl
    uv run python/broad_study.py                    # -> output/broad_study/tables.txt

`broad_panel.py` takes every SEC filer with a ticker today and forms a row each June from
2010 on, from the fiscal year before: the filed flows and balance sheet from SEC's frames
API, a market value from the cover-page share count (never restated, moved onto today's
split basis by the splits after its month, times June's split-adjusted close), and the next
twelve months' dividend-adjusted return beside SPY's. The first build takes about an hour,
most of it the frames; the vendor rate-limits a long run of bulk price requests, which is
what `--retry-missing` is for. Nothing fetched is tracked.

`broad_study.py` cuts each measure into quintiles within the formation year, for the
formations before 2022 and for those from 2022, and prints the top quintile's median excess
less the bottom's, pooled and year by year. The measures are the earnings yield,
book-to-price, gross profitability, the accruals ratio, the nine-signal score, and a
peer-implied gap after Bartram and Grinblatt: each June, market value per dollar of assets
regressed across the companies on equity, revenue, net income and operating cash flow per
dollar of assets, the fitted value being what the market pays that year for those accounts
elsewhere. The main tables are on filers reporting current assets, which leaves banks and
insurers out; the held-out names are left out of everything.

**What it found on the first build (2026-10-03), descriptively.** About 30,600 rows on 3,100
filers, 26,200 with a return. Before 2022, twelve formations: the earnings yield sorted
nothing (the cheapest fifth level with the dearest, ahead in three years of twelve),
book-to-price and the peer-implied gap ran a few points the wrong way, gross profitability
ran four points the right way and was ahead in eight years of twelve, the score two points
the right way in six of eleven. From 2022, four formations: the earnings yield ran ten
points the right way and the score nine, ahead in three and in all four of the years, where
on the anchor study's hundred and seventy-eight names over the same years the cheapest ran
behind the dearest. So two things the narrower studies could not say: cheapness was not
working for a decade before 2022, on survivors at least; and its failure since 2022 is not
the whole market's. The first reading of that, that the universe here was chosen in
hindsight, was half the story: the rule study below shows the same failure among the five
hundred largest filers chosen by size alone, so it belongs to large companies since 2022,
which is what this universe mostly holds, as much as to how its names were picked.

### The rule panel: this tool's own DCF on a universe chosen by a rule

    uv run python/rule_panel.py --check-rule     # the industry-code rule against the declared classes
    uv run python/rule_panel.py                  # -> data/broad/rule/panel.jsonl, about an hour the first time
    uv run python/rule_study.py                  # -> output/rule_study/tables.txt

`rule_panel.py` runs the real pipeline, the point-in-time fetch and the OCaml binary, on
names chosen by a rule that reads nothing later than the date: each 30 June from 2013, the
five hundred largest filers by market value among those reporting current assets, the
held-out names left out. A class is declared by a person and nobody reads a thousand
filers, so the study declares one rule for all and says so: a filer whose SEC industry code
is not in the module's exclusion table runs as an operating company under the generic DCF,
and every other is left out, never valued. `--check-rule` measured that table against the
classes declared here before it was used and it was narrowed once on what that showed; it
agrees with a person on 153 of 184 names, and where it differs it mostly runs a name a
person called cyclical or unprofitable. No vendor statements are fetched, so there is no
cross-check and a filer with no filed operating income is refused; no vendor profile, so
every name has a beta of one. Rates are point-in-time, read from 2009 into the study's own
cache; the other parameter tables are the 2026 vintage.

**What it found on the first build (2026-10-04), descriptively.** 5,193 records on 745
filers over thirteen Junes, 2,755 valued. On the valued rows, cut within the date:

- before 2022, nine formations: the margin of safety sorted nothing, the cheapest fifth
  level with the dearest and ahead in five years of nine; the earnings yield on the same
  rows ran four points the wrong way, ahead in three of nine; the nine-signal score ran
  five points the right way, ahead in seven of nine;
- from 2022, four formations: the margin of safety ran nine points the wrong way and the
  earnings yield ten, each ahead in one year of four; the score one point the right way,
  ahead in three of four;
- the margin of safety's rank correlation with the earnings yield within the date is 0.55
  before 2022 and 0.67 since, so the anchor is again in good part the cheapness sort, a
  little better than it before 2022 and no different since;
- the growth shadow ranked as the headline did, and the refused rows did as the valued.

So on names not picked in hindsight the generic DCF still does not sort returns, in either
stretch, and the score is the one measure that leaned the right way in both. And one
finding about the model's level: the median margin of safety on a date ran from above one
in the low-rate years to below zero since 2023. The discount rate follows the risk-free
rate while the terminal growth does not, so with rates at their lowest most large
companies read as worth double their price, and 264 records met the sanity bound. The cut
is always within the date, so the tables above do not depend on it, but a level that moves
that far with rates is a property of the model to look at on its own.

### A share count in the wrong unit, and the panels rebuilt

Checking the beta study below turned up rows of the broad panel with a market value a
thousand or a million times too large, eight rows of the rule panel among
them. The cause is the filer's: the cover-page share count is
tagged in thousands or millions as if in units. The market value is that count times the
price, so it carries the error whole, the row enters the rule panel's largest five hundred
on a false size, and its earnings yield is wrong.

The guard, in `broad_panel.py`. A row carries no market value, with the reason and never a
corrected figure, when two things hold together: the market value is above a hundred times
the larger of the year's revenue and total assets, and the count is a hundred times the
filer's own weighted count for the fiscal year or more, or that many times the smallest
count it filed for another June. The second sign is what keeps a company the market really
prices at a hundred times its sales or its assets: its count agrees with its own filings
and it keeps its market value. Measured before the rule was set, on some thirty thousand
rows: thirty were above the ceiling; twenty-eight carried the second sign, every one a
count about a thousand or a million times the filer's others; two did not, the line of a
depositary receipt counted in ordinary shares, which the rule leaves as it finds them. The
highest ratio on a company priced that way was seventy-two.

A second error, guarded the next day. A filing made shortly after a split states the count
on the new basis under a date before it, so the split's factor would move it onto today's
basis twice: one filer's count, dated the last day of a June and filed after a seven-for-one
split the month after, gave a market value seven times the company's. The guard, `on_split_basis` in
`broad_panel.py`, looks at a real split, three for two or larger either way, in the three
months after the cover date, and reads the filer's own counts on either side of it: a count
that matches the filer's next count after the split, that count being the one before times
the ratio, is already on the new basis and the row carries no market value, with the
reason; a count that matches the one before is kept; and where neither can be told the row
is kept as it is. Measured before the rule was set: of 114 counts with such a split just
after them, 87 were shown to be on the earlier basis, 5 were already on the new one, and 22
could not be told. The rebuild of 2026-10-06 took the market value from those five rows,
one of them in the rule panel's years, and moved no other; in the rule panel that row left
and the next two names by size entered, and every figure below moved in its last decimal if at all.

One error is known and not guarded, wrong by a ratio and not by a thousand: a filer whose
ticker is a depositary receipt and whose count is in ordinary shares.
A spin-off the vendor carries as a split was taken for a third and is not one: the factor
moves the price history, and the count times it is the count on that history's basis, so
the market value is right (checked on two names).

**Rebuilt 2026-10-05.** Both panels were built again, and three things changed at once,
which the figures below cannot separate:

- the guard: twenty-eight rows of the broad panel lost their market value, and no other
  row's market value moved;
- the day's data: SEC's list of tickers had changed, so fifty-six rows left and nine came,
  and twenty-three tickers the vendor had rate-limited on the first build now carry
  prices, giving a hundred and seventy-two rows a market value they lacked; forward
  returns moved in the sixth decimal;
- the model: the rule panel is valued by the binary of the day, which since its first
  build holds terminal growth to the risk-free rate. So 2,981 of its 5,181 records are
  valued where 2,755 of 5,193 were, fewer meeting the sanity bound, and the median margin
  of safety on a date runs between +0.05 and +0.32 from 2013 to 2020, where it ran above
  one, and below zero in 2021 and from 2023.

The broad study on the rebuilt panel, about 30,600 rows on 3,100 filers: before 2022 the
earnings yield still sorted nothing, the cheapest fifth level with the dearest and ahead in
five years of twelve where it was three; book-to-price and the peer-implied gap a few
points the wrong way; gross profitability four points the right way in eight of twelve; the
score two points the right way, in seven of eleven. From 2022 the earnings yield ten points
the right way and the score ten, in three and in all four of the years. Nothing in the
reading above changes.

The rule study on the rebuilt panel, cut within the date on the valued rows:

- before 2022: the margin of safety one and a half points the right way, ahead in five
  years of nine; the earnings yield three points the wrong way, ahead in three of nine; the
  score three points the right way, in seven of nine;
- from 2022: the margin of safety ten points the wrong way and the earnings yield ten, each
  ahead in one year of four; the score level, ahead in two of four where it was three;
- the margin's rank correlation with the earnings yield within the date is 0.57 before 2022
  and 0.69 since.

So the first build's reading stands: the generic DCF does not sort returns on names chosen
by rule, and no better than the earnings yield. The score's lean from 2022 is weaker than
the first build showed.

### The rule study on market-adjusted returns

    uv run python/rule_alpha.py                  # -> output/rule_alpha/tables.txt

The tables above set a fifth's twelve-month return beside SPY's. That removes the market's
level and nothing else, so a fifth holding the riskier names is credited with the market's
rise as if it had earned it. `rule_alpha.py` scores the same sorts the way two papers read
for this tool do, **beside** the raw tables and never in place of them:

- Jensen, Kelly and Pedersen, "Is There a Replication Crisis in Finance?", NBER Working
  Paper 28432, February 2021, doi:10.3386/w28432. A factor's alpha is the
  intercept of its monthly return on a constant and the market's excess return; of their
  US factors 84.9 per cent replicate on that alpha against 56.9 on raw returns.
- Gormsen and Lazarus, "Duration-Driven Returns", working paper, April 2019,
  doi:10.2139/ssrn.3359027. Their sort's spread is insignificant raw and significant as
  alpha, the market betas of its tenths running from 0.72 to 1.61.

Each June the valued rows are cut into fifths within the date as before; a fifth's monthly
return over the twelve months from July is the mean of its names' dividend-adjusted
returns, and again weighted by market value capped at the formation's eightieth percentile
and carried forward (the first paper's capped value weights, with this panel's own
percentile where the paper uses the New York Stock Exchange's); the formations are chained
into one monthly series and regressed on SPY, both over a twelfth of the one-year Treasury
yield of the month before. The t-ratio is the plain least-squares one.

**What it found (2026-10-06, on the rebuilt panel), descriptively.** 2,981 valued records,
156 months, 48 of them from the 2022 formation on. Highest fifth less lowest, per cent a
month:

| measure | stretch | equal: raw, beta, alpha (t) | capped value: raw, beta, alpha (t) |
|---|---|---|---|
| margin of safety | all | −0.07, −0.01, −0.07 (−0.26) | −0.22, −0.14, −0.08 (−0.27) |
| margin of safety | before 2022 | +0.13, +0.09, +0.04 (+0.12) | −0.03, −0.02, −0.02 (−0.06) |
| margin of safety | from 2022 | −0.52, −0.21, −0.26 (−0.57) | −0.64, −0.37, −0.17 (−0.28) |
| earnings yield | all | −0.23, +0.03, −0.26 (−1.06) | −0.24, −0.06, −0.18 (−0.68) |
| earnings yield | from 2022 | −0.36, −0.01, −0.35 (−0.83) | −0.27, −0.06, −0.20 (−0.38) |
| nine-signal score | all | −0.13, −0.02, −0.11 (−0.67) | −0.23, +0.03, −0.27 (−1.26) |
| nine-signal score | before 2022 | −0.06, −0.01, −0.05 (−0.28) | −0.10, +0.02, −0.11 (−0.63) |
| nine-signal score | from 2022 | −0.31, −0.03, −0.27 (−0.65) | −0.54, +0.07, −0.62 (−1.10) |

- **The adjustment changes little here, because the fifths carry nearly the same market.**
  The betas of the fifths run from 0.78 to 1.21 on every measure and stretch, against 0.72
  to 1.61 across the second paper's tenths. A universe of the five hundred largest
  operating companies, cut on value or quality, does not spread beta the way the papers'
  whole markets do.
- **Since 2022 part of the margin of safety's shortfall was market exposure.** The cheapest
  fifth carried less market than the dearest (a spread beta of −0.21 equal-weighted, −0.37
  capped), so the raw shortfall of a half to two thirds of a point a month becomes about a
  sixth to a quarter of a point as alpha. It stays negative, and nowhere near a size the
  months could tell from nothing.
- **No sort shows an alpha.** The largest t-ratio in the table is 1.3, on the wrong side.
  The rule study's finding stands, raw or adjusted: on names chosen by rule the generic
  DCF does not sort returns, and no better than the earnings yield.
- **The score's lean does not survive the change of measure.** The rule study found the
  nine-signal score leaning the right way in both stretches, on the median twelve-month
  excess of the names in a fifth. On the mean monthly return of the fifth as a portfolio it
  is about level before 2022 and behind since. The two are different statistics, a median over
  names and a mean over a portfolio, and a lean that depends on which is read is a weak one.

What this does not settle: a hundred and fifty-six months is a quarter of the shortest
sample in the papers, the universe is survivors only, and the regression has one factor.
It answers the narrow question it was built for: the raw tables were not hiding a sort
behind unequal market exposure.

### The rule panel sorted on beta

    uv run python/rule_beta.py --fetch-benchmark  # -> output/rule_beta/tables.txt

This tool's cost of equity is a risk-free rate plus a premium times beta, so a name with
twice the beta is charged twice the premium. Whether the market paid that premium on the
kind of company this tool values is a question about returns. Three papers read for the
tool bear on it:

- Frazzini and Pedersen, "Betting Against Beta", NBER Working Paper 16601, December 2010,
  doi:10.3386/w16601. Across ten beta-sorted portfolios of US stocks the monthly excess
  return is flat, 0.99 per cent for the lowest beta and 1.02 for the highest, while the
  CAPM alpha falls from 0.54 to −0.05 and the realised beta rises from 0.75 to 1.82. The
  beta estimator used here is theirs.
- Novy-Marx and Velikov, "Betting Against Betting Against Beta", working paper, November
  2018, doi:10.2139/ssrn.3300965. Most of that premium comes from weighting small stocks
  equally; weighted by value it is about half. So the tables are given under both
  weightings, on names that are the largest five hundred to begin with.
- Levi and Welch, "Best Practice for Cost-of-Capital Estimates", Journal of Financial and
  Quantitative Analysis 52(2), 2017, doi:10.1017/S0022109017000114. Between a beta of 0.0
  and one of 1.5 the textbook difference in the cost of equity is about ten points a year;
  shrunk betas and a long-run premium bring it to about two. The tables read the same
  quantity off these names: the return earned per unit of realised beta.

Each June every name in the rule panel, valued or refused, is given a beta from the daily
returns of the year to the date: the sum of the slopes of its return on SPY's of the same
day and of each of the five days before, halved toward one. The names are cut into fifths
within the date and scored as `rule_alpha.py` scores the other sorts. Two lines close each
table: the return earned per unit of realised beta between the highest fifth and the
lowest, beside SPY's excess return over the same months, which are equal if beta was paid
in full; and the alpha the spread would show had beta not been paid at all, the first
paper's flat line.

**What it found (2026-10-06, on the rebuilt panel), descriptively.** 5,110 names and Junes on
735 filers, 156 months. Highest-beta fifth less lowest, per cent a month unless said:

| stretch | weights | raw | spread beta | alpha (t) | flat line | earned per unit of beta, a year | SPY over the rate, a year |
|---|---|---|---|---|---|---|---|
| all | equal | +0.89 | +0.67 | +0.18 (+0.59) | −0.71 | +16.0% | +12.7% |
| all | capped value | +1.20 | +0.74 | +0.42 (+1.05) | −0.79 | +19.4% | +12.7% |
| before 2022 | equal | +0.46 | +0.52 | −0.04 (−0.15) | −0.50 | +10.6% | +11.6% |
| before 2022 | capped value | +0.56 | +0.52 | +0.06 (+0.17) | −0.50 | +12.8% | +11.6% |
| from 2022 | equal | +1.87 | +0.96 | +0.64 (+0.84) | −1.23 | +23.3% | +15.3% |
| from 2022 | capped value | +2.66 | +1.18 | +1.16 (+1.13) | −1.50 | +27.0% | +15.3% |

- **A year's beta was a fair forecast of the next year's.** The fifths formed at 0.73, 0.90,
  1.02, 1.13 and 1.39 realised 0.77, 0.95, 1.09, 1.24 and 1.44 over the twelve months
  after, equal-weighted.
- **On these names in these years beta was paid, about in full.** The raw return rose with
  beta at every step, and the return earned per unit of beta was the market's own excess
  return or more in every row. The alpha of the spread is near nothing throughout.
- **This is not the first paper's flat line.** Had beta not been paid, the spread's alpha
  would have been about seven tenths of a point a month below zero over the whole sample.
  The estimate sits nearly three of its standard errors above that; about two in each
  stretch taken alone.

**How long a beta lasts (2026-10-07).** The discount rate built on a beta is applied to
every projection year and the terminal value alike, so the run also follows each June's
fifths, fixed at formation, through their first five years. Keloharju, Linnainmaa and
Nyberg, "Long-Term Discount Rates Do Not Vary Across Firms", NBER Working Paper 25579,
February 2019, doi:10.3386/w25579, sort on a quarter's beta and find the gap between the
top and bottom tenths, 1.01 in the quarter after, half of that after five years and 0.36
after ten, while the return spreads of their other sorts are gone within about five years.
Here, per event year after formation, the realised beta of the lowest and highest fifth
and the spread between them:

| event year | months | realised beta, lowest | highest | gap | spread, raw | alpha (t) |
|---|---|---|---|---|---|---|
| at formation | | 0.73 | 1.39 | 0.66 | | |
| 1 | 156 | 0.77 | 1.44 | 0.67 | +0.89 | +0.18 (+0.59) |
| 2 | 148 | 0.87 | 1.33 | 0.46 | +0.49 | +0.05 (+0.16) |
| 3 | 136 | 0.86 | 1.36 | 0.50 | +0.20 | −0.30 (−1.08) |
| 4 | 124 | 0.93 | 1.37 | 0.44 | +0.51 | +0.04 (+0.13) |
| 5 | 112 | 1.02 | 1.30 | 0.28 | +0.84 | +0.55 (+1.99) |

Equal weights; the capped-value figures run from a gap of 0.74 in the first year to 0.36 in
the fifth. So on these names the beta gap of a sort loses a third of itself in a year and
more than half in five, as the paper finds for tenths of the whole market, while the raw
spread stays on beta's side in every year. A discount rate that holds the first year's beta
over seven projection years and a terminal value is charging a spread that the names
themselves do not keep; what a fair value built on a beta faded toward one would read is
not measured here, the rule panel valuing every name at one.

What this does and does not say. The papers that question beta in a discount rate rest on
whole markets over many decades. On the largest five hundred US operating companies from
2013 to 2025 the tool's own data do not show their result, so they give no ground, on this
universe, for taking beta out of the cost of equity. Four limits keep it from saying more:

- it is one stretch of thirteen years in which SPY's excess return ran at about twice the
  six and a half per cent the third paper takes as the textbook premium, and the
  highest-beta fifth held the large semiconductor and internet companies that led it, the
  lowest the consumer staples and telephone companies: a single run of the
  market's premium, earned by the names that led it, is doing much of the work;
- the panel is survivors only, and the names that failed or were bought cheaply are likelier
  to have been high-beta, which flatters that fifth;
- a hundred and fifty-six months cannot tell a line a little flatter than the CAPM's from
  the CAPM's own;
- it reads the market's side only. The rule panel values every name at a beta of one, so
  nothing here says whether a fair value built on another beta would have ranked returns
  any better.

### Duration on the rule panel: the model's timing against a published measure

    uv run python/rule_duration.py                 # -> output/rule_duration/tables.txt, durations.jsonl; about fifteen seconds

A fair value is a sum of discounted cash flows, and its sensitivity to the discount rate is
the weighted average time of those flows, the duration. Dechow, Sloan and Soliman, "Implied
Equity Duration: A New Measure of Equity Risk", working paper, University of Michigan
Business School, May 2002, build one from four filed items and the market value with one
discount rate for every firm, so that the measure carries timing alone: book equity and
sales, each with the year before, and earnings; the return on equity reverts to 12 per cent
with a persistence of 0.57 and sales growth to 6 per cent with 0.24; ten years of
clean-surplus cash flows are discounted at 12 per cent, and the value the price carries
beyond them is taken as a level perpetuity whose duration is 19.33 years. They show
algebraically that the measure is a cousin of the earnings yield and of book to market and
find Spearman correlations of −0.76 and −0.73 with them (their Table 3), and that it
forecasts the next two years' beta and volatility a little (their Table 5: beta on relative
duration, slope 0.32 and an R² of 0.02; with the lagged beta beside it 0.20 and 0.19).
Weber, "Cash Flow Duration and the Term Structure of Equity Returns", NBER Working Paper
22520, August 2016, doi:10.3386/w22520, uses the same construction over fifteen years.

**What it does.** For every valued generic DCF record in the rule panel, three durations.
`dss` is the paper's measure as specified, from the point-in-time record's two latest fiscal
periods and the market value on the date (a name with book equity at or below zero carries
none, as the paper drops them). `model` is the model's own, price-free: the Macaulay duration
of its enterprise value at its own discount rate, the explicit cash flows at their years and
the terminal value as a growing perpetuity whose duration is the horizon plus one plus the
rate over the rate less the terminal growth, levered onto the model's equity value with net
debt at a duration of nought; it reads the shape of the projection and nothing of the price.
`implied` is the paper's device on the model's flows: the explicit present values weighted
over the enterprise value at the price, the model's terminal duration carrying the rest.
Then the measures by date; their rank correlations within the date with the earnings yield,
the margin of safety and book to market; the paper's Table 5 on the panel, the name's plain
beta over the twelve months after the date on its relative duration (its duration over the
date's value-weighted mean), alone and beside this year's beta, and the same for the standard
deviation of daily returns; and the rate study's measured fall in each fair value per point
of risk-free rate against the model's modified duration, within the date.

**What it found (2026-10-17), descriptively.** 2,981 records on 510 names; 2,690 carry the
paper's measure. Pooled medians: `dss` 17.7 years (quartiles 17.0 to 18.3), `model` 29.1
(24.5 to 34.2), `implied` 26.6 (24.1 to 28.8); the paper's mean is 15.1 with quartiles 13.3
to 17.4 on all US stocks, its terminal duration 19.33 for every firm, where the model's is
the horizon plus the rate over the rate less terminal growth, which the panel's rates put
near thirty years.

| rank correlation within the date, median over 13 Junes | earnings yield | margin | book to market | dss | model |
|---|---|---|---|---|---|
| dss | −0.70 | −0.53 | −0.78 | — | −0.26 |
| model | +0.15 | +0.28 | +0.24 | −0.26 | — |
| implied | −0.46 | −0.62 | −0.07 | +0.27 | +0.42 |

The paper's measure replicates on the panel (its −0.76 and −0.73). The model's price-free
duration ranks almost apart from it, and mildly with the margin: a longer projection is a
higher fair value. On Table 5, nothing: next year's beta on any of the three relative
durations has a slope within a hundredth of a standard deviation per standard deviation and
adds nothing to this year's beta (adjusted R² 50.7 to 51.3 per cent with it, 0.0 without);
the same for next year's daily standard deviation (0.015 to 0.038 standard deviations per
standard deviation beside this year's). The measured fall per point of risk-free rate against
the model's modified duration per point of discount rate: below the kink, 2013 to 2022,
medians of 0.8 to 1.3 per cent against 26 to 29, a ratio of 0.03 to 0.05, and a rank
correlation of −0.5 to −0.8 (the names with more of their value in the terminal are hurt
less, since the terminal growth rises with the rate); above it, 2023 to 2025, 21.5 to 23.5
per cent against 24 to 26, a ratio of 0.85 to 0.98, and a rank correlation of 1.00.

**Reading.** The published measure is what its authors say it is, a yield in years: it ranks
the panel as the earnings yield and book to market do, and our margin of safety sits halfway
to it (−0.53; the margin's own rank correlation with the earnings yield is 0.57 to 0.69). The
model's duration carries no information about the beta or the volatility that followed, on
these names in these years, so a duration-implied beta is not an alternative to the beta of
one the panel runs on. And the analytic duration describes a record only above the kink:
below it, with terminal growth held to the risk-free rate, a point of rate moves a fair value
by a thirtieth of its duration, so the margin's swing between the regimes does not scale with
duration at all; above it, the swing is the duration times the share of a risk-free move that
reaches the weighted cost of capital.

**Limits.** No new field: every record already carries the fair value at the discount rate
stepped a point either way in its sensitivity block, and the model duration here is that
step's analytic twin. The paper's market value is at the fiscal year end and ours at the June
date; its discount rate is one constant and the panel's varies only with the date's rate and
each name's debt weight, beta being one; its sample is every US stock over 1963 to 1998 and
ours the largest five hundred over 2013 to 2025. Nothing here moves a record or a parameter.

### Growth on the rule panel: does the starting growth forecast what followed

    uv run python/rule_growth.py                   # -> output/rule_growth/tables.txt, growth.jsonl; seconds

Every generic DCF record starts its projection from one of two estimates: the fundamental
one, the return on invested capital times the reinvestment rate, taken where after-tax
operating profit and net reinvestment are both positive, and otherwise the historical
revenue growth held to the return on capital; the growth shadow carries the higher of the
two beside the headline. The projection then fades the starting growth toward the terminal
rate, a quarter of the gap closing each year. None of it had been tested against what the
companies then did. Weber, "Cash Flow Duration and the Term Structure of Equity Returns",
NBER Working Paper 22520, August 2016, doi:10.3386/w22520, sorts US stocks on a duration
built from the same kind of projection and finds, in his Table 7, the realised five-year
earnings growth of the sorted tenths running from 7 to 31 per cent a year before the sort
and from 10 to 11 after it: the growth the sort read did not persist; the pooled
year-on-year persistence he uses is 0.41 for the return on equity and 0.24 for growth.

**What it does.** For every generic DCF record in the rule panel, each June 2013 to 2025,
the record's own estimates are read as the model computed them at the date: `fundamental`,
`historical`, `headline` (the one the rule chose, after the clamp), `shadow` (the higher),
`path` (the growth the model projected over the horizon, the geometric mean of its faded
path) and `terminal` (the terminal rate alone, the forecast of knowing nothing about the
name). The outcome is what the filer then reported, read from the SEC frames the broad panel
cached: revenue, on the broad panel's chain of revenue elements, and operating income, at
the record's base fiscal year end and at the end one, three and five years after it, within
forty-five days of the anniversary, annualised where both figures are positive. Both sides
are winsorised at the first and ninety-ninth percentile, as the paper does. Each estimate is
scored at forecasting each outcome as it is (one less the squared errors over the squared
deviations from the realised mean, and the root mean squared error) and fitted; then within
each growth source; then the level, what each source read against what followed; then the
paper's table, fifths on the headline within each June; then the persistence of each
estimate and of realised growth on the same name's a year before.

**What it found (2026-10-17), descriptively.** 3,069 records on 518 names: 1,501 whose
headline is the fundamental estimate, 985 the historical, 583 the historical held to the
return on capital. Realised revenue growth at five years (1,998 records, formations 2013 to
2020) has a mean of 7.0 per cent and a standard deviation of 10.6 points.

| estimate, revenue at five years | fitted R² | slope | rmse as it is |
|---|---|---|---|
| fundamental | 0.8% | −0.18 | 0.119 |
| historical | 3.4% | 0.11 | 0.157 |
| headline | 1.3% | 0.20 | 0.098 |
| shadow | 1.9% | 0.20 | 0.098 |
| path | 1.3% | 0.38 | 0.094 |
| terminal | 0.0% | — | 0.099 |

At one and three years the fitted R² is below three per cent for every estimate, the
historical one's the highest (2.8 and 2.2 per cent); the fundamental estimate's slope is
negative at every horizon on the whole panel and 0.04 to 0.11 on the records where the rule
chose it, where the shadow reaches 1.3 to 2.5 per cent. On operating income nothing reaches
2.5 per cent at any horizon. The level: the records whose headline is the fundamental
estimate read a median 2.4 per cent and then grew revenue 5.4 per cent a year over five years
and operating income 6.1; the historical ones read 4.3 and grew 5.6 and 6.4; the capped ones
read 6.9 against a history of 17.6 and grew 9.5 and 12.2; over every record the headline's
median is 3.6 per cent and the realised 6.0 and 7.1. Realised five-year revenue growth was
above the headline on 63, 62 and 58 per cent of the records by source. The fifths on the
headline read a median 0.1 per cent at the bottom and 10.4 at the top, a gap of ten points;
what followed was revenue growth of 5.2 and 8.7 per cent at five years, a gap of 3.5 points
(3.2 at one year, 2.4 at three), and operating income growth of 7.1 and 7.9, a gap of under
one point (−2.0 at three years). Persistence: realised revenue growth one year on the year
before has a slope of 0.21 (the paper's 0.24); realised operating income growth −0.03; the
estimates themselves persist at 0.80 (fundamental), 0.77 (historical, a rate over periods
that mostly overlap from one June to the next) and 0.60 (headline).

**Reading.** On the five hundred largest filers the starting growth carries almost no
information about the growth that followed: the best estimate explains three per cent of it
fitted, and as they stand all of them, the model's faded path included, forecast about as
well as the terminal rate alone. The fundamental estimate carries none, its slope on realised
growth negative pooled and near zero where the rule chose it, and it sits a median three
points below what those companies then did; the historical one carries a little, a tenth to
a quarter of its excess persisting, which is the paper's finding in our form, a year-on-year
persistence of 0.21 against his 0.24. A ten-point gap in the headline across the fifths
became three and a half points of revenue growth at five years and nothing in operating
income, as his Table 7 has it. And every estimate reads below the level that followed, the
terminal rate most of all, on a panel of names that were the largest when read.

**Limits.** Survivors twice over: the names were the largest five hundred at formation, and
an outcome is read while the filer still files, so a company bought or delisted inside the
horizon is among the unmatched (544 of 3,062 at three years, 1,063 at five, most of them
the formations whose horizon has not yet closed). The frames carry each period's latest
reported figure, so base and end are both as restated, while the estimates were computed
from what was filed by the date. Operating income before tax stands for after-tax operating
profit. The five-year horizon reaches the formations of 2013 to 2020 only. Nothing here moves
a record or a parameter: this was the measure on which the headline question was to be
weighed; the fitted line of realised five-year growth on the path, 5.7 per cent plus 0.38 of
the path, says what a shrinkage toward the panel's mean would have fitted, and is recorded
for that weighing.

**Decided (2026-10-18): the fundamental estimate stays the headline, with its lean stated on
the record.** The measurement above could not choose, since every estimate forecasts almost
nothing, so the choice was what the headline should mean. It means the statements' reading:
the return on capital and the reinvestment now being made, projected from here, rather than
the past rate carried forward on the assumption that it continues. Where that estimate cannot
be read the record falls back to revenue history held to the return on capital, and there it
extrapolates; the growth shadow block's first limit now says so, and that a fair value the
fundamental estimate heads leans low by about the three points found here. Weighed and not
taken: the historical estimate as headline (the only one carrying anything, 3.4 per cent
fitted, and the noisiest as it stands); a shrunk estimate on the fitted line (the best
calibrated, and a parameter fitted on one decade of one country's largest survivors placed on
every record, undefined for a name outside the panel); a faster fade (toward a terminal rate
that already reads lowest of all, so it deepens the lean); the terminal rate alone (forecasts
as well as any, and gives up the question). Each is a level shift that would make every
stored record incomparable with the next, and none sorts returns differently, so the choice
changes what the number means to a reader and not what the tool finds. Details in
`docs/run.md`, the growth shadow.

### Betas on the rule panel: which forecasts, and the fair values under each

    uv run python/rule_betas.py [--forecast-only]  # -> output/rule_betas/tables.txt, betas.jsonl; about four minutes

The beta study above left two questions open: which beta, if any, belongs in a cost of
equity, and whether one beta belongs on every projection year. Two papers read for the tool
bear on them. Levi and Welch, "Best Practice for Cost-of-Capital Estimates", Journal of
Financial and Quantitative Analysis 52(2), 2017, doi:10.1017/S0022109017000114, ask which
historical beta best forecasts next year's realised beta: a year of daily returns,
Vasicek's shrinkage toward the cross-sectional mean, then a second shrinkage of about a
quarter toward a target near one for large firms reaches an R-squared near a half; an
industry beta in place of the stock's own explains four per cent; and the slope of a future
beta on today's falls from 0.73 one year ahead to 0.52 at five and 0.39 at ten. Keloharju,
Linnainmaa and Nyberg, "Long-Term Discount Rates Do Not Vary Across Firms", NBER Working
Paper 25579, February 2019, doi:10.3386/w25579, find the beta gap of a sort half gone after
five years and recommend about the same discount rate for every stock.

**The forecast.** Each June every name in the rule panel with a year of daily closes gets
six estimates: `ols`, the plain slope on SPY over the year to the date (220 days at least,
winsorised at −3 and 5); `vck`, that slope weighted by the date's cross-sectional variance
of slopes against its own squared standard error, the rest on the cross-sectional mean;
`lw`, three quarters of `vck` and a quarter on one, the second paper's recipe for a large
firm; `fp`, the beta study's estimate (five lagged market terms, the slopes summed, halved
toward one); `industry`, the mean `ols` of the other names in the same two-digit SEC
industry code, five at least; and `one`. The target is the name's `ols` over the twelve
months after. Each estimate is scored as it is (one less the squared errors over the
squared deviations from the targets' mean, and the root mean squared error) and fitted.

**What it found (2026-10-17), descriptively.** 5,108 names and Junes on 734 filers, 2013 to
2025; the targets' standard deviation, the error of knowing nothing, is 0.436.

| estimate | as it is: R² | rmse | fitted: intercept | slope | R² |
|---|---|---|---|---|---|
| one | −1.1% | 0.438 | 1.05 | 0.00 | 0.0% |
| ols | 39.1% | 0.340 | 0.26 | 0.74 | 44.4% |
| vck | 46.8% | 0.318 | 0.12 | 0.89 | 47.6% |
| lw | 46.3% | 0.320 | −0.17 | 1.18 | 47.6% |
| fp | 28.6% | 0.368 | 0.07 | 0.95 | 28.8% |
| industry (4,221 pairs) | 18.8% | 0.398 | 0.12 | 0.88 | 19.2% |

- **A name's own year of daily slopes forecasts its next year's beta about as the second
  paper finds**, an R-squared near a half once shrunk once; a constant forecasts nothing.
- **The second shrinkage adds nothing on these names.** Their mean beta is already near one
  (1.05), so a quarter toward one is a quarter toward the mean twice; the fitted slope on
  `vck` is 0.89, so a tenth would be the right second shrink here, not a quarter, and `lw`'s
  fitted slope of 1.18 says it over-shrinks.
- **The beta study's own estimate forecasts worse** than the plain slope: the lagged terms
  add noise on names that trade with the market, and halving toward one is too much. That
  study's sort stands, the fifths being ranks; this says what not to put in a cost of equity.
- **An industry mean is far behind the name's own**, though better here than the paper's four
  per cent, these codes being coarse and the names large.
- **The horizon.** The slope of the plain slope one to five years ahead on today's `vck`:
  0.89, 0.83, 0.85, 0.77, 0.75; its R-squared 48%, 39%, 35%, 27%, 24%. The paper's 0.73,
  0.66, 0.61, 0.52 at one to five years. Today's beta says half as much about the beta five
  years out as about next year's, and more than half of the deviation from the mean is still
  there, where the fifths followed above lost more than half of their gap.

**The fair values.** The binary is rerun on the rule panel's point-in-time records with each
name's industry set to its own ticker and a beta table of the date carrying that name's
beta, so the valuation reads it as it reads an industry table and the record says so
(`beta_source` reads the table). Four readings per date: `one`, `lw`, `fp`, and `lw_faded`,
one plus half of `lw`'s deviation from it, the third paper's five-year figure put on a
seven-year projection and its terminal value. Across the thirteen dates:

| reading | rank correlation of margins with `one` | median fair value against `one`'s | status changes |
|---|---|---|---|
| lw | 0.86 to 0.96 | −9.5% to +7.0% | 42 of about 3,000 |
| fp | 0.88 to 0.96 | −5.7% to +4.0% | 36 |
| lw_faded | 0.96 to 0.99 | −4.8% to +4.0% | 20 |

The rank correlation of the margin with `lw` beta within a date, median over the dates:
−0.12 under `one`, −0.40 under `lw`, −0.30 under `fp`, −0.26 under `lw_faded`. At a flat
rate the high-beta names already read a little dear; charging them for beta makes them read
dearer still. The sort, cheapest fifth less dearest on the next twelve months over SPY:

| reading | before 2022, pooled | from 2022, pooled | alpha, equal (t) | alpha, capped value (t) |
|---|---|---|---|---|
| one | +0.015 | −0.098 | −0.07 (−0.26) | −0.08 (−0.27) |
| lw | +0.017 | −0.120 | −0.03 (−0.09) | −0.13 (−0.40) |
| fp | +0.016 | −0.100 | −0.03 (−0.11) | −0.03 (−0.10) |
| lw_faded | +0.018 | −0.110 | −0.06 (−0.21) | −0.06 (−0.19) |

- **No beta sorts returns better than none.** The spreads are nothing before 2022 and
  negative since under every reading, the alphas within half a standard error of zero.
  Whatever beta does to a fair value, it does not move the names the market later paid
  into the cheap fifth.
- **Betas move fair values by a few per cent at the median** and reorder the ranks
  moderately; a faded beta moves them half as far, as it must.

What this does and does not say. The market paid for beta on these names (the study
above), a name's beta is forecastable from its own year of daily returns, and a beta in the
cost of equity does not improve what the fair value sorts. So the tool's data neither
condemn a beta in the cost of equity nor reward one. Three limits: the forecast is pooled
over the largest five hundred on one market and its mean and dispersion are theirs; an
industry here is a mean of own betas, not an industry portfolio's beta; and a faded beta
is put on as one number, the deviation halved, where the question is a beta that falls
year by year through the projection, which the model does not take. Nothing here moves a
record or a parameter.

**Decided (2026-10-18): the industry beta stays in the cost of equity, held through the
projection, with its caveat stated on the record.** The question had come from the papers,
not from the tool: four of them argue that high beta is not paid, that an industry beta
forecasts a name's badly, or that beta gaps fade, each of which would make a flat industry
beta systematically wrong. Tested here: two premises replicate (a name's own shrunk beta
forecasts next year's with an R-squared near a half against the industry mean's fifth; the gap
of a sort is half gone in five years), one does not (on these names beta was paid about in
full, as the first paper's own largest-size decile also finds), and the step from a better
beta to a better fair value did not follow: every beta tried moved levels within a tenth,
reordered ranks moderately, and sorted the returns that followed no better than one. The
declared table's middle span, 0.7 to 1.3 across the industries at the United States premium,
is a spread of about 2.7 points in the cost of equity, inside the two to four Levi and Welch
call justified. Weighed and not taken: a name's own shrunk beta, the best forecast and a
fair value that reads its risk from the name's price history, with shrinkage parameters
fitted on the panel; a beta faded toward one over the projection, the one change the data
support in direction, which would cost a discount rate that varies by year through the
engine, the sensitivity, the implied solver and the duration, for a few per cent of level,
with a fade speed to be declared; one beta for all names, which the market disagreed with
for thirteen years. What moves on the record is one field, `cost_of_equity_limits`, beside
the rate: under CAPM with an industry beta it says whose beta it is, that it is held flat
where the names' own converge, which way that leans, and why it stays; without an industry
it says beta is one by convention; under a declared required return, which carries no beta,
it is empty. The vendor's industry string and the six names at the default are a data item,
not a model decision. Details in `docs/flow.md`, required return.

### The rule panel under shifted rates

    uv run python/rule_rates.py                  # -> output/rule_rates/tables.txt, about six minutes

The discount rate follows the risk-free rate, so the model treats every move in the rate
as a move in what the future is worth. Whether the market does the same is measured in
Gormsen and Lazarus, "Interest Rates and Equity Valuations", NBER Working Paper 34814,
February 2026, doi:10.3386/w34814. A change in the trend real rate is a change in time
preference, in expected growth or in risk, and only the first moves equity prices by their
cash-flow duration; three-year US market returns load about −19 on a point of that
pure-discounting part and insignificantly on a point of the raw ten-year yield; and the
pure-discounting part was under half of the fall in the real rate over 1990–2023. A model
that takes every rate move for pure discounting therefore moves too much, by the share of
the move that was growth or risk.

`rule_rates.py` reruns the binary on the rule panel's own point-in-time records under the
United States curve shifted half a point either way, and reads the elasticity of each fair
value, the difference of its logs over the point between the readings; its sign changed is
the duration the model gives the name. A fourth reading replaces the curve by its mean over
the panel's dates plus 35 per cent of the date's distance from it, the paper's share, to ask
what the level and the sort would have been.

**What it found (2026-10-06), descriptively.** The elasticity per point of rate, median over
the valued records of each June:

| June | rate at the projection tenor | elasticity, median | quartiles |
|---|---|---|---|
| 2013 to 2022 | 0.49% to 3.04% | −0.8% to −1.3% | −1.6% to +0.2% |
| 2023 | 3.97% | −22.3% | −25.4% to −19.1% |
| 2024 | 4.33% | −23.5% | −28.2% to −19.8% |
| 2025 | 3.98% | −21.5% | −25.4% to −18.6% |

- **The model has two regimes, with a kink at the terminal growth rate.** Terminal growth
  is held to the risk-free rate where that is lower (the decision of 2026-10-04). Below the
  country's terminal growth the two move together, the gap between the discount rate and
  the growth does not change, and a point of rate moves a fair value by about one per cent,
  the explicit years alone. Above it the growth stands still and a point of rate moves a
  fair value by a fifth to a quarter: the full duration. In this sample the rate crossed
  the 3.6 per cent of the United States' terminal growth between June 2022 and June 2023.
- **Against the market's measured response, each regime is right about one thing.** Below
  the kink the model's response is near the market's response to a raw move in the yield,
  about nothing; above it, near the market's response to pure discounting, about −19 per
  point, which the paper finds to be a minority of real-rate moves. So since 2023 the model
  has carried against every move in the rate a sensitivity the market shows only to the
  part of a move that is time preference.
- **The pass-through reading changes the level since 2023 and nothing else.** With 35 per
  cent of each date's distance from the mean rate, the median margin of safety is −0.02,
  −0.10 and −0.09 in June 2023, 2024 and 2025 where it was −0.11, −0.27 and −0.19; before
  2022 it is within a hundredth of the run's on every date, the cap having already removed
  the rate from the gap; and the sort is untouched, the cheapest fifth less the dearest
  +0.016 before 2022 and −0.097 from it against +0.015 and −0.098.

What this does not decide. The pass-through reading is a question, not a parameter: the
paper gives the share for one country over one span and says the split of a given move
cannot be read in real time without its survey panel. The kink is a property of the
present rule, which was adopted for the low-rate years and does its work there; what the
model should do above the kink, hold the full duration or part of it, was decided on
2026-10-18 under the discount-rate study below, the full duration staying, and the figures
above are what the choice is worth.

### The discount rate on the rule panel: how much of a rate move to take, and a premium that moves

    uv run python/rule_discount.py [--lambdas 0.7 0.46 0.3 0]    # -> output/rule_discount/tables.txt; about ten minutes

The rate study above found the model carrying its full duration against every rate move
above the kink. Gormsen and Lazarus, "Interest Rates and Equity Valuations", NBER Working
Paper 34814, February 2026, doi:10.3386/w34814, find only the pure-discounting part of a rate
move passes to equity yields, about 35 per cent of the US fall over 1990–2023 and almost
none of it after 2000 (pp. 3, 20, 45). Gormsen and Huber, "Corporate Discount Rates", NBER
Working Paper 31329, June 2023, doi:10.3386/w31329, value firms at a country cost of equity
equal to the earnings yield plus two per cent plus trailing ten-year inflation (p. 14,
equation 6), so the premium over the risk-free rate moves against the rate, and find
managers' perceived cost of equity tracks that measure rather than a constant premium on the
rate (p. 20). The sweep reruns the binary on the rule panel's records under both: the curve
moved to its mean over the panel's dates plus λ of the date's distance from it for λ in 0.7,
0.46, 0.3 and 0 (λ = 1 the run, λ = 0 one flat rate on every date, the flat rate of
candidate C3), and the table's premium replaced by the paper's construct on the panel's own
names, the aggregate earnings yield (each name's mean net income over at most five filed
periods, summed, over the sum of market values) plus two per cent plus trailing ten-year CPI
inflation, less the rate at the projection tenor. The CPI series is fetched once from FRED
into the rule panel's cache.

**What it found (2026-10-17), on thirteen Junes.** Below the kink nothing moves: with the
terminal growth held to the rate, the 2013–2022 medians are the same to the second decimal
under every λ. Above it the partial pass-through lifts the medians, 2023–2025 from −0.11,
−0.27 and −0.19 as run to −0.02, −0.10 and −0.09 at λ = 0.3, and the level's swing, the mean
of the yearly medians before 2022 less from 2023, falls from +0.29 to +0.16 at λ = 0.3 and
+0.15 at a flat rate; the sign flip stays (+0.09 before, −0.07 after), and 2021's −0.24 at a
rate of 1.2 per cent is not the rate's doing. The implied premium runs from 7.3 per cent in
2013 to 3.0 in 2024, against the table's 4.46, because the panel's aggregate earnings yield
fell from 4.9 to 2.4 per cent as the names grew dear while the rate rose two points: it
reverses the swing (−0.17 before, +0.06 after; the yearly median's rank correlation with the
rate +0.71 against −0.36 as run), which is the paper's premium moving against the rate taken
to its end. Under every reading the within-date rank correlation of the margins with the
run's is 1.00 (0.98 at the lowest date), because on this panel every name carries a beta of
one and the readings shift every discount rate alike, and the sort is the run's: the
cheapest fifth less the dearest +1.5 points before 2022 and −9.7 to −10.0 from it under all
six.

**What this closes.** Q5 and the discount-rate half of C3: a flat rate, a partial
pass-through and a premium anchored on the market's earnings yield each move the level and
none moves a rank or a return sort on this panel; the beta half of C3 is the betas study
above. What the readings decide between is what the margin of safety means in absolute
terms, a level, and the data cannot choose a level: the market's return has not followed the
margin in either stretch. That was the open question *What the model does above the kink*,
decided below with these figures beside it. Nothing moves on the valuation path.

**Limits.** The rule study's: large US survivors under one lens with a beta of one, so a
discount-rate reading cannot change a rank here that it could on a universe with declared
betas and classes; thirteen formations; the aggregate earnings yield is the panel's own,
not Shiller's CAPE, and net income is not inflation-adjusted; the premium is applied over the
rate at the projection tenor where the paper's is over the short rate.

**Decided (2026-10-18): above the kink the rate passes through in full, with the regime and
its lean stated on the record.** The choice was weighed on this study, the shifted-rates study
and the duration study, and made on the same ground as the growth headline and the beta: the
rate is observed and declared, every damping of it is a share to be asserted, and the data
cannot choose a level. It differs from those two in one respect, said plainly: there the rule
as it stood was the middle of the readings, here it is the extreme, the model discounting the
whole of a rate move where the market discounts the time-preference part. Weighed and not
taken: a partial pass-through anchored on the long-run mean rate, the reading nearest the
market's measured behaviour, which halves the swing and keeps its sign, at the price of a
share and an anchor fitted on one country over one span, the paper itself finding the share
not constant, about a third over 1990 to 2023 and near nothing after 2000, and not readable for
a given move in real time, so that whatever share is set is asserted, and a fair value that
would depend on the rate's history rather than the rate; a premium moving against the rate on
the market's earnings yield, which reverses the swing and would import the market's pricing of
the panel into every name's rate, a dear market making every name read less dear; a flat rate,
the long-run mean on every date, which gives up the one observed input on the time value of
money; and the hold both ways, terminal growth equal to the rate above the table's figure too,
parameter-free and kink-free and blind to rates against the −19 per point the market shows to
time preference. Each is a level shift above the kink and nothing below it; none moves a rank
or a return sort. What moves on the record is one field, `rate_pass_through_limits` beside the
rate: on a path with a terminal value, which regime the record is in, held to the rate or
above the table's figure, what a point of rate does there, and that above the kink a fair
value leans low after rates have risen and high after they have fallen, by an amount the data
cannot fix; on the residual-income paths, which have no terminal value, the pass-through into
the cost of equity alone. The kink stays a known artefact of two rules meeting, documented
here; each alternative is one function and a declared pair of numbers away (`docs/run.md`,
Terminal growth is held to the risk-free rate); and the stretch that would let the data choose
a level is one in which the market's return follows the margin, which neither stretch here
was.

### Why the anchor's level moves with rates

    uv run python/rule_variants.py               # -> output/rule_variants/tables.txt

The rule study's median margin of safety ran above one in the low-rate years. Two things
could do it, and `rule_variants.py` separates them by rerunning the binary on the rule
panel's own records, statements and prices untouched, under four parameter sets: as run;
the terminal growth held to the date's risk-free rate where that is lower; the equity risk
premium of the date's own vintage (`reference/erp_history.json`, Damodaran's implied
premium at the end of the year before) in place of the 2026 figure; and both.

Measured 2026-10-04. In the nine Junes from 2013 to 2021 the median margin of safety was
between +0.33 and +1.65 as run; between −0.24 and +0.32 with the terminal growth held to
the risk-free rate; between +0.14 and +1.29 with the vintage premium alone; and between
−0.28 and +0.02 with both. In June 2020, the lowest rate of the sample, 97
records met the sanity bound as run and 5 with both. From 2023 the rate is above the
terminal growth, the cap binds nothing, and the variants agree. So most of the drift is the
model's: a terminal growth that does not come down with rates leaves almost no gap under a
low discount rate. The rest is the study's: a 2026 premium on a 2016 date. Neither changes
the sort: under every variant the cheapest fifth less the dearest is within two points of
the baseline's in both stretches. On the live run of the day, five of eighty-nine valued
records have a terminal growth above their risk-free rate (Tencent's Hong Kong line, Roche,
Saab, Sea and Teva), Roche with a discount rate of 3.4 per cent against a terminal growth
of 2.0. The decision was made the same day: the model now holds terminal growth to the
risk-free rate (`docs/run.md`, Terminal growth is held to the risk-free rate), and those five
are the records it moved.

### What the quality score is made of

`broad_study.py` also takes the nine-signal score apart, by its value, each signal alone,
and within thirds of market value. Measured 2026-10-04 on the broad panel. Before 2022 the
score as a whole sorted nothing: seven or more less three or fewer was ahead in five years
of ten with a median of zero. What did sort, one signal at a time, were the levels and the
share count: a filer with no more shares than the year before ran about five points ahead
of one with more and was ahead in ten years of eleven; a profitable one and a
cash-generating one ran five and nine points ahead of their opposites, in seven and six
years of eleven. The five signals that compare this year with last, return on assets,
leverage, current ratio, gross margin and asset turnover, each ran level or slightly the
wrong way. From 2022 the levels are stronger, ten and fifteen points in all four years, the
score is close to monotone, and by size it sorts in the smaller two thirds, sixteen and
nine points, and not in the largest third. Survivorship works against these figures, since
the loss-making filers that later failed are the ones missing. So the composite score has
no claim on more room on a record than it has; what the evidence supports is plainer:
whether a company earns and generates cash, and whether its share count is rising.

**What it is not.** Survivors only: a filer is in the panel only if it has a ticker today,
about a third of 2011's filers, so the failed and the acquired are missing and a sort that
would have held them looks better than it was. A frame carries the latest figure reported
for a period, later restatements included. A filer with several share classes is missing.
Sixteen formations are sixteen. Nothing here feeds a model, a belief or a signal.

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

## What the surprise history preceded

    uv run python/surprise_study.py [--holdout]    # -> output/surprise_study/tables.txt, rows.jsonl; seconds

A pattern of beats and misses is only worth reading if it persists. Bordalo, Gennaioli, La
Porta and Shleifer, "Finance Without Exotic Risk", NBER Working Paper 33004, September 2024,
doi:10.3386/w33004, account for the returns of characteristic sorts by the forecast errors
that followed them under one required return for every firm, and find at the firm level that
a name's forecast-error rank a year earlier predicts its expectations-based return over the
next year positively (0.033 standardised, their Table C4) and over three and five years
negatively; the whole firm-level prediction reaches an adjusted R² of three per cent. Their
errors are on fiscal-year earnings against the consensus of a year before; ours are the
quarterly release against the last consensus before it, which is what the tool holds, so
this is the question in the tool's own terms and not the paper's test.

**What it does.** Every release with an estimate and a reported figure, the estimate not
zero, is a surprise in per cent of the estimate's magnitude with its sign; the held-out names
and every release after the holdout's date are set aside unless `--holdout` opens them.
Three questions. Persistence: whether a beat follows a beat more often than a miss (the
transition rates against the base rate); the pooled slope of the next surprise on the last
and on the trailing four, winsorised at the first and ninety-ninth percentile; and whether
what persists is the name or the quarter, the next surprise on the name's mean over every
earlier release beside the last one. The return after: each release's excess over SPY from
the second close after the report date, so the move across the release is left out, to 63,
126 and 252 trading days, by fifths of the surprise within the calendar quarter, from the
anchor study's closes cache. And the arms of the margin sort: on the anchor panel's
quarter-ends, the valued names in fifths on the margin of safety within the date, each
fifth's mean surprise and beat rate over the twelve months after beside its excess return.

**What it found (2026-10-17), descriptively.** 6,554 releases on 165 names with the holdout
aside (1,231 releases set aside); 3,763 since 2020 carry a forward return.

- *A beat follows a beat.* The base rate of a beat is 69.9 per cent; after a beat 77.1, after
  a miss 53.7, after a meet 52.4. The next surprise on the last: slope 0.17, R² 3.1 per cent,
  rank correlation 0.25; on the trailing four, 0.19 and 3.0 per cent; on the name's mean of
  every earlier release, 0.05 and 0.2 per cent, and beside the last surprise it adds 0.02 to
  the last's 0.16. So what persists is the recent surprise, a sixth of it, not a name's
  habit of beating; the paper's firm-level R² is the same three per cent.
- *The return after.* Highest less lowest fifth of the surprise: +2.0 points at 63 days,
  +3.3 at 126, +0.6 at 252; the top fifth positive on 391 of 742 at 63 days, the bottom on
  367 of 762. A small drift for two quarters, gone by a year, on the paper's side at a year
  only in sign.
- *The arms.* On the anchor panel the dearest fifth's names beat by a mean 12.1 per cent
  over the year after the date (577 beats in 774 releases) and ran level with SPY (+0.001);
  the cheapest fifth beat by 4.1 (477 in 672) and ran 6.2 points behind; the fourth fifth,
  3.5 and 12.1 behind. The paper's account, the dear arm's lead coming from its forecasts
  being beaten more than the cheap arm's, is what these years show, on a hundred and
  seventy names.

**Reading.** The surprise history is a readout of the recent past with a little persistence:
the last surprise says something about the next, a sixth of it, and the name's longer record
adds nothing beside it, so the summary's eight-release window is the right one to read and
the twelve-release one adds little. The drift after a surprise is small and short. And the
tool's own finding, that the cheapest fifth by margin ran behind since 2022, has the shape
the paper gives it: the dear names kept beating the Street and the cheap ones did not. That
is a description of why the sort lost, not a reason to change the model, since the surprises
were not foreseeable from the record at the date (the R² of three per cent above).

**Limits.** Street-adjusted EPS against the Street's own last estimate, on the vendor's dated
table of about fifty releases a name; the return questions reach back to 2020 only, the span
of the closes; the paper's errors are annual and ours quarterly, so the contemporaneous slope
(R² 4.1 per cent against its 28) is not the same quantity. The second half of the queue's
item, returns on the revision of next year's forecast, needs the consensus as it stood a
year before each release, which the daily snapshots will carry only from their first day on
disk (2026-10-02); it is not built. Nothing here feeds back.


## The options bound against what followed

    uv run python/bound_study.py [--holdout]      # -> output/bound_study/tables.txt, rows.jsonl; three minutes

Every record valued under `--options` carries `options_expected_return`, the Martin–Wagner
formula on three risk-neutral variances, labelled a lower bound and the market's risk pricing
rather than a forecast. Back, Crotty and Kazempour, "Validity, tightness, and forecasting
power of risk premium bounds", Journal of Financial Economics 144 (2022) 732–760,
doi:10.1016/j.jfineco.2022.02.003, test it as that bound on S&P 500 names 1996–2020: valid
and slack, the realised excess return about twice the bound (Table 2, 9.23 per cent against
4.50 at twelve months); the ranking of names on it carrying almost nothing (Table 7's
Fama–MacBeth slope negative, Table 10's top less bottom fifth 1.93 points on a standard error
of 4.60); what information there is sitting in a name's bound against its own history; and
the Martin formula on the name itself, the Kadan–Tang bound, a lower bound only where delta,
the name's return variance over its covariance with the market, is small, meeting or
exceeding what followed above seven. Their discrete sum over quoted strikes "is always smaller
than the integral" (p. 759).

The records never carried the expected return on the point-in-time dates, so the study
computes the bound from each day's chains with the paper's own sum: the shortest expiry at
least 365 days out with eight quoted strikes each side of the spot, the record's rule for an
expiry, the strikes with both a put and a call quoted and the cheaper of the two, the strike
step times the smaller neighbouring price summed, twice that over the squared spot, per year.
The Martin–Wagner bound is the benchmark's plus half the name's excess over the names' mean,
equal-weighted here where the record weights by market capitalisation. Delta is from the 252
trading days of closes to the day, two hundred at least; the realised excess is over the
one-year Treasury rate at one, three, six and twelve months, annualised, from split-adjusted
closes without dividends. The tables read the last store day of each month, the held-out
names and dates aside.

**What it found (2026-10-17), on 62 names over 302 store days from April 2025, fifteen
month-ends.** The levels replicate: the market bound 2.8–4.2 per cent a year against the
paper's 3.7, the names' Kadan–Tang median 5.8–9.1 against its 6.9, the Martin–Wagner median
0.4–2.6 against its 2.9. The chains ran from a median 0.41–0.50 of spot to 1.46–1.69 over
29–40 strikes; cutting every chain to a common 0.75–1.50 window takes 10–18 per cent off the
bound, and the chains reached that window in 36–82 per cent of a month's names, so a name
quoted narrower understates by up to a fifth against its peers. The record reads the longest
usable expiry; its bound is 0.91–1.00 of the twelve-month one here. The slack is of one
regime: the dates with a twelve-month outcome run April to September 2025, from the trough,
and the mean excess return was 40 per cent against a Martin–Wagner bound of 3.3 and a
Kadan–Tang of 9.1, so the bound was met on 37 per cent of rows and on 21 of 58 names, the
names that fell. The bound ranks with delta (+0.16 within the date, the paper's direction)
and with the twelve-month return that followed +0.26 over five dates, where the paper's slope
is negative; five dates. The paper's delta groups do not reproduce on these names: the
"other" group is thirteen defensive names whose covariance with the market over the year was
not positive, with the lowest bound and the lowest return, not the volatile high-delta names
of the paper, and the "liberal" group holds the semiconductor names that returned 68 per cent.
A name's demeaned bound against its own six-month mean preceded a lower return at one month
and a higher one at six: nothing to read yet.

**What this closes.** The queue asked for delta on the record with a flag where the bound has
met realised returns, the demeaned bound stored for an own-history test, and strike coverage
beside the variance. The record already carries the strike range; the study measures what the
range does and the limit text on the block already says it. Delta is computed and ranks the
bound as the paper says, but a flag on a record would read as a forecast from six months of
one regime, and the names the formula does not bound here are the ones that fell, not a
delta group; not built. Every day's demeaned bound is in `rows.jsonl` for the own-history
test, which needs years the store does not have. One thing on the record was wrong and is
fixed: the block's first scope limit said the formula is a lower bound without the paper's
assumptions, and it is one only for a name whose return covaries positively with the market's
and whose variance is not large against that covariance, possibly an upper bound otherwise;
the limit now says so. The model reads none of it.

**Limits.** Fifteen month-ends and five with a year's outcome, overlapping; one market from a
trough; 62 names the store happens to hold; dividends left out of the realised return; the
paper's bounds come from a vendor's interpolated surface at exact horizons and these from
quotes at the nearest usable expiry. Nothing here feeds back.
