(** Tests for regime downside optimization *)

open Regime_downside

(* Test risk calculations *)
let test_lpm1 () =
  let active_returns = [| 0.01; -0.005; 0.002; -0.015; 0.003 |] in
  let threshold = -0.01 in
  let lpm1 = Risk.lpm1 ~threshold ~active_returns in

  (* LPM1 should only count the -0.015 return: (-0.01 - (-0.015)) = 0.005 *)
  (* Expected: 0.005 / 5 = 0.001 *)
  Alcotest.(check bool) "LPM1 is positive when there are shortfalls"
    true (lpm1 > 0.0);

  Alcotest.(check bool) "LPM1 is small for small shortfalls"
    true (lpm1 < 0.01)

let test_cvar () =
  let active_returns = [| 0.01; -0.02; -0.01; 0.005; -0.03 |] in
  let cvar = Risk.cvar_95 ~active_returns in

  Alcotest.(check bool) "CVaR is positive for losses"
    true (cvar > 0.0);

  Alcotest.(check bool) "CVaR is reasonable"
    true (cvar < 0.1)

let test_portfolio_beta () =
  let weights : Types.weights = {
    assets = [("AAPL", 0.3); ("GOOGL", 0.5)];
    cash = 0.2;
  } in
  let asset_betas = [("AAPL", 1.2); ("GOOGL", 1.1)] in

  let beta = Risk.portfolio_beta ~weights ~asset_betas in

  (* Expected: 0.3 * 1.2 + 0.5 * 1.1 = 0.36 + 0.55 = 0.91 *)
  Alcotest.(check bool) "Portfolio beta is correct"
    true (abs_float (beta -. 0.91) < 0.01)

(* ========== Beta Module Tests ========== *)

let test_ewm_mean () =
  (* Simple case: constant values *)
  let values = [| 5.0; 5.0; 5.0; 5.0; 5.0 |] in
  let mean = Beta.ewm_mean ~values ~halflife:3.0 in
  Alcotest.(check (float 0.01)) "EWM of constant is constant"
    5.0 mean

