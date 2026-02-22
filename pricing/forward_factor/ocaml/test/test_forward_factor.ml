open Forward_factor
open Types

let float_eq ~eps = Alcotest.testable
  (fun fmt f -> Format.fprintf fmt "%.6f" f)
  (fun a b -> Float.abs (a -. b) < eps)

(* ── Helper: sample expiration data ── *)

let make_exp ?(ticker = "TEST") ?(exp = "2026-03-01") ~dte ~atm_iv
    ?(atm_strike = 180.0) ?(call_price = 5.0) ?(put_price = 4.5)
    ?(d35_call_strike = 190.0) ?(d35_call_price = 2.5)
    ?(d35_put_strike = 170.0) ?(d35_put_price = 2.3) () =
  { ticker; expiration = exp; dte; atm_iv; atm_strike;
    atm_call_price = call_price; atm_put_price = put_price;
    delta_35_call_strike = d35_call_strike; delta_35_call_price = d35_call_price;
    delta_35_put_strike = d35_put_strike; delta_35_put_price = d35_put_price }

(* ── Forward Vol Tests ── *)

let test_forward_vol_backwardation () =
  (* Front IV = 35%, Back IV = 28%, DTE 30/60 *)
  let fv = Forward_vol.calculate_forward_vol
    ~ticker:"TEST" ~front_exp:"F" ~back_exp:"B"
    ~front_dte:30 ~back_dte:60 ~front_iv:0.35 ~back_iv:0.28 in
  (* t1 = 30/365 = 0.08219, t2 = 60/365 = 0.16438 *)
  (* v1 = 0.35^2 = 0.1225, v2 = 0.28^2 = 0.0784 *)
  (* fwd_var = (0.0784 * 0.16438 - 0.1225 * 0.08219) / (0.16438 - 0.08219) *)
  (*         = (0.012887 - 0.010068) / 0.08219 = 0.002819 / 0.08219 = 0.03430 *)
  (* fwd_vol = sqrt(0.03430) = 0.18521 *)
  (* FF = (0.35 - 0.18521) / 0.18521 = 0.8898 *)
  Alcotest.(check bool) "positive fwd var" true (fv.forward_variance > 0.0);
  Alcotest.(check bool) "fwd vol < front IV" true (fv.forward_vol < fv.front_iv);
  Alcotest.(check bool) "positive FF" true (fv.forward_factor > 0.0);
  Alcotest.(check (float_eq ~eps:0.01)) "FF ~ 0.89" 0.89 fv.forward_factor

let test_forward_vol_contango () =
  (* Front IV = 20%, Back IV = 30%, contango *)
  let fv = Forward_vol.calculate_forward_vol
    ~ticker:"TEST" ~front_exp:"F" ~back_exp:"B"
    ~front_dte:30 ~back_dte:60 ~front_iv:0.20 ~back_iv:0.30 in
  (* fwd vol > front IV → negative FF *)
  Alcotest.(check bool) "fwd vol > front IV" true (fv.forward_vol > fv.front_iv);
  Alcotest.(check bool) "negative FF" true (fv.forward_factor < 0.0)

let test_forward_vol_flat () =
  (* Same IV at both expirations *)
  let fv = Forward_vol.calculate_forward_vol
    ~ticker:"TEST" ~front_exp:"F" ~back_exp:"B"
    ~front_dte:30 ~back_dte:60 ~front_iv:0.25 ~back_iv:0.25 in
  (* Flat term structure → forward vol ≈ front vol → FF ≈ 0 *)
  Alcotest.(check (float_eq ~eps:0.01)) "flat FF ~ 0" 0.0 fv.forward_factor

let test_forward_vol_equal_dte () =
  (* back_dte = front_dte → t2 <= t1 → forward_variance = 0 *)
  let fv = Forward_vol.calculate_forward_vol
    ~ticker:"TEST" ~front_exp:"F" ~back_exp:"B"
    ~front_dte:30 ~back_dte:30 ~front_iv:0.35 ~back_iv:0.28 in
  Alcotest.(check (float_eq ~eps:0.001)) "zero fwd var" 0.0 fv.forward_variance;
  Alcotest.(check (float_eq ~eps:0.001)) "zero FF" 0.0 fv.forward_factor

