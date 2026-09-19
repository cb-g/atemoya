(** The bank model: residual income, or excess returns over book. The field
    report's "price/book against ROE" lens made explicit.

    Contract: [value] returns [Ok (inputs, fair_value)] with every field finite,
    or [Error reason]. Fair equity value is book value today plus the present
    value of [(ROE_t - cost of equity) x book at the start of t] over the
    horizon, and nothing after it: ROE has reverted to the cost of equity by
    then and growth at the cost of equity is value neutral, so there is no
    terminal and no spread parameter (a bank whose ROE equals its cost of
    equity is worth exactly book). ROE starts
    from the statements (mean net income over book, at least two periods) and
    mean-reverts toward the CAPM cost of equity at the shared [lambda]; book
    compounds by retained earnings, with retention derived from dividends paid
    (at least two periods) and never assumed. Every guard is an [Error], never
    a substituted zero. No earnings multiple appears anywhere. The loan-loss
    ratios are recorded for the reader and gate nothing. *)

val roe_path :
  roe_0:float -> cost_of_equity:float -> lambda:float -> projection_years:int -> float list
(** [ROE_t = ke + (roe_0 - ke) * exp (-lambda * t)] for t = 1..N. *)

type schedule = {
  book_value_path : float list;  (** start-of-year book for years 1..N *)
  excess_return_path : float list;  (** (ROE_t - ke) x book at start of t *)
  pv_excess_returns : float;
  ending_book : float;  (** book at the end of year N *)
}

val schedule :
  book_equity:float -> cost_of_equity:float -> retention:float -> roe_path:float list -> schedule

val mean_ratio :
  (string * float * float) list -> min_periods:int -> (float * string list) option
(** Mean of [numerator / denominator] over the periods given as
    [(period_end, numerator, denominator)] with denominator > 0; [None] with
    fewer than [min_periods] usable. The periods used, most recent first. *)

val value :
  ?book:(Boundary_t.fiscal_period -> float option) ->
  Dcf.assumptions ->
  country:string ->
  Boundary_t.financials ->
  (Boundary_t.residual_income_inputs * float, string) result
(** [book] is the book value read from a period; the default is reported
    stockholders' equity. The insurer model passes AOCI-adjusted book. *)
