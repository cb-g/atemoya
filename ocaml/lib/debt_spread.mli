(** The pre-tax spread over the risk-free rate a company borrows at, from a synthetic rating
    (2026-10-23; [reference/default_spreads.json]).

    Contract. [resolve rule ~fallback ~ebit ~interest_expense ~total_debt ~period_end] is a
    parameter whose value is the spread of the rating the interest coverage, [ebit] over
    [interest_expense], earns on the rule's table, the large firms' or, below the table's
    market-cap threshold in dollars, the smaller and riskier firms'; its key is the rating and
    its source names the coverage, its two figures, the period, the table and the vintage. A
    row is the last whose [above] the coverage reaches, so every coverage has one. Where the
    period carries no interest expense above nil, the [fallback], the declared flat spread, is
    returned with a source that says why: beside debt the rating cannot be read, and without
    debt the spread carries no weight. Nothing else is read; no rating agency's rating is. *)

type size = Large | Small

type rule = {
  spreads : Reference_t.default_spreads;
  age_days : int;
  size : size;
  size_note : string;  (** why this table: the market cap in dollars against the threshold *)
}

val row : Reference_t.default_spread_row list -> float -> Reference_t.default_spread_row option
(** The last row whose [above] the coverage reaches. *)

val with_size : rule -> market_cap_usd:(float, string) result -> rule
(** The table for a market cap in dollars; the large firms' where it could not be converted,
    the note naming why. *)

val resolve :
  rule ->
  fallback:Boundary_t.parameter ->
  ebit:float ->
  interest_expense:float option ->
  total_debt:float ->
  period_end:string ->
  Boundary_t.parameter
