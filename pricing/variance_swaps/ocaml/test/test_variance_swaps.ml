(** Unit tests for variance swaps model *)

open Variance_swaps_lib

(* ========== Realized Variance Tests ========== *)

let test_realized_variance_constant () =
  (* Constant prices → zero variance *)
  let prices = [| 100.0; 100.0; 100.0; 100.0; 100.0 |] in
  let rv = Realized_variance.compute_realized_variance ~prices ~annualization_factor:252.0 in
  Alcotest.(check (float 0.0001)) "constant prices = 0 var" 0.0 rv

let test_realized_variance_trending () =
  (* Increasing prices → positive variance *)
  let prices = [| 100.0; 101.0; 102.0; 103.0; 104.0 |] in
  let rv = Realized_variance.compute_realized_variance ~prices ~annualization_factor:252.0 in
  Alcotest.(check bool) "trending prices > 0" true (rv > 0.0)

let test_parkinson_estimator () =
  let highs = [| 102.0; 103.0; 104.0; 105.0 |] in
  let lows = [| 98.0; 99.0; 100.0; 101.0 |] in
  let rv = Realized_variance.parkinson_estimator ~highs ~lows ~annualization_factor:252.0 in
  Alcotest.(check bool) "parkinson positive" true (rv > 0.0)

let test_garman_klass_estimator () =
  let opens = [| 100.0; 101.0; 102.0; 103.0 |] in
  let highs = [| 102.0; 103.0; 104.0; 105.0 |] in
  let lows = [| 98.0; 99.0; 100.0; 101.0 |] in
  let closes = [| 101.0; 102.0; 103.0; 104.0 |] in
  let rv = Realized_variance.garman_klass_estimator
    ~opens ~highs ~lows ~closes ~annualization_factor:252.0 in
  Alcotest.(check bool) "garman-klass positive" true (rv > 0.0)

let test_rogers_satchell_estimator () =
  let opens = [| 100.0; 101.0; 102.0; 103.0 |] in
  let highs = [| 102.0; 103.0; 104.0; 105.0 |] in
  let lows = [| 98.0; 99.0; 100.0; 101.0 |] in
  let closes = [| 101.0; 102.0; 103.0; 104.0 |] in
  let rv = Realized_variance.rogers_satchell_estimator
    ~opens ~highs ~lows ~closes ~annualization_factor:252.0 in
  Alcotest.(check bool) "rogers-satchell positive" true (rv > 0.0)

let test_yang_zhang_estimator () =
  let opens = [| 100.0; 101.0; 102.0; 103.0 |] in
  let highs = [| 102.0; 103.0; 104.0; 105.0 |] in
  let lows = [| 98.0; 99.0; 100.0; 101.0 |] in
  let closes = [| 101.0; 102.0; 103.0; 104.0 |] in
  let rv = Realized_variance.yang_zhang_estimator
    ~opens ~highs ~lows ~closes ~annualization_factor:252.0 in
  Alcotest.(check bool) "yang-zhang positive" true (rv > 0.0)

let test_rolling_realized_variance () =
  let prices = Array.init 20 (fun i -> 100.0 +. float_of_int i *. 0.5) in
  let rolling = Realized_variance.rolling_realized_variance
    ~prices ~window_days:5 ~annualization_factor:252.0 in
  Alcotest.(check bool) "rolling has values" true (Array.length rolling > 0);
  Array.iter (fun v ->
    Alcotest.(check bool) "each value >= 0" true (v >= 0.0)
  ) rolling

let test_forecast_ewma () =
  let returns = [| 0.01; -0.02; 0.015; -0.005; 0.008; -0.012 |] in
  let forecast = Realized_variance.forecast_ewma
    ~returns ~lambda:0.94 ~annualization_factor:252.0 in
  Alcotest.(check bool) "EWMA forecast positive" true (forecast > 0.0)

let test_forecast_garch () =
  let returns = [| 0.01; -0.02; 0.015; -0.005; 0.008; -0.012 |] in
  let forecast = Realized_variance.forecast_garch
    ~returns ~omega:0.00001 ~alpha:0.1 ~beta:0.85 ~annualization_factor:252.0 in
  Alcotest.(check bool) "GARCH forecast positive" true (forecast > 0.0)

(* ========== Variance Swap Pricing Tests ========== *)

let test_bs_price_call () =
  let price = Variance_swap_pricing.bs_price
    ~option_type:Types.Call ~spot:100.0 ~strike:100.0
    ~expiry:1.0 ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  Alcotest.(check bool) "ATM call positive" true (price > 0.0);
  Alcotest.(check bool) "ATM call < spot" true (price < 100.0)

let test_bs_price_put () =
  let price = Variance_swap_pricing.bs_price
    ~option_type:Types.Put ~spot:100.0 ~strike:100.0
    ~expiry:1.0 ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  Alcotest.(check bool) "ATM put positive" true (price > 0.0)

let test_bs_put_call_parity () =
  let call = Variance_swap_pricing.bs_price
    ~option_type:Types.Call ~spot:100.0 ~strike:100.0
    ~expiry:1.0 ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  let put = Variance_swap_pricing.bs_price
    ~option_type:Types.Put ~spot:100.0 ~strike:100.0
    ~expiry:1.0 ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  (* C - P = S*exp(-q*T) - K*exp(-r*T) *)
  let lhs = call -. put in
  let rhs = 100.0 -. 100.0 *. exp (-0.05) in
  Alcotest.(check (float 0.01)) "put-call parity" rhs lhs

