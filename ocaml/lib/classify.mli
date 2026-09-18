(** Which valuation model applies to a company.

    [Boundary_t.model] is a closed variant, so every caller must handle every
    constructor: a model that cannot run is a compile-time case, never a silent
    fall-through to the generic one. Only [`Generic] exists so far. *)

val classify : Boundary_t.financials -> Boundary_t.model