let test_forward_vol_inverted_dte () =
  (* front_dte > back_dte → invalid *)
  let fv = Forward_vol.calculate_forward_vol
    ~ticker:"TEST" ~front_exp:"F" ~back_exp:"B"
    ~front_dte:60 ~back_dte:30 ~front_iv:0.35 ~back_iv:0.28 in
  Alcotest.(check (float_eq ~eps:0.001)) "inverted = 0 var" 0.0 fv.forward_variance

let test_forward_vol_extreme () =
  (* High front IV with long back DTE → positive variance but extreme FF *)
  let fv = Forward_vol.calculate_forward_vol
    ~ticker:"TEST" ~front_exp:"F" ~back_exp:"B"
    ~front_dte:30 ~back_dte:365 ~front_iv:0.50 ~back_iv:0.25 in
  Alcotest.(check bool) "positive fwd var" true (fv.forward_variance > 0.0);
  Alcotest.(check bool) "extreme FF > 1" true (fv.forward_factor > 1.0)

let test_passes_threshold () =
  let fv = Forward_vol.calculate_forward_vol
    ~ticker:"TEST" ~front_exp:"F" ~back_exp:"B"
    ~front_dte:30 ~back_dte:60 ~front_iv:0.35 ~back_iv:0.28 in
  Alcotest.(check bool) "passes 0.20" true
    (Forward_vol.passes_threshold ~fv ~threshold:0.20);
  Alcotest.(check bool) "passes 0.50" true
    (Forward_vol.passes_threshold ~fv ~threshold:0.50);
  Alcotest.(check bool) "fails 1.0" false
    (Forward_vol.passes_threshold ~fv ~threshold:1.0)

(* ── Calendar Spread Tests ── *)

let front_exp = make_exp ~exp:"2026-03-01" ~dte:30 ~atm_iv:0.35
    ~call_price:4.50 ~put_price:4.30
    ~d35_call_price:2.50 ~d35_put_price:2.30 ()

let back_exp = make_exp ~exp:"2026-04-01" ~dte:60 ~atm_iv:0.28
    ~call_price:6.80 ~put_price:6.50
    ~d35_call_price:4.00 ~d35_put_price:3.80 ()

let sample_fv = Forward_vol.calculate_forward_vol
    ~ticker:"TEST" ~front_exp:"2026-03-01" ~back_exp:"2026-04-01"
    ~front_dte:30 ~back_dte:60 ~front_iv:0.35 ~back_iv:0.28

let test_atm_calendar_debit () =
  let cs = Calendar.create_atm_call_calendar
    ~ticker:"TEST" ~front_exp ~back_exp ~forward_vol:sample_fv in
  (* net_debit = back_call - front_call = 6.80 - 4.50 = 2.30 *)
  Alcotest.(check (float_eq ~eps:0.01)) "net debit" 2.30 cs.net_debit;
  Alcotest.(check string) "spread type" "atm_call" cs.spread_type

let test_atm_calendar_max_loss () =
  let cs = Calendar.create_atm_call_calendar
    ~ticker:"TEST" ~front_exp ~back_exp ~forward_vol:sample_fv in
  Alcotest.(check (float_eq ~eps:0.01)) "max loss = debit" cs.net_debit cs.max_loss

let test_atm_calendar_max_profit () =
  let cs = Calendar.create_atm_call_calendar
    ~ticker:"TEST" ~front_exp ~back_exp ~forward_vol:sample_fv in
  (* max_profit = 0.75 * net_debit = 0.75 * 2.30 = 1.725 *)
  Alcotest.(check (float_eq ~eps:0.01)) "max profit" 1.725 cs.max_profit

let test_double_calendar () =
  let cs = Calendar.create_double_calendar
    ~ticker:"TEST" ~front_exp ~back_exp ~forward_vol:sample_fv in
  Alcotest.(check string) "spread type" "double_calendar" cs.spread_type;
  (* call_debit = 4.00 - 2.50 = 1.50, put_debit = 3.80 - 2.30 = 1.50, total = 3.00 *)
  Alcotest.(check (float_eq ~eps:0.01)) "double debit" 3.00 cs.net_debit;
  (* max_profit = net_debit for double calendar *)
  Alcotest.(check (float_eq ~eps:0.01)) "double max profit" 3.00 cs.max_profit;
  Alcotest.(check (float_eq ~eps:0.01)) "double max loss" 3.00 cs.max_loss

