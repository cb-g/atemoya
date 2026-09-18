open Atemoya

let today = "2026-09-10"

(* --- boundary fixtures --- *)

let period ?(period_end = "2025-09-30") ?ebit ?pretax_income ?tax_provision
    ?depreciation_amortization ?capex ?delta_nwc ?cash ?total_debt () :
    Boundary_t.fiscal_period =
  {
    period_end;
    ebit;
    pretax_income;
    tax_provision;
    depreciation_amortization;
    capex;
    delta_nwc;
    cash;
    total_debt;
  }

let financials ?(currency = Some "USD") ?(price = Some 10.)
    ?(market_cap = Some 5000.) ?(country = Some "United States")
    ?(industry = Some "Consumer Electronics") periods : Boundary_t.financials =
  {
    ticker = "TEST";
    as_of = "2026-09-10T00:00:00+00:00";
    currency;
    price;
    market_cap;
    country;
    industry;
    periods;
    notes = [];
  }

let full_period ?period_end () =
  period ?period_end ~ebit:1200. ~pretax_income:1000. ~tax_provision:500.
    ~depreciation_amortization:200. ~capex:50. ~delta_nwc:50. ~cash:1000.
    ~total_debt:5000. ()

(* --- parameter fixtures --- *)

let param ?(key = "k") ?(source = "test") ?(as_of = today) ?(age_days = 0)
    ?(estimated = false) value : Boundary_t.parameter =
  { value; key; source; as_of; age_days; estimated }

(* The first version's round numbers, now as provenance-carrying parameters:
   tax 500 / 1000 = 0.5;  fcff = 1200 * 0.5 + 200 - 50 - 50 = 700
   ke = 0.02 + 1.0 * 0.10 = 0.12;  kd = 0.02 + 0.02 = 0.04, after tax 0.02
   E = D = 5000  ->  wacc = 0.5 * 0.12 + 0.5 * 0.02 = 0.07
   zero growth   ->  EV = 700 / 0.07 = 10000 whatever the horizon
   net debt = 5000 - 1000 = 4000;  equity = 6000;  shares = 5000 / 10 = 500
   fair value = 12;  margin of safety = 0.2  ->  Hold *)
