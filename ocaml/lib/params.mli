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
    [source = "default_no_industry"]. *)

type t = {
  risk_free : Reference_t.risk_free_rates;
  equity_risk_premiums : Reference_t.country_table;
  tax_rates : Reference_t.country_table;
  industry_betas : Reference_t.industry_table;
  params : Reference_t.params;
  admissibility : Reference_t.admissibility;
  fx_sources : Reference_t.fx_sources;
  fx_rates : Reference_t.fx_rates;
}

val load : dir:string -> (t, string) result
(** Reads the eight files under [dir]; the error names the file and the parse
    problem. *)

val days_between : from:string -> until:string -> (int, string) result
(** Calendar days from [from] to [until], both ISO 8601 dates (YYYY-MM-DD);
    negative when [until] is earlier. *)

val classification_threshold :
  t -> today:string -> (Boundary_t.parameter, string) result
(** The bank net-interest-income ratio threshold, with provenance and the same
    freshness rule as every other parameter. *)

val bank_terminal_roe_spread :
  t -> today:string -> (Boundary_t.parameter, string) result
(** The residual-income model's terminal excess return, with provenance and
    the same freshness rule as every other parameter. *)

val insurer_terminal_roe_spread :
  t -> today:string -> (Boundary_t.parameter, string) result

val resolve :
  t ->
  today:string ->
  country:string ->
  industry:string option ->
  (Dcf.assumptions, string) result
(** The same-currency path: every parameter from [country], domestic CAPM.
    [country] and [industry] are the vendor's strings; aliases in the tables map
    alternate country spellings to the canonical key. The risk-free tenor is
    ["<projection_years>y"]. *)

val resolve_cross :
  t ->
  today:string ->
  domicile:string ->
  rate_country:string ->
  industry:string option ->
  (Dcf.assumptions, string) result
(** The cross-currency path: the risk-free rate and terminal growth from
    [rate_country] (the trading currency's), the statutory tax rate from the
    [domicile], and the international CAPM's components: [equity_risk_premium]
    is the mature-market base and [country_risk_premium] the domicile's total
    ERP less that base. Beta from the industry table as always. *)
