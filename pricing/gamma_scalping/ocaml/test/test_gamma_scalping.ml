(** Unit tests for gamma scalping model *)

open Gamma_scalping_lib

(* ========== Pricing Tests ========== *)

let test_put_call_parity () =
  let spot = 100.0 in
  let strike = 100.0 in
  let expiry = 30.0 /. 365.0 in
  let rate = 0.05 in
  let dividend = 0.0 in
  let volatility = 0.20 in
  let call = Pricing.price_option ~option_type:Call ~spot ~strike ~expiry ~rate ~dividend ~volatility in
  let put = Pricing.price_option ~option_type:Put ~spot ~strike ~expiry ~rate ~dividend ~volatility in
  (* C - P = S - K*e^(-rT) *)
  let lhs = call -. put in
  let rhs = spot -. strike *. exp (-. rate *. expiry) in
  Alcotest.(check (float 0.001)) "put-call parity" rhs lhs

let test_call_price_positive () =
  let price = Pricing.price_option ~option_type:Call
    ~spot:100.0 ~strike:100.0 ~expiry:0.0822 ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  Alcotest.(check bool) "call price positive" true (price > 0.0)

let test_put_price_positive () =
  let price = Pricing.price_option ~option_type:Put
    ~spot:100.0 ~strike:100.0 ~expiry:0.0822 ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  Alcotest.(check bool) "put price positive" true (price > 0.0)

let test_deep_itm_call () =
  (* Deep ITM call ~ S - K*e^(-rT) *)
  let call = Pricing.price_option ~option_type:Call
    ~spot:150.0 ~strike:100.0 ~expiry:0.0822 ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  let intrinsic = 150.0 -. 100.0 *. exp (-0.05 *. 0.0822) in
  Alcotest.(check bool) "deep ITM call >= intrinsic" true (call >= intrinsic -. 0.01)

let test_deep_otm_call () =
  (* Deep OTM call ~ 0 *)
  let call = Pricing.price_option ~option_type:Call
    ~spot:50.0 ~strike:100.0 ~expiry:0.0822 ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  Alcotest.(check bool) "deep OTM call near zero" true (call < 0.01)

(* ========== Greeks Tests ========== *)

let test_call_delta_range () =
  let greeks = Pricing.compute_greeks ~option_type:Call
    ~spot:100.0 ~strike:100.0 ~expiry:0.0822 ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  Alcotest.(check bool) "call delta in (0,1)" true (greeks.delta > 0.0 && greeks.delta < 1.0)

let test_put_delta_range () =
  let greeks = Pricing.compute_greeks ~option_type:Put
    ~spot:100.0 ~strike:100.0 ~expiry:0.0822 ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  Alcotest.(check bool) "put delta in (-1,0)" true (greeks.delta < 0.0 && greeks.delta > -1.0)

let test_gamma_positive () =
  let greeks = Pricing.compute_greeks ~option_type:Call
    ~spot:100.0 ~strike:100.0 ~expiry:0.0822 ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  Alcotest.(check bool) "gamma positive" true (greeks.gamma > 0.0)

let test_theta_negative () =
  let greeks = Pricing.compute_greeks ~option_type:Call
    ~spot:100.0 ~strike:100.0 ~expiry:0.0822 ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  Alcotest.(check bool) "theta negative" true (greeks.theta < 0.0)

let test_vega_positive () =
  let greeks = Pricing.compute_greeks ~option_type:Call
    ~spot:100.0 ~strike:100.0 ~expiry:0.0822 ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  Alcotest.(check bool) "vega positive" true (greeks.vega > 0.0)

let test_gamma_same_for_call_put () =
  let call_g = Pricing.gamma ~spot:100.0 ~strike:100.0 ~expiry:0.0822
    ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  let put_g = Pricing.gamma ~spot:100.0 ~strike:100.0 ~expiry:0.0822
    ~rate:0.05 ~dividend:0.0 ~volatility:0.20 in
  Alcotest.(check (float 0.0001)) "gamma same for call/put" call_g put_g

