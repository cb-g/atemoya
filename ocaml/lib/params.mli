(** Country and industry parameters from [reference/], with provenance and
    freshness enforcement.

    Contract: [resolve] returns every parameter the generic DCF needs for one
    company, each carrying value, canonical lookup key, source, as_of and age in
    days at [today], or [Error reason]. The reason names the country or the
    parameter concerned. A country absent from any table is an error; a
    parameter older than its table's [max_age_days] is an error, never a
    warning; an [as_of] in the future of [today] is an error. Nothing falls back
    to another country's values. The one default is beta: a missing or unlisted
    industry yields 1.0 with [beta_source = `Default_no_industry] and
    [source = "default_no_industry"]. A curve or FX table that was never fetched is
    an error naming the refresher (29). With [hold_vintage] (point-in-time, 17) a
    parameter whose as_of postdates [today] is not an error: it comes back with a
    negative age, for the valuation to declare as anachronistic. *)

type t = {
  risk_free : Reference_t.risk_free_rates option;
      (** fetched by python/refresh_rates.py to data/reference, never tracked (29); [None] when absent *)
  equity_risk_premiums : Reference_t.country_table;
  tax_rates : Reference_t.country_table;
  industry_betas : Reference_t.industry_table;
  params : Reference_t.params;
  admissibility : Reference_t.admissibility;
  fx_sources : Reference_t.fx_sources;
  fx_rates : Reference_t.fx_rates option;
      (** fetched by python/refresh_fx.py to data/reference, never tracked (29); [None] when absent *)
  base_rates : Reference_t.base_rates option;
      (** fetched by python/base_rates.py to data/reference, never tracked; [None] when absent *)
  rate_sources : Reference_t.rate_sources;
      (** the tracked curve registry: where each country's curve comes from, and which
          domiciles are declared to have none (54) *)
  xbrl_tags : Reference_t.xbrl_tags;
  field_definitions : Reference_t.field_definitions;
      (** the one definition per composed statement field, applied by both fetchers *)
  beliefs : Reference_t.class_beliefs;
      (** the declared class defaults on long-run growth (24); empty when the directory has no beliefs.json *)
  required_returns : Reference_t.required_returns;
      (** the declared required returns (34); both sections empty until the user declares one *)
}

val load : dir:string -> fetched:string -> (t, string) result
(** Reads the declarations under [dir] (and beliefs.json when present) and the two
    fetched files under [fetched] when present; a fetched file that is absent leaves
    [None], and every record that needs it fails naming the refresher to run. The
    error names the file and the parse problem. *)

val hold_to_risk_free : risk_free_rate:Boundary_t.parameter -> Boundary_t.parameter -> Boundary_t.parameter
(** The terminal growth held to the risk-free rate where the table's figure is above it,
    the parameter's source saying so with both figures; unchanged otherwise. Both
    [resolve] and [resolve_cross] apply it. *)

val days_between : from:string -> until:string -> (int, string) result
(** Calendar days from [from] to [until], both ISO 8601 dates (YYYY-MM-DD);
    negative when [until] is earlier. *)

val classification_threshold :
  ?hold_vintage:bool -> t -> today:string -> (Boundary_t.parameter, string) result
(** The bank net-interest-income ratio threshold, with provenance and the same
    freshness rule as every other parameter. *)

val resolve :
  ?hold_vintage:bool ->
  t ->
  today:string ->
  country:string ->
  industry:string option ->
  (Dcf.assumptions, string) result
(** The same-currency path: every parameter from [country], domestic CAPM.
    [country] and [industry] are the vendor's strings; aliases in the tables map
    alternate country spellings to the canonical key. The risk-free tenor is
    ["<projection_years>y"]. *)

val has_curve : Reference_t.risk_free_rates option -> country:string -> bool
(** Whether a risk-free curve exists for the domicile at all. *)

val no_curve_declared : Reference_t.rate_sources -> country:string -> bool
(** (54) Whether reference/rate_sources.json declares the domicile in [no_curve_fallback]:
    a domicile with no reachable official curve, whose single-currency records take the
    trading currency's risk-free rate and keep the domicile's country risk premium. The
    declaration is inert while the domicile does have a curve, and a domicile not named
    there still fails. *)

val domicile_currency : t -> country:string -> (string, string) result
(** The domicile's own currency from reference/fx_sources.json's [country_currencies], the
    vendor's country string mapped through the registry's aliases; an undeclared domicile
    is an error naming it. *)

val resolve_cross :
  ?hold_vintage:bool ->
  ?rf_note:string ->
  t ->
  today:string ->
  domicile:string ->
  rate_country:string ->
  industry:string option ->
  (Dcf.assumptions, string) result
(** The cross-currency path: the risk-free rate and terminal growth from
    [rate_country] (the trading currency's), the statutory tax rate from the
    [domicile], and the international CAPM's components (a declared required return,
    resolved by the valuation per name, replaces them above the risk-free rate, 34): [equity_risk_premium]
    is the mature-market base and [country_risk_premium] the domicile's total
    ERP less that base. Beta from the industry table as always. [rf_note] is appended to
    the risk-free parameter's source when the rate came from somewhere the domicile did
    not choose (54). *)
