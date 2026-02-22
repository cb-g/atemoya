(* Unit Tests for Options Hedging Model *)

open Options_hedging

(* Test Black-Scholes pricing *)
let test_bs_put_call_parity () =
  (* Put-call parity: C - P = S - K × e^(-rT) *)
  let spot = 100.0 in
  let strike = 100.0 in
  let expiry = 1.0 in
  let rate = 0.05 in
  let dividend = 0.02 in
  let volatility = 0.25 in

  let call_price = Black_scholes.price_european_option
    ~option_type:Types.Call ~spot ~strike ~expiry ~rate ~dividend ~volatility in

  let put_price = Black_scholes.price_european_option
    ~option_type:Types.Put ~spot ~strike ~expiry ~rate ~dividend ~volatility in

  let parity_lhs = call_price -. put_price in
  let parity_rhs = spot *. exp (-. dividend *. expiry) -. strike *. exp (-. rate *. expiry) in

  Alcotest.(check (float 0.01)) "put-call parity holds" parity_lhs parity_rhs

(* Test Delta bounds *)
let test_delta_bounds () =
  let spot = 100.0 in
  let strike = 100.0 in
  let expiry = 0.25 in
  let rate = 0.05 in
  let dividend = 0.0 in
  let volatility = 0.20 in

  (* Call delta should be in [0, 1] *)
  let call_delta = Black_scholes.delta Types.Call
    ~spot ~strike ~expiry ~rate ~dividend ~volatility in
  Alcotest.(check bool) "call delta >= 0" true (call_delta >= 0.0);
  Alcotest.(check bool) "call delta <= 1" true (call_delta <= 1.0);

  (* Put delta should be in [-1, 0] *)
  let put_delta = Black_scholes.delta Types.Put
    ~spot ~strike ~expiry ~rate ~dividend ~volatility in
  Alcotest.(check bool) "put delta >= -1" true (put_delta >= -1.0);
  Alcotest.(check bool) "put delta <= 0" true (put_delta <= 0.0)

(* Test Gamma non-negativity *)
let test_gamma_non_negative () =
  let spot = 100.0 in
  let strike = 100.0 in
  let expiry = 0.5 in
  let rate = 0.05 in
  let dividend = 0.0 in
  let volatility = 0.30 in

  let gamma = Black_scholes.gamma ~spot ~strike ~expiry ~rate ~dividend ~volatility in
  Alcotest.(check bool) "gamma >= 0" true (gamma >= 0.0)

(* Test SVI no-arbitrage check *)
let test_svi_no_arbitrage () =
  (* Valid SVI parameters *)
  let valid_params = {
    Types.expiry = 0.25;
    a = 0.04;
    b = 0.10;
    rho = -0.3;
    m = 0.0;
    sigma = 0.15;
  } in

  let is_valid = Vol_surface.check_svi_arbitrage valid_params in
  Alcotest.(check bool) "valid SVI params pass arbitrage check" true is_valid;

  (* Invalid SVI parameters (butterfly arbitrage) *)
  let invalid_params = {
    Types.expiry = 0.25;
    a = 0.04;
    b = 0.05;      (* Too small b *)
    rho = -0.9;    (* Large negative rho *)
    m = 0.0;
    sigma = 0.20;  (* Would violate b/σ >= |ρ| *)
  } in

  let is_invalid = Vol_surface.check_svi_arbitrage invalid_params in
  Alcotest.(check bool) "invalid SVI params fail arbitrage check" false is_invalid

(* Test SABR parameter validation *)
let test_sabr_validation () =
  (* Valid SABR parameters *)
  let valid_params = {
    Types.expiry = 0.5;
    alpha = 0.25;
    beta = 0.5;
    rho = -0.2;
    nu = 0.3;
  } in

  let is_valid = Vol_surface.validate_sabr valid_params in
  Alcotest.(check bool) "valid SABR params pass validation" true is_valid;

  (* Invalid SABR parameters (beta out of bounds) *)
  let invalid_params = {
    Types.expiry = 0.5;
    alpha = 0.25;
    beta = 1.5;    (* Should be in [0, 1] *)
    rho = -0.2;
    nu = 0.3;
  } in

  let is_invalid = Vol_surface.validate_sabr invalid_params in
  Alcotest.(check bool) "invalid SABR params fail validation" false is_invalid

(* Test protective put payoff *)
let test_protective_put_payoff () =
  let underlying_position = 100.0 in
  let put_strike = 95.0 in

  (* Stock price below strike: protected *)
  let spot_low = 90.0 in
  let payoff_low = Strategies.strategy_payoff
    (Types.ProtectivePut { put_strike })
    ~underlying_position
    ~spot_at_expiry:spot_low
  in
  let expected_low = underlying_position *. put_strike in
  Alcotest.(check (float 0.01)) "protective put ITM" expected_low payoff_low;

  (* Stock price above strike: no protection needed *)
  let spot_high = 105.0 in
  let payoff_high = Strategies.strategy_payoff
    (Types.ProtectivePut { put_strike })
    ~underlying_position
    ~spot_at_expiry:spot_high
  in
  let expected_high = underlying_position *. spot_high in
  Alcotest.(check (float 0.01)) "protective put OTM" expected_high payoff_high