(* ========== Positions Tests ========== *)

let test_straddle_delta_neutral () =
  let (_, greeks) = Positions.build_straddle
    ~spot:100.0 ~strike:100.0 ~expiry:0.0822 ~volatility:0.20
    ~rate:0.05 ~dividend:0.0 ~contracts:1 in
  Alcotest.(check bool) "straddle delta near zero" true (abs_float greeks.delta < 0.15)

let test_straddle_gamma_positive () =
  let (_, greeks) = Positions.build_straddle
    ~spot:100.0 ~strike:100.0 ~expiry:0.0822 ~volatility:0.20
    ~rate:0.05 ~dividend:0.0 ~contracts:1 in
  Alcotest.(check bool) "straddle gamma positive" true (greeks.gamma > 0.0)

let test_straddle_premium_positive () =
  let (premium, _) = Positions.build_straddle
    ~spot:100.0 ~strike:100.0 ~expiry:0.0822 ~volatility:0.20
    ~rate:0.05 ~dividend:0.0 ~contracts:1 in
  Alcotest.(check bool) "straddle premium > 0" true (premium > 0.0)

let test_strangle_cheaper_than_straddle () =
  let (straddle_prem, _) = Positions.build_straddle
    ~spot:100.0 ~strike:100.0 ~expiry:0.0822 ~volatility:0.20
    ~rate:0.05 ~dividend:0.0 ~contracts:1 in
  let (strangle_prem, _) = Positions.build_strangle
    ~spot:100.0 ~call_strike:105.0 ~put_strike:95.0 ~expiry:0.0822
    ~volatility:0.20 ~rate:0.05 ~dividend:0.0 ~contracts:1 in
  Alcotest.(check bool) "strangle cheaper" true (strangle_prem < straddle_prem)

let test_contracts_scale_premium () =
  let (prem1, _) = Positions.build_straddle
    ~spot:100.0 ~strike:100.0 ~expiry:0.0822 ~volatility:0.20
    ~rate:0.05 ~dividend:0.0 ~contracts:1 in
  let (prem3, _) = Positions.build_straddle
    ~spot:100.0 ~strike:100.0 ~expiry:0.0822 ~volatility:0.20
    ~rate:0.05 ~dividend:0.0 ~contracts:3 in
  Alcotest.(check (float 0.01)) "3 contracts = 3x premium" (prem1 *. 3.0) prem3

let test_add_greeks () =
  let g1 : Types.greeks = { delta = 0.5; gamma = 0.02; theta = -0.05; vega = 0.10; rho = 0.01 } in
  let g2 : Types.greeks = { delta = -0.4; gamma = 0.02; theta = -0.04; vega = 0.10; rho = -0.01 } in
  let sum = Positions.add_greeks g1 g2 in
  Alcotest.(check (float 0.001)) "delta adds" 0.1 sum.delta;
  Alcotest.(check (float 0.001)) "gamma adds" 0.04 sum.gamma

let test_scale_greeks () =
  let g : Types.greeks = { delta = 0.5; gamma = 0.02; theta = -0.05; vega = 0.10; rho = 0.01 } in
  let scaled = Positions.scale_greeks g 2.0 in
  Alcotest.(check (float 0.001)) "delta scaled" 1.0 scaled.delta;
  Alcotest.(check (float 0.001)) "gamma scaled" 0.04 scaled.gamma

let test_zero_greeks () =
  let z = Positions.zero_greeks in
  Alcotest.(check (float 0.001)) "zero delta" 0.0 z.delta;
  Alcotest.(check (float 0.001)) "zero gamma" 0.0 z.gamma

(* ========== Hedging Tests ========== *)

let test_threshold_hedge_triggered () =
  Alcotest.(check bool) "hedge at |0.15| >= 0.10" true
    (Hedging.should_hedge_threshold ~current_delta:0.15 ~threshold:0.10)

