# Tried, measured, removed

What was built, measured and taken out again, with what would have to be different for it
to be worth building again. A negative result is a result; without this page the same idea
comes back in a new shape every few months and teaches the same lesson each time.

## Capitalising research and development (built and removed 2026-10-03)

**The idea.** The anchor study and the naive baseline found the anchors rank names much as a
plain cheapness sort does, and that the 2022 to 2026 market did not pay cheapness. The
intangibles literature blames that on research being expensed: a company investing through
its income statement shows less profit and less capital than one building plants. So the
generic DCF was given a shadow that treats research and development as an investment:
the filed expense of the latest year and the five before it capitalised straight-line, the
asset added to invested capital, the year's amortisation replacing the year's expense in
operating profit, the net investment added to reinvestment. The shadow carried its own fair
value and margin of safety beside the headline's.

**What was measured.** On the point-in-time panel, 448 generic-DCF rows on 32 names over
eighteen quarter-ends, the holdout unread: the shadow's margin of safety ranked names as the
headline's did, a rank correlation within the date of 0.99 at the median, 58 rows changing
quintile; the cheapest fifth less the dearest ran 21 points below at a year on both. On the
live snapshot the fair value moved by a few per cent on most of 38 names and closed no large
gap between an anchor and a price.

**Why, and this is the lesson.** In a free-cash-flow DCF, capitalising an expense that was
paid in cash changes no cash flow. After-tax operating profit rises by the net investment
and reinvestment rises by the same amount, so free cash flow is identical on both sides by
construction; the block recorded it as its own check and it held on every name. The only
way the adjustment reaches the value is through the return on capital and the reinvestment
rate, that is through the starting growth, and that lever is small. The literature's finding
is about book-value and earnings ratios, which capitalisation does change; a cash-flow
model was never exposed to the distortion in the first place.

**What would not rescue it.** A life per industry, ten years for a drug and three for
software, changes the size of a small effect and not its kind. Capitalising selling and
marketing spend as well is the same adjustment on a second line. Neither changes a cash flow.

**What would justify building it again.** A model here whose value depends on book capital
or accounting earnings and not on cash flow: a residual-income or economic-profit model for
operating companies, a multiple of book or of earnings, or a quality measure built on the
return on capital. There the adjustment changes the answer and should be measured again.

**What it found on the way, which stays.** The growth rule has a cliff at zero net
reinvestment: a name reinvesting slightly less than nothing takes its historical revenue
growth, one reinvesting slightly more takes the fundamental estimate, which is near zero
for a small reinvestment. Capitalising research tipped four names across it and their
starting growth fell from above ten per cent to about one. That is a property of the
headline model and is being addressed on its own. And one filer taught a tagging lesson:
Johnson & Johnson files its research spend under the element that excludes acquired
in-process research and a figure a hundredth of the size under the plain element, so an
element's name is not proof of what a filer put under it.

The code is in the history: the shadow was added in `12cedbe` and removed in the commit
that added this page.

## Peer-implied value (measured twice, kept as a study measure, 2026-10-04)

**The idea.** After Bartram and Grinblatt: each June, regress market value across all
companies on their accounting items, read the fitted value as what the market pays that
year for those accounts elsewhere, and sort on the gap between it and a company's own
price. No return enters the fit, so there is little room to snoop.

**What was measured.** On the broad panel, about thirty thousand rows on three thousand
filers, per dollar of assets with every column winsorised. With four items (equity,
revenue, net income, operating cash flow) the widest gap less the narrowest ran three
points the wrong way before 2022 and one since, ahead in four years of twelve and one of
four. With eight, adding operating income, current assets, current liabilities and
long-term debt on the two thirds of rows that carry them all, three points the wrong way
before and two since, ahead in six of twelve and two of four. The yearly figures swing
from minus forty-five points to plus fifty-seven and move with book-to-price.

**Why.** With items this few the fit is close to a book and earnings multiple, so the gap
is the value factor by another road, and the value factor did nothing in this sample.

**What would justify more.** The paper uses twenty-one items and a robust fit, on a sample
with the delisted names in it. The frames data could supply more items; it cannot supply
the delisted names' returns, and without them a wider fit is still a survivors' value sort.
The measure stays in `broad_study.py` so the next reader sees the figures and not the idea.

## A cache on reading option chains (tried and reverted, 2026-10-04)

A run with the options store took two and a half minutes, and the first guess was that a
chain, megabytes of JSON, was being read several times over. Caching the read changed the
time by two seconds. The cost was the smile fit, run several times for the same chain and
expiry; caching the fit's result took the run from 152 seconds to 42 with byte-identical
output. Measure before optimising: the read cache was removed.

## Taking the largest revenue element (measured and not built, 2026-10-03)

**The idea.** Blue Owl tags a fee line under the element for total revenues and its total
under the contract-revenue element, so the record reads a part of the whole. Taking the
largest of the revenue elements a filer files for a year would fix it.

**What was measured.** On the cached filings of every universe filer: Vistra, Freeport and
Southern file a total below their contract revenue, correctly, because hedging losses and
pricing adjustments are negative revenue. The rule would have replaced three right figures
to repair one wrong one.

**What stands instead.** The first element in the declared order, and a scope limit on Blue
Owl saying the revenue read is a part. A filer's own mis-tagging is not repaired by a rule
that is wrong for filers who tag correctly.