let test_double_calendar_strikes () =
  let cs = Calendar.create_double_calendar
    ~ticker:"TEST" ~front_exp ~back_exp ~forward_vol:sample_fv in
  Alcotest.(check int) "2 front strikes" 2 (List.length cs.front_strikes);
  Alcotest.(check int) "2 back strikes" 2 (List.length cs.back_strikes)

(* ── Kelly Sizing Tests ── *)

let test_kelly_moderate () =
  (* FF = 0.30, moderate → quarter kelly, clamped to [0.02, 0.08] *)
  let k = Calendar.calculate_kelly_fraction ~ff:0.30 in
  Alcotest.(check bool) "above min" true (k >= min_position_size);
  Alcotest.(check bool) "below max" true (k <= max_position_size)

let test_kelly_extreme () =
  (* FF >= 1.0 → scaled up by 1.5x *)
  let k = Calendar.calculate_kelly_fraction ~ff:1.5 in
  Alcotest.(check bool) "above min" true (k >= min_position_size);
  Alcotest.(check bool) "at max" true (k <= max_position_size)

let test_kelly_clamped () =
  (* Verify never exceeds bounds *)
  let k_low = Calendar.calculate_kelly_fraction ~ff:0.20 in
  let k_high = Calendar.calculate_kelly_fraction ~ff:5.0 in
  Alcotest.(check bool) "low >= 2%" true (k_low >= 0.02);
  Alcotest.(check bool) "high <= 8%" true (k_high <= 0.08)

let test_expected_return_extreme () =
  Alcotest.(check (float_eq ~eps:0.01)) "extreme = 80%" 0.80
    (Calendar.calculate_expected_return ~ff:1.5)

let test_expected_return_strong () =
  Alcotest.(check (float_eq ~eps:0.01)) "strong = 50%" 0.50
    (Calendar.calculate_expected_return ~ff:0.75)

let test_expected_return_valid () =
  Alcotest.(check (float_eq ~eps:0.01)) "valid = 30%" 0.30
    (Calendar.calculate_expected_return ~ff:0.25)

let test_expected_return_below () =
  Alcotest.(check (float_eq ~eps:0.01)) "below = 0%" 0.0
    (Calendar.calculate_expected_return ~ff:0.10)

(* ── Scanner Tests ── *)

let expirations = [
  make_exp ~exp:"2026-03-01" ~dte:30 ~atm_iv:0.35 ~call_price:4.50 ~put_price:4.30 ();
  make_exp ~exp:"2026-04-01" ~dte:60 ~atm_iv:0.28 ~call_price:6.80 ~put_price:6.50 ();
  make_exp ~exp:"2026-05-01" ~dte:90 ~atm_iv:0.26 ~call_price:8.50 ~put_price:8.20 ();
]

let test_find_closest () =
  let result = Scanner.find_closest_expiration ~expirations ~target_dte:30 in
  Alcotest.(check bool) "found" true (Option.is_some result);
  Alcotest.(check int) "dte 30" 30 (Option.get result).dte

let test_find_closest_between () =
  let result = Scanner.find_closest_expiration ~expirations ~target_dte:50 in
  Alcotest.(check bool) "found" true (Option.is_some result);
  (* 60 is closer to 50 than 30 or 90 *)
  Alcotest.(check int) "dte 60" 60 (Option.get result).dte

let test_find_closest_empty () =
  let result = Scanner.find_closest_expiration ~expirations:[] ~target_dte:30 in
  Alcotest.(check bool) "empty = None" true (Option.is_none result)

let test_scan_ticker () =
  let recs = Scanner.scan_ticker ~expirations
    ~dte_pairs:Scanner.default_dte_pairs ~threshold:0.20 in
  Alcotest.(check bool) "found opportunities" true (List.length recs > 0);
  List.iter (fun r ->
    Alcotest.(check bool) "passes filter" true r.passes_filter;
    Alcotest.(check bool) "FF >= 0.20" true (r.forward_factor >= 0.20)
  ) recs

let test_scan_ticker_high_threshold () =
  let recs = Scanner.scan_ticker ~expirations
    ~dte_pairs:Scanner.default_dte_pairs ~threshold:10.0 in
  Alcotest.(check int) "no results at extreme threshold" 0 (List.length recs)