let test_threshold_hedge_not_triggered () =
  Alcotest.(check bool) "no hedge at |0.05| < 0.10" false
    (Hedging.should_hedge_threshold ~current_delta:0.05 ~threshold:0.10)

let test_threshold_negative_delta () =
  Alcotest.(check bool) "hedge at |-0.15| >= 0.10" true
    (Hedging.should_hedge_threshold ~current_delta:(-0.15) ~threshold:0.10)

let test_time_hedge_triggered () =
  (* 0.25 days = 6 hours, interval = 240 min = 4 hours *)
  Alcotest.(check bool) "hedge after 6h with 4h interval" true
    (Hedging.should_hedge_time ~current_time:0.25 ~last_hedge_time:0.0 ~interval_minutes:240)

let test_time_hedge_not_triggered () =
  (* 0.1 days = 2.4 hours < 4 hours *)
  Alcotest.(check bool) "no hedge after 2.4h with 4h interval" false
    (Hedging.should_hedge_time ~current_time:0.1 ~last_hedge_time:0.0 ~interval_minutes:240)

let test_hybrid_triggers_on_delta () =
  Alcotest.(check bool) "hybrid: delta triggers" true
    (Hedging.should_hedge_hybrid ~current_delta:0.15 ~threshold:0.10
       ~current_time:0.01 ~last_hedge_time:0.0 ~interval_minutes:240)

let test_hybrid_triggers_on_time () =
  Alcotest.(check bool) "hybrid: time triggers" true
    (Hedging.should_hedge_hybrid ~current_delta:0.05 ~threshold:0.10
       ~current_time:0.25 ~last_hedge_time:0.0 ~interval_minutes:240)

let test_execute_hedge () =
  let event = Hedging.execute_hedge
    ~timestamp:0.5 ~spot_price:100.0 ~current_delta:0.20 ~transaction_cost_bps:5.0 in
  Alcotest.(check (float 0.001)) "hedge qty" (-0.20) event.hedge_quantity;
  (* cost = |0.20| * 100 * 5/10000 = 0.01 *)
  Alcotest.(check (float 0.001)) "hedge cost" 0.01 event.hedge_cost;
  Alcotest.(check (float 0.001)) "delta before" 0.20 event.delta_before

let test_realized_volatility () =
  (* Constant returns of 0.01 → variance = 0.01^2 = 0.0001, vol = 0.01 *)
  let returns = [| 0.01; 0.01; 0.01; 0.01; 0.01 |] in
  let rv = Hedging.realized_volatility ~returns ~annualization_factor:1.0 in
  Alcotest.(check (float 0.001)) "realized vol" 0.01 rv

let test_realized_volatility_empty () =
  let rv = Hedging.realized_volatility ~returns:[||] ~annualization_factor:252.0 in
  Alcotest.(check (float 0.001)) "empty returns = 0" 0.0 rv

(* ========== P&L Attribution Tests ========== *)

let test_gamma_pnl () =
  (* gamma_pnl = 0.5 * gamma * dS^2 *)
  let pnl = Pnl_attribution.compute_gamma_pnl ~gamma:0.05 ~spot_change:2.0 in
  (* 0.5 * 0.05 * 4.0 = 0.10 *)
  Alcotest.(check (float 0.001)) "gamma pnl" 0.10 pnl

let test_gamma_pnl_always_positive () =
  let pnl_up = Pnl_attribution.compute_gamma_pnl ~gamma:0.05 ~spot_change:2.0 in
  let pnl_down = Pnl_attribution.compute_gamma_pnl ~gamma:0.05 ~spot_change:(-2.0) in
  Alcotest.(check bool) "gamma pnl positive (up)" true (pnl_up > 0.0);
  Alcotest.(check bool) "gamma pnl positive (down)" true (pnl_down > 0.0);
  Alcotest.(check (float 0.001)) "gamma pnl symmetric" pnl_up pnl_down