let assumptions : Dcf.assumptions =
  {
    risk_free_rate = param 0.02;
    equity_risk_premium = param 0.10;
    beta = param 1.0;
    beta_source = `Industry_table;
    debt_spread = param 0.02;
    growth_rate = param 0.0;
    terminal_growth_rate = param 0.0;
    projection_years =
      { value = 5; key = "global"; source = "test"; as_of = today; age_days = 0 };
    statutory_tax_rate = param 0.21;
  }

(* A reference set as JSON, exercising aliases, estimated cells and staleness.
   Singapore is fresh with interpolated cells; Germany's curve is 97 days old
   against a 45-day limit. *)
let risk_free_json =
  {|{
  "max_age_days": 45,
  "tenors": ["1y", "3y", "5y", "7y", "10y"],
  "aliases": {"USA": "United States"},
  "countries": {
    "United States": {"source": "FRED", "as_of": "2026-09-08",
      "rates": {"1y": 0.037, "3y": 0.040, "5y": 0.043, "7y": 0.0468, "10y": 0.050}},
    "Singapore": {"source": "copied", "as_of": "2026-09-08",
      "rates": {"1y": 0.015, "3y": 0.016, "5y": 0.017, "7y": 0.018, "10y": 0.019},
      "estimated": ["3y", "7y"]},
    "Germany": {"source": "copied", "as_of": "2026-06-05",
      "rates": {"1y": 0.025, "3y": 0.026, "5y": 0.027, "7y": 0.028, "10y": 0.030}}
  }}|}

let country_table_json ~source values =
  Printf.sprintf
    {|{"source": %S, "as_of": "2026-01-01", "max_age_days": 400,
       "aliases": {"USA": "United States"}, "values": %s}|}
    source values

let params_json =
  {|{
  "projection_years": {"value": 7, "source": "seed", "as_of": "2026-06-01", "max_age_days": 400},
  "growth_rate": {"value": 0.05, "source": "assumption", "as_of": "2026-09-01", "max_age_days": 400},
  "debt_spread": {"value": 0.01, "source": "assumption", "as_of": "2026-09-01", "max_age_days": 400},
  "terminal_growth_rate": {"source": "seed", "as_of": "2026-06-01", "max_age_days": 400,
    "aliases": {"USA": "United States"},
    "values": {"United States": 0.02, "Singapore": 0.025, "Germany": 0.015}},
  "unwired": {"growth_clamp": {"upper": 0.5}}
  }|}

let params : Params.t =
  {
    risk_free = Reference_j.risk_free_rates_of_string risk_free_json;
    equity_risk_premiums =
      Reference_j.country_table_of_string
        (country_table_json ~source:"Damodaran Jan 2026"
           {|{"United States": 0.0446, "Singapore": 0.0423, "Germany": 0.0423}|});
    tax_rates =
      Reference_j.country_table_of_string
        (country_table_json ~source:"PwC 2026"
           {|{"United States": 0.21, "Singapore": 0.17, "Germany": 0.30}|});
    industry_betas =
      Reference_j.industry_table_of_string
        {|{"source": "sector betas 2026", "as_of": "2026-01-01", "max_age_days": 400,
           "values": {"Consumer Electronics": 0.9, "Software - Application": 1.3}}|};
    params = Reference_j.params_of_string params_json;
  }

(* --- testables --- *)

let via_json to_string =
  Alcotest.testable
    (fun fmt v -> Format.pp_print_string fmt (to_string v))
    ( = )

let status = via_json Boundary_j.string_of_status
let signal = via_json Boundary_j.string_of_signal
let tax_rate_source = via_json Boundary_j.string_of_tax_rate_source
let beta_source = via_json Boundary_j.string_of_beta_source
let valuation = via_json Boundary_j.string_of_valuation
let approx = Alcotest.float 1e-9
let check_float = Alcotest.check approx

let contains haystack needle =
  let n = String.length needle and h = String.length haystack in
  let rec go i = i + n <= h && (String.sub haystack i n = needle || go (i + 1)) in
  go 0

let check_mentions what text needles =
  List.iter
    (fun needle ->
      if not (contains text needle) then
        Alcotest.failf "%s %S does not mention %S" what text needle)
    needles

let check_reason (v : Boundary_t.valuation) needles =
  Alcotest.check status "status" `Failed v.status;
  match v.failed_reason with
  | None -> Alcotest.fail "Failed without a reason"
  | Some reason -> check_mentions "reason" reason needles

let check_error what result needles =
  match result with
  | Ok _ -> Alcotest.failf "%s: expected an error" what
  | Error reason -> check_mentions what reason needles

let check_nulls (v : Boundary_t.valuation) =
  Alcotest.(check (option approx)) "fair_value" None v.fair_value;
  Alcotest.(check (option approx)) "margin_of_safety" None v.margin_of_safety;
  Alcotest.(check (option signal)) "signal" None v.signal

let get = function Ok v -> v | Error e -> Alcotest.failf "unexpected error: %s" e

(* --- dcf arithmetic --- *)

let test_fcff () =
  check_float "fcff" 700.
    (Dcf.fcff ~ebit:1200. ~tax_rate:0.5 ~depreciation_amortization:200.
       ~capex:50. ~delta_nwc:50.)

let test_wacc () =
  check_float "wacc" 0.07
    (Dcf.wacc ~cost_of_equity:0.12 ~cost_of_debt:0.04 ~tax_rate:0.5
       ~market_cap:5000. ~total_debt:5000.)

let test_ev_perpetuity () =
  List.iter
    (fun projection_years ->
      check_float
        (Printf.sprintf "zero growth, %d years, is fcff / wacc" projection_years)
        10000.
        (Dcf.enterprise_value ~fcff:700. ~wacc:0.07 ~growth_rate:0.
           ~terminal_growth_rate:0. ~projection_years))
    [ 0; 1; 5; 7 ]

let test_ev_growth () =
  (* 110 / 1.07 + 121 / 1.07^2 + (121 * 1.02 / 0.05) / 1.07^2 *)
  let expected =
    (110. /. 1.07) +. (121. /. 1.1449) +. (121. *. 1.02 /. 0.05 /. 1.1449)
  in
  check_float "two explicit years then Gordon" expected
    (Dcf.enterprise_value ~fcff:100. ~wacc:0.07 ~growth_rate:0.10
       ~terminal_growth_rate:0.02 ~projection_years:2)

let test_tax_rate () =
  let check name expected (rate, source) =
    let rate', source' =
      Dcf.tax_rate ~statutory:0.21 ~pretax_income:(fst expected)
        ~tax_provision:(snd expected)
    in
    check_float (name ^ " rate") rate rate';
    Alcotest.check tax_rate_source (name ^ " source") source source'
  in
  check "effective" (Some 1000., Some 250.) (0.25, `Effective);
  check "missing pretax" (None, Some 250.) (0.21, `Statutory);
  check "missing provision" (Some 1000., None) (0.21, `Statutory);
  check "loss-making" (Some (-1000.), Some 10.) (0.21, `Statutory);
  check "tax benefit" (Some 1000., Some (-10.)) (0.21, `Statutory);
  check "implausibly high" (Some 1000., Some 600.) (0.21, `Statutory)

let test_signal () =
  let t = Valuation.default_thresholds in
  Alcotest.check signal "buy" `Buy (Valuation.signal t 0.25);
  Alcotest.check signal "hold" `Hold (Valuation.signal t 0.);
  Alcotest.check signal "hold just below buy" `Hold (Valuation.signal t 0.2499);
  Alcotest.check signal "sell" `Sell (Valuation.signal t (-0.25))

let test_arithmetic_unchanged () =
  (* The same numbers as the unparameterised version, through the parameterised path. *)
  let inputs, fair_value =
    get (Dcf.value assumptions ~country:"Testland" (financials [ full_period () ]))
  in
  check_float "fair value" 12. fair_value;
  check_float "fcff" 700. inputs.fcff;
  check_float "wacc" 0.07 inputs.wacc;
  check_float "enterprise_value" 10000. inputs.enterprise_value;
  check_float "shares" 500. inputs.shares;
  Alcotest.check tax_rate_source "tax_rate_source" `Effective inputs.tax_rate_source;
  Alcotest.(check string) "country recorded as fetched" "Testland" inputs.country

(* --- dates --- *)

let test_days_between () =
  let days from until = get (Params.days_between ~from ~until) in
  Alcotest.(check int) "same day" 0 (days today today);
  Alcotest.(check int) "two days" 2 (days "2026-09-08" today);
  Alcotest.(check int) "copied curve, 2026-06-05 to 2026-09-10" 97 (days "2026-06-05" today);
  Alcotest.(check int) "leap day" 2 (days "2024-02-28" "2024-03-01");
  Alcotest.(check int) "negative when reversed" (-2) (days today "2026-09-08");
  check_error "month only" (Params.days_between ~from:"2026-06" ~until:today) [ "2026-06"; "ISO 8601" ];
  check_error "bad month" (Params.days_between ~from:"2026-13-01" ~until:today) [ "2026-13-01" ]

(* --- parameter loading and resolution --- *)

let test_estimated_round_trip () =
  let rf = Reference_j.risk_free_rates_of_string risk_free_json in
  let rf' = Reference_j.risk_free_rates_of_string (Reference_j.string_of_risk_free_rates rf) in
  Alcotest.(check bool) "round trip" true (rf = rf');
  let singapore = List.assoc "Singapore" rf'.countries in
  Alcotest.(check (list string)) "estimated tenors" [ "3y"; "7y" ] singapore.estimated;
  Alcotest.(check (list string)) "no flag means none" []
    (List.assoc "United States" rf'.countries).estimated;
  let a = get (Params.resolve params ~today ~country:"Singapore" ~industry:None) in
  Alcotest.(check bool) "7y flagged estimated" true a.risk_free_rate.estimated;
  let us = get (Params.resolve params ~today ~country:"United States" ~industry:None) in
  Alcotest.(check bool) "sourced cell not flagged" false us.risk_free_rate.estimated

let test_resolve_provenance () =
  let a =
    get
      (Params.resolve params ~today ~country:"United States"
         ~industry:(Some "Consumer Electronics"))
  in
  let check_param name (p : Boundary_t.parameter) ~value ~key ~source ~as_of ~age_days =
    check_float (name ^ " value") value p.value;
    Alcotest.(check string) (name ^ " key") key p.key;
    Alcotest.(check string) (name ^ " source") source p.source;
    Alcotest.(check string) (name ^ " as_of") as_of p.as_of;
    Alcotest.(check int) (name ^ " age_days") age_days p.age_days
  in
  check_param "risk_free_rate" a.risk_free_rate ~value:0.0468 ~key:"United States/7y"
    ~source:"FRED" ~as_of:"2026-09-08" ~age_days:2;
  check_param "equity_risk_premium" a.equity_risk_premium ~value:0.0446
    ~key:"United States" ~source:"Damodaran Jan 2026" ~as_of:"2026-01-01" ~age_days:252;
  check_param "statutory_tax_rate" a.statutory_tax_rate ~value:0.21 ~key:"United States"
    ~source:"PwC 2026" ~as_of:"2026-01-01" ~age_days:252;
  check_param "terminal_growth_rate" a.terminal_growth_rate ~value:0.02
    ~key:"United States" ~source:"seed" ~as_of:"2026-06-01" ~age_days:101;
  check_param "growth_rate" a.growth_rate ~value:0.05 ~key:"global" ~source:"assumption"
    ~as_of:"2026-09-01" ~age_days:9;
  check_param "debt_spread" a.debt_spread ~value:0.01 ~key:"global" ~source:"assumption"
    ~as_of:"2026-09-01" ~age_days:9;
  check_param "beta" a.beta ~value:0.9 ~key:"Consumer Electronics"
    ~source:"sector betas 2026" ~as_of:"2026-01-01" ~age_days:252;
  Alcotest.check beta_source "beta_source" `Industry_table a.beta_source;
  Alcotest.(check int) "projection_years" 7 a.projection_years.value;
  Alcotest.(check int) "projection_years age" 101 a.projection_years.age_days

let test_resolve_alias () =
  let a = get (Params.resolve params ~today ~country:"USA" ~industry:None) in
  Alcotest.(check string) "rf key canonical" "United States/7y" a.risk_free_rate.key;
  Alcotest.(check string) "erp key canonical" "United States" a.equity_risk_premium.key;
  check_float "erp value" 0.0446 a.equity_risk_premium.value

let test_resolve_unknown_country () =
  check_error "unknown country"
    (Params.resolve params ~today ~country:"Atlantis" ~industry:None)
    [ "Atlantis" ]

let test_resolve_stale () =
  check_error "stale curve"
    (Params.resolve params ~today ~country:"Germany" ~industry:None)
    [ "risk_free_rate"; "Germany/7y"; "97 days"; "45" ]

let test_resolve_future_as_of () =
  let rf =
    Reference_j.risk_free_rates_of_string
      {|{"max_age_days": 45, "tenors": ["7y"],
         "countries": {"United States": {"source": "FRED", "as_of": "2026-09-11", "rates": {"7y": 0.04}}}}|}
  in
  check_error "as_of after today"
    (Params.resolve { params with risk_free = rf } ~today ~country:"United States" ~industry:None)
    [ "risk_free_rate"; "2026-09-11"; "later than" ]

let test_beta_default () =
  let check name industry =
    let a = get (Params.resolve params ~today ~country:"United States" ~industry) in
    check_float (name ^ " beta") 1.0 a.beta.value;
    Alcotest.check beta_source (name ^ " beta_source") `Default_no_industry a.beta_source;
    Alcotest.(check string) (name ^ " source") "default_no_industry" a.beta.source
  in
  check "no industry" None;
  check "unlisted industry" (Some "Interstellar Mining");
  let a =
    get
      (Params.resolve params ~today ~country:"United States"
         ~industry:(Some "Software - Application"))
  in
  check_float "listed industry" 1.3 a.beta.value;
  Alcotest.check beta_source "listed source" `Industry_table a.beta_source

let test_reference_files_load () =
  (* The tracked reference/ tree, as copied into the test's build directory. *)
  let t = get (Params.load ~dir:"../../reference") in
  let tenors = t.risk_free.tenors in
  List.iter
    (fun (country, (curve : Reference_t.curve)) ->
      List.iter
        (fun tenor ->
          if not (List.mem_assoc tenor curve.rates) then
            Alcotest.failf "%s lacks the %s tenor" country tenor)
        tenors;
      List.iter
        (fun tenor ->
          if not (List.mem tenor tenors) then
            Alcotest.failf "%s marks unknown tenor %s as estimated" country tenor)
        curve.estimated)
    t.risk_free.countries;
  Alcotest.(check (list string)) "Singapore estimated cells" [ "3y"; "7y" ]
    (List.assoc "Singapore" t.risk_free.countries).estimated;
  Alcotest.(check (list string)) "Taiwan estimated cells" [ "1y"; "3y"; "7y" ]
    (List.assoc "Taiwan" t.risk_free.countries).estimated;
  Alcotest.(check int) "projection horizon" 7 t.params.projection_years.value;
  Alcotest.(check int) "industry betas" 155 (List.length t.industry_betas.values);
  let countries (c : Reference_t.country_table) = List.sort compare (List.map fst c.values) in
  Alcotest.(check (list string)) "erp and tax cover the same countries"
    (countries t.equity_risk_premiums) (countries t.tax_rates);
  Alcotest.(check bool) "no U.S. alias key duplicated in the tables" false
    (List.mem_assoc "USA" t.equity_risk_premiums.values)

(* --- valuation end to end --- *)

let test_ok () =
  let v = Valuation.run params ~today (financials [ full_period () ]) in
  Alcotest.check status "status" `Ok v.status;
  Alcotest.(check string) "valued_on" today v.valued_on;
  Alcotest.(check (option string)) "failed_reason" None v.failed_reason;
  Alcotest.(check bool) "fair value present" true (Option.is_some v.fair_value);
  Alcotest.(check bool) "signal present" true (Option.is_some v.signal);
  match v.inputs with
  | None -> Alcotest.fail "Ok without inputs"
  | Some i ->
      Alcotest.(check string) "country" "United States" i.country;
      Alcotest.(check (option string)) "industry" (Some "Consumer Electronics") i.industry;
      Alcotest.(check string) "rf source" "FRED" i.risk_free_rate.source;
      Alcotest.(check string) "rf as_of" "2026-09-08" i.risk_free_rate.as_of;
      Alcotest.(check int) "rf age" 2 i.risk_free_rate.age_days;
      check_float "rf value" 0.0468 i.risk_free_rate.value;
      Alcotest.(check string) "erp source" "Damodaran Jan 2026" i.equity_risk_premium.source;
      Alcotest.check beta_source "beta_source" `Industry_table i.beta_source;
      check_float "cost of equity = rf + beta * erp"
        (0.0468 +. (0.9 *. 0.0446)) i.cost_of_equity;
      check_float "cost of debt = rf + spread" (0.0468 +. 0.01) i.cost_of_debt;
      Alcotest.(check int) "projection_years" 7 i.projection_years.value;
      List.iter
        (fun (name, (p : Boundary_t.parameter)) ->
          if p.age_days < 0 || p.source = "" || p.as_of = "" then
            Alcotest.failf "%s lacks provenance" name)
        [
          ("risk_free_rate", i.risk_free_rate);
          ("equity_risk_premium", i.equity_risk_premium);
          ("statutory_tax_rate", i.statutory_tax_rate);
          ("terminal_growth_rate", i.terminal_growth_rate);
          ("growth_rate", i.growth_rate);
          ("debt_spread", i.debt_spread);
          ("beta", i.beta);
        ]

let test_no_country () =
  let v = Valuation.run params ~today (financials ~country:None [ full_period () ]) in
  check_reason v [ "country" ];
  check_nulls v;
  Alcotest.(check bool) "inputs" true (Option.is_none v.inputs)

let test_unknown_country () =
  let v =
    Valuation.run params ~today (financials ~country:(Some "Atlantis") [ full_period () ])
  in
  check_reason v [ "Atlantis" ];
  check_nulls v

let test_stale_parameter () =
  let v =
    Valuation.run params ~today (financials ~country:(Some "Germany") [ full_period () ])
  in
  check_reason v [ "risk_free_rate"; "97 days"; "max_age_days 45" ];
  check_nulls v;
  Alcotest.(check bool) "inputs" true (Option.is_none v.inputs)

let test_no_industry () =
  let v = Valuation.run params ~today (financials ~industry:None [ full_period () ]) in
  Alcotest.check status "status" `Ok v.status;
  match v.inputs with
  | None -> Alcotest.fail "Ok without inputs"
  | Some i ->
      check_float "beta" 1.0 i.beta.value;
      Alcotest.check beta_source "beta_source" `Default_no_industry i.beta_source;
      Alcotest.(check (option string)) "industry" None i.industry

let test_latest_period_wins () =
  let v =
    Valuation.run params ~today
      (financials
         [
           full_period ~period_end:"2024-09-30" ();
           period ~period_end:"2025-09-30" ~ebit:1200. ();
         ])
  in
  check_reason v [ "2025-09-30"; "capex" ];
  Alcotest.(check bool) "inputs" true (Option.is_none v.inputs)

let test_no_periods () =
  let v = Valuation.run params ~today (financials []) in
  check_reason v [ "no fiscal periods" ];
  check_nulls v;
  Alcotest.(check bool) "inputs" true (Option.is_none v.inputs);
  Alcotest.(check (option approx)) "price still reported" (Some 10.) v.price

let test_missing_statement_fields () =
  let v =
    Valuation.run params ~today
      (financials
         [
           period ~ebit:1200. ~pretax_income:1000. ~tax_provision:500.
             ~depreciation_amortization:200. ~cash:1000. ~total_debt:5000. ();
         ])
  in
  check_reason v [ "2025-09-30"; "capex"; "delta_nwc" ];
  check_nulls v

let test_missing_market_data () =
  let v =
    Valuation.run params ~today
      (financials ~currency:None ~market_cap:None [ full_period () ])
  in
  check_reason v [ "currency"; "market_cap" ];
  check_nulls v

let test_wacc_below_terminal_growth () =
  let v =
    Valuation.run
      { params with
        params =
          Reference_j.params_of_string
            {|{"projection_years": {"value": 7, "source": "seed", "as_of": "2026-06-01", "max_age_days": 400},
               "growth_rate": {"value": 0.05, "source": "a", "as_of": "2026-09-01", "max_age_days": 400},
               "debt_spread": {"value": 0.01, "source": "a", "as_of": "2026-09-01", "max_age_days": 400},
               "terminal_growth_rate": {"source": "seed", "as_of": "2026-06-01", "max_age_days": 400,
                 "values": {"United States": 0.5}},
               "unwired": {}}|} }
      ~today (financials [ full_period () ])
  in
  check_reason v [ "terminal growth" ];
  check_nulls v;
  Alcotest.(check bool) "inputs" true (Option.is_none v.inputs)

let test_non_positive_fair_value () =
  let v =
    Valuation.run params ~today
      (financials [ period ~ebit:(-5000.) ~pretax_income:(-5000.) ~tax_provision:0.
           ~depreciation_amortization:200. ~capex:50. ~delta_nwc:50. ~cash:1000.
           ~total_debt:5000. () ])
  in
  check_reason v [ "non-positive fair value" ];
  check_nulls v;
  Alcotest.(check bool) "inputs kept for audit" true (Option.is_some v.inputs)

let test_sanity_bound () =
  (* Tiny market cap: wacc collapses towards the cost of debt and the DCF says
     the equity is worth hundreds of times its price. Not a Buy -- a failure. *)
  let v =
    Valuation.run params ~today (financials ~market_cap:(Some 100.) [ full_period () ])
  in
  check_reason v [ "sanity bound" ];
  check_nulls v;
  Alcotest.(check bool) "inputs kept for audit" true (Option.is_some v.inputs)

let test_json_round_trip () =
  let ok = Valuation.run params ~today (financials [ full_period () ]) in
  let failed = Valuation.run params ~today (financials []) in
  List.iter
    (fun v ->
      Alcotest.check valuation "round trip" v
        (Boundary_j.valuation_of_string (Boundary_j.string_of_valuation v)))
    [ ok; failed ];
  check_mentions "failed json" (Boundary_j.string_of_valuation failed)
    [ {|"status":"Failed"|}; {|"fair_value":null|}; {|"signal":null|};
      {|"inputs":null|}; {|"model":"Generic"|}; {|"valued_on":"2026-09-10"|} ];
  check_mentions "ok json" (Boundary_j.string_of_valuation ok)
    [ {|"beta_source":"industry_table"|}; {|"source":"FRED"|}; {|"age_days":2|} ]

let () =
  let case name f = Alcotest.test_case name `Quick f in
  Alcotest.run "atemoya"
    [
      ( "dcf arithmetic",
        [
          case "fcff" test_fcff;
          case "wacc" test_wacc;
          case "enterprise value, zero growth" test_ev_perpetuity;
          case "enterprise value, growth" test_ev_growth;
          case "tax rate" test_tax_rate;
          case "signal thresholds" test_signal;
          case "unchanged for given parameters" test_arithmetic_unchanged;
        ] );
      ( "parameters",
        [
          case "days between dates" test_days_between;
          case "estimated cells round-trip" test_estimated_round_trip;
          case "resolve carries provenance" test_resolve_provenance;
          case "resolve follows aliases" test_resolve_alias;
          case "unknown country is an error naming it" test_resolve_unknown_country;
          case "stale parameter is an error naming it and its age" test_resolve_stale;
          case "as_of in the future is an error" test_resolve_future_as_of;
          case "beta defaults only without a listed industry" test_beta_default;
          case "tracked reference files load" test_reference_files_load;
        ] );
      ( "valuation",
        [
          case "ok end to end with provenance" test_ok;
          case "failed: no country" test_no_country;
          case "failed: unknown country" test_unknown_country;
          case "failed: stale parameter" test_stale_parameter;
          case "ok: no industry takes the documented beta default" test_no_industry;
          case "latest period wins" test_latest_period_wins;
          case "failed: no periods" test_no_periods;
          case "failed: missing statement fields" test_missing_statement_fields;
          case "failed: missing market data" test_missing_market_data;
          case "failed: wacc below terminal growth" test_wacc_below_terminal_growth;
          case "failed: non-positive fair value" test_non_positive_fair_value;
          case "failed: sanity bound" test_sanity_bound;
          case "json round trip" test_json_round_trip;
        ] );
    ]
