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
}

val load : dir:string -> (t, string) result
(** Reads the five files under [dir]; the error names the file and the parse
    problem. *)

val days_between : from:string -> until:string -> (int, string) result
(** Calendar days from [from] to [until], both ISO 8601 dates (YYYY-MM-DD);
    negative when [until] is earlier. *)

val resolve :
  t ->
  today:string ->
  country:string ->
  industry:string option ->
  (Dcf.assumptions, string) result
(** [country] and [industry] are the vendor's strings; aliases in the tables map
    alternate country spellings to the canonical key. The risk-free tenor is
    ["<projection_years>y"]. *)
