open Atemoya

let today = "2026-09-10"

(* --- boundary fixtures --- *)

let period ?(period_end = "2025-09-30") ?ebit ?pretax_income ?tax_provision
    ?total_revenue ?net_interest_income ?premiums_earned ?premiums_earned_row
    ?depreciation_amortization ?depreciation_amortization_row ?capex ?delta_nwc
    ?cash ?total_debt ?total_debt_source ?book_equity ?net_income ?dividends_paid
    ?dividends_paid_row ?provision_for_credit_losses ?provision_for_credit_losses_row
    ?net_loans ?net_loans_row ?filed ?accession ?aoci ?aoci_row ?claims_incurred
    ?claims_incurred_row ?benefits_losses_and_expenses ?benefits_losses_and_expenses_row
    ?policy_acquisition_expense ?policy_acquisition_expense_row ?operating_expense
    ?operating_expense_row ?future_policy_benefits ?future_policy_benefits_row
    ?claims_liability ?claims_liability_row ?total_revenue_row ?ebit_row ?pretax_income_row
    ?tax_provision_row ?capex_row ?delta_nwc_row ?cash_row ?book_equity_row ?net_income_row
    ?net_interest_income_row ?ebit_recipe ?ebit_composition ?cash_composition
    ?total_debt_composition ?delta_nwc_composition ?ffo ?ffo_composition ?weighted_shares
    ?weighted_shares_tag () : Boundary_t.fiscal_period =
  {
    period_end;
    ebit;
    pretax_income;
    tax_provision;
    total_revenue;
    net_interest_income;
    premiums_earned;
    premiums_earned_row;
    depreciation_amortization;
    depreciation_amortization_row;
    capex;
    delta_nwc;
    cash;
    total_debt;
    total_debt_source;
    book_equity;
    net_income;
    dividends_paid;
    dividends_paid_row;
    provision_for_credit_losses;
    provision_for_credit_losses_row;
    net_loans;
    net_loans_row;
    filed;
    accession;
    aoci;
    aoci_row;
    claims_incurred;
    claims_incurred_row;
    benefits_losses_and_expenses;
    benefits_losses_and_expenses_row;
    policy_acquisition_expense;
    policy_acquisition_expense_row;
    operating_expense;
    operating_expense_row;
    future_policy_benefits;
    future_policy_benefits_row;
    claims_liability;
    claims_liability_row;
    total_revenue_row;
    ebit_row;
    pretax_income_row;
    tax_provision_row;
    capex_row;
    delta_nwc_row;
    cash_row;
    book_equity_row;
    net_income_row;
    net_interest_income_row;
    ffo;
    ffo_composition;
    weighted_shares;
    weighted_shares_tag;
    ebit_recipe;
    ebit_composition;
    cash_composition;
    total_debt_composition;
    delta_nwc_composition;
  }

let financials ?(currency = Some "USD") ?financial_currency ?trading_currency
    ?(price_unit = `Major) ?(price_unit_divisor = 1.0) ?(price = Some 10.)
    ?(market_cap = Some 5000.) ?(country = Some "United States")
    ?(industry = Some "Consumer Electronics") ?(provider = "yfinance")
    ?(statements_unavailable = "") ?latest_filing ?cross_check ?(taxonomy = "")
    ?vendor_financial_currency periods : Boundary_t.financials =
  {
    ticker = "TEST";
    as_of = "2026-09-10T00:00:00+00:00";
    currency;
    financial_currency = Option.value financial_currency ~default:currency;
    trading_currency = Option.value trading_currency ~default:currency;
    price_unit;
    price_unit_divisor;
    price;
    market_cap;
    country;
    industry;
    periods;
    notes = [];
    provider;
    taxonomy;
    vendor_financial_currency;
    market_provider = "yfinance";
    provider_reason = "";
    statements_unavailable;
    latest_filing;
    cross_check;
    submissions_latest_annual = None;
    submissions_unavailable = None;
    point_in_time = None;
  }

let full_period ?period_end ?(ebit = 1200.) ?(pretax_income = 1000.)
    ?(total_revenue = 10000.) ?(capex = 50.) ?(delta_nwc = 50.) () =
  period ?period_end ~ebit ~pretax_income ~tax_provision:500. ~total_revenue
    ~depreciation_amortization:200. ~capex ~delta_nwc ~cash:1000. ~total_debt:5000.
    ~book_equity:5000. ()

(* Three identical years: flat revenue, so historical growth is exactly zero, and
   net reinvestment 50 + 50 - 200 < 0, so the fundamental estimate is unusable.
   Selected growth is therefore 0 (historical, uncapped since roic = 0.06 > 0),
   the path is flat, and the arithmetic reduces to the zero-growth perpetuity. *)
let history ?ebit ?pretax_income ?capex ?delta_nwc () =
  List.map
    (fun period_end -> full_period ~period_end ?ebit ?pretax_income ?capex ?delta_nwc ())
    [ "2025-09-30"; "2024-09-30"; "2023-09-30" ]

(* --- parameter fixtures --- *)

let param ?(key = "k") ?(source = "test") ?(as_of = today) ?(age_days = 0)
    ?(estimated = false) value : Boundary_t.parameter =
  { value; key; source; as_of; age_days; estimated; tier = ""; tenor_requested = ""; tenor_used = "" }

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
    country_risk_premium = None;
    growth_clamp_lower = param (-0.20);
    growth_clamp_upper = param 0.50;
    mean_reversion_lambda = param 0.25;
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
    "United States": {"source": "FRED", "tier": "official", "as_of": "2026-09-08",
      "rates": {"1y": 0.037, "3y": 0.040, "5y": 0.043, "7y": 0.0468, "10y": 0.050}},
    "South Korea": {"source": "OECD via FRED", "tier": "fred_oecd_10y", "as_of": "2026-08-31",
      "rates": {"7y": 0.045, "10y": 0.045}, "tenor_used": {"7y": "10y"}},
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
  "debt_spread": {"value": 0.01, "source": "assumption", "as_of": "2026-09-01", "max_age_days": 400},
  "bank_nii_ratio_threshold": {"value": 0.25, "source": "assumption", "as_of": "2026-09-01", "max_age_days": 400},
  "growth_clamp_lower": {"value": -0.2, "source": "seed", "as_of": "2026-06-01", "max_age_days": 400},
  "growth_clamp_upper": {"value": 0.5, "source": "seed", "as_of": "2026-06-01", "max_age_days": 400},
  "mean_reversion_lambda": {"value": 0.25, "source": "seed", "as_of": "2026-06-01", "max_age_days": 400},
  "mature_market_erp": {"value": 0.0423, "source": "Damodaran mature base", "as_of": "2026-01-01", "max_age_days": 400},
  "terminal_growth_rate": {"source": "seed", "as_of": "2026-06-01", "max_age_days": 400,
    "aliases": {"USA": "United States"},
    "values": {"United States": 0.02, "Singapore": 0.025, "Germany": 0.015, "South Korea": 0.03, "Brazil": 0.035}},
  "unwired": {"growth_clamp": {"upper": 0.5}}
  }|}

let params : Params.t =
  {
    risk_free = Reference_j.risk_free_rates_of_string risk_free_json;
    equity_risk_premiums =
      Reference_j.country_table_of_string
        (country_table_json ~source:"Damodaran Jan 2026"
           {|{"United States": 0.0446, "Singapore": 0.0423, "Germany": 0.0423, "South Korea": 0.0487, "Brazil": 0.0747}|});
    tax_rates =
      Reference_j.country_table_of_string
        (country_table_json ~source:"PwC 2026"
           {|{"United States": 0.21, "Singapore": 0.17, "Germany": 0.30, "South Korea": 0.275, "Brazil": 0.34}|});
    industry_betas =
      Reference_j.industry_table_of_string
        {|{"source": "sector betas 2026", "as_of": "2026-01-01", "max_age_days": 400,
           "values": {"Consumer Electronics": 0.9, "Software - Application": 1.3}}|};
    params = Reference_j.params_of_string params_json;
    admissibility =
      Reference_j.admissibility_of_string
        {|{"source": "test", "as_of": "2026-09-18", "classes": {
            "OperatingCompany": {"lens": "FCFF-based DCF", "admissible_models": ["dcf"], "never": "a DCF through a break", "floor_basis_default": "a completed FCFF DCF"},
            "Bank": {"lens": "price/book against ROE", "admissible_models": ["residual_income"], "never": "an FCFF DCF", "floor_basis_default": "tangible book value per share"},
            "Insurer": {"lens": "operating-profit multiple with the solvency ratio", "admissible_models": ["residual_income_insurer"], "never": "an FCFF DCF", "floor_basis_default": "adjusted book value per share"},
            "Reit": {"lens": "price/FFO and dividend coverage by FFO; never accounting EPS", "admissible_models": ["reit_ffo_dividend"], "never": "accounting EPS", "floor_basis_default": "FFO per share and the dividend it covers"},
            "PreProfit": {"lens": "cash runway vs the catalyst calendar", "admissible_models": [], "never": "any multiple", "floor_basis_default": "no floor until the catalyst", "floor_present_default": false},
            "Wrapper": {"lens": "NAV premium or discount", "admissible_models": [], "never": "headline yield", "floor_basis_default": "NAV per unit"},
            "HighGrowthSoftware": {"lens": "the DCF at the settled reversion is the anchor", "admissible_models": ["dcf"], "never": "P/E or FCF yield", "floor_basis_default": "a completed FCFF DCF"}}}|};
    fx_sources =
      Reference_j.fx_sources_of_string
        {|{"source": "test", "as_of": "2026-09-10", "max_age_days": 10,
           "currency_countries": {"USD": "United States", "GBP": "United Kingdom", "BRL": "Brazil", "EUR": "Germany"},
           "currencies": {"BRL": {"series": "DEXBZUS", "direction": "units_per_usd"},
                          "EUR": {"series": "DEXUSEU", "direction": "usd_per_unit"},
                          "GBP": {"series": "DEXUSUK", "direction": "usd_per_unit"}}}|};
    xbrl_tags =
      Reference_j.xbrl_tags_of_string
        {|{"source": "test", "as_of": "2026-09-19", "cross_check_threshold": 0.02, "max_filing_age_days": 400,
           "annual_forms": ["10-K"], "annual_span_days": [350, 380], "fields": {},
           "ifrs_full_fields": {}, "ifrs_full_net_interest_income": {"interest_revenue": [], "interest_expense": []},
           "depreciation_components": []}|};
    field_definitions =
      Atdgen_runtime.Util.Json.from_file Reference_j.read_field_definitions
        "../../reference/field_definitions.json";
    fx_rates =
      Reference_j.fx_rates_of_string
        {|{"source": "test", "currencies": {
            "BRL": {"series": "DEXBZUS", "direction": "units_per_usd", "as_of": "2026-09-08", "quoted": 5.0, "usd_per_unit": 0.2},
            "EUR": {"series": "DEXUSEU", "direction": "usd_per_unit", "as_of": "2026-09-09", "quoted": 1.25, "usd_per_unit": 1.25},
            "GBP": {"series": "DEXUSUK", "direction": "usd_per_unit", "as_of": "2026-08-01", "quoted": 1.3, "usd_per_unit": 1.3}}}|};
  }

let declaration ?(scope_limits = []) entity_class = { Valuation.entity_class; scope_limits }

(* Most valuation tests declare an operating company; the class tests declare otherwise. *)
let run ?(declared = Some (declaration `OperatingCompany)) fin =
  Valuation.run params ~today ~model_version:"test" ~declaration:declared fin

(* --- testables --- *)

let via_json to_string =
  Alcotest.testable
    (fun fmt v -> Format.pp_print_string fmt (to_string v))
    ( = )

let status = via_json Boundary_j.string_of_status
let signal = via_json Boundary_j.string_of_signal
let tax_rate_source = via_json Boundary_j.string_of_tax_rate_source
let beta_source = via_json Boundary_j.string_of_beta_source
let model = via_json Boundary_j.string_of_model
let entity_class = via_json Boundary_j.string_of_entity_class
let class_check_outcome = via_json Boundary_j.string_of_class_check_outcome
let growth_source = via_json Boundary_j.string_of_growth_source
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
        (Dcf.enterprise_value ~fcff:700. ~wacc:0.07
           ~growth_path:(List.init projection_years (fun _ -> 0.))
           ~terminal_growth_rate:0.))
    [ 0; 1; 5; 7 ]

let test_ev_growth () =
  (* 110 / 1.07 + 121 / 1.07^2 + (121 * 1.02 / 0.05) / 1.07^2 *)
  let expected =
    (110. /. 1.07) +. (121. /. 1.1449) +. (121. *. 1.02 /. 0.05 /. 1.1449)
  in
  check_float "two explicit years then Gordon" expected
    (Dcf.enterprise_value ~fcff:100. ~wacc:0.07 ~growth_path:[ 0.10; 0.10 ]
       ~terminal_growth_rate:0.02);
  (* 110 / 1.07 + 110 * 1.05 / 1.07^2 + (115.5 * 1.02 / 0.05) / 1.07^2 *)
  let expected =
    (110. /. 1.07) +. (115.5 /. 1.1449) +. (115.5 *. 1.02 /. 0.05 /. 1.1449)
  in
  check_float "a path compounds year by year" expected
    (Dcf.enterprise_value ~fcff:100. ~wacc:0.07 ~growth_path:[ 0.10; 0.05 ]
       ~terminal_growth_rate:0.02)

(* --- growth --- *)

let revenues = [ ("2025-09-30", 10000.); ("2024-09-30", 9000.); ("2023-09-30", 8000.) ]

let estimate ?(ebit = 1200.) ?(book_equity = 5000.) ?(capex = 400.) ?(delta_nwc = 50.)
    ?(revenues = revenues) () =
  Growth.estimate ~ebit ~tax_rate:0.5 ~book_equity ~total_debt:5000. ~capex ~delta_nwc
    ~depreciation_amortization:200. ~revenues

let test_growth_fundamental () =
  (* nopat 600; invested 10000 -> roic 0.06; reinvestment 400 + 50 - 200 = 250 ->
     rate 250 / 600; g = 0.06 * 250 / 600 = 0.025 *)
  let e = estimate () in
  check_float "nopat" 600. e.nopat;
  Alcotest.(check (option approx)) "roic" (Some 0.06) e.roic;
  check_float "reinvestment" 250. e.reinvestment;
  Alcotest.(check (option approx)) "reinvestment_rate" (Some (250. /. 600.)) e.reinvestment_rate;
  Alcotest.(check (option approx)) "g_fundamental" (Some 0.025) e.g_fundamental;
  let g, source = get (Growth.select e) in
  check_float "selected" 0.025 g;
  Alcotest.check growth_source "source" `Fundamental source

let test_growth_historical_capped () =
  (* capex 50: reinvestment 50 + 50 - 200 < 0, so the fundamental estimate collapses;
     revenue 8000 -> 10000 over 731 days is 11.79%, above roic 0.06, so it is capped. *)
  let e = estimate ~capex:50. () in
  Alcotest.(check (option approx)) "g_historical" (Some 0.11794866981848795) e.g_historical;
  Alcotest.(check (list string)) "revenue periods, most recent first"
    [ "2025-09-30"; "2024-09-30"; "2023-09-30" ] e.revenue_periods;
  let g, source = get (Growth.select e) in
  check_float "capped at roic" 0.06 g;
  Alcotest.check growth_source "source" `Historical_capped_at_roic source

let test_growth_historical_uncapped () =
  (* ebit 12000 -> nopat 6000, roic 0.6 > 0.118 -> the cap does not bind. *)
  let e = estimate ~ebit:12000. ~capex:50. () in
  let g, source = get (Growth.select e) in
  check_float "uncapped historical" 0.11794866981848795 g;
  Alcotest.check growth_source "source" `Historical source;
  (* roic unknown (invested capital <= 0): historical, uncapped *)
  let e = estimate ~book_equity:(-6000.) ~capex:50. () in
  Alcotest.(check (option approx)) "no roic" None e.roic;
  let _, source = get (Growth.select e) in
  Alcotest.check growth_source "no cap without roic" `Historical source

let test_growth_not_derivable () =
  check_error "single period, negative reinvestment"
    (Growth.select (estimate ~capex:50. ~revenues:[ ("2025-09-30", 10000.) ] ()))
    [ "growth not derivable"; "have 1" ];
  check_error "nopat <= 0 and two periods"
    (Growth.select
       (estimate ~ebit:(-100.) ~revenues:[ ("2025-09-30", 10000.); ("2024-09-30", 9000.) ] ()))
    [ "growth not derivable" ];
  Alcotest.(check (option approx)) "non-positive revenue is skipped" None
    (fst (Growth.cagr [ ("2025-09-30", 10000.); ("2024-09-30", 0.); ("2023-09-30", 8000.) ]))

let test_growth_clamp () =
  Alcotest.(check (pair approx bool)) "above" (0.5, true) (Growth.clamp ~lower:(-0.2) ~upper:0.5 0.7);
  Alcotest.(check (pair approx bool)) "below" (-0.2, true) (Growth.clamp ~lower:(-0.2) ~upper:0.5 (-0.3));
  Alcotest.(check (pair approx bool)) "inside" (0.1, false) (Growth.clamp ~lower:(-0.2) ~upper:0.5 0.1)

