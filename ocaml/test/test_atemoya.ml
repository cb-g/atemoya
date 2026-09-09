open Atemoya

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
    ?(market_cap = Some 5000.) periods : Boundary_t.financials =
  {
    ticker = "TEST";
    as_of = "2026-09-06T00:00:00+00:00";
    currency;
    price;
    market_cap;
    periods;
    notes = [];
  }

(* Round numbers so every intermediate is exact by hand:
   tax 500 / 1000 = 0.5;  fcff = 1200 * 0.5 + 200 - 50 - 50 = 700
   ke = 0.02 + 1.0 * 0.10 = 0.12;  kd = 0.02 + 0.02 = 0.04, after tax 0.02
   E = D = 5000  ->  wacc = 0.5 * 0.12 + 0.5 * 0.02 = 0.07
   zero growth   ->  EV = 700 / 0.07 = 10000 whatever the horizon
   net debt = 5000 - 1000 = 4000;  equity = 6000;  shares = 5000 / 10 = 500
   fair value = 12;  margin of safety = 0.2  ->  Hold *)
let assumptions : Dcf.assumptions =
  {
    risk_free_rate = 0.02;
    equity_risk_premium = 0.10;
    beta = 1.0;
    debt_spread = 0.02;
    growth_rate = 0.0;
    terminal_growth_rate = 0.0;
    projection_years = 5;
    statutory_tax_rate = 0.21;
  }

let full_period ?period_end () =
  period ?period_end ~ebit:1200. ~pretax_income:1000. ~tax_provision:500.
    ~depreciation_amortization:200. ~capex:50. ~delta_nwc:50. ~cash:1000.
    ~total_debt:5000. ()

let via_json to_string =
  Alcotest.testable
    (fun fmt v -> Format.pp_print_string fmt (to_string v))
    ( = )

let status = via_json Boundary_j.string_of_status
let signal = via_json Boundary_j.string_of_signal
let tax_rate_source = via_json Boundary_j.string_of_tax_rate_source
let valuation = via_json Boundary_j.string_of_valuation
let approx = Alcotest.float 1e-9
let check_float = Alcotest.check approx

let contains haystack needle =
  let n = String.length needle and h = String.length haystack in
  let rec go i = i + n <= h && (String.sub haystack i n = needle || go (i + 1)) in
  go 0

let check_reason (v : Boundary_t.valuation) needles =
  Alcotest.check status "status" `Failed v.status;
  match v.failed_reason with
  | None -> Alcotest.fail "Failed without a reason"
  | Some reason ->
      List.iter
        (fun needle ->
          if not (contains reason needle) then
            Alcotest.failf "reason %S does not mention %S" reason needle)
        needles

let check_nulls (v : Boundary_t.valuation) =
  Alcotest.(check (option approx)) "fair_value" None v.fair_value;
  Alcotest.(check (option approx)) "margin_of_safety" None v.margin_of_safety;
  Alcotest.(check (option signal)) "signal" None v.signal

(* --- arithmetic --- *)

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
    [ 0; 1; 5 ]

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
      Dcf.tax_rate assumptions ~pretax_income:(fst expected)
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

(* --- end to end --- *)

let test_ok () =
  let v = Valuation.run ~assumptions (financials [ full_period () ]) in
  Alcotest.check status "status" `Ok v.status;
  Alcotest.(check (option string)) "failed_reason" None v.failed_reason;
  Alcotest.(check (option string)) "currency" (Some "USD") v.currency;
  Alcotest.(check (option approx)) "price" (Some 10.) v.price;
  Alcotest.(check (option approx)) "fair_value" (Some 12.) v.fair_value;
  Alcotest.(check (option approx)) "margin_of_safety" (Some 0.2) v.margin_of_safety;
  Alcotest.(check (option signal)) "signal" (Some `Hold) v.signal;
  match v.inputs with
  | None -> Alcotest.fail "Ok without inputs"
  | Some i ->
      Alcotest.(check string) "fiscal_period_end" "2025-09-30" i.fiscal_period_end;
      check_float "shares" 500. i.shares;
      check_float "tax_rate" 0.5 i.tax_rate;
      Alcotest.check tax_rate_source "tax_rate_source" `Effective i.tax_rate_source;
      check_float "fcff" 700. i.fcff;
      check_float "wacc" 0.07 i.wacc;
      check_float "enterprise_value" 10000. i.enterprise_value;
      check_float "net_debt" 4000. i.net_debt;
      check_float "equity_value" 6000. i.equity_value

let test_latest_period_wins () =
  (* Older period is complete and given first; a newer, incomplete one must be
     the one valued -- the model never reaches back to an older year. *)
  let v =
    Valuation.run ~assumptions
      (financials
         [
           full_period ~period_end:"2024-09-30" ();
           period ~period_end:"2025-09-30" ~ebit:1200. ();
         ])
  in
  check_reason v [ "2025-09-30"; "capex" ];
  Alcotest.(check bool) "inputs" true (Option.is_none v.inputs)

let test_no_periods () =
  let v = Valuation.run ~assumptions (financials []) in
  check_reason v [ "no fiscal periods" ];
  check_nulls v;
  Alcotest.(check bool) "inputs" true (Option.is_none v.inputs);
  Alcotest.(check (option approx)) "price still reported" (Some 10.) v.price

let test_missing_statement_fields () =
  let v =
    Valuation.run ~assumptions
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
    Valuation.run ~assumptions
      (financials ~currency:None ~market_cap:None [ full_period () ])
  in
  check_reason v [ "currency"; "market_cap" ];
  check_nulls v

let test_wacc_below_terminal_growth () =
  let v =
    Valuation.run
      ~assumptions:{ assumptions with terminal_growth_rate = 0.5 }
      (financials [ full_period () ])
  in
  check_reason v [ "terminal growth" ];
  check_nulls v;
  Alcotest.(check bool) "inputs" true (Option.is_none v.inputs)

let test_non_positive_fair_value () =
  let v =
    Valuation.run ~assumptions
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
    Valuation.run ~assumptions
      (financials ~market_cap:(Some 100.) [ full_period () ])
  in
  check_reason v [ "sanity bound" ];
  check_nulls v;
  Alcotest.(check bool) "inputs kept for audit" true (Option.is_some v.inputs)

let test_json_round_trip () =
  let ok = Valuation.run ~assumptions (financials [ full_period () ]) in
  let failed = Valuation.run ~assumptions (financials []) in
  List.iter
    (fun v ->
      Alcotest.check valuation "round trip" v
        (Boundary_j.valuation_of_string (Boundary_j.string_of_valuation v)))
    [ ok; failed ];
  let json = Boundary_j.string_of_valuation failed in
  List.iter
    (fun needle ->
      if not (contains json needle) then
        Alcotest.failf "json %s lacks %s" json needle)
    [ {|"status":"Failed"|}; {|"fair_value":null|}; {|"signal":null|};
      {|"inputs":null|}; {|"model":"Generic"|} ]

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
        ] );
      ( "valuation",
        [
          case "ok end to end" test_ok;
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
