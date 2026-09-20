(** Assembles the per-ticker output contract: the declared entity class checked
    against the statement signatures, the admissibility decision, the currency
    gate, parameter resolution, the routed model, sanity checks, signal, floor,
    and the [`Failed]-with-nulls shape.

    Order: declaration and class check -> admissibility -> country -> currency
    agreement (a filing's unit against the vendor's statement currency) -> field
    definitions -> filing age -> currency gate -> resolve parameters -> the first
    admissible model -> sanity bound -> record. The field-definitions gate: a
    record whose periods carry a composition naming another definition than
    [reference/field_definitions.json] (or an ebit recipe it does not list) is
    [`Failed] naming both, so statements fetched under one definition are never
    valued under another; a record naming none passes. The currency gate: with both currencies present and equal the
    same-currency path runs exactly as before; otherwise the record's statement
    totals are converted at one recorded FX rate into the trading currency, the
    parameters come from [Params.resolve_cross], the same model runs on the
    converted record, and the conversion rides on its inputs. A missing currency
    field or FX pair is [`Failed] naming it. On the dcf path a derived ebit (any
    recipe but operating income) runs only when the record's cross-check found it
    within threshold of the vendor's operating income; otherwise the
    [refinement_policy.on_miss] [`Failed]; the mid-cycle DCF (22) is outside the policy
    since its NOPAT is bottom-up from net income and interest expense (25). Each model's arithmetic lives in its own module. A record's [scope_limits]
    are the entry's own followed by the class's defaults from the admissibility row. [floor] is always populated and gates nothing. An [`Ok] record carries
    the implied readouts ([Implied]), the sensitivity block ([Sensitivity]) and, on a
    growth-then-terminal path, the belief map's price contour ([Belief_map]) (23) and,
    given a declared belief for its class or name, the implied long-run growth and the
    probability of overpaying under it ([Beliefs]) (24); the headline never depends on
    them. [name_beliefs] are per-name entries from a --beliefs file, overriding the tracked
    ones and the class defaults; [name_required_returns] likewise for the declared
    required return (34), which replaces CAPM above the risk-free rate on every model and
    is recorded beside the CAPM rate on every Ok record. [options], given only under
    --options DIR, looks a ticker's option chain up ([Options_store.lookup], with the
    no-lookahead window on the point-in-time panel (37)); every Ok record then carries the
    market-implied readout ([Market_implied]) (36) or the reason it has none, the lookup's
    when it found no chain; without it neither field exists. *)

type thresholds = {
  buy_above : float;  (** margin of safety at or above which the signal is [`Buy] *)
  sell_below : float;  (** margin of safety at or below which the signal is [`Sell] *)
  sanity_bound : float;  (** a margin of safety above this is [`Failed] *)
}

val default_thresholds : thresholds

val signal : thresholds -> float -> Boundary_t.signal

(** A human's declaration of what the company is, from the universe file or the
    command line. *)
type declaration = {
  entity_class : Boundary_t.entity_class;
  scope_limits : string list;
  adr_ratio : float option;  (** (42) ordinary shares per depositary receipt, declared on the universe entry *)
}

val receipt_tolerance : float
(** 0.03: the relative disagreement beyond which the receipt-ratio check flags. *)

val receipt_check : declared:float option -> Boundary_t.financials -> Boundary_t.receipt_check option
(** (42) On a record carrying the cover page, with a declared ratio or a financial currency
    other than its trading currency: the cover page's ordinary count over the effective
    shares against the declared ratio, the count first multiplied by the record's
    cover_page_split_factor (44) when it carries one; the flag names both numbers on a disagreement beyond
    the tolerance, or the implied ratio when none is declared and it is not 1. A flag,
    never a gate. *)

val currency_agreement : Boundary_t.financials -> (unit, string) result
(** [`Failed] naming both when the filing's currency and the vendor's disagree. *)

val definitions_check :
  Reference_t.field_definitions -> Boundary_t.financials -> (unit, string) result
(** The field-definitions gate on every period of the record. *)

val point_in_time_gates : Boundary_t.financials -> (unit, string) result
(** A point-in-time record (17) with no filed statements, cover-page shares or
    rate history on its date is [`Failed] naming which. *)

val anachronistic :
  class_check:Boundary_t.class_check option -> Boundary_t.model_inputs option -> string list
(** The parameters a record used whose vintage postdates its valuation date, as
    "name (vintage as_of)"; non-empty only on point-in-time records, whose held
    vintages are declared rather than refused. *)

val run :
  ?thresholds:thresholds ->
  ?name_beliefs:Reference_t.name_beliefs ->
  ?name_required_returns:Reference_t.name_required_returns ->
  ?options:(string -> (Boundary_t.option_chain, string) result) ->
  Params.t ->
  today:string ->
  model_version:string ->
  declaration:declaration option ->
  Boundary_t.financials ->
  Boundary_t.valuation
(** [today] is the ISO 8601 date parameter ages are measured at; it is echoed
    as [valued_on]. [model_version] ([Model_version.stamp]) is echoed on the
    record: the code that produced it. *)