let test_growth_path () =
  Alcotest.(check (list (float 1e-12))) "mean reversion toward terminal"
    [ 0.0823040626457124; 0.06852245277701068; 0.05778932421928118 ]
    (Growth.path ~g0:0.10 ~terminal_growth_rate:0.02 ~lambda:0.25 ~projection_years:3);
  Alcotest.(check (list approx)) "g0 at terminal stays there" [ 0.02; 0.02 ]
    (Growth.path ~g0:0.02 ~terminal_growth_rate:0.02 ~lambda:0.25 ~projection_years:2);
  Alcotest.(check (list approx)) "no years, no path" []
    (Growth.path ~g0:0.10 ~terminal_growth_rate:0.02 ~lambda:0.25 ~projection_years:0)

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
  (* The same numbers as the unparameterised version, through the derived-growth path:
     flat history selects zero growth, so the result is the zero-growth perpetuity. *)
  let inputs, fair_value =
    get (Dcf.value assumptions ~country:"Testland" (financials (history ())))
  in
  check_float "fair value" 12. fair_value;
  check_float "fcff" 700. inputs.fcff;
  check_float "wacc" 0.07 inputs.wacc;
  check_float "enterprise_value" 10000. inputs.enterprise_value;
  check_float "shares" 500. inputs.shares;
  Alcotest.check tax_rate_source "tax_rate_source" `Effective inputs.tax_rate_source;
  Alcotest.(check string) "country recorded as fetched" "Testland" inputs.country;
  Alcotest.check growth_source "growth_source" `Historical inputs.growth_source;
  check_float "g0" 0. inputs.g0;
  Alcotest.(check bool) "not clamped" false inputs.growth_clamped;
  Alcotest.(check (list approx)) "flat path" [ 0.; 0.; 0.; 0.; 0. ] inputs.growth_path;
  Alcotest.(check (list string)) "delta_nwc averaged over all three"
    [ "2025-09-30"; "2024-09-30"; "2023-09-30" ] inputs.delta_nwc_periods

let test_delta_nwc_is_averaged () =
  let periods =
    [ full_period ~period_end:"2025-09-30" ~delta_nwc:100. ();
      full_period ~period_end:"2024-09-30" ~delta_nwc:(-50.) ();
      full_period ~period_end:"2023-09-30" ~delta_nwc:100. () ]
  in
  let inputs, _ = get (Dcf.value assumptions ~country:"T" (financials periods)) in
  check_float "mean of 100, -50, 100" 50. inputs.delta_nwc;
  check_float "fcff on the mean" 700. inputs.fcff;
  check_error "one period only"
    (Dcf.value assumptions ~country:"T" (financials [ full_period () ]))
    [ "delta_nwc"; "have 1" ]

let test_growth_selected_end_to_end () =
  (* capex 400 makes reinvestment positive: fundamental growth 0.025, mean-reverting
     toward the fixture's zero terminal growth over five years. *)
  let inputs, fair_value =
    get (Dcf.value assumptions ~country:"T" (financials (history ~capex:400. ())))
  in
  Alcotest.check growth_source "source" `Fundamental inputs.growth_source;
  check_float "g0" 0.025 inputs.g0;
  Alcotest.(check int) "path length is the horizon" 5 (List.length inputs.growth_path);
  check_float "first year" (0.025 *. exp (-0.25)) (List.hd inputs.growth_path);
  check_float "fcff base uses capex 400" 350. inputs.fcff;
  Alcotest.(check bool) "worth more than the flat perpetuity on the same base" true
    (fair_value > (350. /. 0.07 -. 4000.) /. 500.)

let test_growth_clamped_end_to_end () =
  (* revenue 1000 -> 10000 in two years is a 216% CAGR: clamped to 0.5 and flagged.
     ebit 120000 keeps roic (60000 / 10000 = 6) above it so the roic cap does not bind. *)
  let periods =
    [ full_period ~period_end:"2025-09-30" ~ebit:120000. ~total_revenue:10000. ();
      full_period ~period_end:"2024-09-30" ~ebit:120000. ~total_revenue:3000. ();
      full_period ~period_end:"2023-09-30" ~ebit:120000. ~total_revenue:1000. () ]
  in
  let inputs, _ = get (Dcf.value assumptions ~country:"T" (financials periods)) in
  Alcotest.(check bool) "clamped" true inputs.growth_clamped;
  check_float "g0 at the upper bound" 0.5 inputs.g0;
  Alcotest.check growth_source "source" `Historical inputs.growth_source

let test_debt_absent_fails () =
  let periods =
    List.map
      (fun (p : Boundary_t.fiscal_period) -> { p with total_debt = None; total_debt_source = None })
      (history ())
  in
  check_error "no total debt" (Dcf.value assumptions ~country:"T" (financials periods)) [ "total_debt" ];
  let periods =
    List.map (fun (p : Boundary_t.fiscal_period) -> { p with book_equity = None }) (history ())
  in
  check_error "no book equity" (Dcf.value assumptions ~country:"T" (financials periods)) [ "book_equity" ]

let test_provenance_of_mappings () =
  let periods =
    List.map
      (fun (p : Boundary_t.fiscal_period) ->
        { p with depreciation_amortization_row = Some "Depreciation Amortization Depletion";
                 total_debt_source = Some "Long Term Debt + Current Debt" })
      (history ())
  in
  let inputs, _ = get (Dcf.value assumptions ~country:"T" (financials periods)) in
  Alcotest.(check (option string)) "d&a row" (Some "Depreciation Amortization Depletion")
    inputs.depreciation_amortization_row;
  Alcotest.(check (option string)) "debt path" (Some "Long Term Debt + Current Debt")
    inputs.total_debt_source

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
  check_param "growth_clamp_lower" a.growth_clamp_lower ~value:(-0.2) ~key:"global"
    ~source:"seed" ~as_of:"2026-06-01" ~age_days:101;
  check_param "growth_clamp_upper" a.growth_clamp_upper ~value:0.5 ~key:"global"
    ~source:"seed" ~as_of:"2026-06-01" ~age_days:101;
  check_param "mean_reversion_lambda" a.mean_reversion_lambda ~value:0.25 ~key:"global"
    ~source:"seed" ~as_of:"2026-06-01" ~age_days:101;
  check_param "debt_spread" a.debt_spread ~value:0.01 ~key:"global" ~source:"assumption"
    ~as_of:"2026-09-01" ~age_days:9;
  check_param "beta" a.beta ~value:0.9 ~key:"Consumer Electronics"
    ~source:"sector betas 2026" ~as_of:"2026-01-01" ~age_days:252;
  Alcotest.check beta_source "beta_source" `Industry_table a.beta_source;
  Alcotest.(check int) "projection_years" 7 a.projection_years.value;
  Alcotest.(check int) "projection_years age" 101 a.projection_years.age_days

let test_resolve_tenor_substitution () =
  let a = get (Params.resolve params ~today ~country:"South Korea" ~industry:None) in
  check_float "the 10y value stands in" 0.045 a.risk_free_rate.value;
  Alcotest.(check string) "requested" "7y" a.risk_free_rate.tenor_requested;
  Alcotest.(check string) "used" "10y" a.risk_free_rate.tenor_used;
  Alcotest.(check string) "tier" "fred_oecd_10y" a.risk_free_rate.tier;
  Alcotest.(check int) "age from the month end" 10 a.risk_free_rate.age_days;
  let us = get (Params.resolve params ~today ~country:"United States" ~industry:None) in
  Alcotest.(check string) "no substitution: used equals requested" "7y" us.risk_free_rate.tenor_used;
  Alcotest.(check string) "official" "official" us.risk_free_rate.tier

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
  let horizon = Printf.sprintf "%dy" t.params.projection_years.value in
  let registry =
    Atdgen_runtime.Util.Json.from_file Reference_j.read_rate_sources
      "../../reference/rate_sources.json"
  in
  List.iter
    (fun (country, (curve : Reference_t.curve)) ->
      if not (List.mem_assoc horizon curve.rates) then
        Alcotest.failf "%s lacks the %s tenor the horizon needs" country horizon;
      List.iter
        (fun (tenor, _) ->
          if not (List.mem tenor tenors) then
            Alcotest.failf "%s carries unknown tenor %s" country tenor)
        curve.rates;
      List.iter
        (fun tenor ->
          if not (List.mem_assoc tenor curve.rates) then
            Alcotest.failf "%s marks %s as estimated but does not carry it" country tenor)
        curve.estimated;
      List.iter
        (fun (requested, used) ->
          if not (List.mem_assoc requested curve.rates && List.mem_assoc used curve.rates) then
            Alcotest.failf "%s records a substitution %s<-%s it does not carry" country requested used)
        curve.tenor_used;
      match List.assoc_opt country registry.countries with
      | None -> Alcotest.failf "%s has a curve but no registry entry" country
      | Some (r : Reference_t.rate_source) ->
          if List.mem curve.tier [ "official"; "fred_oecd_10y"; "manual" ] |> not then
            Alcotest.failf "%s has tier %S" country curve.tier;
          if curve.tier <> "manual" && curve.tier <> r.tier then
            Alcotest.failf "%s: curve tier %s but registry tier %s" country curve.tier r.tier)
    t.risk_free.countries;
  List.iter
    (fun (country, _) ->
      if not (List.mem_assoc country t.risk_free.countries) then
        Alcotest.failf "registry lists %s but the rate file has no curve" country)
    registry.countries;
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

(* --- entity class: signatures as a consistency check, admissibility, floor --- *)

let threshold = param ~key:"global" ~source:"assumption" 0.25

let signature_of ?(industry = Some "Consumer Electronics") periods =
  Classify.signature ~threshold (financials ~industry periods)

let bank_period ?(nii = 5000.) ?(revenue = 10000.) ?premiums_earned
    ?premiums_earned_row () =
  period ~total_revenue:revenue ~net_interest_income:nii ?premiums_earned
    ?premiums_earned_row ()

let check_indicated name expected periods =
  Alcotest.(check (option entity_class)) name expected (signature_of periods).indicated

let test_signature_bank_ratio () =
  check_indicated "52% indicates a bank" (Some `Bank) [ bank_period () ];
  check_indicated "exactly at threshold indicates a bank" (Some `Bank)
    [ bank_period ~nii:2500. () ];
  check_indicated "24% does not" None [ bank_period ~nii:2400. () ];
  check_indicated "MSFT-like tiny positive NII does not" None
    [ bank_period ~nii:250. ~revenue:331840. () ];
  check_indicated "negative NII does not" None [ bank_period ~nii:(-180.) () ];
  check_indicated "no revenue means no ratio" None [ period ~net_interest_income:5000. () ];
  let e = signature_of [ bank_period () ] in
  Alcotest.(check (option approx)) "ratio recorded" (Some 0.5) e.nii_ratio;
  check_float "threshold recorded" 0.25 e.threshold.value;
  Alcotest.(check (option string)) "period recorded" (Some "2025-09-30") e.fiscal_period_end

let test_signature_insurer_row () =
  let e =
    signature_of
      [ bank_period ~nii:(-100.) ~premiums_earned:5000.
          ~premiums_earned_row:"Net Premiums Earned" () ]
  in
  Alcotest.(check (option entity_class)) "premium row present and positive" (Some `Insurer) e.indicated;
  Alcotest.(check (option string)) "row recorded" (Some "Net Premiums Earned") e.premiums_earned_row;
  check_indicated "premium row zero is no signature" None
    [ bank_period ~nii:(-100.) ~premiums_earned:0. ~premiums_earned_row:"Premiums Earned" () ];
  check_indicated "bank beats insurer" (Some `Bank)
    [ bank_period ~premiums_earned:5000. ~premiums_earned_row:"Premiums Earned" () ];
  check_indicated "no periods, nothing indicated" None [];
  check_indicated ".info is never consulted" None
    (let _ = Some "Banks - Diversified" in [ period () ])

let outcome_of ~declared periods =
  match Classify.check ~declared (signature_of periods) with
  | Classify.Proceed e -> (`Proceed, e)
  | Classify.Refuse (reason, e) -> (`Refuse reason, e)

let test_check_undeclared () =
  (match outcome_of ~declared:None [ period () ] with
  | `Refuse reason, e ->
      check_mentions "reason" reason [ "entity_class not declared" ];
      Alcotest.check class_check_outcome "outcome" `Undeclared e.outcome;
      Alcotest.(check (option entity_class)) "nothing declared" None e.declared
  | `Proceed, _ -> Alcotest.fail "undeclared must refuse");
  match outcome_of ~declared:None [ bank_period () ] with
  | `Refuse reason, _ ->
      check_mentions "hint appended" reason
        [ "entity_class not declared"; "statements indicate Bank"; "NII/revenue 0.50" ]
  | `Proceed, _ -> Alcotest.fail "undeclared must refuse"

let test_check_disagreement_is_fatal () =
  (* JPM declared as an operating company: the signature would have let the dcf run. *)
  match outcome_of ~declared:(Some `OperatingCompany) [ bank_period ~nii:5200. () ] with
  | `Refuse reason, e ->
      check_mentions "reason" reason
        [ "class disagreement"; "declared OperatingCompany"; "statements indicate Bank";
          "NII/revenue 0.52" ];
      Alcotest.check class_check_outcome "outcome" `Disagreement e.outcome;
      Alcotest.(check (option entity_class)) "indicated" (Some `Bank) e.indicated
  | `Proceed, _ -> Alcotest.fail "must refuse"

let test_check_harmless_directions () =
  (* MSFT declared a bank: nothing fires; recorded, not fatal. *)
  (match outcome_of ~declared:(Some `Bank) [ bank_period ~nii:250. ~revenue:331840. () ] with
  | `Proceed, e -> Alcotest.check class_check_outcome "signature absent" `Signature_absent e.outcome
  | `Refuse r, _ -> Alcotest.failf "must proceed, got %s" r);
  (match outcome_of ~declared:(Some `Bank) [ bank_period () ] with
  | `Proceed, e -> Alcotest.check class_check_outcome "consistent" `Consistent e.outcome
  | `Refuse r, _ -> Alcotest.failf "must proceed, got %s" r);
  (match outcome_of ~declared:(Some `Reit) [ bank_period () ] with
  | `Proceed, e -> Alcotest.check class_check_outcome "differs, harmless" `Signature_differs e.outcome
  | `Refuse r, _ -> Alcotest.failf "must proceed, got %s" r);
  (match outcome_of ~declared:(Some `Reit) [ period () ] with
  | `Proceed, e -> Alcotest.check class_check_outcome "nothing contradicts" `Consistent e.outcome
  | `Refuse r, _ -> Alcotest.failf "must proceed, got %s" r);
  match outcome_of ~declared:(Some `OperatingCompany) [ period ~net_interest_income:(-20.) ~total_revenue:1000. () ] with
  | `Proceed, e -> Alcotest.check class_check_outcome "oil & gas style, consistent" `Consistent e.outcome
  | `Refuse r, _ -> Alcotest.failf "must proceed, got %s" r

let check_floor name (v : Boundary_t.valuation) present =
  Alcotest.(check (option bool)) (name ^ " floor.present") present v.floor.present;
  if v.floor.basis = "" then Alcotest.failf "%s: empty floor basis" name

let test_inadmissible_refuses_with_lens () =
  (* Full generic statement fields present: the dcf could run, and must not. *)
  let v =
    run ~declared:(Some (declaration ~scope_limits:[ "a"; "b" ] `Wrapper))
      (financials (history ()))
  in
  check_reason v [ "dcf not admissible for Wrapper"; "lens: NAV premium or discount" ];
  check_nulls v;
  Alcotest.(check (option entity_class)) "class" (Some `Wrapper) v.entity_class;
  Alcotest.(check (option model)) "no model ran" None v.model;
  Alcotest.(check bool) "inputs never computed" true (Option.is_none v.inputs);
  check_floor "wrapper" v None;
  check_mentions "floor basis" v.floor.basis [ "NAV per unit" ];
  Alcotest.(check (list string)) "scope_limits carried" [ "a"; "b" ] v.scope_limits;
  match v.class_check with
  | None -> Alcotest.fail "no class_check evidence"
  | Some e -> Alcotest.check class_check_outcome "consistent" `Consistent e.outcome

let test_insurer_declared_without_signature () =
  (* What yfinance cannot signal, the declaration carries: not "unresolved". The insurer
     model then refuses vendor rows that lack filed fields, naming what would fix it. *)
  let v = run ~declared:(Some (declaration `Insurer)) (financials (history ())) in
  check_reason v [ "insurer model requires filed-statement data"; "no AOCI or premiums earned" ];
  match v.class_check with
  | None -> Alcotest.fail "no evidence"
  | Some e -> Alcotest.check class_check_outcome "signature absent" `Signature_absent e.outcome

let test_undeclared_record () =
  let v = run ~declared:None (financials (history ())) in
  check_reason v [ "entity_class not declared" ];
  Alcotest.(check (option entity_class)) "no class" None v.entity_class;
  Alcotest.(check (option model)) "no model" None v.model;
  check_floor "undeclared" v None;
  Alcotest.(check bool) "inputs never computed" true (Option.is_none v.inputs)

let test_disagreement_record () =
  let jpm_like =
    List.map
      (fun (p : Boundary_t.fiscal_period) -> { p with net_interest_income = Some 5200. })
      (history ())
  in
  let v = run (financials jpm_like) in
  check_reason v [ "class disagreement"; "declared OperatingCompany"; "Bank" ];
  Alcotest.(check (option model)) "no model" None v.model;
  Alcotest.(check bool) "inputs never computed" true (Option.is_none v.inputs)

let test_floor_three_valued () =
  let ok = run (financials (history ())) in
  Alcotest.check status "ok" `Ok ok.status;
  check_floor "verified" ok (Some true);
  check_mentions "verified basis" ok.floor.basis [ "dcf"; "fcff"; "fair value" ];
  let none_by_definition = run ~declared:(Some (declaration `PreProfit)) (financials (history ())) in
  check_reason none_by_definition [ "dcf not admissible for PreProfit" ];
  check_floor "pre-profit" none_by_definition (Some false);
  let not_assessed = run (financials ~country:(Some "Atlantis") (history ())) in
  check_reason not_assessed [ "Atlantis" ];
  check_floor "operating company that failed before the dcf" not_assessed None;
  Alcotest.(check (option model)) "routed to the dcf" (Some `Dcf) not_assessed.model

let test_operating_company_record_carries_evidence () =
  let v = run (financials (history ())) in
  Alcotest.check status "status" `Ok v.status;
  Alcotest.(check (option model)) "model" (Some `Dcf) v.model;
  Alcotest.(check (option entity_class)) "class" (Some `OperatingCompany) v.entity_class;
  match v.class_check with
  | None -> Alcotest.fail "no class_check evidence"
  | Some e ->
      Alcotest.check class_check_outcome "consistent" `Consistent e.outcome;
      Alcotest.(check string) "threshold provenance" "assumption"
        e.bank_nii_ratio_threshold.source;
      Alcotest.(check int) "threshold age" 9 e.bank_nii_ratio_threshold.age_days

let test_no_admissibility_row () =
  let v = run ~declared:(Some (declaration `Miner)) (financials (history ())) in
  check_reason v [ "no admissibility row"; "Miner" ];
  check_floor "no row" v None

