(** The mid-cycle DCF (22): the FCFF DCF engine run on through-cycle earning power.

    Contract: [value] returns [Ok (inputs, fair_value)] with every field finite, or
    [Error reason]. On the shared definitions (cash, debt, delta_nwc, ebit recipe), per
    period t in the window (every annual period the record carries, newest first, up
    to [midcycle_window_years]): invested capital [IC_t = book_equity + total_debt -
    cash]. [NOPAT_t] follows one of two recipes, chosen per name and named in
    [nopat_recipe], never mixed inside a window. Where every period in the window carries
    an operating-income line the filer itself reported ([ebit_recipe = operating_income]),
    [NOPAT_t = ebit_t * (1 - tax_t)], [tax_t] the period's effective rate where the DCF's
    own rule derives one and the statutory rate otherwise: a loss on extinguishing debt, a
    mark on an investment or any other non-operating item then never enters the window as
    an operating year, and [roic_mid_bottom_up] records the other recipe's mean beside it.
    Otherwise [NOPAT_t = net_income_t + interest_expense_t * (1 - statutory tax rate)],
    bottom-up from filed lines (25): a filer with no operating-income line has only a
    derived one, which is not held to a filed figure year by year, and the through-cycle
    mean is then what dampens one-offs. The EBIT policy does not apply on this path under
    either recipe: the first reads only filed lines and the second reads none.
    [ROIC_t = NOPAT_t / IC_(t-1)] on beginning capital, so N periods give at
    most N-1 observations. A period whose opening capital is below
    [midcycle_scale_floor * IC_latest] is left out of the return average and listed as an
    exclusion reading "opening capital below the scale floor" (55): the ratio would be a
    number about a business a fraction of the present one's size, and the window is there
    to hold two commodity cycles, not two corporate lifetimes. The reinvestment sums are
    untouched by the floor, being sums rather than a mean of ratios. Fewer than 8
    observations, counting what the floor left, is an [Error] naming the count and the
    periods the provider carries:
    the vendor path's four or five can never serve this model. [ROIC_mid] is the
    arithmetic mean, the bad years included on purpose (the median is recorded, not
    used); [NOPAT_mid = ROIC_mid * IC_latest]; the reinvestment rate is
    [sum (capex - d&a + delta_nwc) / sum NOPAT_t] over the window, sums not a mean of
    ratios, so a negative-NOPAT year cannot poison it; [FCFF_mid = NOPAT_mid * (1 -
    r_mid)]; [g0 = ROIC_mid * r_mid] under the DCF's clamp, lambda, horizon, terminal,
    WACC, net debt and shares. Guards: [ROIC_mid <= 0] (or a non-positive NOPAT sum)
    and [r_mid >= 1] are [Error]s in the words of the record. A negative measured rate is
    floored at zero (33): no net reinvestment through the cycle, [FCFF_mid = NOPAT_mid],
    [g0 = 0], the measured rate and the flag on the record; disinvestment cash flows are
    not valued. No price deck: nothing
    outside the filed statements and the DCF's parameters enters. *)

val minimum_observations : int
(** 8 *)

val minimum_reinvestment_periods : int
(** 8: periods carrying every flow the reinvestment sums need (27). *)

val invested_capital : Boundary_t.fiscal_period -> float option
(** [book_equity + total_debt - cash] when all three are present. *)

val value :
  Dcf.assumptions ->
  country:string ->
  required:string list ->
  Boundary_t.financials ->
  (Boundary_t.midcycle_inputs * float, string) result
(** [required] are the fields the latest period must carry for this model, from
    [field_definitions.json]'s [required_on_latest_period] (the balance sheet: the model
    applies a through-cycle return to today's capital). Inside the window a period
    lacking a flow is excluded from the sum it cannot serve and named on the record
    (27); the guards count what remains; the spot fcff is a readout, null with reason
    when the latest period lacks a flow. *)
