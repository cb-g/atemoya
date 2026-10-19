(** The declared growth (--growth FILE): the generic or mid-cycle DCF on a reader's own
    starting growth, or on the starting growth at which the headline's own fading path
    reaches a free cash flow the reader declares for a year inside the projection. Beside
    the headline, never the headline.

    An entry is exactly one of [g0] (percentage points) or [fcff] (in the record's currency,
    its major unit) with [currency] and [fiscal_year_ending], an optional [steady_fcff]
    beside [fcff], and [why] and [as_of]. The loader is strict: an unknown or missing field,
    both bases or neither, a non-positive free cash flow, a g0 at or below -100, an empty
    why or a malformed as_of is an [Error] naming the entry. Nothing here estimates a field.

    Contract. [of_inputs] takes a completed generic or mid-cycle DCF's inputs and fair value
    and returns the block, or [Error] with the reason there is none. A declared g0 runs as
    declared through [Growth.path] and [Implied.dcf_fair_value], not held to the clamp. A
    declared free cash flow names the calendar year its fiscal year ends in; that year less
    the base period's must lie in 1 to [projection_years], and the record's currency must be
    the declaration's. The starting growth is then solved by bisection over
    [Implied.level_domain] so the path from the base free cash flow reaches the declared one
    in that year, the flow there being strictly increasing in the starting growth; past
    either end is an [Error]. With [steady_fcff], every flow after the declared year and the
    terminal value are scaled by [steady_fcff / fcff]: the years after it grow along the
    path from the steady figure. The discount rate, the fade, terminal growth, net debt and
    shares are the headline's own. The record's fair value, margin of safety and signal are
    never moved by it. *)

val load_names_string : string -> (Reference_t.name_growth, string) result
val load_names : string -> (Reference_t.name_growth, string) result

val version : Reference_t.growth_declaration -> string
(** [as_of-<7 hex of the declared fields>-name]: changes when any field changes. *)

val stepped_fair_value : Boundary_t.inputs -> g0:float -> step_after:int -> ratio:float -> float
(** The fair value per share on the headline's arithmetic with every flow after year
    [step_after], and the terminal value, scaled by [ratio]. *)

val of_inputs :
  Reference_t.growth_declaration ->
  midcycle:bool ->
  currency:string option ->
  Boundary_t.inputs ->
  fair_value:float ->
  (Boundary_t.declared_growth, string) result
(** [currency] is the record's, the basis of its price and of [inputs.fcff]. *)

val not_run : model:Boundary_t.model option -> string
(** Why a declared name's record has no block when its model gave no generic or mid-cycle
    DCF inputs. *)