let test_theta_pnl () =
  (* theta_pnl = theta * dt *)
  let pnl = Pnl_attribution.compute_theta_pnl ~theta:(-0.05) ~time_step_days:1.0 in
  Alcotest.(check (float 0.001)) "theta pnl" (-0.05) pnl

let test_vega_pnl () =
  (* vega_pnl = vega * dIV *)
  let pnl = Pnl_attribution.compute_vega_pnl ~vega:0.15 ~iv_change:2.0 in
  Alcotest.(check (float 0.001)) "vega pnl" 0.30 pnl

let test_initial_pnl_snapshot () =
  let snap = Pnl_attribution.initial_pnl_snapshot
    ~timestamp:0.0 ~spot_price:100.0 ~entry_premium:5.0 in
  Alcotest.(check (float 0.001)) "initial total pnl" 0.0 snap.total_pnl;
  Alcotest.(check (float 0.001)) "initial gamma pnl" 0.0 snap.gamma_pnl;
  Alcotest.(check (float 0.001)) "initial option value" 5.0 snap.option_value

let test_win_rate_all_profitable () =
  let snaps = Array.init 5 (fun _ ->
    { Types.timestamp = 0.0; spot_price = 100.0; option_value = 10.0;
      option_pnl = 1.0; gamma_pnl = 0.5; theta_pnl = -0.1;
      vega_pnl = 0.0; hedge_pnl = 0.0; transaction_costs = 0.0;
      total_pnl = 1.0; cumulative_pnl = 1.0 }) in
  let wr = Pnl_attribution.calculate_win_rate ~pnl_timeseries:snaps in
  Alcotest.(check (float 0.01)) "100% win rate" 1.0 wr

let test_win_rate_empty () =
  let wr = Pnl_attribution.calculate_win_rate ~pnl_timeseries:[||] in
  Alcotest.(check (float 0.01)) "empty = 0" 0.0 wr

let test_max_drawdown_no_drawdown () =
  let dd = Pnl_attribution.calculate_max_drawdown ~pnl_timeseries:[||] in
  Alcotest.(check (float 0.01)) "empty = 0" 0.0 dd

let test_sharpe_insufficient_data () =
  let snaps = [| { Types.timestamp = 0.0; spot_price = 100.0; option_value = 5.0;
    option_pnl = 0.0; gamma_pnl = 0.0; theta_pnl = 0.0; vega_pnl = 0.0;
    hedge_pnl = 0.0; transaction_costs = 0.0; total_pnl = 0.0; cumulative_pnl = 0.0 } |] in
  let sharpe = Pnl_attribution.calculate_sharpe_ratio ~pnl_timeseries:snaps in
  Alcotest.(check bool) "insufficient data = None" true (sharpe = None)

(* ========== Simulation Integration Tests ========== *)

(* Helper: generate synthetic intraday prices as (timestamp_days, price) *)
let make_prices prices =
  (* Space observations ~5 minutes apart = 5/(24*60) days *)
  let dt = 5.0 /. (24.0 *. 60.0) in
  Array.mapi (fun i p -> (float_of_int i *. dt, p)) prices

let default_sim_config : Types.simulation_config = {
  transaction_cost_bps = 5.0;
  rate = 0.05;
  dividend = 0.0;
  contracts = 1;
}

let test_simulation_basic () =
  (* Stock moves 100 → 102 → 104 → 101 → 98 → 100 with intermediate steps *)
  let raw_prices = [|
    100.0; 100.5; 101.0; 101.5; 102.0; 102.5; 103.0; 103.5; 104.0;
    103.0; 102.0; 101.0; 100.0; 99.0; 98.0; 98.5; 99.0; 99.5; 100.0;
  |] in
  let prices = make_prices raw_prices in
  let result = Simulation.run_simulation
    ~position_type:(Types.Straddle { strike = 100.0 })
    ~intraday_prices:prices
    ~entry_iv:0.20
    ~iv_timeseries:None
    ~hedging_strategy:(Types.DeltaThreshold { threshold = 0.10 })
    ~config:default_sim_config
    ~expiry:(30.0 /. 365.0)
  in
  Alcotest.(check bool) "num_hedges > 0" true (result.num_hedges > 0);
  Alcotest.(check bool) "final_pnl is finite" true (Float.is_finite result.final_pnl);
  Alcotest.(check bool) "pnl_timeseries length" true
    (Array.length result.pnl_timeseries = Array.length prices);
  Alcotest.(check bool) "hedge_log length = num_hedges" true
    (Array.length result.hedge_log = result.num_hedges)

