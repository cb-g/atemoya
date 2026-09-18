(** Starting growth derived from the statements. Never a constant, never from
    the vendor's summary fields.

    Two estimates are always computed and both are reported. [select] takes
    the fundamental one, [roic * reinvestment_rate], when NOPAT and net
    reinvestment are both positive; otherwise the historical revenue CAGR,
    held to ROIC when ROIC is known (a firm cannot compound faster than its
    return on capital without reinvesting more than it earns). With neither
    computable it is an [Error]: the valuation fails rather than assume. *)

type estimate = {
  nopat : float;
  invested_capital : float;  (** book_equity + total_debt *)
  roic : float option;  (** nopat / invested_capital; [None] iff invested_capital <= 0 *)
  reinvestment : float;  (** capex + delta_nwc - depreciation_amortization *)
  reinvestment_rate : float option;  (** reinvestment / nopat; [None] iff nopat <= 0 *)
  g_fundamental : float option;
  g_historical : float option;
  revenue_periods : string list;  (** most recent first *)
}

val cagr : (string * float) list -> float option * string list
(** Revenue by fiscal period end, any order. Uses every period with revenue
    > 0, needs at least three, and measures the span in calendar years from
    the period-end dates. *)

val estimate :
  ebit:float ->
  tax_rate:float ->
  book_equity:float ->
  total_debt:float ->
  capex:float ->
  delta_nwc:float ->
  depreciation_amortization:float ->
  revenues:(string * float) list ->
  estimate

val select : estimate -> (float * Boundary_t.growth_source, string) result

val clamp : lower:float -> upper:float -> float -> float * bool
(** The value held to [lower, upper], and whether that changed it. *)

val path :
  g0:float -> terminal_growth_rate:float -> lambda:float -> projection_years:int -> float list
(** [g_t = terminal + (g0 - terminal) * exp (-lambda * t)] for t = 1..N. *)
