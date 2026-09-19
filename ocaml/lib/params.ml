open Reference_t

let ( let* ) = Result.bind

type t = {
  risk_free : risk_free_rates;
  equity_risk_premiums : country_table;
  tax_rates : country_table;
  industry_betas : industry_table;
  params : params;
  admissibility : admissibility;
  fx_sources : fx_sources;
  fx_rates : fx_rates;
  xbrl_tags : xbrl_tags;
  field_definitions : field_definitions;
}

let read reader path =
  match Atdgen_runtime.Util.Json.from_file reader path with
  | v -> Ok v
  | exception
      ( Yojson.Json_error m
      | Atdgen_runtime.Oj_run.Error m
      | Sys_error m
      | Failure m ) ->
      Error (Printf.sprintf "%s: %s" path m)

let load ~dir =
  let file name = Filename.concat dir name in
  let* risk_free =
    read Reference_j.read_risk_free_rates (file "risk_free_rates.json")
  in
  let* equity_risk_premiums =
    read Reference_j.read_country_table (file "equity_risk_premiums.json")
  in
  let* tax_rates = read Reference_j.read_country_table (file "tax_rates.json") in
  let* industry_betas =
    read Reference_j.read_industry_table (file "industry_betas.json")
  in
  let* params = read Reference_j.read_params (file "params.json") in
  let* admissibility =
    read Reference_j.read_admissibility (file "admissibility.json")
  in
  let* fx_sources = read Reference_j.read_fx_sources (file "fx_sources.json") in
  let* fx_rates = read Reference_j.read_fx_rates (file "fx_rates.json") in
  let* xbrl_tags = read Reference_j.read_xbrl_tags (file "xbrl_tags.json") in
  let* field_definitions =
    read Reference_j.read_field_definitions (file "field_definitions.json")
  in
  Ok
    {
      risk_free;
      equity_risk_premiums;
      tax_rates;
      industry_betas;
      params;
      admissibility;
      fx_sources;
      fx_rates;
      xbrl_tags;
      field_definitions;
    }

let days_between = Date.days_between

(* --- lookup --- *)

let canonical aliases key =
  match List.assoc_opt key aliases with Some k -> k | None -> key

let age ?(hold_vintage = false) ~today ~name ~key ~as_of ~max_age_days () =
  let* age_days = days_between ~from:as_of ~until:today in
  if age_days < 0 && hold_vintage then Ok age_days
  else if age_days < 0 then
    Error
      (Printf.sprintf "%s for %s has as_of %s, later than the valuation date %s"
         name key as_of today)
  else if age_days > max_age_days then
    Error
      (Printf.sprintf
         "%s for %s (as_of %s) is %d days old, older than its max_age_days %d"
         name key as_of age_days max_age_days)
  else Ok age_days

let parameter ?(estimated = false) ?(tier = "") ?(tenor_requested = "")
    ?(tenor_used = "") ~value ~key ~source ~as_of ~age_days () : Boundary_t.parameter =
  { value; key; source; as_of; age_days; estimated; tier; tenor_requested; tenor_used }

let country_value ?hold_vintage (table : country_table) ~today ~name ~country =
  let key = canonical table.aliases country in
  match List.assoc_opt key table.values with
  | None -> Error (Printf.sprintf "no %s for country %s" name country)
  | Some value ->
      let* age_days =
        age ?hold_vintage ~today ~name ~key ~as_of:table.as_of ~max_age_days:table.max_age_days ()
      in
      Ok (parameter ~value ~key ~source:table.source ~as_of:table.as_of ~age_days ())

let risk_free ?hold_vintage (rf : risk_free_rates) ~today ~country ~tenor =
  let key = canonical rf.aliases country in
  match List.assoc_opt key rf.countries with
  | None -> Error (Printf.sprintf "no risk-free curve for country %s" country)
  | Some curve -> (
      match List.assoc_opt tenor curve.rates with
      | None ->
          Error
            (Printf.sprintf "risk-free curve for %s has no %s tenor" key tenor)
      | Some value ->
          let key = key ^ "/" ^ tenor in
          let* age_days =
            age ?hold_vintage ~today ~name:"risk_free_rate" ~key ~as_of:curve.as_of
              ~max_age_days:rf.max_age_days ()
          in
          let tenor_used =
            Option.value (List.assoc_opt tenor curve.tenor_used) ~default:tenor
          in
          Ok
            (parameter
               ~estimated:(List.mem tenor curve.estimated)
               ~tier:curve.tier ~tenor_requested:tenor ~tenor_used ~value ~key
               ~source:curve.source ~as_of:curve.as_of ~age_days ()))

let beta ?hold_vintage (table : industry_table) ~today ~industry =
  let default key =
    Ok
      ( parameter ~value:1.0 ~key ~source:"default_no_industry" ~as_of:today
          ~age_days:0 (),
        `Default_no_industry )
  in
  match industry with
  | None -> default ""
  | Some industry -> (
      match List.assoc_opt industry table.values with
      | None -> default industry
      | Some value ->
          let* age_days =
            age ?hold_vintage ~today ~name:"beta" ~key:industry ~as_of:table.as_of
              ~max_age_days:table.max_age_days ()
          in
          Ok
            ( parameter ~value ~key:industry ~source:table.source
                ~as_of:table.as_of ~age_days (),
              `Industry_table ))