let test_sanity_bound_names_structural_break () =
  let v = run (financials ~market_cap:(Some 100.) (history ())) in
  check_reason v [ "sanity bound"; "structural break"; "entity_class" ]

let test_table_and_variant_agree () =
  let t = get (Params.load ~dir:"../../reference") in
  List.iter
    (fun c ->
      match Admissibility.rule t.admissibility c with
      | Ok r ->
          if r.lens = "" || r.floor_basis_default = "" || r.never = "" then
            Alcotest.failf "%s: incomplete row" (Admissibility.class_name c);
          Alcotest.(check bool)
            (Admissibility.class_name c ^ " admits the dcf iff it is the operating company or the software class (21)")
            (c = `OperatingCompany || c = `HighGrowthSoftware) (Admissibility.admits r `Dcf);
          Alcotest.(check bool)
            (Admissibility.class_name c ^ " admits residual income iff it is a bank")
            (c = `Bank) (Admissibility.admits r `Residual_income);
          Alcotest.(check bool)
            (Admissibility.class_name c ^ " admits the insurer model iff it is an insurer")
            (c = `Insurer) (Admissibility.admits r `Residual_income_insurer);
          Alcotest.(check bool) "routed model exists iff some model is admissible"
            (r.admissible_models <> []) (Option.is_some (Admissibility.routed r))
      | Error e -> Alcotest.fail e)
    Admissibility.all_classes;
  List.iter
    (fun (name, _) ->
      match Admissibility.class_of_string name with
      | Some c -> Alcotest.(check string) "round trip" name (Admissibility.class_name c)
      | None -> Alcotest.failf "table row %s is not a variant constructor" name)
    t.admissibility.classes;
  Alcotest.(check int) "one row per constructor" (List.length Admissibility.all_classes)
    (List.length t.admissibility.classes);
  Alcotest.(check (option entity_class)) "parser rejects unknown" None
    (Admissibility.class_of_string "Conglomerate");
  let u =
    get (Universe.load "../../reference/universe.json")
  in
  List.iter
    (fun (e : Reference_t.universe_entry) ->
      if Option.is_none (Admissibility.class_of_string e.entity_class) then
        Alcotest.failf "universe entry %s declares unknown class %s" e.ticker e.entity_class)
    u.tickers

(* --- residual income (the bank model) --- *)

(* Hand-computable: lambda 0 keeps ROE at 20% against a 10% cost of equity; retention 0.5.
   book 1000: year 1 excess 100 (pv 90.909), book -> 1100; year 2 excess 110 (pv 90.909),
   book -> 1210; terminal 0.02 * 1210 / (0.10 - 0.02) = 302.5, pv 250;
   equity 1000 + 181.818 + 250 = 1431.818; shares 100 -> fair value 14.31818, P/B 1.4318 *)
let bank_assumptions : Dcf.assumptions =
  { assumptions with
    equity_risk_premium = param 0.08;
    mean_reversion_lambda = param 0.0;
    terminal_growth_rate = param 0.02;
    projection_years = { value = 2; key = "global"; source = "test"; as_of = today; age_days = 0 } }

let bank_history ?(net_income = 200.) ?(dividends = Some 100.) ?(book_equity = 1000.) () =
  List.map
    (fun period_end ->
      period ~period_end ~total_revenue:1000. ~net_interest_income:600. ~net_income
        ?dividends_paid:dividends ~dividends_paid_row:"Cash Dividends Paid" ~book_equity
        ~net_loans:5000. ~net_loans_row:"Net Loan" ())
    [ "2025-12-31"; "2024-12-31" ]

let bank_financials ?(price = Some 10.) ?(market_cap = Some 1000.) periods =
  financials ~price ~market_cap ~industry:(Some "Banks - Diversified") periods

let test_ri_schedule () =
  let s =
    Residual_income.schedule ~book_equity:1000. ~cost_of_equity:0.10 ~retention:0.5
      ~roe_path:[ 0.20; 0.20 ]
  in
  Alcotest.(check (list approx)) "start-of-year book" [ 1000.; 1100. ] s.book_value_path;
  Alcotest.(check (list approx)) "excess returns" [ 100.; 110. ] s.excess_return_path;
  check_float "pv of excess returns" (100. /. 1.1 +. 110. /. 1.21) s.pv_excess_returns;
  check_float "ending book" 1210. s.ending_book

let test_ri_roe_path () =
  Alcotest.(check (list (float 1e-12))) "reverts toward the cost of equity"
    [ 0.1 +. 0.1 *. exp (-0.25); 0.1 +. 0.1 *. exp (-0.5); 0.1 +. 0.1 *. exp (-0.75) ]
    (Residual_income.roe_path ~roe_0:0.20 ~cost_of_equity:0.10 ~lambda:0.25 ~projection_years:3);
  Alcotest.(check (list approx)) "lambda 0 holds ROE" [ 0.2; 0.2 ]
    (Residual_income.roe_path ~roe_0:0.20 ~cost_of_equity:0.10 ~lambda:0. ~projection_years:2)

let test_ri_value_by_hand () =
  let inputs, fair_value =
    get
      (Residual_income.value bank_assumptions ~country:"T"
         (bank_financials (bank_history ())))
  in
  (* book 1000 + PV of excess 100/1.1 + 110/1.21 = 1181.818; nothing after the horizon *)
  check_float "fair value" (1181.8181818181818 /. 100.) fair_value;
  check_float "roe_0" 0.2 inputs.roe_0;
  Alcotest.(check (list string)) "roe periods" [ "2025-12-31"; "2024-12-31" ] inputs.roe_periods;
  check_float "payout" 0.5 inputs.payout_ratio;
  check_float "retention" 0.5 inputs.retention;
  check_float "cost of equity" 0.10 inputs.cost_of_equity;
  check_float "pv excess" (100. /. 1.1 +. 110. /. 1.21) inputs.pv_excess_returns;
  check_float "equity value is book plus the pv of excess" 1181.8181818181818 inputs.equity_value;
  check_float "justified P/B" 1.1818181818181818 inputs.justified_price_to_book;
  check_float "book value per share" 10. inputs.book_value_per_share;
  (* a 3-year path by hand: book 1000, roe 0.2 held (lambda 0), retention 0.5, ke 0.10 *)
  let three = { bank_assumptions with projection_years = { bank_assumptions.projection_years with value = 3 } } in
  let inputs, fair_value = get (Residual_income.value three ~country:"T" (bank_financials (bank_history ()))) in
  let pv = (100. /. 1.1) +. (110. /. 1.21) +. (121. /. 1.331) in
  check_float "3-year value is book plus the hand-summed pv" ((1000. +. pv) /. 100.) fair_value;
  check_float "3-year pv" pv inputs.pv_excess_returns;
  if contains (Boundary_j.string_of_residual_income_inputs inputs) "terminal" then Alcotest.fail "a terminal field survives on the record"

let test_ri_value_neutrality () =
  (* ROE0 equal to the cost of equity: no excess return ever, so the value is exactly book,
     whatever the horizon; the terminal spread used to violate this *)
  let at_ke = bank_history ~net_income:100. () in
  List.iter
    (fun years ->
      let a = { bank_assumptions with projection_years = { bank_assumptions.projection_years with value = years } } in
      let inputs, fair_value = get (Residual_income.value a ~country:"T" (bank_financials at_ke)) in
      check_float "roe_0 = ke" 0.10 inputs.roe_0;
      check_float (Printf.sprintf "value is book at %d years" years) 10. fair_value;
      check_float "justified P/B 1" 1. inputs.justified_price_to_book)
    [ 1; 7; 40 ]

let test_ri_retention_derivation () =
  (* payout 100/200 and 50/200 -> mean 0.375; a loss year is skipped; dividends above
     net income clamp to 1. *)
  let periods =
    [ period ~period_end:"2025-12-31" ~net_income:200. ~dividends_paid:100. ~book_equity:1000. ();
      period ~period_end:"2024-12-31" ~net_income:200. ~dividends_paid:50. ~book_equity:1000. ();
      period ~period_end:"2023-12-31" ~net_income:(-50.) ~dividends_paid:100. ~book_equity:1000. () ]
  in
  let inputs, _ =
    get (Residual_income.value bank_assumptions ~country:"T" (bank_financials periods))
  in
  check_float "payout" 0.375 inputs.payout_ratio;
  Alcotest.(check (list string)) "loss year skipped" [ "2025-12-31"; "2024-12-31" ] inputs.payout_periods;
  let inputs, _ =
    get
      (Residual_income.value bank_assumptions ~country:"T"
         (bank_financials (bank_history ~dividends:(Some 500.) ())))
  in
  check_float "clamped to 1" 1. inputs.payout_ratio;
  check_float "retention 0" 0. inputs.retention;
  check_error "one usable period"
    (Residual_income.value bank_assumptions ~country:"T"
       (bank_financials [ List.hd (bank_history ()) ]))
    [ "roe not derivable"; "have 1" ];
  check_error "no dividends row"
    (Residual_income.value bank_assumptions ~country:"T"
       (bank_financials (bank_history ~dividends:None ())))
    [ "payout not derivable"; "have 0" ]

let test_ri_guards () =
  (* terminal growth is no input of this path: an absurd value changes nothing *)
  let _, with_absurd_terminal =
    get (Residual_income.value { bank_assumptions with terminal_growth_rate = param 0.5 } ~country:"T" (bank_financials (bank_history ())))
  in
  let _, plain = get (Residual_income.value bank_assumptions ~country:"T" (bank_financials (bank_history ()))) in
  check_float "terminal growth does not enter" plain with_absurd_terminal;
  check_error "book equity not positive"
    (Residual_income.value bank_assumptions ~country:"T"
       (bank_financials (bank_history ~book_equity:(-1.) ())))
    [ "book equity"; "not positive" ];
  check_error "missing net income"
    (Residual_income.value bank_assumptions ~country:"T"
       (bank_financials
          (List.map (fun (p : Boundary_t.fiscal_period) -> { p with net_income = None }) (bank_history ()))))
    [ "missing statement fields"; "net_income" ]

let test_ri_loan_loss_recorded () =
  let with_provision =
    List.map
      (fun (p : Boundary_t.fiscal_period) ->
        { p with provision_for_credit_losses = Some 60.; provision_for_credit_losses_row = Some "Credit Losses Provision" })
      (bank_history ())
  in
  let inputs, _ =
    get (Residual_income.value bank_assumptions ~country:"T" (bank_financials with_provision))
  in
  Alcotest.(check (option approx)) "provision / NII" (Some 0.1) inputs.provision_to_net_interest_income;
  Alcotest.(check (option approx)) "provision / net loans" (Some 0.012) inputs.provision_to_net_loans;
  Alcotest.(check (option string)) "row" (Some "Credit Losses Provision") inputs.provision_for_credit_losses_row;
  let inputs, _ =
    get (Residual_income.value bank_assumptions ~country:"T" (bank_financials (bank_history ())))
  in
  Alcotest.(check (option approx)) "absent provision, null ratio" None inputs.provision_to_net_interest_income;
  Alcotest.(check (option string)) "net loans row still recorded" (Some "Net Loan") inputs.net_loans_row

let test_bank_routes_to_residual_income () =
  let v = run ~declared:(Some (declaration `Bank)) (bank_financials (bank_history ())) in
  Alcotest.check status "status" `Ok v.status;
  Alcotest.(check (option model)) "routed model" (Some `Residual_income) v.model;
  check_floor "bank floor verified" v (Some true);
  check_mentions "floor basis" v.floor.basis [ "residual income"; "book value"; "justified price/book" ];
  (match v.inputs with
  | Some (`Residual_income i) ->
      Alcotest.(check int) "roe path spans the horizon" 7 (List.length i.roe_path);
      Alcotest.(check bool) "no terminal on the record" false (contains (Boundary_j.string_of_residual_income_inputs i) "terminal")
  | Some (`Dcf _) -> Alcotest.fail "a bank reached the dcf"
  | Some (`Residual_income_insurer _) -> Alcotest.fail "a bank reached the insurer model"
  | Some (`Reit_ffo_dividend _) -> Alcotest.fail "a bank reached the reit model"
  | None -> Alcotest.fail "no inputs");
  match v.class_check with
  | Some e -> Alcotest.check class_check_outcome "signature consistent" `Consistent e.outcome
  | None -> Alcotest.fail "no evidence"

let test_flow_chart_names_every_reason () =
  let chart =
    In_channel.with_open_bin "../../docs/flow.md" In_channel.input_all
  in
  List.iter
    (fun needle ->
      if not (contains chart needle) then
        Alcotest.failf "docs/flow.md does not mention the reason %S" needle)
    [ "entity_class not declared"; "class disagreement: declared OperatingCompany";
      "no admissibility row for entity class"; "dcf not admissible for";
      "country not determinable from the fetch"; "no risk-free curve for country";
      "has no"; "days old, older than its max_age_days"; "later than the valuation date";
      "no fiscal periods in statements"; "missing market data"; "missing statement fields for fiscal period ending";
      "must be positive"; "years is negative"; "does not exceed terminal growth";
      "growth not derivable"; "fair value is not finite"; "non-positive fair value";
      "exceeds sanity bound"; "likely structural break; check entity_class";
      "is not positive"; "roe not derivable"; "payout not derivable";
      "insurer model requires filed-statement data"; "fx not available for";
      "latest annual filing is";
      "missing market data: financial_currency"; "missing market data: trading_currency";
      "fx for"; "field definition mismatch"; "operating income not filed; derived EBIT misses the cross-check";
      "financial currency disagreement"; "no point-in-time statements"; "no point-in-time shares";
      "rate source has no history for"; "ffo growth needs two periods"; "is not positive" ]

(* --- the insurer model --- *)

(* The bank fixture's numbers with book split into reported equity 1200 and AOCI 200, so
   the adjusted book is 1000 and every core figure equals the bank case: fair value
   14.318, justified P/B 1.4318 on adjusted book. *)
let insurer_history ?(aoci = 200.) ?claims ?(total = Some 900.) ?acq ?opex ?fpb ?(claims_liability = Some 3000.) () =
  List.map
    (fun period_end ->
      period ~period_end ~total_revenue:1200. ~net_income:200. ~dividends_paid:100.
        ~dividends_paid_row:"PaymentsOfDividendsCommonStock" ~book_equity:1200. ~aoci
        ~aoci_row:"AccumulatedOtherComprehensiveIncomeLossNetOfTax" ~premiums_earned:1000.
        ~premiums_earned_row:"PremiumsEarnedNet" ?claims_incurred:claims
        ?benefits_losses_and_expenses:total ?policy_acquisition_expense:acq ?operating_expense:opex
        ?future_policy_benefits:fpb ?claims_liability ~filed:"2026-02-20" ~accession:"0001-26-1" ())
    [ "2025-12-31"; "2024-12-31" ]

let insurer_financials ?(provider = "SEC XBRL companyfacts") ?statements_unavailable periods =
  financials ~price:(Some 10.) ~market_cap:(Some 1000.) ~industry:(Some "Insurance - Life")
    ~provider ?statements_unavailable periods

let test_insurer_aoci_adjustment () =
  let inputs, fair_value =
    get (Insurer.value bank_assumptions ~country:"T" (insurer_financials (insurer_history ())))
  in
  check_float "fair value on adjusted book equals the bank case" (1181.8181818181818 /. 100.) fair_value;
  check_float "core book is adjusted" 1000. inputs.core.book_equity;
  check_float "reported book recorded" 1200. inputs.reported_book_equity;
  check_float "aoci recorded" 200. inputs.aoci;
  check_float "aoci share of reported book" (200. /. 1200.) inputs.aoci_to_reported_book;
  check_float "roe on adjusted book" 0.2 inputs.core.roe_0;
  Alcotest.(check string) "provider" "SEC XBRL companyfacts" inputs.provider;
  Alcotest.(check (option string)) "filed" (Some "2026-02-20") inputs.filed;
  Alcotest.(check (option string)) "aoci row" (Some "AccumulatedOtherComprehensiveIncomeLossNetOfTax") inputs.aoci_row;
  Alcotest.(check (option approx)) "solvency null" None inputs.solvency;
  check_mentions "solvency basis" inputs.solvency_basis [ "not available from filed financial statements" ];
  (* a negative AOCI raises the adjusted book *)
  let inputs, _ =
    get (Insurer.value bank_assumptions ~country:"T"
           (insurer_financials (insurer_history ~aoci:(-300.) ())))
  in
  check_float "negative aoci adds back" 1500. inputs.core.book_equity

let test_insurer_underwriting_checks () =
  let inputs, _ =
    get (Insurer.value bank_assumptions ~country:"T" (insurer_financials (insurer_history ())))
  in
  Alcotest.(check (option approx)) "combined via the filed total" (Some 0.9) inputs.combined_ratio_proxy;
  check_mentions "basis" inputs.combined_ratio_basis [ "filed total" ];
  Alcotest.(check (option approx)) "reserves over premiums" (Some 3.0) inputs.reserves_to_premiums;
  let inputs, _ =
    get (Insurer.value bank_assumptions ~country:"T"
           (insurer_financials (insurer_history ~total:None ~claims:800. ~acq:50. ~opex:70. ~fpb:500. ())))
  in
  Alcotest.(check (option approx)) "combined via claims plus expenses" (Some 0.92) inputs.combined_ratio_proxy;
  check_mentions "basis" inputs.combined_ratio_basis [ "claims incurred plus" ];
  Alcotest.(check (option approx)) "reserves sum both liabilities" (Some 3.5) inputs.reserves_to_premiums;
  let inputs, _ =
    get (Insurer.value bank_assumptions ~country:"T"
           (insurer_financials (insurer_history ~total:None ~claims_liability:None ())))
  in
  Alcotest.(check (option approx)) "no claims line, no ratio" None inputs.combined_ratio_proxy;
  Alcotest.(check (option approx)) "no reserves, no ratio" None inputs.reserves_to_premiums

let test_insurer_requires_filed_statements () =
  check_error "vendor rows"
    (Insurer.value bank_assumptions ~country:"T" (financials (history ())))
    [ "insurer model requires filed-statement data"; "no AOCI or premiums earned"; "provider yfinance" ];
  check_error "provider had nothing"
    (Insurer.value bank_assumptions ~country:"T"
       (insurer_financials ~statements_unavailable:"no SEC filings for ALV.DE: not in company_tickers.json" []))
    [ "insurer model requires filed-statement data; no SEC filings for ALV.DE" ];
  check_error "no periods at all"
    (Insurer.value bank_assumptions ~country:"T" (insurer_financials []))
    [ "insurer model requires filed-statement data; no filed statements for TEST" ]

let test_insurer_routes_and_floors () =
  let v = run ~declared:(Some (declaration `Insurer)) (insurer_financials (insurer_history ())) in
  Alcotest.check status "status" `Ok v.status;
  Alcotest.(check (option model)) "routed model" (Some `Residual_income_insurer) v.model;
  check_floor "verified" v (Some true);
  check_mentions "floor basis" v.floor.basis
    [ "AOCI-adjusted book"; "reserve adequacy not assessed"; "justified price/book" ];
  (match v.inputs with
  | Some (`Residual_income_insurer i) ->
      Alcotest.(check bool) "no terminal on the insurer core" false (contains (Boundary_j.string_of_residual_income_inputs i.core) "terminal");
      Alcotest.(check int) "roe path spans the horizon" 7 (List.length i.core.roe_path)
  | Some _ -> Alcotest.fail "an insurer reached another model"
  | None -> Alcotest.fail "no inputs");
  (match v.class_check with
  | Some e -> Alcotest.check class_check_outcome "premium row fires, consistent" `Consistent e.outcome
  | None -> Alcotest.fail "no evidence");
  let refused = run ~declared:(Some (declaration `Insurer))
      (insurer_financials ~statements_unavailable:"no SEC filings for ALV.DE: not in company_tickers.json" []) in
  check_reason refused [ "insurer model requires filed-statement data; no SEC filings for ALV.DE" ];
  Alcotest.(check (option model)) "routed but never ran" (Some `Residual_income_insurer) refused.model;
  check_floor "not assessed" refused None

(* --- cross-currency and ADR --- *)

let brl_bank ?(price = Some 10.) ?(market_cap = Some 1000.) () =
  (* the bank fixture's statements, declared in BRL under a USD line *)
  financials ~currency:None ~financial_currency:(Some "BRL") ~trading_currency:(Some "USD")
    ~country:(Some "Brazil") ~industry:(Some "Banks - Diversified") ~price ~market_cap
    (bank_history ())

let test_fx_rate_through_usd () =
  let legs = get (Fx.rate params.fx_sources params.fx_rates ~today ~financial:"BRL" ~trading:"USD") in
  check_float "BRL to USD" 0.2 legs.fx_rate;
  check_float "usd per BRL" 0.2 legs.usd_per_financial;
  check_float "usd per USD" 1.0 legs.usd_per_trading;
  Alcotest.(check string) "dated by the BRL leg" "2026-09-08" legs.as_of;
  Alcotest.(check int) "age" 2 legs.age_days;
  check_mentions "source" legs.source [ "BRL via FRED DEXBZUS" ];
  let legs = get (Fx.rate params.fx_sources params.fx_rates ~today ~financial:"BRL" ~trading:"EUR") in
  check_float "cross rate" (0.2 /. 1.25) legs.fx_rate;
  check_mentions "both legs" legs.source [ "BRL via FRED DEXBZUS"; "EUR via FRED DEXUSEU"; "through USD" ];
  Alcotest.(check string) "the older leg dates it" "2026-09-08" legs.as_of;
  check_error "missing pair" (Fx.rate params.fx_sources params.fx_rates ~today ~financial:"KZT" ~trading:"USD")
    [ "fx not available for KZT/USD" ];
  check_error "stale leg" (Fx.rate params.fx_sources params.fx_rates ~today ~financial:"USD" ~trading:"GBP")
    [ "fx for GBP"; "40 days old"; "max_age_days 10" ];
  Alcotest.(check string) "trading currency's country" "United Kingdom" (get (Fx.country_of params.fx_sources "GBP"));
  check_error "unknown currency" (Fx.country_of params.fx_sources "XXX") [ "XXX" ]

let test_fx_convert_scales_totals_only () =
  let c = Fx.convert ~rate:2.0 (brl_bank ()) in
  let p = List.hd c.periods in
  Alcotest.(check (option approx)) "net income doubled" (Some 400.) p.net_income;
  Alcotest.(check (option approx)) "book doubled" (Some 2000.) p.book_equity;
  Alcotest.(check (option approx)) "dividends doubled" (Some 200.) p.dividends_paid;
  Alcotest.(check (option approx)) "revenue doubled" (Some 2000.) p.total_revenue;
  Alcotest.(check (option approx)) "price untouched" (Some 10.) c.price;
  Alcotest.(check (option approx)) "market cap untouched" (Some 1000.) c.market_cap;
  Alcotest.(check (option string)) "currency becomes the trading one" (Some "USD") c.currency;
  Alcotest.(check (option string)) "ratio unchanged: signature still fires"
    (Some "Banks - Diversified") c.industry

let test_international_capm () =
  let a = get (Params.resolve_cross params ~today ~domicile:"Brazil" ~rate_country:"United States" ~industry:None) in
  check_float "risk-free from the trading country" 0.0468 a.risk_free_rate.value;
  Alcotest.(check string) "rf key" "United States/7y" a.risk_free_rate.key;
  check_float "terminal growth from the trading country" 0.02 a.terminal_growth_rate.value;
  check_float "tax from the domicile" 0.34 a.statutory_tax_rate.value;
  check_float "mature base as the erp" 0.0423 a.equity_risk_premium.value;
  Alcotest.(check string) "erp key" "mature market" a.equity_risk_premium.key;
  (match a.country_risk_premium with
  | None -> Alcotest.fail "no country risk premium"
  | Some crp ->
      check_float "crp = total less base" (0.0747 -. 0.0423) crp.value;
      Alcotest.(check string) "crp key is the domicile" "Brazil" crp.key;
      check_mentions "crp source" crp.source [ "less the mature-market base" ]);
  let inputs, _ =
    get (Residual_income.value a ~country:"Brazil" (Fx.convert ~rate:0.2 (brl_bank ())))
  in
  check_float "ke = rf + beta * mature + crp" (0.0468 +. (1.0 *. 0.0423) +. (0.0747 -. 0.0423)) inputs.cost_of_equity;
  let domestic = get (Params.resolve params ~today ~country:"United States" ~industry:None) in
  Alcotest.(check bool) "same-currency path has no crp" true (Option.is_none domestic.country_risk_premium);
  let inputs, _ = get (Residual_income.value domestic ~country:"United States" (bank_financials (bank_history ()))) in
  check_float "domestic ke unchanged" (0.0468 +. (1.0 *. 0.0446)) inputs.cost_of_equity

let test_adr_ratio_invariance () =
  (* the same company: one line at price 10 (1:1), one at price 50 (1:5), same market cap *)
  let ordinary = run ~declared:(Some (declaration `Bank)) (brl_bank ~price:(Some 10.) ()) in
  let adr = run ~declared:(Some (declaration `Bank)) (brl_bank ~price:(Some 50.) ()) in
  Alcotest.check status "ordinary ok" `Ok ordinary.status;
  Alcotest.check status "adr ok" `Ok adr.status;
  let fv r = Option.get r.Boundary_t.fair_value and mos r = Option.get r.Boundary_t.margin_of_safety in
  check_float "margin of safety identical" (mos ordinary) (mos adr);
  check_float "fair value per ADR is five ordinaries" (5. *. fv ordinary) (fv adr);
  Alcotest.(check (option string)) "valued in the trading currency" (Some "USD") adr.currency;
  match adr.inputs with
  | Some (`Residual_income i) -> (
      match i.conversion with
      | None -> Alcotest.fail "no conversion recorded"
      | Some c ->
          check_float "fx rate" 0.2 c.fx_rate;
          Alcotest.(check string) "rate country" "United States" c.rate_country;
          Alcotest.(check string) "growth country" "United States" c.growth_country;
          Alcotest.(check string) "domicile" "Brazil" c.domicile;
          Alcotest.(check string) "fx as_of" "2026-09-08" c.fx_as_of;
          check_float "book converted" 200. i.book_equity;
          Alcotest.(check bool) "crp recorded" true (Option.is_some i.country_risk_premium))
  | _ -> Alcotest.fail "wrong inputs"

let test_minor_unit_guard () =
  (* USD statements under a GBP line quoted in pence: the fetch divides the price by 100.
     With effective shares = market cap / price the margin of safety is invariant to the
     unit, but the reported fair value is not: unconverted it comes out in pence. *)
  let gbp price ~price_unit ~price_unit_divisor =
    financials ~currency:None ~financial_currency:(Some "USD") ~trading_currency:(Some "GBP")
      ~country:(Some "United Kingdom") ~price:(Some price) ~market_cap:(Some 5000.)
      ~price_unit ~price_unit_divisor (history ())
  in
  let fresh_gbp = { params with fx_rates = Reference_j.fx_rates_of_string
    {|{"source": "t", "currencies": {"GBP": {"series": "DEXUSUK", "direction": "usd_per_unit", "as_of": "2026-09-09", "quoted": 1.25, "usd_per_unit": 1.25}}}|} } in
  let uk_rates = { fresh_gbp with risk_free = Reference_j.risk_free_rates_of_string
    {|{"max_age_days": 45, "tenors": ["7y"], "countries": {"United Kingdom": {"source": "t", "tier": "official", "as_of": "2026-09-08", "rates": {"7y": 0.0468}}}}|};
    equity_risk_premiums = Reference_j.country_table_of_string (country_table_json ~source:"t" {|{"United States": 0.0446, "United Kingdom": 0.0501}|});
    tax_rates = Reference_j.country_table_of_string (country_table_json ~source:"t" {|{"United States": 0.21, "United Kingdom": 0.25}|});
    params = Reference_j.params_of_string (String.concat "" [ {|{"projection_years": {"value": 7, "source": "seed", "as_of": "2026-06-01", "max_age_days": 400},
      "debt_spread": {"value": 0.02, "source": "a", "as_of": "2026-09-01", "max_age_days": 400},
      "bank_nii_ratio_threshold": {"value": 0.25, "source": "a", "as_of": "2026-09-01", "max_age_days": 400},
      "growth_clamp_lower": {"value": -0.2, "source": "a", "as_of": "2026-06-01", "max_age_days": 400},
      "growth_clamp_upper": {"value": 0.5, "source": "a", "as_of": "2026-06-01", "max_age_days": 400},
      "mean_reversion_lambda": {"value": 0.25, "source": "a", "as_of": "2026-06-01", "max_age_days": 400},
      "mature_market_erp": {"value": 0.0423, "source": "a", "as_of": "2026-01-01", "max_age_days": 400},
      "terminal_growth_rate": {"source": "seed", "as_of": "2026-06-01", "max_age_days": 400, "values": {"United States": 0.02, "United Kingdom": 0.0}},
      "unwired": {}}|} ]) } in
  let run_gbp fin = Valuation.run uk_rates ~today ~model_version:"test" ~declaration:(Some (declaration `OperatingCompany)) fin in
  let converted = run_gbp (gbp 10. ~price_unit:`Minor ~price_unit_divisor:100.) in
  let unconverted = run_gbp (gbp 1000. ~price_unit:`Major ~price_unit_divisor:1.) in
  (match converted.failed_reason with Some r -> Alcotest.failf "converted: %s" r | None -> ());
  (match unconverted.failed_reason with Some r -> Alcotest.failf "unconverted: %s" r | None -> ());
  let fv r = Option.get r.Boundary_t.fair_value and mos r = Option.get r.Boundary_t.margin_of_safety in
  check_float "the unit error cancels in the margin of safety" (mos converted) (mos unconverted);
  check_float "but the unconverted fair value is 100x, in pence" (100. *. fv converted) (fv unconverted);
  Alcotest.(check bool) "converted fair value is in pounds, on the order of the price" true
    (fv converted > 1. && fv converted < 100.);
  match converted.inputs with
  | Some (`Dcf i) -> (
      match i.conversion with
      | Some c ->
          Alcotest.(check bool) "unit recorded" true (c.price_unit = `Minor);
          check_float "divisor recorded" 100. c.price_unit_divisor;
          Alcotest.(check string) "rate country" "United Kingdom" c.rate_country;
          check_float "USD statements to GBP" (1. /. 1.25) c.fx_rate
      | None -> Alcotest.fail "no conversion")
  | _ -> Alcotest.fail "wrong inputs"

let test_currency_gate_failures () =
  let v = run ~declared:(Some (declaration `Bank)) (financials ~financial_currency:None (bank_history ())) in
  check_reason v [ "missing market data: financial_currency" ];
  let v =
    run ~declared:(Some (declaration `Bank))
      (financials ~currency:None ~financial_currency:(Some "USD") ~trading_currency:None (bank_history ()))
  in
  check_reason v [ "missing market data: trading_currency" ];
  let kzt =
    financials ~currency:None ~financial_currency:(Some "KZT") ~trading_currency:(Some "USD")
      ~country:(Some "Brazil") ~industry:(Some "Banks - Diversified") (bank_history ())
  in
  let v = run ~declared:(Some (declaration `Bank)) kzt in
  check_reason v [ "fx not available for KZT/USD" ];
  Alcotest.(check (option model)) "routed before the gate" (Some `Residual_income) v.model;
  Alcotest.(check bool) "nothing computed" true (Option.is_none v.inputs)

let test_same_currency_path_carries_no_conversion () =
  let v = run (financials (history ())) in
  match v.inputs with
  | Some (`Dcf i) ->
      Alcotest.(check bool) "no conversion" true (Option.is_none i.conversion);
      Alcotest.(check bool) "no crp" true (Option.is_none i.country_risk_premium);
      check_mentions "json omits them" (Boundary_j.string_of_valuation v) [ {|"cost_of_equity"|} ];
      if contains (Boundary_j.string_of_valuation v) "conversion" then Alcotest.fail "conversion leaked into a same-currency record"
  | _ -> Alcotest.fail "wrong inputs"

(* --- filed statements as the primary source --- *)

let a_cross_check : Boundary_t.cross_check =
  {
    provider = "yfinance"; source = ""; period_end = "2025-09-27"; secondary_period_end = "2025-09-30"; threshold = 0.02;
    fields =
      [ { field = "cash"; primary = Some 36.; secondary = Some 54.7; relative_difference = Some 0.342; agree = Some false };
        { field = "net_income"; primary = Some 112.; secondary = Some 112.; relative_difference = Some 0.; agree = Some true };
        { field = "ebit"; primary = None; secondary = Some 133.; relative_difference = None; agree = None } ];
    disagreements = 1;
  }

let filed ?(latest_filing = "2026-02-20") ?cross_check periods =
  { (financials ~provider:"SEC XBRL companyfacts" ~latest_filing ?cross_check periods) with
    provider_reason = "CIK 0000320193: us-gaap annual filer (10-K)" }

let test_filing_age_gate () =
  let v = run (filed (history ())) in
  Alcotest.check status "fresh filing values" `Ok v.status;
  Alcotest.(check (option int)) "age recorded" (Some 202) v.filing_age_days;
  let v = run (filed ~latest_filing:"2025-01-01" (history ())) in
  check_reason v [ "latest annual filing is 617 days old, older than its max_filing_age_days 400" ];
  Alcotest.(check (option int)) "age recorded on the failure too" (Some 617) v.filing_age_days;
  Alcotest.(check (option model)) "routed before the gate" (Some `Dcf) v.model;
  Alcotest.(check bool) "nothing computed" true (Option.is_none v.inputs);
  let v = run (filed ~latest_filing:"2026-02" (history ())) in
  check_reason v [ "latest_filing"; "2026-02" ];
  let v = run (financials (history ())) in
  Alcotest.(check (option int)) "vendor records carry no filing age" None v.filing_age_days

let test_provider_decision_on_every_record () =
  let refused = run ~declared:(Some (declaration `Wrapper)) (filed ~cross_check:a_cross_check (history ())) in
  check_reason refused [ "dcf not admissible for Wrapper" ];
  Alcotest.(check string) "statements provider" "SEC XBRL companyfacts" refused.statements_provider;
  Alcotest.(check string) "market provider" "yfinance" refused.market_provider;
  check_mentions "reason" refused.provider_reason [ "us-gaap annual filer" ];
  (match refused.cross_check with
  | Some c -> Alcotest.(check int) "cross-check carried" 1 c.disagreements
  | None -> Alcotest.fail "cross-check dropped");
  let vendor = run (financials (history ())) in
  Alcotest.(check string) "vendor statements" "yfinance" vendor.statements_provider;
  Alcotest.(check bool) "no cross-check" true (Option.is_none vendor.cross_check);
  check_mentions "json" (Boundary_j.string_of_valuation refused) [ {|"statements_provider":"SEC XBRL companyfacts"|}; {|"cross_check":{|} ];
  if contains (Boundary_j.string_of_valuation vendor) "cross_check" then Alcotest.fail "cross_check leaked into a vendor record"

let test_summary_cross_check_line_and_provider_diff () =
  let primary = run (filed ~cross_check:a_cross_check (history ())) in
  let shadow = run (financials (history ~capex:400. ())) in
  let s = Batch.summary [ primary; shadow ] in
  check_mentions "summary" s [ "cross-check: 1 of 1 filed-statement records disagree"; "most often: cash (1)" ];
  let d = Batch.provider_diff [ (primary, Some shadow); (shadow, None) ] in
  check_mentions "diff" d
    [ "yfinance -> SEC XBRL companyfacts: old"; "delta";
      "cash                       filed 36.00  vendor 54.70  differ 34.2%";
      "absent from the filing, present at the vendor: ebit";
      "TEST       unchanged (statements from yfinance)" ];
  let quiet = Batch.summary [ shadow ] in
  if contains quiet "cross-check:" then Alcotest.fail "cross-check line on a batch without checks"

(* --- field definitions: compositions carried, the gate, fx, the run diff --- *)

let comp ?(definition = "cash_and_short_term_investments") parts : Boundary_t.composition =
  { definition; components = List.map (fun (name, value, row) -> ({ name; value; row } : Boundary_t.component)) parts }

let defined_period ?(cash_definition = "cash_and_short_term_investments") ?(ebit_recipe = "operating_income") period_end =
  { (full_period ~period_end ()) with
    cash_composition = Some (comp ~definition:cash_definition [ ("cash_equivalents", 600., "Cash"); ("short_term_investments", 400., "Other Short Term Investments") ]);
    total_debt_composition = Some (comp ~definition:"financial_debt_excluding_operating_leases" [ ("long_term_debt", 4000., "Long Term Debt"); ("current_debt", 1000., "Current Debt") ]);
    delta_nwc_composition = Some (comp ~definition:"cash_flow_statement_change_in_operating_working_capital" [ ("change_in_working_capital", 50., "Change In Working Capital") ]);
    ebit_recipe = Some ebit_recipe;
    ebit_composition = Some (comp ~definition:"operating_income_else_pretax_plus_interest" [ ("operating_income", 1200., "Operating Income") ]) }

let defined_history () = List.map defined_period [ "2025-09-30"; "2024-09-30"; "2023-09-30" ]

let test_compositions_carried_into_inputs () =
  let v = run (financials (defined_history ())) in
  Alcotest.check status "values" `Ok v.status;
  match v.inputs with
  | Some (`Dcf (i : Boundary_t.inputs)) ->
      Alcotest.(check (option string)) "recipe" (Some "operating_income") i.ebit_recipe;
      (match i.cash_composition with
      | Some c ->
          Alcotest.(check string) "cash definition" "cash_and_short_term_investments" c.definition;
          Alcotest.(check (list string)) "cash components"
            [ "cash_equivalents"; "short_term_investments" ]
            (List.map (fun (k : Boundary_t.component) -> k.name) c.components);
          check_float "components sum to the field" i.cash
            (List.fold_left (fun acc (k : Boundary_t.component) -> acc +. k.value) 0. c.components)
      | None -> Alcotest.fail "cash composition dropped");
      Alcotest.(check bool) "debt composition carried" true (Option.is_some i.total_debt_composition);
      Alcotest.(check int) "one delta_nwc composition per averaged period" (List.length i.delta_nwc_periods)
        (List.length i.delta_nwc_compositions);
      Alcotest.(check bool) "every averaged period has its composition" true
        (List.for_all Option.is_some i.delta_nwc_compositions);
      check_mentions "json" (Boundary_j.string_of_valuation v)
        [ {|"ebit_recipe":"operating_income"|}; {|"cash_composition":{"definition":"cash_and_short_term_investments"|};
          {|"delta_nwc_compositions":[{"definition":"cash_flow_statement_change_in_operating_working_capital"|} ]
  | _ -> Alcotest.fail "no dcf inputs"

let test_definitions_gate () =
  let stale = [ defined_period "2025-09-30"; defined_period ~cash_definition:"cash_equivalents_only" "2024-09-30"; defined_period "2023-09-30" ] in
  let v = run (financials stale) in
  check_reason v
    [ "field definition mismatch: cash follows \"cash_equivalents_only\", reference/field_definitions.json defines \"cash_and_short_term_investments\"; refetch the statements" ];
  Alcotest.(check (option model)) "routed before the gate" (Some `Dcf) v.model;
  Alcotest.(check bool) "nothing computed" true (Option.is_none v.inputs);
  let v = run (financials [ defined_period ~ebit_recipe:"vendor_ebit_row" "2025-09-30"; defined_period "2024-09-30" ]) in
  check_reason v [ "field definition mismatch: ebit recipe follows \"vendor_ebit_row\", reference/field_definitions.json defines \"operating_income | pretax_plus_interest_less_nonoperating\"" ];
  (* the gate sits before the filing-age gate *)
  let v = run (filed ~latest_filing:"2025-01-01" stale) in
  check_reason v [ "field definition mismatch" ];
  (* a record naming no definition passes *)
  Alcotest.check status "legacy record values" `Ok (run (financials (history ()))).status;
  Alcotest.(check bool) "check is pure" true (Result.is_ok (Valuation.definitions_check params.field_definitions (financials (defined_history ()))))

let test_fx_scales_compositions () =
  let c = Fx.convert ~rate:2.0 (financials ~currency:None ~financial_currency:(Some "BRL") ~trading_currency:(Some "USD") (defined_history ())) in
  match (List.hd c.periods).cash_composition with
  | Some k ->
      Alcotest.(check (list approx)) "component values scaled" [ 1200.; 800. ]
        (List.map (fun (k : Boundary_t.component) -> k.value) k.components);
      Alcotest.(check (option approx)) "field scaled" (Some 2000.) (List.hd c.periods).cash
  | None -> Alcotest.fail "composition dropped"

let test_run_diff_lists_drivers () =
  let rename t (v : Boundary_t.valuation) = { v with ticker = t } in
  let base_ok = run (financials (history ())) in
  let base_failed = rename "WAS_FAILED" (run (financials [])) in
  let base_gone = rename "GONE" base_ok in
  let base_ghost = rename "GHOST" base_ok in
  let moved = run (financials (history ~capex:400. ())) in
  let recovered = rename "WAS_FAILED" (run (financials (defined_history ()))) in
  let ghost = rename "GHOST" { base_ok with fair_value = Option.map (fun fv -> fv +. 1.) base_ok.fair_value } in
  let same = rename "SAME" base_ok in
  let fresh = rename "FRESH" base_ok in
  let d = Batch.run_diff ~baseline:[ base_ok; base_failed; base_gone; base_ghost; rename "SAME" base_ok ] [ moved; recovered; ghost; same; fresh ] in
  check_mentions "diff" d
    [ "TEST       Ok 27.94 Buy -> Ok 11.21 Hold delta -16.73 (-59.9%); statements yfinance -> yfinance";
      "capex                      50 -> 400";
      "WAS_FAILED Failed none -> Ok 27.94 Buy; statements yfinance -> yfinance";
      "was: no fiscal periods in statements"; "inputs now present (dcf)";
      "cash                       1000 [cash_and_short_term_investments: cash_equivalents 600 (Cash) + short_term_investments 400 (Other Short Term Investments)]";
      "GHOST      Ok 27.94 Buy -> Ok 28.94 Buy delta +1.00 (+3.6%)";
      "NO DRIVER: moved under test against test with unchanged inputs";
      "SAME       Ok 27.94 Buy -> Ok 27.94 Buy unchanged";
      "FRESH      new: Ok 27.94 Buy; not in the baseline";
      "GONE       in the baseline (Ok 27.94 Buy), not in this run";
      "3 of 5 fair values moved, 1 status changes, 1 moved without a driver" ];
  if contains d "SAME       Ok 27.94 Buy -> Ok 27.94 Buy unchanged; statements yfinance -> yfinance\n           " then
    Alcotest.fail "an unchanged record listed drivers";
  Alcotest.(check string) "deterministic" d (Batch.run_diff ~baseline:[ base_ok; base_failed; base_gone; base_ghost; rename "SAME" base_ok ] [ moved; recovered; ghost; same; fresh ]);
  (* a term the model lost is a driver: the baseline's raw record names it with its value *)
  let raw = Yojson.Safe.from_string (Boundary_j.string_of_valuation base_ghost) in
  let with_term =
    match raw with
    | `Assoc fields ->
        `Assoc
          (List.map
             (fun (k, v) ->
               match (k, v) with
               | "inputs", `List [ tag; `Assoc inputs ] -> (k, `List [ tag; `Assoc (("pv_terminal_value", `Float 250.) :: inputs) ])
               | _ -> (k, v))
             fields)
    | other -> other
  in
  let d = Batch.run_diff ~baseline_raw:[ ("GHOST", with_term) ] ~baseline:[ base_ghost ] [ ghost ] in
  check_mentions "removed term" d [ Printf.sprintf "%-26s %s -> removed from the model" "pv_terminal_value" "250"; "0 moved without a driver" ]

let test_summary_definitions_and_cross_check_listing () =
  let primary = run (filed ~cross_check:a_cross_check (history ())) in
  let s = Batch.summary ~definitions:params.field_definitions [ primary ] in
  check_mentions "summary" s
    [ "field definitions (reference/field_definitions.json, as_of 2026-09-19): cash = cash_and_short_term_investments; total_debt = financial_debt_excluding_operating_leases; delta_nwc = cash_flow_statement_change_in_operating_working_capital; ebit = operating_income_else_pretax_plus_interest";
      "cross-check: 1 of 1 filed-statement records disagree";
      "  on a field the routed model reads: 1 of 1 (TEST)";
      "  TEST       cash filed 36 vendor 54.7 (34.2%)" ];
  let bank = run ~declared:(Some (declaration `Bank)) (filed ~cross_check:a_cross_check [ bank_period () ]) in
  check_mentions "a flag off the model's inputs" (Batch.summary [ bank ]) [ "on a field the routed model reads: 0 of 1\n" ];
  (* a disagreement is listed with its values and nothing else: no free text *)
  let lines = String.split_on_char '\n' s in
  let flag_line = List.find (fun l -> contains l "TEST       cash filed 36 vendor 54.7 (34.2%)") lines in
  Alcotest.(check string) "the flag line is values only" "  TEST       cash filed 36 vendor 54.7 (34.2%)" flag_line;
  if contains s "uncharacterised" || contains s "read by the model" then Alcotest.fail "free text beside a cross-check flag";
  if contains (Batch.summary [ run (financials (history ())) ]) "field definitions" then
    Alcotest.fail "definitions line without definitions"

(* --- implied readouts: what the price needs to be true --- *)

let dcf_inputs (v : Boundary_t.valuation) =
  match v.inputs with Some (`Dcf i) -> i | _ -> Alcotest.fail "no dcf inputs"

let ri_inputs (v : Boundary_t.valuation) =
  match v.inputs with Some (`Residual_income i) -> i | _ -> Alcotest.fail "no residual-income inputs"

let implied_of (v : Boundary_t.valuation) =
  match v.implied with Some i -> i | None -> Alcotest.fail "no implied block on an Ok record"

let horizon_of (s : Boundary_t.implied) =
  match s.horizon_years with Some r -> r | None -> Alcotest.fail "no horizon readout"

(* A growing fixture: rising revenue and reinvestment, so the derived g0 sits above terminal. *)
let growing () =
  List.map2
    (fun period_end revenue -> full_period ~period_end ~total_revenue:revenue ~capex:400. ~delta_nwc:100. ())
    [ "2025-09-30"; "2024-09-30"; "2023-09-30" ] [ 12000.; 10500.; 9000. ]

(* The block for the same inputs at another price: what the solver sees on a record is
   exactly this (price enters the record's wacc through market cap, so a repriced record
   would be a different function; the solver holds the recorded one). *)
let implied_at (m : Boundary_t.model_inputs) price = Implied.of_inputs m ~price

let test_bisect () =
  (match Implied.bisect ~f:(fun x -> x *. x) ~target:2. ~lo:0. ~hi:3. ~tolerance:1e-9 with
  | Implied.Root x -> check_float "sqrt 2" (sqrt 2.) x
  | _ -> Alcotest.fail "no root");
  (match Implied.bisect ~f:(fun x -> -.x) ~target:0.5 ~lo:0. ~hi:3. ~tolerance:1e-9 with
  | Implied.Beyond_low -> ()
  | _ -> Alcotest.fail "a decreasing f with the target above f lo lies beyond the bottom");
  (match Implied.bisect ~f:(fun x -> x) ~target:5. ~lo:0. ~hi:3. ~tolerance:1e-9 with
  | Implied.Beyond_high -> ()
  | _ -> Alcotest.fail "beyond the top");
  match Implied.bisect ~f:(fun _ -> 1.) ~target:5. ~lo:0. ~hi:3. ~tolerance:1e-9 with
  | Implied.Flat -> ()
  | _ -> Alcotest.fail "flat"

let test_dcf_solver_recovers_known_g0_and_lambda () =
  let v = run (financials (growing ())) in
  Alcotest.check status "fixture values" `Ok v.status;
  let i = dcf_inputs v in
  let lambda = i.mean_reversion_lambda.value in
  check_float "the fair-value function reproduces the headline at the recorded g0 and lambda"
    (Option.get v.fair_value) (Implied.dcf_fair_value i ~g0:i.g0 ~lambda);
  Alcotest.(check bool) "fixture grows above terminal" true (i.g0 > i.terminal_growth_rate.value);
  (* at the fair value of another g0, the solver must find that g0 *)
  let target_g0 = 0.08 in
  let solved = implied_at (`Dcf i) (Implied.dcf_fair_value i ~g0:target_g0 ~lambda) in
  Alcotest.(check string) "level name" "implied_g0" solved.level_name;
  (match solved.level.value with
  | Some g -> Alcotest.(check bool) "recovers g0 = 0.08" true (Float.abs (g -. target_g0) < 1e-5)
  | None -> Alcotest.failf "level null: %s" (Option.value solved.level.reason ~default:""));
  (* ... and a known lambda from the half-life *)
  let target_lambda = 0.5 in
  let solved = implied_at (`Dcf i) (Implied.dcf_fair_value i ~g0:i.g0 ~lambda:target_lambda) in
  (match solved.half_life_years.value with
  | Some h -> Alcotest.(check bool) "recovers lambda = 0.5 as its half-life" true (Float.abs (h -. (log 2. /. target_lambda)) < 1e-4)
  | None -> Alcotest.failf "half-life null: %s" (Option.value solved.half_life_years.reason ~default:""));
  Alcotest.(check string) "meaningful by the three-way rule" (if Option.is_some (horizon_of solved).value then "horizon" else "level") solved.meaningful_readout;
  check_mentions "rule" solved.meaningful_rule [ "g0 "; "> terminal growth" ];
  Alcotest.(check (list approx)) "domains" [ -0.5; 3.0 ] solved.level_domain;
  Alcotest.(check (list approx)) "lambda domain" [ 0.01; 5.0 ] solved.lambda_domain;
  Alcotest.(check bool) "held inputs on the record" true
    (List.exists (fun (h : Boundary_t.held_input) -> h.name = "fcff") solved.held);
  (* the record's own block is the block at its own price: the level is its own g0 *)
  let own = implied_of v in
  (match own.level.value with
  | Some g -> Alcotest.(check bool) "at the fair value itself the implied g0 is the recorded g0" true
                (Float.abs (g -. i.g0) < 1e-5 || Float.abs (Option.get v.fair_value -. Option.get v.price) > 1e-9)
  | None -> ());
  check_mentions "json" (Boundary_j.string_of_valuation v) [ {|"implied":{"level_name":"implied_g0"|}; {|"solver":"bisection"|} ]

let test_half_life_guard_and_level_rule () =
  (* the flat fixture: g0 = 0 (historical), terminal 0.025 above it *)
  let v = run (financials (history ())) in
  let i = dcf_inputs v in
  Alcotest.(check bool) "fixture below terminal" true (i.g0 <= i.terminal_growth_rate.value);
  let s = implied_of v in
  Alcotest.(check (option approx)) "half-life not solved" None s.half_life_years.value;
  Alcotest.(check (option string)) "with the exact reason"
    (Some "observed growth is below terminal; persistence is not the question") s.half_life_years.reason;
  Alcotest.(check string) "level is the meaningful readout" "level" s.meaningful_readout;
  check_mentions "rule" s.meaningful_rule [ "<= terminal growth" ];
  Alcotest.(check bool) "level solved" true (Option.is_some s.level.value)

let test_no_solution_in_range_both_ends () =
  let i = dcf_inputs (run (financials (growing ()))) in
  let above = implied_at (`Dcf i) 1e9 in
  Alcotest.(check (option string)) "beyond the top of the growth domain"
    (Some "the price needs a starting growth above 3.00, the top of the domain") above.level.reason;
  Alcotest.(check (option string)) "growth would have to never decay"
    (Some "growth would have to never decay and the price is still above the result") above.half_life_years.reason;
  let below = implied_at (`Dcf i) (-1e9) in
  Alcotest.(check (option string)) "below the bottom of the growth domain"
    (Some "the price needs a starting growth below -0.50, the bottom of the domain") below.level.reason;
  Alcotest.(check (option string)) "price below the no-growth value"
    (Some "price is below the no-growth value") below.half_life_years.reason;
  Alcotest.(check bool) "every null carries a reason" true
    (List.for_all
       (fun (r : Boundary_t.readout) -> (Option.is_some r.value) <> (Option.is_some r.reason))
       [ above.level; above.half_life_years; below.level; below.half_life_years ])

let test_bank_solver_recovers_known_roe () =
  let fin = bank_financials (bank_history ()) in
  let v = run ~declared:(Some (declaration `Bank)) fin in
  Alcotest.check status "bank values" `Ok v.status;
  let i = ri_inputs v in
  let lambda = i.mean_reversion_lambda.value in
  check_float "reproduces the headline" (Option.get v.fair_value)
    (Implied.residual_income_fair_value i ~roe_0:i.roe_0 ~lambda);
  let target = 0.15 in
  let s = implied_at (`Residual_income i) (Implied.residual_income_fair_value i ~roe_0:target ~lambda) in
  Alcotest.(check string) "level name" "implied_roe0" s.level_name;
  (match s.level.value with
  | Some r -> Alcotest.(check bool) "recovers roe 0.15" true (Float.abs (r -. target) < 1e-5)
  | None -> Alcotest.failf "null: %s" (Option.value s.level.reason ~default:""));
  Alcotest.(check (list approx)) "roe domain" [ -0.5; 1.0 ] s.level_domain;
  (* the bank fixture's roe 0.2 sits above its cost of equity: persistence is the question *)
  Alcotest.(check string) "meaningful by the three-way rule" (if Option.is_some (horizon_of s).value then "horizon" else "level") s.meaningful_readout;
  check_mentions "rule" s.meaningful_rule [ "roe_0 "; "> cost of equity" ];
  let s = implied_at (`Residual_income i) (Implied.residual_income_fair_value i ~roe_0:i.roe_0 ~lambda:1.0) in
  (match s.half_life_years.value with
  | Some h -> Alcotest.(check bool) "recovers lambda 1.0" true (Float.abs (h -. log 2.) < 1e-4)
  | None -> Alcotest.failf "null: %s" (Option.value s.half_life_years.reason ~default:""));
  (* an insurer carries the same block on its core *)
  let ins = run ~declared:(Some (declaration `Insurer)) (insurer_financials (insurer_history ())) in
  Alcotest.(check string) "insurer level name" "implied_roe0" (implied_of ins).level_name;
  (* a bank whose roe sits below its cost of equity reads the level, with the roe wording *)
  let s = implied_at (`Residual_income { i with roe_0 = i.cost_of_equity -. 0.01 }) 10. in
  Alcotest.(check (option string)) "roe guard names the cost of equity"
    (Some "observed roe is below the cost of equity; persistence is not the question") s.half_life_years.reason;
  Alcotest.(check string) "level then" "level" s.meaningful_readout;
  (* a Failed record carries none *)
  Alcotest.(check bool) "no block on a failed record" true (Option.is_none (run (financials [])).implied)

let test_headline_independent_of_the_readouts () =
  let v = run (financials (growing ())) in
  let stripped = { v with implied = None } in
  Alcotest.(check (option approx)) "fair value" v.fair_value stripped.fair_value;
  Alcotest.(check bool) "block is pure: same inputs, same block" true
    (Boundary_j.string_of_implied (implied_of v) = Boundary_j.string_of_implied (implied_of (run (financials (growing ())))))

let derived_ebit_period ?(recipe = "pretax_plus_interest_less_nonoperating") period_end =
  { (full_period ~period_end ()) with ebit_recipe = Some recipe }

let ebit_check ~agree : Boundary_t.cross_check =
  { a_cross_check with
    fields = [ { field = "ebit"; primary = Some 25287.; secondary = Some 25596.; relative_difference = Some 0.012; agree = Some agree } ];
    disagreements = (if agree then 0 else 1) }

let test_ebit_policy_gate () =
  let periods = List.map derived_ebit_period [ "2025-09-30"; "2024-09-30"; "2023-09-30" ] in
  let ok = run (filed ~cross_check:(ebit_check ~agree:true) periods) in
  Alcotest.check status "a derived ebit within threshold runs" `Ok ok.status;
  let miss = run (filed ~cross_check:(ebit_check ~agree:false) periods) in
  check_reason miss
    [ "operating income not filed; derived EBIT misses the cross-check (pretax_plus_interest_less_nonoperating: derived 2.529e+04 against the vendor's 2.56e+04, 1.2% beyond the 2% threshold)" ];
  Alcotest.(check bool) "nothing computed" true (Option.is_none miss.inputs);
  let unchecked = run (filed periods) in
  check_reason unchecked [ "operating income not filed; derived EBIT misses the cross-check (pretax_plus_interest_less_nonoperating: no vendor operating income to check against)" ];
  let reported = run (filed ~cross_check:(ebit_check ~agree:false) (List.map (derived_ebit_period ~recipe:"operating_income") [ "2025-09-30"; "2024-09-30"; "2023-09-30" ])) in
  Alcotest.check status "filed operating income is never gated" `Ok reported.status;
  let bank = run ~declared:(Some (declaration `Bank)) (filed ~cross_check:(ebit_check ~agree:false) [ { (bank_period ()) with ebit_recipe = Some "pretax_plus_interest_less_nonoperating" }; { (bank_period ()) with period_end = "2024-09-30"; ebit_recipe = Some "pretax_plus_interest_less_nonoperating" } ]) in
  Alcotest.(check bool) "the gate is a dcf gate" true (bank.failed_reason = None || not (contains (Option.get bank.failed_reason) "derived EBIT"));
  Alcotest.(check int) "policy allows one refinement" 1 params.field_definitions.refinement_policy.max_refinements_per_field;
  Alcotest.(check int) "recipes: operating income plus one derived" 2 (List.length params.field_definitions.ebit.recipes)

let test_summary_implied_line () =
  let rename t (v : Boundary_t.valuation) = { v with ticker = t } in
  let grow = run (financials (growing ())) in
  let i = dcf_inputs grow in
  let at t price = rename t { grow with implied = Some (implied_at (`Dcf i) price) } in
  let vs =
    [ at "SOLVED" (Implied.dcf_fair_value i ~g0:i.g0 ~lambda:0.5); rename "FLAT" (run (financials (history ())));
      at "HIGH" 1e9; at "LOW" (-1e9); rename "NOPE" (run (financials [])) ]
  in
  check_mentions "summary" (Batch.summary vs)
    [ "implied half-life, across 4 Ok names: median "; "years (range "; ", 1 solved)";
      "beyond range: 1 would need growth or roe that never decays, 1 priced below the no-growth value";
      "level is the meaningful readout for 1 (start at or below its target)" ];
  if contains (Batch.summary [ rename "NOPE" (run (financials [])) ]) "implied half-life, across" then
    Alcotest.fail "implied line without Ok records"

(* --- ifrs filers: the currency agreement gate, taxonomy carried, zero dividends --- *)

let test_currency_agreement_gate () =
  let ifrs ?(latest_filing = "2026-02-26") periods = financials ~provider:"SEC XBRL companyfacts" ~taxonomy:"ifrs-full" ~latest_filing periods in
  let agree = run { (ifrs (history ())) with vendor_financial_currency = Some "USD" } in
  Alcotest.check status "agreeing currencies value" `Ok agree.status;
  Alcotest.(check string) "taxonomy carried onto the valuation" "ifrs-full" agree.taxonomy;
  check_mentions "json" (Boundary_j.string_of_valuation agree) [ {|"taxonomy":"ifrs-full"|} ];
  let disagree = run { (ifrs (history ())) with vendor_financial_currency = Some "EUR" } in
  check_reason disagree [ "financial currency disagreement: filing USD, vendor EUR" ];
  Alcotest.(check (option model)) "routed before the gate" (Some `Dcf) disagree.model;
  Alcotest.(check bool) "nothing computed" true (Option.is_none disagree.inputs);
  (* the gate sits before the definitions and filing-age gates *)
  let both = run { (ifrs ~latest_filing:"2025-01-01" (history ())) with vendor_financial_currency = Some "EUR" } in
  check_reason both [ "financial currency disagreement" ];
  (* a vendor record names no vendor currency: nothing to compare *)
  Alcotest.(check bool) "vendor record passes" true (Result.is_ok (Valuation.currency_agreement (financials (history ()))));
  if contains (Boundary_j.string_of_valuation (run (financials (history ())))) "taxonomy" then
    Alcotest.fail "taxonomy leaked into a vendor record"

let test_zero_dividends_is_a_payout_absent_is_not () =
  (* a bank that files dividends of zero retains everything: retention 1.0, recorded *)
  let zero = run ~declared:(Some (declaration `Bank)) (bank_financials (bank_history ~dividends:(Some 0.) ())) in
  Alcotest.check status "zero dividends values" `Ok zero.status;
  (match zero.inputs with
  | Some (`Residual_income i) ->
      check_float "retention 1.0" 1.0 i.retention;
      check_float "payout 0" 0. i.payout_ratio;
      Alcotest.(check (option approx)) "dividends recorded as 0" (Some 0.) i.dividends_paid
  | _ -> Alcotest.fail "no residual-income inputs");
  (* an absent dividends tag cannot be told from none: refused *)
  let absent = run ~declared:(Some (declaration `Bank)) (bank_financials (bank_history ~dividends:None ())) in
  check_reason absent [ "payout not derivable: need 2 fiscal periods with positive net income and dividends paid, have 0" ]

(* --- the implied horizon (14) --- *)

let test_horizon_recovers_known_n_and_is_monotone () =
  let v = run (financials (growing ())) in
  let i = dcf_inputs v in
  let lambda = i.mean_reversion_lambda.value in
  let fv n = Implied.dcf_fair_value ~projection_years:n i ~g0:i.g0 ~lambda in
  check_float "at the recorded horizon the function is the headline" (Option.get v.fair_value) (fv i.projection_years.value);
  (* monotone increasing in the horizon under the guard, converging *)
  let values = List.init 40 (fun k -> fv (k + 1)) in
  List.iteri (fun k x -> if k > 0 && x < List.nth values (k - 1) then Alcotest.failf "fair value fell from %d to %d years" k (k + 1)) values;
  Alcotest.(check bool) "converging: the last step is smaller than the first" true
    (List.nth values 39 -. List.nth values 38 < List.nth values 1 -. List.nth values 0);
  (* priced exactly at the 14-year value: the scan lands on 14 with its bracket *)
  let s = implied_at (`Dcf i) (fv 14) in
  let h = horizon_of s in
  Alcotest.(check (option approx)) "recovers N = 14" (Some 14.) h.value;
  Alcotest.(check (list approx)) "bracket is fair value at 13 and 14" [ fv 13; fv 14 ] s.horizon_bracket;
  Alcotest.(check (option approx)) "fair value at 40 recorded" (Some (fv 40)) s.fair_value_at_40;
  Alcotest.(check string) "meaningful: horizon" "horizon" s.meaningful_readout;
  check_mentions "rule" s.meaningful_rule [ "> terminal growth"; "a horizon solves at 14 years: horizon" ];
  Alcotest.(check string) "rf tenor stated" "held at the recorded 7y point, not re-selected per horizon" s.rf_tenor;
  Alcotest.(check bool) "rf held" true (List.exists (fun (h : Boundary_t.held_input) -> h.name = "risk_free_rate" && h.value = i.risk_free_rate.value) s.held);
  (* a price between two integer years lands on the first year that reaches it *)
  let between = implied_at (`Dcf i) (0.5 *. (fv 9 +. fv 10)) in
  Alcotest.(check (option approx)) "N = 10" (Some 10.) (horizon_of between).value;
  check_mentions "json" (Boundary_j.string_of_valuation v) [ {|"horizon_years":{"value":|}; {|"fair_value_at_40":|}; {|"rf_tenor":"held at the recorded 7y point|} ]

let test_horizon_guard_beyond_40_and_below_one_year () =
  let i = dcf_inputs (run (financials (growing ()))) in
  let lambda = i.mean_reversion_lambda.value in
  let fv n = Implied.dcf_fair_value ~projection_years:n i ~g0:i.g0 ~lambda in
  let beyond = implied_at (`Dcf i) (fv 40 +. 1.) in
  Alcotest.(check (option string)) "beyond 40 names the 40-year value and the price"
    (Some (Printf.sprintf "even indefinite persistence of the decaying growth path does not reach the price: fair value at 40 years %.2f against price %.2f" (fv 40) (fv 40 +. 1.)))
    (horizon_of beyond).reason;
  Alcotest.(check (option approx)) "fair value at 40 on the record" (Some (fv 40)) beyond.fair_value_at_40;
  Alcotest.(check string) "then level is the readout" "level" beyond.meaningful_readout;
  check_mentions "rule" beyond.meaningful_rule [ "no horizon at or below 40 years reaches the price: level" ];
  let below = implied_at (`Dcf i) (fv 1 -. 1.) in
  Alcotest.(check (option string)) "below one year" (Some "price is at or below the one-year value") (horizon_of below).reason;
  Alcotest.(check bool) "bracket empty" true (below.horizon_bracket = []);
  (* the guard: the flat fixture sits below terminal *)
  let flat = implied_of (run (financials (history ()))) in
  Alcotest.(check (option string)) "guard reason" (Some "observed growth is below terminal; persistence is not the question") (horizon_of flat).reason;
  Alcotest.(check (option approx)) "no 40-year value without the guard" None flat.fair_value_at_40;
  Alcotest.(check string) "level" "level" flat.meaningful_readout;
  check_mentions "rule" flat.meaningful_rule [ "<= terminal growth"; ": level" ];
  Alcotest.(check bool) "every null carries a reason" true
    (List.for_all (fun (r : Boundary_t.readout) -> Option.is_some r.value <> Option.is_some r.reason)
       [ horizon_of beyond; horizon_of below; horizon_of flat ])

let test_residual_income_horizon_recovers_known_n () =
  let v = run ~declared:(Some (declaration `Bank)) (bank_financials (bank_history ())) in
  let i = ri_inputs v in
  let lambda = i.mean_reversion_lambda.value in
  let fv n = Implied.residual_income_fair_value ~projection_years:n i ~roe_0:i.roe_0 ~lambda in
  check_float "headline reproduced" (Option.get v.fair_value) (fv i.projection_years.value);
  (* without a terminal the horizon is monotone increasing and converging on this path too *)
  let values = List.init 40 (fun k -> fv (k + 1)) in
  List.iteri (fun k x -> if k > 0 && x < List.nth values (k - 1) then Alcotest.failf "bank fair value fell from %d to %d years" k (k + 1)) values;
  Alcotest.(check bool) "converging" true (List.nth values 39 -. List.nth values 38 < List.nth values 1 -. List.nth values 0);
  let s = implied_at (`Residual_income i) (fv 9) in
  Alcotest.(check (option approx)) "recovers N = 9" (Some 9.) (horizon_of s).value;
  Alcotest.(check (list approx)) "bracket" [ fv 8; fv 9 ] s.horizon_bracket;
  Alcotest.(check string) "horizon" "horizon" s.meaningful_readout;
  check_mentions "rule" s.meaningful_rule [ "> cost of equity"; "a horizon solves at 9 years" ];
  let guard = implied_at (`Residual_income { i with roe_0 = i.cost_of_equity -. 0.01 }) 10. in
  Alcotest.(check (option string)) "roe guard" (Some "observed roe is below the cost of equity; persistence is not the question") (horizon_of guard).reason;
  Alcotest.(check string) "level under a failed guard" "level" guard.meaningful_readout

let test_summary_horizon_line () =
  let rename t (v : Boundary_t.valuation) = { v with ticker = t } in
  let grow = run (financials (growing ())) in
  let i = dcf_inputs grow in
  let fv n = Implied.dcf_fair_value ~projection_years:n i ~g0:i.g0 ~lambda:i.mean_reversion_lambda.value in
  let at t price = rename t { grow with implied = Some (implied_at (`Dcf i) price) } in
  let vs = [ at "H14" (fv 14); at "H10" (fv 10); at "H20" (fv 20); at "FAR" (fv 40 +. 1.); rename "FLAT" (run (financials (history ()))) ] in
  check_mentions "summary" (Batch.summary vs)
    [ "implied horizon, across 4 Ok names under the guard (start above its target): median 14 years (range 10 to 20, 3 solved); 1 beyond 40 years";
      "level is the meaningful readout for 2 (1 guard failed, 1 beyond 40)";
      "implied half-life, across 5 Ok names:" ]

(* --- stability: the same name on two snapshots (16) --- *)

let classes (items : Batch.moved_input list) = List.map (fun (m : Batch.moved_input) -> (m.name, Batch.class_name m.klass)) items

let filed_at ~accession periods =
  { (filed periods) with periods = List.map (fun (p : Boundary_t.fiscal_period) -> { p with accession = Some accession }) periods }

let test_stability_classifier () =
  let base = financials (history ()) in
  let v0 = run base in
  (* a price move on the same statements: price, market cap and shares, nothing else *)
  let priced = { base with price = Some 12.; market_cap = Some 6000. } in
  Alcotest.(check (list (pair string string))) "price only"
    [ ("price", "price"); ("market_cap", "price") ]
    (classes (Batch.moved_inputs ~old:(v0, Some base) ~now:(run priced, Some priced)));
  (* a vendor row moved with no filing behind it *)
  let vendor_moved = financials (history ~capex:400. ()) in
  Alcotest.(check (list (pair string string))) "vendor row"
    [ ("capex", "vendor_row") ]
    (classes (Batch.moved_inputs ~old:(v0, Some base) ~now:(run vendor_moved, Some vendor_moved)));
  (* filed statements: the same accession and period with a changed value is a restatement *)
  let a = filed_at ~accession:"0001-26-1" (history ()) in
  let restated = filed_at ~accession:"0001-26-1" (history ~capex:400. ()) in
  Alcotest.(check (list (pair string string))) "restated"
    [ ("capex", "restated") ]
    (classes (Batch.moved_inputs ~old:(run a, Some a) ~now:(run restated, Some restated)));
  (* ... and with a new accession it is a new filing *)
  let newer = filed_at ~accession:"0001-27-1" (history ~capex:400. ()) in
  Alcotest.(check (list (pair string string))) "new filing"
    [ ("capex", "new_filing") ]
    (classes (Batch.moved_inputs ~old:(run a, Some a) ~now:(run newer, Some newer)));
  (* a parameter moved: rate or fx *)
  let rf_moved = { params with risk_free = Reference_j.risk_free_rates_of_string (String.concat "" [ {|{"max_age_days": 45, "tenors": ["7y"], "countries": {"United States": {"source": "FRED", "tier": "official", "as_of": "2026-09-09", "rates": {"7y": 0.05}}}}|} ]) } in
  let v_rf = Valuation.run rf_moved ~today ~model_version:"test" ~declaration:(Some (declaration `OperatingCompany)) base in
  Alcotest.(check (list (pair string string))) "rate"
    [ ("risk_free_rate", "rate_or_fx") ]
    (classes (Batch.moved_inputs ~old:(v0, Some base) ~now:(v_rf, Some base)));
  (* a provider change, or a status change, is unexplained and named *)
  let items = Batch.moved_inputs ~old:(v0, Some base) ~now:(run a, Some a) in
  Alcotest.(check bool) "provider change unexplained" true
    (List.exists (fun (m : Batch.moved_input) -> m.klass = Batch.Unexplained && m.name = "statements_provider yfinance -> SEC XBRL companyfacts") items);
  let items = Batch.moved_inputs ~old:(v0, Some base) ~now:(run (financials []), None) in
  Alcotest.(check (list (pair string string))) "status change unexplained" [ ("status Ok -> Failed", "unexplained") ] (classes items);
  Alcotest.(check (list (pair string string))) "unchanged" [] (classes (Batch.moved_inputs ~old:(v0, Some base) ~now:(v0, Some base)))

let test_stability_report () =
  let base = financials (history ()) in
  let priced = { base with price = Some 12.; market_cap = Some 6000. } in
  let text, line =
    Batch.stability ~snapshot_old:"2026-09-19" ~snapshot_new:"2026-09-19-2"
      ~old:[ (run base, Some base) ]
      ~now:[ (run priced, Some priced) ]
  in
  check_mentions "report" text
    [ "stability: snapshot 2026-09-19-2 against snapshot 2026-09-19"; "rates or fx refreshed between the runs: no (risk-free as_of 2026-09-08 on both)";
      "TEST       2 moved input(s); fair value 27.94 -> 25.58"; "price        price"; "10 -> 12" ];
  Alcotest.(check string) "summary line" "stability against snapshot 2026-09-19: price 2, new_filing 0, restated 0, vendor_row 0, rate_or_fx 0, unexplained 0" line;
  check_mentions "summary carries the line" (Batch.summary ~stability_line:line [ run base ]) [ line ]

(* --- point-in-time (17) --- *)

let pit ?statements_unavailable ?shares_unavailable ?rates_unavailable as_of_date : Boundary_t.point_in_time =
  { as_of_date; price_date = Some as_of_date; close_as_served = Some 10.; split_factor = Some 1.; shares_source = "dei cover page";
    shares_tag = Some "EntityCommonStockSharesOutstanding"; shares_as_of = Some as_of_date; shares_filed = Some as_of_date;
    rate_observations = [ ("DGS7", as_of_date) ]; anachronistic_inputs = []; statements_unavailable; shares_unavailable; rates_unavailable }

let test_point_in_time_gates_and_vintages () =
  let vendor = { (financials (history ())) with point_in_time = Some (pit ~statements_unavailable:"vendor provider carries no filing dates" "2025-06-30") } in
  check_reason (run vendor) [ "no point-in-time statements: vendor provider carries no filing dates" ];
  let no_shares = { (filed (history ())) with point_in_time = Some (pit ~shares_unavailable:"dei cover page count not filed" "2025-06-30") } in
  check_reason (run no_shares) [ "no point-in-time shares: dei cover page count not filed" ];
  let no_rates = { (filed (history ())) with point_in_time = Some (pit ~rates_unavailable:"EUR" "2025-06-30") } in
  check_reason (run no_rates) [ "rate source has no history for EUR" ];
  (* a past date: the ERP, tax and assumption vintages postdate it; held and declared, never refused *)
  let past = { (filed ~latest_filing:"2025-02-20" (history ())) with point_in_time = Some (pit "2025-06-30") } in
  let v = Valuation.run params ~today:"2025-06-30" ~model_version:"test" ~declaration:(Some (declaration `OperatingCompany)) past in
  Alcotest.check status "valued on the past date" `Ok v.status;
  (match v.point_in_time with
  | Some p ->
      check_mentions "anachronistic inputs named with their vintage" (String.concat "; " p.anachronistic_inputs)
        [ "equity_risk_premium (vintage 2026-01-01)"; "statutory_tax_rate (vintage 2026-01-01)"; "beta (vintage 2026-01-01)"; "bank_nii_ratio_threshold (vintage 2026-09-01)" ];
      (* the fixture's curve is dated 2026-09-08, so on this date it is anachronistic too and says so *)
      check_mentions "a curve dated after the date is declared" (String.concat "; " p.anachronistic_inputs) [ "risk_free_rate (vintage 2026-09-08)" ]
  | None -> Alcotest.fail "point-in-time block dropped");
  (match v.inputs with
  | Some (`Dcf i) -> Alcotest.(check bool) "held vintage carries a negative age" true (i.equity_risk_premium.age_days < 0)
  | _ -> Alcotest.fail "no inputs");
  (* the live path is untouched: a future vintage is still refused *)
  let live = Valuation.run params ~today:"2025-06-30" ~model_version:"test" ~declaration:(Some (declaration `OperatingCompany)) (filed ~latest_filing:"2025-02-20" (history ())) in
  check_reason live [ "later than the valuation date" ];
  if contains (Boundary_j.string_of_valuation live) "point_in_time" then Alcotest.fail "point_in_time leaked into a live record"

(* --- the REIT model (18) --- *)

(* Two filed years of a REIT: FFO 400 then 440 on 100 weighted-average diluted shares (ffo
   per share 4.0 -> 4.4, a 10% CAGR), dividends 300 (covered: coverage 0.75), 100 effective
   shares at price 40 (market cap 4000). *)
let reit_history ?(dividends = Some 300.) ?(ffo_now = Some 440.) ?(shares_now = 100.) () =
  [ period ~period_end:"2025-12-31" ~net_income:200. ~depreciation_amortization:240. ?ffo:ffo_now ~weighted_shares:shares_now
      ~weighted_shares_tag:"WeightedAverageNumberOfDilutedSharesOutstanding" ?dividends_paid:dividends ~dividends_paid_row:"PaymentsOfDividendsCommonStock" ();
    period ~period_end:"2024-12-31" ~net_income:180. ~depreciation_amortization:220. ~ffo:400. ~weighted_shares:100.
      ~weighted_shares_tag:"WeightedAverageNumberOfDilutedSharesOutstanding" ~dividends_paid:280. ~dividends_paid_row:"PaymentsOfDividendsCommonStock" () ]

let reit_financials periods =
  { (filed periods) with price = Some 40.; market_cap = Some 4000.; industry = Some "REIT - Retail" }

(* lambda 0 holds growth at g0 = 0.10 for 2 years; ke = 0.02 + 1.0 x 0.10 = 0.12; g_T 0.02.
   D0 = 300 / 100 = 3; D1 = 3.3, D2 = 3.63; pv = 3.3/1.12 + 3.63/1.2544; terminal = 3.63 x 1.02 / 0.10 = 37.026 at N = 2 *)
let reit_assumptions = { bank_assumptions with equity_risk_premium = param 0.10 }

let test_reit_value_by_hand () =
  let inputs, fair_value = get (Reit.value reit_assumptions ~country:"T" (reit_financials (reit_history ()))) in
  (* the CAGR spans 365 days, so g = 1.1 ^ (365.25 / 365) - 1, a hair above 0.10, as the dcf's Growth.cagr *)
  let g = (1.1 ** (365.25 /. 365.)) -. 1. in
  let d1 = 3. *. (1. +. g) and d2 = 3. *. (1. +. g) *. (1. +. g) in
  let pv = (d1 /. 1.12) +. (d2 /. 1.2544) in
  let terminal = d2 *. 1.02 /. 0.10 in
  check_float "fair value" (pv +. (terminal /. 1.2544)) fair_value;
  check_float "ffo per share on effective shares" 4.4 inputs.ffo_per_share;
  check_float "price to ffo" (40. /. 4.4) inputs.price_to_ffo;
  check_float "coverage" (300. /. 440.) inputs.coverage;
  check_float "covered dividend" 300. inputs.covered_dividend;
  check_float "dividend per share" 3. inputs.dividend_per_share;
  check_float "ffo per weighted share cagr" g inputs.g_historical;
  Alcotest.(check (list string)) "periods" [ "2025-12-31"; "2024-12-31" ] inputs.ffo_periods;
  Alcotest.(check (list (pair string string))) "the count's tag per period"
    [ ("2025-12-31", "WeightedAverageNumberOfDilutedSharesOutstanding"); ("2024-12-31", "WeightedAverageNumberOfDilutedSharesOutstanding") ]
    inputs.weighted_shares_tags;
  Alcotest.(check (list approx)) "dividend path" [ d1; d2 ] inputs.dividend_path;
  check_float "terminal" terminal inputs.terminal_value;
  check_mentions "caveat" inputs.caveat [ "FFO overstates distributable cash" ]

(* A merger year: FY2025's FFO 440 accrued over a weighted 100 shares, but a point count
   taken after the merger closed would be 160. The growth series uses the weighted count,
   and the period record has no field a point count could enter by. *)
let test_reit_growth_uses_the_weighted_count_not_a_point_count () =
  let inputs, _ = get (Reit.value reit_assumptions ~country:"T" (reit_financials (reit_history ()))) in
  Alcotest.(check (list (pair string approx))) "ffo per weighted share" [ ("2025-12-31", 4.4); ("2024-12-31", 4.0) ] inputs.ffo_per_weighted_share;
  let point_count_cagr = (440. /. 160.) /. 4.0 -. 1. in
  Alcotest.(check bool) "a point count would have read the merger as negative growth" true (point_count_cagr < 0. && inputs.g_historical > 0.09);
  (* the weighted count moves with the merger: the same flows on 120 weighted shares *)
  let merged, _ = get (Reit.value reit_assumptions ~country:"T" (reit_financials (reit_history ~shares_now:120. ()))) in
  check_float "ffo per weighted share on the merger year" (440. /. 120.) (List.assoc "2025-12-31" merged.ffo_per_weighted_share);
  Alcotest.(check bool) "growth read on the period's own count" true (merged.g_historical < inputs.g_historical);
  (* no weighted count on a period: that period leaves the series, never a substitute *)
  let one = { (List.hd (reit_history ())) with weighted_shares = None } in
  check_error "count absent" (Reit.value reit_assumptions ~country:"T" (reit_financials [ one; List.nth (reit_history ()) 1 ])) [ "ffo growth needs two periods with ffo and weighted-average shares, have 1" ]

let test_reit_covered_dividend_and_guards () =
  (* payout above FFO: only the covered part is valued, coverage > 1 recorded *)
  let inputs, fair_value = get (Reit.value reit_assumptions ~country:"T" (reit_financials (reit_history ~dividends:(Some 500.) ()))) in
  check_float "covered at ffo" 440. inputs.covered_dividend;
  check_float "coverage above 1" (500. /. 440.) inputs.coverage;
  check_float "D0 is the covered dividend per share" 4.4 inputs.dividend_per_share;
  let _, covered_only = get (Reit.value reit_assumptions ~country:"T" (reit_financials (reit_history ~dividends:(Some 440.) ()))) in
  check_float "the uncovered part adds nothing" covered_only fair_value;
  check_error "one period of ffo per share"
    (Reit.value reit_assumptions ~country:"T" (reit_financials [ List.hd (reit_history ()) ]))
    [ "ffo growth needs two periods with ffo and weighted-average shares"; "have 1" ];
  check_error "cost of equity vs terminal"
    (Reit.value { reit_assumptions with terminal_growth_rate = param 0.5 } ~country:"T" (reit_financials (reit_history ())))
    [ "cost of equity"; "does not exceed terminal growth" ];
  check_error "no ffo" (Reit.value reit_assumptions ~country:"T" (reit_financials (reit_history ~ffo_now:None ()))) [ "missing statement fields"; "ffo" ];
  check_error "no dividends" (Reit.value reit_assumptions ~country:"T" (reit_financials (reit_history ~dividends:None ()))) [ "missing statement fields"; "dividends_paid" ]

let test_reit_routes_and_implied () =
  let v = run ~declared:(Some (declaration `Reit)) (reit_financials (reit_history ())) in
  Alcotest.(check (option string)) "a reit values" None v.failed_reason;
  Alcotest.check status "a reit values" `Ok v.status;
  Alcotest.(check (option model)) "routed to the reit model" (Some `Reit_ffo_dividend) v.model;
  check_mentions "floor" v.floor.basis [ "reit ffo dividend"; "coverage"; "FFO overstates" ];
  check_mentions "json" (Boundary_j.string_of_valuation v) [ {|"model":"reit_ffo_dividend"|}; {|"inputs":["reit_ffo_dividend",{|}; {|"caveat":"FFO overstates|} ];
  (match v.inputs with
  | Some (`Reit_ffo_dividend i) ->
      let lambda = i.mean_reversion_lambda.value in
      check_float "the fair-value function reproduces the headline" (Option.get v.fair_value) (Implied.reit_fair_value i ~g0:i.g0 ~lambda);
      let target = 0.05 in
      let s = implied_at (`Reit_ffo_dividend i) (Implied.reit_fair_value i ~g0:target ~lambda) in
      Alcotest.(check string) "level name" "implied_g0" s.level_name;
      (match s.level.value with
      | Some g -> Alcotest.(check bool) "recovers g0 = 0.05" true (Float.abs (g -. target) < 1e-5)
      | None -> Alcotest.failf "null: %s" (Option.value s.level.reason ~default:""));
      let s = implied_at (`Reit_ffo_dividend i) (Implied.reit_fair_value ~projection_years:12 i ~g0:i.g0 ~lambda) in
      Alcotest.(check (option approx)) "horizon recovers N = 12" (Some 12.) (horizon_of s).value
  | _ -> Alcotest.fail "no reit inputs");
  let vendor = run ~declared:(Some (declaration `Reit)) (financials (reit_history ())) in
  Alcotest.check status "vendor rows carry no ffo: the model still runs when the fetch left ffo on the period" `Ok vendor.status

(* --- batch summary --- *)

let test_batch_summary () =
  let universe =
    get
      (Universe.load_string
         {|{"tickers": [
          {"ticker": "TEST", "entity_class": "OperatingCompany", "why": "a plain operating company"},
          {"ticker": "WRP", "entity_class": "Wrapper", "why": "a fund"},
          {"ticker": "WRONG", "entity_class": "OperatingCompany", "why": "a plain operating company"},
          {"ticker": "ABSENT", "entity_class": "Wrapper", "why": "a fund", "scope_limits": ["never run"]}]}|})
  in
  let rename t (v : Boundary_t.valuation) = { v with ticker = t } in
  let vs =
    [
      run (financials (history ()));
      rename "WRP" (run ~declared:(Some (declaration `Wrapper)) (financials [ bank_period () ]));
      rename "WRONG" (run (financials []));
    ]
  in
  let s = Batch.summary ~universe vs in
  check_mentions "summary" s
    [ "3 records, 1 Ok, 2 Failed"; "by class: OperatingCompany 2, Wrapper 1";
      "1  dcf not admissible for Wrapper"; "1  no fiscal periods in statements";
      "TEST       Ok      OperatingCompany   fair_value";
      "WRONG      Failed  OperatingCompany   no fiscal periods in statements";
      "in the universe but not run: ABSENT" ];
  if contains s "EXPECTED" || contains s "as expected" then Alcotest.fail "the summary judged a run against a stored expectation";
  check_mentions "a ticker outside the universe is marked" (Batch.summary ~universe [ rename "ELSE" (run (financials (history ()))) ]) [ "[not in universe]" ];
  (* the strict loader: an unknown field, a missing why, an unknown class *)
  let reject text needles = match Universe.load_string text with Ok _ -> Alcotest.fail "loaded" | Error e -> check_mentions "load error" e needles in
  reject {|{"tickers": [{"ticker": "X", "entity_class": "Bank", "why": "a bank", "outcome": "Ok"}]}|} [ "universe entry X carries unknown field(s) outcome"; "exactly ticker, entity_class, why, scope_limits" ];
  reject {|{"tickers": [{"ticker": "X", "entity_class": "Bank", "why": "a bank", "note": "n", "finding": "f"}]}|} [ "unknown field(s) note, finding" ];
  reject {|{"tickers": [{"ticker": "X", "entity_class": "Bank"}]}|} [ "universe entry X lacks why" ];
  reject {|{"tickers": [{"ticker": "X", "entity_class": "Bank", "why": "  "}]}|} [ "lacks why" ];
  reject {|{"tickers": [{"ticker": "X", "entity_class": "Hedge", "why": "a fund"}]}|} [ "declares unknown class \"Hedge\"" ];
  reject {|{"tickers": [{"ticker": "X", "entity_class": "Bank", "why": "a bank", "scope_limits": "x"}]}|} [ "scope_limits must be a list of strings" ];
  reject {|{"names": []}|} [ "no tickers list" ];
  Alcotest.(check bool) "the tracked file loads strictly" true (Result.is_ok (Universe.load "../../reference/universe.json"));
  (* model_version (21): the stamp, the summary's first line, the run diff's header *)
  let ok = List.hd vs in
  Alcotest.(check string) "clean tree" "abc1234" (Model_version.stamp ~head:(Some "abc1234\n") ~porcelain:"");
  Alcotest.(check string) "dirty tree" "abc1234-dirty"
    (Model_version.stamp ~head:(Some "abc1234\n") ~porcelain:" M ocaml/lib/batch.ml\n?? notes.txt\n");
  Alcotest.(check string) "outside a checkout" "unversioned" (Model_version.stamp ~head:None ~porcelain:"");
  Alcotest.(check string) "an empty hash is no version" "unversioned" (Model_version.stamp ~head:(Some "\n") ~porcelain:"");
  check_mentions "summary opens with the version" s [ "valued_on 2026-09-10, model_version test: 3 records, 1 Ok, 2 Failed" ];
  check_mentions "a run without a version is said so"
    (Batch.summary [ { ok with model_version = "" } ]) [ "model_version unrecorded:" ];
  check_mentions "the dated run directory is named last" (Batch.summary ~run_dir:"output/runs/2026-09-10-2" [ ok ])
    [ "\nrun written to output/runs/2026-09-10-2\n" ];
  check_mentions "the run diff names both versions"
    (Batch.run_diff ~baseline:[ { ok with model_version = "old1" } ] [ { ok with fair_value = Some 1.0 } ])
    [ "this run (valued_on 2026-09-10, model_version test) against the baseline run (valued_on 2026-09-10, model_version old1)";
      "NO DRIVER: moved under test against old1 with unchanged inputs" ];
  (* dated runs (21): never overwritten *)
  let taken = [ "out/runs/2026-09-10"; "out/runs/2026-09-10-2" ] in
  let exists d = List.mem d taken in
  Alcotest.(check string) "first run of the day" "out/runs/2026-09-11" (Batch.dated_run_dir ~exists ~root:"out/runs" "2026-09-11");
  Alcotest.(check string) "third run of the day" "out/runs/2026-09-10-3" (Batch.dated_run_dir ~exists ~root:"out/runs" "2026-09-10");
  (* the software class (21) values on the dcf like an operating company *)
  let software = run ~declared:(Some (declaration `HighGrowthSoftware)) (financials (history ())) in
  Alcotest.check status "software class is Ok on the dcf" `Ok software.status;
  Alcotest.(check (option model)) "routed to the dcf" (Some `Dcf) software.model;
  Alcotest.(check (option approx)) "same number as the operating company" ok.fair_value software.fair_value;
  Alcotest.(check string) "stamped" "test" software.model_version;
  (* and in the tracked table the software class admits the dcf while PreProfit still refuses *)
  let tracked = get (Params.load ~dir:"../../reference") in
  let admits c = match Admissibility.rule tracked.admissibility c with Ok r -> r.admissible_models | Error e -> Alcotest.fail e in
  Alcotest.(check (list string)) "tracked: software admits the dcf" [ "dcf" ] (admits `HighGrowthSoftware);
  Alcotest.(check (list string)) "tracked: pre-profit admits nothing" [] (admits `PreProfit);
  Alcotest.(check string) "reason key drops specifics" "risk_free_rate for Germany/7y"
    (Batch.reason_key "risk_free_rate for Germany/7y (as_of 2026-06-05) is 97 days old");
  Alcotest.(check string) "reason key groups refusals by class" "dcf not admissible for Bank"
    (Batch.reason_key "dcf not admissible for Bank; lens: price/book against ROE");
  Alcotest.(check string) "summary is deterministic" s (Batch.summary ~universe vs)

(* --- valuation end to end --- *)

let test_ok () =
  let v = run (financials (history ())) in
  Alcotest.check status "status" `Ok v.status;
  Alcotest.(check string) "valued_on" today v.valued_on;
  Alcotest.(check (option string)) "failed_reason" None v.failed_reason;
  Alcotest.(check bool) "fair value present" true (Option.is_some v.fair_value);
  Alcotest.(check bool) "signal present" true (Option.is_some v.signal);
  match v.inputs with
  | None -> Alcotest.fail "Ok without inputs"
  | Some (`Residual_income _ | `Residual_income_insurer _ | `Reit_ffo_dividend _) -> Alcotest.fail "routed to the wrong model"
  | Some (`Dcf i) ->
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
      Alcotest.(check int) "growth path spans the horizon" 7 (List.length i.growth_path);
      Alcotest.(check string) "lambda provenance" "seed" i.mean_reversion_lambda.source;
      List.iter
        (fun (name, (p : Boundary_t.parameter)) ->
          if p.age_days < 0 || p.source = "" || p.as_of = "" then
            Alcotest.failf "%s lacks provenance" name)
        [
          ("risk_free_rate", i.risk_free_rate);
          ("equity_risk_premium", i.equity_risk_premium);
          ("statutory_tax_rate", i.statutory_tax_rate);
          ("terminal_growth_rate", i.terminal_growth_rate);
          ("growth_clamp_lower", i.growth_clamp_lower);
          ("growth_clamp_upper", i.growth_clamp_upper);
          ("mean_reversion_lambda", i.mean_reversion_lambda);
          ("debt_spread", i.debt_spread);
          ("beta", i.beta);
        ]

let test_no_country () =
  let v = run (financials ~country:None [ full_period () ]) in
  check_reason v [ "country" ];
  check_nulls v;
  Alcotest.(check bool) "inputs" true (Option.is_none v.inputs)

let test_unknown_country () =
  let v =
    run (financials ~country:(Some "Atlantis") [ full_period () ])
  in
  check_reason v [ "Atlantis" ];
  check_nulls v

let test_stale_parameter () =
  let v =
    run (financials ~country:(Some "Germany") [ full_period () ])
  in
  check_reason v [ "risk_free_rate"; "97 days"; "max_age_days 45" ];
  check_nulls v;
  Alcotest.(check bool) "inputs" true (Option.is_none v.inputs)

let test_no_industry () =
  let v = run (financials ~industry:None (history ())) in
  Alcotest.check status "status" `Ok v.status;
  match v.inputs with
  | None -> Alcotest.fail "Ok without inputs"
  | Some (`Residual_income _ | `Residual_income_insurer _ | `Reit_ffo_dividend _) -> Alcotest.fail "routed to the wrong model"
  | Some (`Dcf i) ->
      check_float "beta" 1.0 i.beta.value;
      Alcotest.check beta_source "beta_source" `Default_no_industry i.beta_source;
      Alcotest.(check (option string)) "industry" None i.industry

let test_latest_period_wins () =
  let v =
    run
      (financials
         [
           full_period ~period_end:"2024-09-30" ();
           period ~period_end:"2025-09-30" ~ebit:1200. ();
         ])
  in
  check_reason v [ "2025-09-30"; "capex" ];
  Alcotest.(check bool) "inputs" true (Option.is_none v.inputs)

let test_no_periods () =
  let v = run (financials []) in
  check_reason v [ "no fiscal periods" ];
  check_nulls v;
  Alcotest.(check bool) "inputs" true (Option.is_none v.inputs);
  Alcotest.(check (option approx)) "price still reported" (Some 10.) v.price

let test_missing_statement_fields () =
  let v =
    run
      (financials
         [
           period ~ebit:1200. ~pretax_income:1000. ~tax_provision:500.
             ~depreciation_amortization:200. ~cash:1000. ~total_debt:5000. ();
         ])
  in
  check_reason v [ "2025-09-30"; "capex"; "delta_nwc" ];
  check_nulls v

let test_missing_market_data () =
  let v = run (financials ~market_cap:None (history ())) in
  check_reason v [ "missing market data"; "market_cap" ];
  check_nulls v;
  (* a missing currency stops at the gate, before any model *)
  let v = run (financials ~currency:None (history ())) in
  check_reason v [ "missing market data: financial_currency" ];
  Alcotest.(check bool) "nothing computed" true (Option.is_none v.inputs)
let test_wacc_below_terminal_growth () =
  let v =
    Valuation.run ~model_version:"test" ~declaration:(Some (declaration `OperatingCompany))
      { params with
        params =
          Reference_j.params_of_string
            {|{"projection_years": {"value": 7, "source": "seed", "as_of": "2026-06-01", "max_age_days": 400},
               "debt_spread": {"value": 0.01, "source": "a", "as_of": "2026-09-01", "max_age_days": 400},
               "bank_nii_ratio_threshold": {"value": 0.25, "source": "a", "as_of": "2026-09-01", "max_age_days": 400},
               "growth_clamp_lower": {"value": -0.2, "source": "a", "as_of": "2026-06-01", "max_age_days": 400},
               "growth_clamp_upper": {"value": 0.5, "source": "a", "as_of": "2026-06-01", "max_age_days": 400},
               "mean_reversion_lambda": {"value": 0.25, "source": "a", "as_of": "2026-06-01", "max_age_days": 400},
               "mature_market_erp": {"value": 0.0423, "source": "a", "as_of": "2026-01-01", "max_age_days": 400},
               "terminal_growth_rate": {"source": "seed", "as_of": "2026-06-01", "max_age_days": 400,
                 "values": {"United States": 0.5}},
               "unwired": {}}|} }
      ~today (financials (history ()))
  in
  check_reason v [ "terminal growth" ];
  check_nulls v;
  Alcotest.(check bool) "inputs" true (Option.is_none v.inputs)

let test_non_positive_fair_value () =
  (* Loss-making every year: nopat < 0 so fundamental growth is unusable, flat revenue
     gives zero historical growth, roic is negative so the cap pulls g0 down to it, and
     the clamp holds it at -0.2. The cash flows shrink from a negative base. *)
  let v =
    run
      (financials (history ~ebit:(-5000.) ~pretax_income:(-5000.) ()))
  in
  check_reason v [ "non-positive fair value" ];
  check_nulls v;
  Alcotest.(check bool) "inputs kept for audit" true (Option.is_some v.inputs)

let test_sanity_bound () =
  (* Tiny market cap: wacc collapses towards the cost of debt and the DCF says
     the equity is worth hundreds of times its price. Not a Buy -- a failure. *)
  let v =
    run (financials ~market_cap:(Some 100.) (history ()))
  in
  check_reason v [ "sanity bound" ];
  check_nulls v;
  Alcotest.(check bool) "inputs kept for audit" true (Option.is_some v.inputs)

let test_json_round_trip () =
  let ok = run (financials (history ())) in
  let failed = run (financials []) in
  List.iter
    (fun v ->
      Alcotest.check valuation "round trip" v
        (Boundary_j.valuation_of_string (Boundary_j.string_of_valuation v)))
    [ ok; failed ];
  check_mentions "failed json" (Boundary_j.string_of_valuation failed)
    [ {|"status":"Failed"|}; {|"fair_value":null|}; {|"signal":null|};
      {|"inputs":null|}; {|"model":"dcf"|}; {|"valued_on":"2026-09-10"|};
      {|"floor":{"present":null,|} ];
  check_mentions "ok json" (Boundary_j.string_of_valuation ok)
    [ {|"beta_source":"industry_table"|}; {|"source":"FRED"|}; {|"age_days":2|};
      {|"model":"dcf"|}; {|"entity_class":"OperatingCompany"|}; {|"class_check":{|};
      {|"outcome":"Consistent"|}; {|"nii_ratio":null|}; {|"floor":{"present":true,|};
      {|"scope_limits":[]|}; {|"growth_source":"historical"|}; {|"growth_clamped":false|} ]

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
          case "delta_nwc is averaged" test_delta_nwc_is_averaged;
          case "derived growth end to end" test_growth_selected_end_to_end;
          case "clamp binds and is recorded" test_growth_clamped_end_to_end;
          case "debt or equity absent fails" test_debt_absent_fails;
          case "mapping provenance carried" test_provenance_of_mappings;
        ] );
      ( "growth",
        [
          case "fundamental when reinvesting" test_growth_fundamental;
          case "historical capped at roic" test_growth_historical_capped;
          case "historical uncapped" test_growth_historical_uncapped;
          case "not derivable" test_growth_not_derivable;
          case "clamp" test_growth_clamp;
          case "mean-reversion path" test_growth_path;
        ] );
      ( "parameters",
        [
          case "days between dates" test_days_between;
          case "estimated cells round-trip" test_estimated_round_trip;
          case "resolve carries provenance" test_resolve_provenance;
          case "resolve records a tenor substitution and tier" test_resolve_tenor_substitution;
          case "resolve follows aliases" test_resolve_alias;
          case "unknown country is an error naming it" test_resolve_unknown_country;
          case "stale parameter is an error naming it and its age" test_resolve_stale;
          case "as_of in the future is an error" test_resolve_future_as_of;
          case "beta defaults only without a listed industry" test_beta_default;
          case "tracked reference files load" test_reference_files_load;
        ] );
      ( "entity class",
        [
          case "bank signature is a materiality ratio" test_signature_bank_ratio;
          case "insurer signature is a named premium row" test_signature_insurer_row;
          case "undeclared is refused, hint appended" test_check_undeclared;
          case "signature against a declared operating company is fatal" test_check_disagreement_is_fatal;
          case "other mismatches are recorded, not fatal" test_check_harmless_directions;
          case "inadmissible refuses with the lens named" test_inadmissible_refuses_with_lens;
          case "declared insurer with no signature is refused, not unresolved" test_insurer_declared_without_signature;
          case "undeclared record shape" test_undeclared_record;
          case "disagreement record shape" test_disagreement_record;
          case "floor is three-valued with a basis" test_floor_three_valued;
          case "operating company record carries the evidence" test_operating_company_record_carries_evidence;
          case "class without a table row fails" test_no_admissibility_row;
          case "sanity bound names a structural break" test_sanity_bound_names_structural_break;
          case "table and variant agree, universe declares known classes" test_table_and_variant_agree;
          case "batch summary" test_batch_summary;
          case "flow chart names every failure reason" test_flow_chart_names_every_reason;
        ] );
      ( "residual income",
        [
          case "schedule by hand" test_ri_schedule;
          case "roe path" test_ri_roe_path;
          case "value by hand" test_ri_value_by_hand;
          case "roe at the cost of equity is worth exactly book" test_ri_value_neutrality;
          case "retention derived, never assumed" test_ri_retention_derivation;
          case "guards fail, never zero" test_ri_guards;
          case "loan-loss ratios recorded" test_ri_loan_loss_recorded;
          case "a bank routes to residual income, never the dcf" test_bank_routes_to_residual_income;
        ] );
      ( "filed statements",
        [
          case "filing-age gate" test_filing_age_gate;
          case "provider decision on every record, cross-check carried" test_provider_decision_on_every_record;
          case "summary cross-check line and provider diff" test_summary_cross_check_line_and_provider_diff;
        ] );
      ( "field definitions",
        [
          case "compositions carried into the inputs" test_compositions_carried_into_inputs;
          case "gate refuses another definition, names both" test_definitions_gate;
          case "fx scales the components too" test_fx_scales_compositions;
          case "run diff lists every moved fair value's drivers" test_run_diff_lists_drivers;
          case "summary names the definitions and characterises each flag" test_summary_definitions_and_cross_check_listing;
        ] );
      ( "implied readouts",
        [
          case "bisection on a bounded domain, either direction" test_bisect;
          case "dcf solver recovers a known g0 and a known lambda" test_dcf_solver_recovers_known_g0_and_lambda;
          case "half-life guarded below terminal; level is then the readout" test_half_life_guard_and_level_rule;
          case "no solution in range, both ends, with reasons" test_no_solution_in_range_both_ends;
          case "bank solver recovers a known roe; insurer carries the block" test_bank_solver_recovers_known_roe;
          case "the headline does not depend on the readouts" test_headline_independent_of_the_readouts;
          case "derived ebit runs only within the cross-check, else the policy's failed" test_ebit_policy_gate;
          case "summary carries the universe-level implied line" test_summary_implied_line;
        ] );
      ( "reit",
        [
          case "value by hand" test_reit_value_by_hand;
          case "growth on the weighted count, never a point count" test_reit_growth_uses_the_weighted_count_not_a_point_count;
          case "covered dividend, growth needs two periods, guards" test_reit_covered_dividend_and_guards;
          case "routes, floors, implied g0 and horizon" test_reit_routes_and_implied;
        ] );
      ( "point-in-time",
        [ case "gates name the missing history; held vintages declared" test_point_in_time_gates_and_vintages ] );
      ( "stability",
        [
          case "classifier: price, vendor row, restated, new filing, rate, unexplained" test_stability_classifier;
          case "report and summary line" test_stability_report;
        ] );
      ( "implied horizon",
        [
          case "recovers a known N; monotone and converging under the guard" test_horizon_recovers_known_n_and_is_monotone;
          case "guard, beyond 40 with the 40-year value, below one year" test_horizon_guard_beyond_40_and_below_one_year;
          case "residual-income horizon recovers a known N" test_residual_income_horizon_recovers_known_n;
          case "summary carries the horizon line" test_summary_horizon_line;
        ] );
      ( "ifrs filers",
        [
          case "filing and vendor currencies must agree; taxonomy carried" test_currency_agreement_gate;
          case "zero dividends is a payout, an absent tag is not" test_zero_dividends_is_a_payout_absent_is_not;
        ] );
      ( "cross-currency",
        [
          case "fx rate through usd, dated by the older leg" test_fx_rate_through_usd;
          case "conversion scales totals, not price" test_fx_convert_scales_totals_only;
          case "international capm decomposes; domestic form untouched" test_international_capm;
          case "adr ratio invariance" test_adr_ratio_invariance;
          case "minor-unit price guard" test_minor_unit_guard;
          case "currency gate failures name the field or pair" test_currency_gate_failures;
          case "same-currency record carries no conversion" test_same_currency_path_carries_no_conversion;
        ] );
      ( "insurer",
        [
          case "aoci adjustment applied and recorded" test_insurer_aoci_adjustment;
          case "underwriting checks recorded, never gates" test_insurer_underwriting_checks;
          case "requires filed statements, names the fix" test_insurer_requires_filed_statements;
          case "routes to the insurer model with a verified floor" test_insurer_routes_and_floors;
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