(* Test collar bounds *)
let test_collar_bounds () =
  let underlying_position = 100.0 in
  let put_strike = 90.0 in
  let call_strike = 110.0 in

  let strategy_type = Types.Collar { put_strike; call_strike } in

  (* Test various spot prices *)
  let spots = [| 80.0; 90.0; 100.0; 110.0; 120.0 |] in

  Array.iter (fun spot ->
    let payoff = Strategies.strategy_payoff strategy_type
      ~underlying_position ~spot_at_expiry:spot in

    (* Payoff should be bounded *)
    let min_value = underlying_position *. put_strike in
    let max_value = underlying_position *. call_strike in

    Alcotest.(check bool) (Printf.sprintf "collar payoff >= min at spot=%.0f" spot)
      true (payoff >= min_value -. 0.01);
    Alcotest.(check bool) (Printf.sprintf "collar payoff <= max at spot=%.0f" spot)
      true (payoff <= max_value +. 0.01)
  ) spots

(* Test portfolio Greeks additivity *)
let test_portfolio_greeks_additivity () =
  let greeks1 = {
    Types.delta = 0.5;
    gamma = 0.02;
    vega = 15.0;
    theta = -0.05;
    rho = 10.0;
  } in

  let greeks2 = {
    Types.delta = -0.3;
    gamma = 0.01;
    vega = 10.0;
    theta = -0.03;
    rho = 5.0;
  } in

  let combined = Types.add_greeks greeks1 greeks2 in

  Alcotest.(check (float 0.0001)) "portfolio delta additive" 0.2 combined.delta;
  Alcotest.(check (float 0.0001)) "portfolio gamma additive" 0.03 combined.gamma;
  Alcotest.(check (float 0.0001)) "portfolio vega additive" 25.0 combined.vega;
  Alcotest.(check (float 0.0001)) "portfolio theta additive" (-0.08) combined.theta;
  Alcotest.(check (float 0.0001)) "portfolio rho additive" 15.0 combined.rho

(* Test Pareto dominance *)
let test_pareto_dominance () =
  let strategy1 = {
    Types.strategy_type = Types.ProtectivePut { put_strike = 95.0 };
    expiry = 0.25;
    contracts = 1;
    cost = 300.0;
    greeks = Types.zero_greeks;
    protection_level = 9500.0;
  } in

  let strategy2 = {
    Types.strategy_type = Types.ProtectivePut { put_strike = 90.0 };
    expiry = 0.25;
    contracts = 1;
    cost = 200.0;  (* Lower cost *)
    greeks = Types.zero_greeks;
    protection_level = 9000.0;  (* Lower protection *)
  } in

  let strategy3 = {
    Types.strategy_type = Types.ProtectivePut { put_strike = 95.0 };
    expiry = 0.25;
    contracts = 1;
    cost = 250.0;  (* Lower cost than strategy1 *)
    greeks = Types.zero_greeks;
    protection_level = 9500.0;  (* Same protection as strategy1 *)
  } in

  let point1 = { Types.cost = strategy1.cost; protection_level = strategy1.protection_level; strategy = strategy1 } in
  let point2 = { Types.cost = strategy2.cost; protection_level = strategy2.protection_level; strategy = strategy2 } in
  let point3 = { Types.cost = strategy3.cost; protection_level = strategy3.protection_level; strategy = strategy3 } in

  let candidates = [| point1; point2; point3 |] in

  (* point1 is dominated by point3 (same protection, lower cost) *)
  let point1_dominated = Optimization.is_pareto_dominated point1 ~candidates in
  Alcotest.(check bool) "point1 is dominated" true point1_dominated;

  (* point3 is NOT dominated *)
  let point3_dominated = Optimization.is_pareto_dominated point3 ~candidates in
  Alcotest.(check bool) "point3 is not dominated" false point3_dominated;

  (* point2 is NOT dominated (different trade-off) *)
  let point2_dominated = Optimization.is_pareto_dominated point2 ~candidates in
  Alcotest.(check bool) "point2 is not dominated" false point2_dominated

(* Test suite *)
let () =
  let open Alcotest in
  run "Options Hedging" [
    "Black-Scholes", [
      test_case "Put-Call Parity" `Quick test_bs_put_call_parity;
      test_case "Delta Bounds" `Quick test_delta_bounds;
      test_case "Gamma Non-Negative" `Quick test_gamma_non_negative;
    ];
    "Volatility Surface", [
      test_case "SVI No-Arbitrage" `Quick test_svi_no_arbitrage;
      test_case "SABR Validation" `Quick test_sabr_validation;
    ];
    "Strategies", [
      test_case "Protective Put Payoff" `Quick test_protective_put_payoff;
      test_case "Collar Bounds" `Quick test_collar_bounds;
    ];
    "Greeks", [
      test_case "Portfolio Greeks Additivity" `Quick test_portfolio_greeks_additivity;
    ];
    "Optimization", [
      test_case "Pareto Dominance" `Quick test_pareto_dominance;
    ];
  ]
