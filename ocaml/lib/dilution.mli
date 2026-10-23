(** The shares awards and warrants add to the count the price is quoted on (2026-10-23;
    [python/dilution.py], [reference/field_definitions.json] dilution).

    Contract. [shares fin ~market_cap ~price] is the effective count, market cap over price,
    times one plus the financials' dilution ratio, or the effective count where the
    financials carry none. The ratio is the filer's own: its diluted count's increment over
    its basic count for the newest quarter or year with both and a profit, conversion shares
    tagged apart left out. Every model that divides an equity value or a total dividend by the
    count scales it here (the generic and mid-cycle DCF, the residual-income models, the REIT
    model and the build-out readout); the BDC's net asset value per share is the filer's per
    share outstanding and is not scaled. *)

val ratio : Boundary_t.financials -> float
(** The dilution ratio, 0 where none was read. *)

val shares : Boundary_t.financials -> market_cap:float -> price:float -> float