let test_scan_ticker_recommendation_strings () =
  let recs = Scanner.scan_ticker ~expirations
    ~dte_pairs:Scanner.default_dte_pairs ~threshold:0.20 in
  List.iter (fun r ->
    let valid = r.recommendation = "STRONG BUY"
      || r.recommendation = "BUY"
      || r.recommendation = "CONSIDER" in
    Alcotest.(check bool) "valid recommendation" true valid
  ) recs

let test_scan_universe_sorted () =
  let universe = [expirations; expirations] in
  let recs = Scanner.scan_universe ~universe
    ~dte_pairs:Scanner.default_dte_pairs ~threshold:0.20 in
  (* Verify sorted by FF descending *)
  let rec is_sorted = function
    | [] | [_] -> true
    | a :: b :: rest -> a.forward_factor >= b.forward_factor && is_sorted (b :: rest)
  in
  Alcotest.(check bool) "sorted by FF desc" true (is_sorted recs)

let test_scan_empty_universe () =
  let recs = Scanner.scan_universe ~universe:[]
    ~dte_pairs:Scanner.default_dte_pairs ~threshold:0.20 in
  Alcotest.(check int) "empty universe" 0 (List.length recs)

(* ── Types Tests ── *)

let test_default_threshold () =
  Alcotest.(check (float_eq ~eps:0.001)) "threshold" 0.20 default_ff_threshold

let test_position_sizes () =
  Alcotest.(check (float_eq ~eps:0.001)) "default size" 0.04 default_position_size;
  Alcotest.(check (float_eq ~eps:0.001)) "min size" 0.02 min_position_size;
  Alcotest.(check (float_eq ~eps:0.001)) "max size" 0.08 max_position_size

let () =
  Alcotest.run "Forward Factor Tests" [
    ("forward_vol", [
      Alcotest.test_case "Backwardation" `Quick test_forward_vol_backwardation;
      Alcotest.test_case "Contango" `Quick test_forward_vol_contango;
      Alcotest.test_case "Flat" `Quick test_forward_vol_flat;
      Alcotest.test_case "Equal DTE" `Quick test_forward_vol_equal_dte;
      Alcotest.test_case "Inverted DTE" `Quick test_forward_vol_inverted_dte;
      Alcotest.test_case "Extreme" `Quick test_forward_vol_extreme;
      Alcotest.test_case "Passes threshold" `Quick test_passes_threshold;
    ]);
    ("calendar", [
      Alcotest.test_case "ATM debit" `Quick test_atm_calendar_debit;
      Alcotest.test_case "ATM max loss" `Quick test_atm_calendar_max_loss;
      Alcotest.test_case "ATM max profit" `Quick test_atm_calendar_max_profit;
      Alcotest.test_case "Double calendar" `Quick test_double_calendar;
      Alcotest.test_case "Double strikes" `Quick test_double_calendar_strikes;
    ]);
    ("kelly_sizing", [
      Alcotest.test_case "Moderate FF" `Quick test_kelly_moderate;
      Alcotest.test_case "Extreme FF" `Quick test_kelly_extreme;
      Alcotest.test_case "Clamped" `Quick test_kelly_clamped;
      Alcotest.test_case "Expected return extreme" `Quick test_expected_return_extreme;
      Alcotest.test_case "Expected return strong" `Quick test_expected_return_strong;
      Alcotest.test_case "Expected return valid" `Quick test_expected_return_valid;
      Alcotest.test_case "Expected return below" `Quick test_expected_return_below;
    ]);
    ("scanner", [
      Alcotest.test_case "Find closest" `Quick test_find_closest;
      Alcotest.test_case "Find closest between" `Quick test_find_closest_between;
      Alcotest.test_case "Find closest empty" `Quick test_find_closest_empty;
      Alcotest.test_case "Scan ticker" `Quick test_scan_ticker;
      Alcotest.test_case "High threshold" `Quick test_scan_ticker_high_threshold;
      Alcotest.test_case "Recommendation strings" `Quick test_scan_ticker_recommendation_strings;
      Alcotest.test_case "Universe sorted" `Quick test_scan_universe_sorted;
      Alcotest.test_case "Empty universe" `Quick test_scan_empty_universe;
    ]);
    ("types", [
      Alcotest.test_case "Default threshold" `Quick test_default_threshold;
      Alcotest.test_case "Position sizes" `Quick test_position_sizes;
    ]);
  ]