let test_compute_vega_notional () =
  (* Vega notional = notional / (2 * sqrt(variance_strike)) *)
  let vn = Variance_swap_pricing.compute_vega_notional
    ~notional:100000.0 ~variance_strike:0.04 in
  (* 100000 / (2 * 0.2) = 250000 *)
  Alcotest.(check (float 1.0)) "vega notional" 250000.0 vn

let test_variance_swap_payoff () =
  let swap : Types.variance_swap = {
    ticker = "SPY"; notional = 100000.0; strike_var = 0.04;
    expiry = 1.0; vega_notional = 250000.0;
    entry_date = 0.0; entry_spot = 100.0;
  } in
  (* Payoff = notional * (realized - strike) *)
  let pnl = Variance_swap_pricing.variance_swap_payoff swap ~realized_variance:0.05 in
  (* 100000 * (0.05 - 0.04) = 1000 *)
  Alcotest.(check (float 0.01)) "positive payoff" 1000.0 pnl

let test_variance_swap_payoff_negative () =
  let swap : Types.variance_swap = {
    ticker = "SPY"; notional = 100000.0; strike_var = 0.04;
    expiry = 1.0; vega_notional = 250000.0;
    entry_date = 0.0; entry_spot = 100.0;
  } in
  let pnl = Variance_swap_pricing.variance_swap_payoff swap ~realized_variance:0.03 in
  Alcotest.(check (float 0.01)) "negative payoff" (-1000.0) pnl

let test_generate_strike_grid () =
  let grid = Variance_swap_pricing.generate_strike_grid
    ~spot:100.0 ~num_strikes:11 ~log_moneyness_range:(-0.3, 0.3) in
  Alcotest.(check int) "grid size" 11 (Array.length grid);
  Alcotest.(check bool) "grid sorted" true
    (grid.(0) < grid.(Array.length grid - 1));
  Alcotest.(check bool) "ATM near center" true
    (abs_float (grid.(5) -. 100.0) < 5.0)

(* ========== VRP Calculation Tests ========== *)

let test_compute_vrp () =
  let obs = Vrp_calculation.compute_vrp
    ~ticker:"SPY" ~horizon_days:30
    ~implied_var:0.04 ~forecast_realized_var:0.03 in
  (* VRP = implied - realized = 0.04 - 0.03 = 0.01 *)
  Alcotest.(check (float 0.001)) "VRP = 0.01" 0.01 obs.vrp;
  Alcotest.(check (float 0.1)) "VRP pct = 25%"
    25.0 obs.vrp_percent

let test_vrp_statistics () =
  let obs = Array.init 10 (fun i ->
    Vrp_calculation.compute_vrp ~ticker:"SPY" ~horizon_days:30
      ~implied_var:(0.04 +. float_of_int i *. 0.001)
      ~forecast_realized_var:0.03
  ) in
  let (mean_vrp, std_vrp, _sharpe) = Vrp_calculation.vrp_statistics obs in
  Alcotest.(check bool) "mean VRP > 0" true (mean_vrp > 0.0);
  Alcotest.(check bool) "std VRP > 0" true (std_vrp > 0.0)

(* ========== Test Suite ========== *)

let () =
  Alcotest.run "Variance Swaps Tests" [
    "realized_variance", [
      Alcotest.test_case "Constant prices" `Quick test_realized_variance_constant;
      Alcotest.test_case "Trending prices" `Quick test_realized_variance_trending;
      Alcotest.test_case "Parkinson estimator" `Quick test_parkinson_estimator;
      Alcotest.test_case "Garman-Klass estimator" `Quick test_garman_klass_estimator;
      Alcotest.test_case "Rogers-Satchell estimator" `Quick test_rogers_satchell_estimator;
      Alcotest.test_case "Yang-Zhang estimator" `Quick test_yang_zhang_estimator;
      Alcotest.test_case "Rolling variance" `Quick test_rolling_realized_variance;
      Alcotest.test_case "EWMA forecast" `Quick test_forecast_ewma;
      Alcotest.test_case "GARCH forecast" `Quick test_forecast_garch;
    ];
    "pricing", [
      Alcotest.test_case "BS call price" `Quick test_bs_price_call;
      Alcotest.test_case "BS put price" `Quick test_bs_price_put;
      Alcotest.test_case "Put-call parity" `Quick test_bs_put_call_parity;
      Alcotest.test_case "Vega notional" `Quick test_compute_vega_notional;
      Alcotest.test_case "Variance swap payoff" `Quick test_variance_swap_payoff;
      Alcotest.test_case "Variance swap payoff negative" `Quick test_variance_swap_payoff_negative;
      Alcotest.test_case "Strike grid" `Quick test_generate_strike_grid;
    ];
    "vrp", [
      Alcotest.test_case "Compute VRP" `Quick test_compute_vrp;
      Alcotest.test_case "VRP statistics" `Quick test_vrp_statistics;
    ];
  ]
