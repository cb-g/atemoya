(** The mid-cycle DCF (22): the FCFF DCF engine run on through-cycle earning power.

    Contract: [value] returns [Ok (inputs, fair_value)] with every field finite, or
    [Error reason]. On the shared definitions (cash, debt, delta_nwc, ebit recipe), per
    period t in the window (every annual period the record carries, newest first, up
    to [midcycle_window_years]): invested capital [IC_t = book_equity + total_debt -
    cash], [NOPAT_t = net_income_t + interest_expense_t * (1 - statutory tax rate)]
    bottom-up from filed lines (25: no operating-income line is needed and the EBIT
    policy does not apply on this path; the through-cycle mean is what dampens
    one-offs), [ROIC_t = NOPAT_t / IC_(t-1)] on beginning capital, so N periods give at
    most N-1 observations. Fewer than 8
    observations is an [Error] naming the count and the periods the provider carries:
    the vendor path's four or five can never serve this model. [ROIC_mid] is the
    arithmetic mean, the bad years included on purpose (the median is recorded, not
    used); [NOPAT_mid = ROIC_mid * IC_latest]; the reinvestment rate is
    [sum (capex - d&a + delta_nwc) / sum NOPAT_t] over the window, sums not a mean of
    ratios, so a negative-NOPAT year cannot poison it; [FCFF_mid = NOPAT_mid * (1 -
    r_mid)]; [g0 = ROIC_mid * r_mid] under the DCF's clamp, lambda, horizon, terminal,
    WACC, net debt and shares. Guards: [ROIC_mid <= 0] (or a non-positive NOPAT sum)
    and [r_mid >= 1] are [Error]s in the words of the record. No price deck: nothing
    outside the filed statements and the DCF's parameters enters. *)

val minimum_observations : int
(** 8 *)

val invested_capital : Boundary_t.fiscal_period -> float option
(** [book_equity + total_debt - cash] when all three are present. *)

val value :
  Dcf.assumptions ->
  country:string ->
  Boundary_t.financials ->
  (Boundary_t.midcycle_inputs * float, string) result