let test_simulation_hedge_pnl_nonzero () =
  (* Large moves to trigger hedges and generate hedge P&L *)
  let raw_prices = [|
    100.0; 101.0; 102.0; 103.0; 104.0; 105.0; 106.0; 107.0; 108.0;
    107.0; 106.0; 105.0; 104.0; 103.0; 102.0; 101.0; 100.0; 99.0; 98.0;
  |] in
  let prices = make_prices raw_prices in
  let result = Simulation.run_simulation
    ~position_type:(Types.Straddle { strike = 100.0 })
    ~intraday_prices:prices
    ~entry_iv:0.20
    ~iv_timeseries:None
    ~hedging_strategy:(Types.DeltaThreshold { threshold = 0.05 })
    ~config:default_sim_config
    ~expiry:(30.0 /. 365.0)
  in
  (* With hedges occurring, hedge_pnl should be non-zero *)
  Alcotest.(check bool) "hedges occurred" true (result.num_hedges > 0);
  Alcotest.(check bool) "hedge_pnl_total is non-zero" true
    (abs_float result.hedge_pnl_total > 0.0001)

let test_simulation_pnl_consistency () =
  (* Verify total_pnl = option_pnl + hedge_pnl - transaction_costs *)
  let raw_prices = [|
    100.0; 100.5; 101.0; 101.5; 102.0; 101.5; 101.0; 100.5; 100.0;
    99.5; 99.0; 98.5; 99.0; 99.5; 100.0;
  |] in
  let prices = make_prices raw_prices in
  let result = Simulation.run_simulation
    ~position_type:(Types.Straddle { strike = 100.0 })
    ~intraday_prices:prices
    ~entry_iv:0.20
    ~iv_timeseries:None
    ~hedging_strategy:(Types.DeltaThreshold { threshold = 0.08 })
    ~config:default_sim_config
    ~expiry:(30.0 /. 365.0)
  in
  let final = result.pnl_timeseries.(Array.length result.pnl_timeseries - 1) in
  let expected_total = final.option_pnl +. final.hedge_pnl -. final.transaction_costs in
  Alcotest.(check (float 0.001)) "total_pnl = option + hedge - costs"
    expected_total final.total_pnl

let test_simulation_no_movement () =
  (* Flat price: no hedges, no gamma P&L, only theta decay *)
  let raw_prices = Array.make 20 100.0 in
  let prices = make_prices raw_prices in
  let result = Simulation.run_simulation
    ~position_type:(Types.Straddle { strike = 100.0 })
    ~intraday_prices:prices
    ~entry_iv:0.20
    ~iv_timeseries:None
    ~hedging_strategy:(Types.DeltaThreshold { threshold = 0.10 })
    ~config:default_sim_config
    ~expiry:(30.0 /. 365.0)
  in
  Alcotest.(check bool) "no hedges needed" true (result.num_hedges = 0);
  Alcotest.(check (float 0.001)) "gamma pnl = 0" 0.0 result.gamma_pnl_total;
  Alcotest.(check bool) "theta pnl < 0" true (result.theta_pnl_total < 0.0);
  Alcotest.(check (float 0.001)) "hedge pnl = 0" 0.0 result.hedge_pnl_total

(* ========== Test Suite ========== *)

