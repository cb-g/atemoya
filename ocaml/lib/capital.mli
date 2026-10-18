(** Two readouts from the statements on what the capital is doing: the latest period's
    spending against its depreciation, and the generic DCF's return on capital with and
    without acquired goodwill. Both describe; neither moves a value, a growth or a signal.

    Contract: [intensity] is [Ok] on any period carrying capex and a positive depreciation,
    with [fcff_maintenance] filled when the headline's free cash flow is given; else [Error]
    naming the missing line. [goodwill] is [Ok] on generic DCF inputs whose period files
    goodwill; else [Error] saying so. Neither estimates a missing line. *)

val intensity_limits : string list
val goodwill_limits : string list

val intensity :
  Boundary_t.fiscal_period option -> fcff:float option -> (Boundary_t.capital_intensity, string) result

val goodwill : Boundary_t.fiscal_period option -> Boundary_t.inputs -> (Boundary_t.goodwill_readout, string) result