let scalar ?hold_vintage (s : scalar) ~today ~name =
  let* age_days =
    age ?hold_vintage ~today ~name ~key:"global" ~as_of:s.as_of ~max_age_days:s.max_age_days ()
  in
  Ok (parameter ~value:s.value ~key:"global" ~source:s.source ~as_of:s.as_of ~age_days ())

let int_scalar ?hold_vintage (p : int_scalar) ~today ~name =
  let* age_days =
    age ?hold_vintage ~today ~name ~key:"global" ~as_of:p.as_of ~max_age_days:p.max_age_days ()
  in
  Ok ({ value = p.value; key = "global"; source = p.source; as_of = p.as_of; age_days } : Boundary_t.int_parameter)

let classification_threshold ?hold_vintage t ~today =
  scalar ?hold_vintage t.params.bank_nii_ratio_threshold ~today ~name:"bank_nii_ratio_threshold"


let resolve ?hold_vintage t ~today ~country ~industry =
  let* projection_years = int_scalar ?hold_vintage t.params.projection_years ~today ~name:"projection_years" in
  let* midcycle_window_years =
    int_scalar ?hold_vintage t.params.midcycle_window_years ~today ~name:"midcycle_window_years"
  in
  let tenor = Printf.sprintf "%dy" projection_years.value in
  let* risk_free_rate = risk_free ?hold_vintage t.risk_free ~today ~country ~tenor in
  let* equity_risk_premium =
    country_value ?hold_vintage t.equity_risk_premiums ~today ~name:"equity_risk_premium"
      ~country
  in
  let* statutory_tax_rate =
    country_value ?hold_vintage t.tax_rates ~today ~name:"statutory_tax_rate" ~country
  in
  let* terminal_growth_rate =
    country_value ?hold_vintage t.params.terminal_growth_rate ~today
      ~name:"terminal_growth_rate" ~country
  in
  let* debt_spread = scalar ?hold_vintage t.params.debt_spread ~today ~name:"debt_spread" in
  let* growth_clamp_lower =
    scalar ?hold_vintage t.params.growth_clamp_lower ~today ~name:"growth_clamp_lower"
  in
  let* growth_clamp_upper =
    scalar ?hold_vintage t.params.growth_clamp_upper ~today ~name:"growth_clamp_upper"
  in
  let* mean_reversion_lambda =
    scalar ?hold_vintage t.params.mean_reversion_lambda ~today ~name:"mean_reversion_lambda"
  in
  let* beta, beta_source = beta ?hold_vintage t.industry_betas ~today ~industry in
  Ok
    {
      Dcf.risk_free_rate;
      equity_risk_premium;
      country_risk_premium = None;
      beta;
      beta_source;
      debt_spread;
      growth_clamp_lower;
      growth_clamp_upper;
      mean_reversion_lambda;
      terminal_growth_rate;
      projection_years;
      statutory_tax_rate;
      midcycle_window_years;
    }

let resolve_cross ?hold_vintage t ~today ~domicile ~rate_country ~industry =
  let* projection_years = int_scalar ?hold_vintage t.params.projection_years ~today ~name:"projection_years" in
  let* midcycle_window_years =
    int_scalar ?hold_vintage t.params.midcycle_window_years ~today ~name:"midcycle_window_years"
  in
  let tenor = Printf.sprintf "%dy" projection_years.value in
  let* risk_free_rate = risk_free ?hold_vintage t.risk_free ~today ~country:rate_country ~tenor in
  let* terminal_growth_rate =
    country_value ?hold_vintage t.params.terminal_growth_rate ~today ~name:"terminal_growth_rate"
      ~country:rate_country
  in
  let* statutory_tax_rate =
    country_value ?hold_vintage t.tax_rates ~today ~name:"statutory_tax_rate" ~country:domicile
  in
  let* mature =
    scalar ?hold_vintage t.params.mature_market_erp ~today ~name:"mature_market_erp"
  in
  let* total_erp =
    country_value ?hold_vintage t.equity_risk_premiums ~today ~name:"equity_risk_premium" ~country:domicile
  in
  let country_risk_premium =
    parameter
      ~value:(total_erp.value -. mature.value)
      ~key:total_erp.key
      ~source:(total_erp.source ^ ", less the mature-market base")
      ~as_of:total_erp.as_of ~age_days:total_erp.age_days ()
  in
  let* growth_clamp_lower =
    scalar ?hold_vintage t.params.growth_clamp_lower ~today ~name:"growth_clamp_lower"
  in
  let* growth_clamp_upper =
    scalar ?hold_vintage t.params.growth_clamp_upper ~today ~name:"growth_clamp_upper"
  in
  let* mean_reversion_lambda =
    scalar ?hold_vintage t.params.mean_reversion_lambda ~today ~name:"mean_reversion_lambda"
  in
  let* debt_spread = scalar ?hold_vintage t.params.debt_spread ~today ~name:"debt_spread" in
  let* beta, beta_source = beta ?hold_vintage t.industry_betas ~today ~industry in
  Ok
    {
      Dcf.risk_free_rate;
      equity_risk_premium = { mature with key = "mature market" };
      country_risk_premium = Some country_risk_premium;
      beta;
      beta_source;
      debt_spread;
      growth_clamp_lower;
      growth_clamp_upper;
      mean_reversion_lambda;
      terminal_growth_rate;
      projection_years;
      statutory_tax_rate;
      midcycle_window_years;
    }