let () =
  Alcotest.run "Gamma Scalping Tests" [
    "pricing", [
      Alcotest.test_case "Put-call parity" `Quick test_put_call_parity;
      Alcotest.test_case "Call price positive" `Quick test_call_price_positive;
      Alcotest.test_case "Put price positive" `Quick test_put_price_positive;
      Alcotest.test_case "Deep ITM call" `Quick test_deep_itm_call;
      Alcotest.test_case "Deep OTM call" `Quick test_deep_otm_call;
    ];
    "greeks", [
      Alcotest.test_case "Call delta range" `Quick test_call_delta_range;
      Alcotest.test_case "Put delta range" `Quick test_put_delta_range;
      Alcotest.test_case "Gamma positive" `Quick test_gamma_positive;
      Alcotest.test_case "Theta negative" `Quick test_theta_negative;
      Alcotest.test_case "Vega positive" `Quick test_vega_positive;
      Alcotest.test_case "Gamma same call/put" `Quick test_gamma_same_for_call_put;
    ];
    "positions", [
      Alcotest.test_case "Straddle delta neutral" `Quick test_straddle_delta_neutral;
      Alcotest.test_case "Straddle gamma positive" `Quick test_straddle_gamma_positive;
      Alcotest.test_case "Straddle premium positive" `Quick test_straddle_premium_positive;
      Alcotest.test_case "Strangle cheaper" `Quick test_strangle_cheaper_than_straddle;
      Alcotest.test_case "Contracts scale premium" `Quick test_contracts_scale_premium;
      Alcotest.test_case "Add Greeks" `Quick test_add_greeks;
      Alcotest.test_case "Scale Greeks" `Quick test_scale_greeks;
      Alcotest.test_case "Zero Greeks" `Quick test_zero_greeks;
    ];
    "hedging", [
      Alcotest.test_case "Threshold triggered" `Quick test_threshold_hedge_triggered;
      Alcotest.test_case "Threshold not triggered" `Quick test_threshold_hedge_not_triggered;
      Alcotest.test_case "Threshold negative delta" `Quick test_threshold_negative_delta;
      Alcotest.test_case "Time triggered" `Quick test_time_hedge_triggered;
      Alcotest.test_case "Time not triggered" `Quick test_time_hedge_not_triggered;
      Alcotest.test_case "Hybrid delta triggers" `Quick test_hybrid_triggers_on_delta;
      Alcotest.test_case "Hybrid time triggers" `Quick test_hybrid_triggers_on_time;
      Alcotest.test_case "Execute hedge" `Quick test_execute_hedge;
      Alcotest.test_case "Realized volatility" `Quick test_realized_volatility;
      Alcotest.test_case "Realized vol empty" `Quick test_realized_volatility_empty;
    ];
    "pnl_attribution", [
      Alcotest.test_case "Gamma P&L" `Quick test_gamma_pnl;
      Alcotest.test_case "Gamma P&L always positive" `Quick test_gamma_pnl_always_positive;
      Alcotest.test_case "Theta P&L" `Quick test_theta_pnl;
      Alcotest.test_case "Vega P&L" `Quick test_vega_pnl;
      Alcotest.test_case "Initial snapshot" `Quick test_initial_pnl_snapshot;
      Alcotest.test_case "Win rate all profitable" `Quick test_win_rate_all_profitable;
      Alcotest.test_case "Win rate empty" `Quick test_win_rate_empty;
      Alcotest.test_case "Max drawdown empty" `Quick test_max_drawdown_no_drawdown;
      Alcotest.test_case "Sharpe insufficient data" `Quick test_sharpe_insufficient_data;
    ];
    "simulation", [
      Alcotest.test_case "Basic simulation" `Quick test_simulation_basic;
      Alcotest.test_case "Hedge P&L nonzero" `Quick test_simulation_hedge_pnl_nonzero;
      Alcotest.test_case "P&L consistency" `Quick test_simulation_pnl_consistency;
      Alcotest.test_case "No movement" `Quick test_simulation_no_movement;
    ];
  ]