let test_ewm_mean_trending () =
  (* Trending series - recent values weighted more *)
  let values = [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  let mean = Beta.ewm_mean ~values ~halflife:2.0 in
  (* Recent values (4.0, 5.0) should dominate *)
  Alcotest.(check bool) "EWM of trending series is > simple mean"
    true (mean > 3.0);  (* Simple mean = 3.0 *)
  Alcotest.(check bool) "EWM is below max (recent weighted, not just last)"
    true (mean < 5.0)

let test_ewm_var () =
  (* Zero variance case *)
  let values = [| 2.0; 2.0; 2.0; 2.0 |] in
  let var = Beta.ewm_var ~values ~halflife:3.0 in
  Alcotest.(check bool) "EWM variance of constant is zero"
    true (var < 0.0001)

let test_ewm_var_nonzero () =
  (* Non-zero variance *)
  let values = [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  let var = Beta.ewm_var ~values ~halflife:3.0 in
  Alcotest.(check bool) "EWM variance is positive for varying data"
    true (var > 0.0)

let test_ewm_cov () =
  (* Perfect positive correlation *)
  let x = [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  let y = [| 2.0; 4.0; 6.0; 8.0; 10.0 |] in  (* y = 2*x *)
  let cov = Beta.ewm_cov ~x ~y ~halflife:3.0 in
  Alcotest.(check bool) "EWM covariance is positive for positive correlation"
    true (cov > 0.0)

let test_ewm_cov_negative () =
  (* Perfect negative correlation *)
  let x = [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  let y = [| 10.0; 8.0; 6.0; 4.0; 2.0 |] in  (* y decreases as x increases *)
  let cov = Beta.ewm_cov ~x ~y ~halflife:3.0 in
  Alcotest.(check bool) "EWM covariance is negative for negative correlation"
    true (cov < 0.0)

let test_estimate_beta () =
  (* Beta = 1.0 case: asset moves with market *)
  let market = [| 0.01; -0.02; 0.03; -0.01; 0.02 |] in
  let asset = [| 0.01; -0.02; 0.03; -0.01; 0.02 |] in  (* Same as market *)
  let beta = Beta.estimate_beta ~asset_returns:asset ~benchmark_returns:market ~halflife:10.0 in
  Alcotest.(check (float 0.1)) "Beta is 1.0 when asset = market"
    1.0 beta

let test_estimate_beta_high () =
  (* Beta = 2.0 case: asset is 2× market *)
  let market = [| 0.01; -0.02; 0.03; -0.01; 0.02 |] in
  let asset = [| 0.02; -0.04; 0.06; -0.02; 0.04 |] in  (* 2× market *)
  let beta = Beta.estimate_beta ~asset_returns:asset ~benchmark_returns:market ~halflife:10.0 in
  Alcotest.(check (float 0.2)) "Beta is 2.0 when asset = 2× market"
    2.0 beta

let test_estimate_beta_zero () =
  (* Beta = 0 case: asset uncorrelated with market *)
  let market = [| 0.01; -0.02; 0.03; -0.01; 0.02 |] in
  let asset = [| 0.005; 0.005; 0.005; 0.005; 0.005 |] in  (* Constant, no correlation *)
  let beta = Beta.estimate_beta ~asset_returns:asset ~benchmark_returns:market ~halflife:10.0 in
  Alcotest.(check (float 0.2)) "Beta is ~0 when asset is constant"
    0.0 beta

let test_estimate_all_betas () =
  let benchmark = [| 0.01; -0.01; 0.02; -0.02 |] in
  let asset1 : Types.return_series = {
    ticker = "AAPL";
    dates = [| "2024-01-01"; "2024-01-02"; "2024-01-03"; "2024-01-04" |];
    returns = [| 0.01; -0.01; 0.02; -0.02 |];  (* Beta ≈ 1.0 *)
  } in
  let asset2 : Types.return_series = {
    ticker = "GOOGL";
    dates = [| "2024-01-01"; "2024-01-02"; "2024-01-03"; "2024-01-04" |];
    returns = [| 0.02; -0.02; 0.04; -0.04 |];  (* Beta ≈ 2.0 *)
  } in
  let assets = [asset1; asset2] in
  let betas = Beta.estimate_all_betas ~asset_returns_list:assets ~benchmark_returns:benchmark () in

  (* Check both betas are present *)
  Alcotest.(check bool) "AAPL beta exists"
    true (List.mem_assoc "AAPL" betas);
  Alcotest.(check bool) "GOOGL beta exists"
    true (List.mem_assoc "GOOGL" betas);

  (* Check approximate values *)
  let aapl_beta = List.assoc "AAPL" betas in
  let googl_beta = List.assoc "GOOGL" betas in
  Alcotest.(check bool) "AAPL beta is close to 1.0"
    true (abs_float (aapl_beta -. 1.0) < 0.2);
  Alcotest.(check bool) "GOOGL beta is close to 2.0"
    true (abs_float (googl_beta -. 2.0) < 0.3)

(* ========== Regime Module Tests ========== *)

let test_realized_volatility () =
  (* Create synthetic returns with known volatility *)
  let returns = Array.make 20 0.01 in  (* Constant 1% returns *)
  let vol = Regime.realized_volatility ~returns ~window_days:20 in

  Alcotest.(check bool) "Volatility of constant returns is zero"
    true (vol < 0.0001)

let test_realized_volatility_nonzero () =
  (* Varying returns *)
  let returns = [| 0.01; -0.02; 0.03; -0.01; 0.02; -0.015; 0.025; -0.005 |] in
  let vol = Regime.realized_volatility ~returns ~window_days:8 in
  Alcotest.(check bool) "Volatility is positive for varying returns"
    true (vol > 0.0);
  Alcotest.(check bool) "Volatility is reasonable (annualized)"
    true (vol < 1.0)  (* Less than 100% annualized *)

let test_percentile_median () =
  let values = [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  let p50 = Regime.percentile ~values ~p:0.5 in
  Alcotest.(check (float 0.1)) "50th percentile is median"
    3.0 p50

let test_percentile_extremes () =
  let values = [| 10.0; 20.0; 30.0; 40.0; 50.0 |] in
  let p0 = Regime.percentile ~values ~p:0.0 in
  let p100 = Regime.percentile ~values ~p:1.0 in
  Alcotest.(check (float 0.1)) "0th percentile is min"
    10.0 p0;
  Alcotest.(check (float 0.1)) "100th percentile is max"
    50.0 p100

let test_percentile_quartiles () =
  let values = [| 1.0; 2.0; 3.0; 4.0; 5.0; 6.0; 7.0; 8.0; 9.0; 10.0 |] in
  let p25 = Regime.percentile ~values ~p:0.25 in
  let p75 = Regime.percentile ~values ~p:0.75 in
  Alcotest.(check bool) "25th percentile is in lower quarter"
    true (p25 >= 2.0 && p25 <= 4.0);
  Alcotest.(check bool) "75th percentile is in upper quarter"
    true (p75 >= 7.0 && p75 <= 9.0)

let test_stress_weight_calm () =
  (* Volatility below lower threshold → weight = 0 (calm) *)
  let weight = Regime.stress_weight ~current_vol:0.08 ~lower_pct:0.10 ~upper_pct:0.20 in
  Alcotest.(check (float 0.01)) "Stress weight is 0 in calm regime"
    0.0 weight

let test_stress_weight_stress () =
  (* Volatility above upper threshold → weight = 1 (stress) *)
  let weight = Regime.stress_weight ~current_vol:0.25 ~lower_pct:0.10 ~upper_pct:0.20 in
  Alcotest.(check (float 0.01)) "Stress weight is 1 in stress regime"
    1.0 weight

let test_stress_weight_transition () =
  (* Volatility between thresholds → smooth transition *)
  let weight = Regime.stress_weight ~current_vol:0.15 ~lower_pct:0.10 ~upper_pct:0.20 in
  Alcotest.(check bool) "Stress weight is between 0 and 1 in transition"
    true (weight > 0.0 && weight < 1.0);
  Alcotest.(check (float 0.1)) "Stress weight is ~0.5 at midpoint"
    0.5 weight

let test_detect_regime () =
  (* Create synthetic benchmark returns with low volatility *)
  (* Need 252+ days for 1 year lookback *)
  let returns = Array.make 300 0.005 in  (* 300 days of constant 0.5% returns *)
  let regime = Regime.detect_regime
    ~benchmark_returns:returns
    ~lookback_years:1
    ~vol_window_days:60
    ~lower_percentile:0.10
    ~upper_percentile:0.20 in

  (* With constant returns, volatility should be near zero → calm regime *)
  Alcotest.(check bool) "Realized volatility is low for constant returns"
    true (regime.volatility < 0.01);
  Alcotest.(check bool) "Stress weight is low in calm market"
    true (regime.stress_weight < 0.1)

(* ========== Risk Module Edge Cases ========== *)

let test_lpm1_all_positive () =
  (* All returns above threshold → LPM1 = 0 *)
  let active_returns = [| 0.01; 0.02; 0.03; 0.015; 0.025 |] in
  let threshold = -0.01 in
  let lpm1 = Risk.lpm1 ~threshold ~active_returns in
  Alcotest.(check (float 0.001)) "LPM1 is zero when all returns above threshold"
    0.0 lpm1

let test_lpm1_all_below () =
  (* All returns below threshold *)
  let active_returns = [| -0.02; -0.03; -0.025; -0.015; -0.018 |] in
  let threshold = -0.01 in
  let lpm1 = Risk.lpm1 ~threshold ~active_returns in
  Alcotest.(check bool) "LPM1 is positive when all returns below threshold"
    true (lpm1 > 0.0);
  (* Expected: average shortfall *)
  let expected = (0.01 +. 0.02 +. 0.015 +. 0.005 +. 0.008) /. 5.0 in
  Alcotest.(check (float 0.001)) "LPM1 matches expected average shortfall"
    expected lpm1

let test_cvar_all_positive () =
  (* All positive returns → CVaR should be zero or very small *)
  let active_returns = [| 0.01; 0.02; 0.015; 0.025; 0.03 |] in
  let cvar = Risk.cvar_95 ~active_returns in
  Alcotest.(check (float 0.001)) "CVaR is zero for all positive returns"
    0.0 cvar

let test_portfolio_beta_all_cash () =
  (* 100% cash → beta = 0 *)
  let weights : Types.weights = {
    assets = [];
    cash = 1.0;
  } in
  let asset_betas = [] in
  let beta = Risk.portfolio_beta ~weights ~asset_betas in
  Alcotest.(check (float 0.001)) "Portfolio beta is 0 for all cash"
    0.0 beta

let test_portfolio_beta_no_cash () =
  (* No cash, 100% equities *)
  let weights : Types.weights = {
    assets = [("AAPL", 0.6); ("GOOGL", 0.4)];
    cash = 0.0;
  } in
  let asset_betas = [("AAPL", 1.2); ("GOOGL", 1.1)] in
  let beta = Risk.portfolio_beta ~weights ~asset_betas in
  (* Expected: 0.6 * 1.2 + 0.4 * 1.1 = 0.72 + 0.44 = 1.16 *)
  Alcotest.(check (float 0.01)) "Portfolio beta with no cash"
    1.16 beta

(* ========== Optimization Module Tests ========== *)

let test_turnover () =
  let current : Types.weights = {
    assets = [("AAPL", 0.4); ("GOOGL", 0.4)];
    cash = 0.2;
  } in
  let new_weights : Types.weights = {
    assets = [("AAPL", 0.3); ("GOOGL", 0.5)];
    cash = 0.2;
  } in

  let turnover = Optimization.calculate_turnover ~current_weights:current ~new_weights in

  (* AAPL: |0.3 - 0.4| = 0.1, GOOGL: |0.5 - 0.4| = 0.1, Cash: 0 *)
  (* Total: (0.1 + 0.1) / 2 = 0.1 *)
  Alcotest.(check bool) "Turnover is correctly calculated"
    true (abs_float (turnover -. 0.1) < 0.01)

let test_turnover_no_change () =
  (* No changes → turnover = 0 *)
  let weights : Types.weights = {
    assets = [("AAPL", 0.5); ("GOOGL", 0.3)];
    cash = 0.2;
  } in
  let turnover = Optimization.calculate_turnover ~current_weights:weights ~new_weights:weights in
  Alcotest.(check (float 0.001)) "Turnover is 0 when no changes"
    0.0 turnover

let test_turnover_full_rebalance () =
  (* Complete rebalance: 100% AAPL → 100% GOOGL *)
  let current : Types.weights = {
    assets = [("AAPL", 1.0)];
    cash = 0.0;
  } in
  let new_weights : Types.weights = {
    assets = [("GOOGL", 1.0)];
    cash = 0.0;
  } in
  let turnover = Optimization.calculate_turnover ~current_weights:current ~new_weights in
  (* AAPL: |0 - 1.0| = 1.0, GOOGL: |1.0 - 0| = 1.0 *)
  (* Total: (1.0 + 1.0) / 2 = 1.0 = 100% turnover *)
  Alcotest.(check (float 0.01)) "Turnover is 100% for full rebalance"
    1.0 turnover

let test_transaction_costs () =
  let current : Types.weights = {
    assets = [("AAPL", 0.4); ("GOOGL", 0.3)];
    cash = 0.3;
  } in
  let new_weights : Types.weights = {
    assets = [("AAPL", 0.5); ("GOOGL", 0.2)];
    cash = 0.3;
  } in
  let cost_bps = 10.0 in  (* 10 basis points *)

  let costs = Optimization.calculate_transaction_costs
    ~current_weights:current ~new_weights ~cost_bps in

  (* Turnover: AAPL |0.5-0.4|=0.1, GOOGL |0.2-0.3|=0.1 → total 0.2/2 = 0.1 *)
  (* Cost: 0.1 * 10 bps = 0.1 * 0.001 = 0.0001 = 1 bp total *)
  Alcotest.(check bool) "Transaction costs are reasonable"
    true (costs > 0.0 && costs < 0.01)

let test_transaction_costs_zero () =
  (* No changes → zero costs *)
  let weights : Types.weights = {
    assets = [("AAPL", 0.6); ("GOOGL", 0.4)];
    cash = 0.0;
  } in
  let costs = Optimization.calculate_transaction_costs
    ~current_weights:weights ~new_weights:weights ~cost_bps:10.0 in
  Alcotest.(check (float 0.0001)) "Zero costs when no trades"
    0.0 costs

let test_calculate_portfolio_returns () =
  let weights : Types.weights = {
    assets = [("AAPL", 0.5); ("GOOGL", 0.3)];
    cash = 0.2;
  } in
  let aapl : Types.return_series = {
    ticker = "AAPL";
    dates = [| "2024-01-01"; "2024-01-02"; "2024-01-03" |];
    returns = [| 0.01; -0.02; 0.03 |];
  } in
  let googl : Types.return_series = {
    ticker = "GOOGL";
    dates = [| "2024-01-01"; "2024-01-02"; "2024-01-03" |];
    returns = [| 0.02; -0.01; 0.02 |];
  } in
  let returns_list = [aapl; googl] in

  let portfolio_returns = Optimization.calculate_portfolio_returns
    ~weights ~asset_returns_list:returns_list in

  (* Day 1: 0.5*0.01 + 0.3*0.02 + 0.2*0.0 = 0.005 + 0.006 = 0.011 *)
  (* Day 2: 0.5*(-0.02) + 0.3*(-0.01) + 0.2*0.0 = -0.01 + (-0.003) = -0.013 *)
  (* Day 3: 0.5*0.03 + 0.3*0.02 + 0.2*0.0 = 0.015 + 0.006 = 0.021 *)
  Alcotest.(check int) "Portfolio returns has correct length"
    3 (Array.length portfolio_returns);
  Alcotest.(check (float 0.001)) "Day 1 return is correct"
    0.011 portfolio_returns.(0);
  Alcotest.(check (float 0.001)) "Day 2 return is correct"
    (-0.013) portfolio_returns.(1);
  Alcotest.(check (float 0.001)) "Day 3 return is correct"
    0.021 portfolio_returns.(2)

let test_should_rebalance_yes () =
  (* High improvement in objective → should rebalance *)
  let current : Types.optimization_result = {
    weights = {assets = [("AAPL", 0.5)]; cash = 0.5};
    objective_value = 0.10;  (* Higher objective = worse *)
    risk_metrics = { lpm1 = 0.01; cvar_95 = 0.03; portfolio_beta = 1.0 };
    turnover = 0.0;
    transaction_costs = 0.0;
  } in
  let proposed : Types.optimization_result = {
    weights = {assets = [("AAPL", 0.6); ("GOOGL", 0.3)]; cash = 0.1};
    objective_value = 0.05;  (* Lower = better, 50% improvement *)
    risk_metrics = { lpm1 = 0.005; cvar_95 = 0.015; portfolio_beta = 1.05 };
    turnover = 0.15;
    transaction_costs = 0.001;
  } in
  let threshold = 0.05 in  (* 5% improvement threshold *)

  let decision = Optimization.should_rebalance
    ~current_result:current ~proposed_result:proposed ~threshold in

  Alcotest.(check bool) "Should rebalance when improvement exceeds threshold"
    true decision.should_rebalance;
  Alcotest.(check bool) "Improvement delta is positive"
    true (decision.objective_improvement > 0.0)

let test_should_rebalance_no () =
  (* Small improvement → should not rebalance *)
  let current : Types.optimization_result = {
    weights = {assets = [("AAPL", 0.5)]; cash = 0.5};
    objective_value = 0.10;
    risk_metrics = { lpm1 = 0.01; cvar_95 = 0.03; portfolio_beta = 1.0 };
    turnover = 0.0;
    transaction_costs = 0.0;
  } in
  let proposed : Types.optimization_result = {
    weights = {assets = [("AAPL", 0.52); ("GOOGL", 0.03)]; cash = 0.45};
    objective_value = 0.098;  (* Only 2% improvement *)
    risk_metrics = { lpm1 = 0.0098; cvar_95 = 0.029; portfolio_beta = 1.01 };
    turnover = 0.05;
    transaction_costs = 0.0005;
  } in
  let threshold = 0.05 in  (* 5% improvement threshold *)

  let decision = Optimization.should_rebalance
    ~current_result:current ~proposed_result:proposed ~threshold in

  Alcotest.(check bool) "Should not rebalance when improvement is small"
    false decision.should_rebalance

(* Test suite *)
let () =
  Alcotest.run "Regime Downside Tests" [
    "beta", [
      Alcotest.test_case "EWM mean constant" `Quick test_ewm_mean;
      Alcotest.test_case "EWM mean trending" `Quick test_ewm_mean_trending;
      Alcotest.test_case "EWM variance zero" `Quick test_ewm_var;
      Alcotest.test_case "EWM variance nonzero" `Quick test_ewm_var_nonzero;
      Alcotest.test_case "EWM covariance positive" `Quick test_ewm_cov;
      Alcotest.test_case "EWM covariance negative" `Quick test_ewm_cov_negative;
      Alcotest.test_case "Estimate beta equals 1.0" `Quick test_estimate_beta;
      Alcotest.test_case "Estimate beta equals 2.0" `Quick test_estimate_beta_high;
      Alcotest.test_case "Estimate beta equals 0.0" `Quick test_estimate_beta_zero;
      Alcotest.test_case "Estimate all betas" `Quick test_estimate_all_betas;
    ];
    "regime", [
      Alcotest.test_case "Realized volatility zero" `Quick test_realized_volatility;
      Alcotest.test_case "Realized volatility nonzero" `Quick test_realized_volatility_nonzero;
      Alcotest.test_case "Percentile median" `Quick test_percentile_median;
      Alcotest.test_case "Percentile extremes" `Quick test_percentile_extremes;
      Alcotest.test_case "Percentile quartiles" `Quick test_percentile_quartiles;
      Alcotest.test_case "Stress weight calm" `Quick test_stress_weight_calm;
      Alcotest.test_case "Stress weight stress" `Quick test_stress_weight_stress;
      Alcotest.test_case "Stress weight transition" `Quick test_stress_weight_transition;
      Alcotest.test_case "Detect regime" `Quick test_detect_regime;
    ];
    "risk", [
      Alcotest.test_case "LPM1" `Quick test_lpm1;
      Alcotest.test_case "LPM1 all positive" `Quick test_lpm1_all_positive;
      Alcotest.test_case "LPM1 all below" `Quick test_lpm1_all_below;
      Alcotest.test_case "CVaR" `Quick test_cvar;
      Alcotest.test_case "CVaR all positive" `Quick test_cvar_all_positive;
      Alcotest.test_case "Portfolio Beta" `Quick test_portfolio_beta;
      Alcotest.test_case "Portfolio Beta all cash" `Quick test_portfolio_beta_all_cash;
      Alcotest.test_case "Portfolio Beta no cash" `Quick test_portfolio_beta_no_cash;
    ];
    "optimization", [
      Alcotest.test_case "Turnover" `Quick test_turnover;
      Alcotest.test_case "Turnover no change" `Quick test_turnover_no_change;
      Alcotest.test_case "Turnover full rebalance" `Quick test_turnover_full_rebalance;
      Alcotest.test_case "Transaction costs" `Quick test_transaction_costs;
      Alcotest.test_case "Transaction costs zero" `Quick test_transaction_costs_zero;
      Alcotest.test_case "Calculate portfolio returns" `Quick test_calculate_portfolio_returns;
      Alcotest.test_case "Should rebalance yes" `Quick test_should_rebalance_yes;
      Alcotest.test_case "Should rebalance no" `Quick test_should_rebalance_no;
    ];
  ]
