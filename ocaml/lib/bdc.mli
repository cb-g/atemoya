(** The BDC lens (59): the filed net asset value per share, with the coverage of the
    distribution beside it.

    Contract: [value] returns [Ok (inputs, fair_value)] with every field finite, or
    [Error reason]. **Fair value is the net asset value per share the filing states, and
    nothing else.** This is not a discount model and there is no projection in it: a
    business development company is a portfolio of loans and equity stakes the filer marks
    to fair value every quarter, and the tool does not second-guess a mark on assets it
    cannot see. No discount rate, no growth rate and no country parameter appears on the
    record; the parameters gate the pipeline, they are not inputs to the lens, and
    [Dcf.assumptions] is taken and ignored so the routing stays uniform.

    The readouts are what make the mark useful, and each is a ratio of filed lines:
    [price_to_nav] (above one is a premium, and the signal follows the margin of safety as
    everywhere, so a premium reads Sell and a discount Buy), [nii_yield_on_nav] (what the
    portfolio earns against the mark), [distribution_yield] (what the holder is paid), and
    [nii_coverage] (net investment income per share over distributions per share; below one
    the distribution is paid out of capital and erodes the mark, which [coverage_note]
    says). [nav_cagr] is the trend of the mark itself over the filed periods, at least two,
    measured in calendar years as every other growth here is.

    Both per-share figures use the period's own weighted-average count, per
    [shares_for_flows]: a flow per share may use no other denominator. Every guard is an
    [Error] naming what failed — an absent filed line, a non-positive mark, a non-positive
    distribution (there is then no coverage to read, and coverage is the point), or fewer
    than two periods with a filed mark. [caveat] states on every record that the mark is
    the filer's own. *)

val caveat : string

val nav_series : Boundary_t.financials -> (string * float) list
(** Period end and the filed net asset value per share, newest first, over the periods that
    carry a positive one. *)

val value :
  Dcf.assumptions ->
  country:string ->
  Boundary_t.financials ->
  (Boundary_t.bdc_inputs * float, string) result
