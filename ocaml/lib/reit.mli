(** The REIT model: a dividend discount on the dividend FFO covers.

    Contract: [value] returns [Ok (inputs, fair_value)] with every field finite,
    or [Error reason]. FFO arrives on the period from the fetch (the NAREIT
    recipe from filed tags, components recorded); the model never derives it.
    D0 = min(dividends_paid, ffo) / effective shares: an uncovered dividend is
    never valued, and [coverage] records dividends over FFO. g0 is the CAGR of
    FFO per cover-page share over the filed periods (at least two, else
    [Error]), clamped as the DCF clamps and mean-reverting toward terminal growth
    at the shared lambda; the cost of equity is CAPM with the industry beta; the
    cost of equity must exceed terminal growth. Value per share = sum of
    D_t / (1 + ke)^t + D_N (1 + g_T) / (ke - g_T) / (1 + ke)^N. Every guard is
    an [Error], never a substituted value. The caveat that FFO overstates
    distributable cash by what the filer does not tag is on every record. *)

val caveat : string

val dividend_path : d0:float -> growth_path:float list -> float list
(** D_1 .. D_N: D0 compounded along the growth path. *)

val present_value :
  dividend_path:float list -> cost_of_equity:float -> terminal_growth_rate:float ->
  float * float * float
(** (pv of the explicit dividends, terminal value at N, pv of the terminal). *)

val value :
  Dcf.assumptions ->
  country:string ->
  Boundary_t.financials ->
  (Boundary_t.reit_inputs * float, string) result
