(* Unit Tests for Perpetual Futures Pricing *)

open Perpetual_futures

let float_eq ~eps a b = Float.abs (a -. b) < eps

let float_t =
  Alcotest.testable (fun fmt v -> Format.fprintf fmt "%.10f" v)
    (float_eq ~eps:0.0001)

let float_precise =
  Alcotest.testable (fun fmt v -> Format.fprintf fmt "%.10f" v)
    (float_eq ~eps:0.000001)

(* ── Linear Pricing ── *)

let test_linear_continuous_basic () =
  let futures = Pricing.price_linear_continuous
    ~kappa:1.0 ~iota:0.0 ~r_a:0.0 ~r_b:0.0 ~spot:100.0 in
  Alcotest.(check float_t) "f = spot when rates = 0" 100.0 futures

let test_linear_continuous_contango () =
  let futures = Pricing.price_linear_continuous
    ~kappa:1.0 ~iota:0.0 ~r_a:0.05 ~r_b:0.0 ~spot:100.0 in
  Alcotest.(check bool) "contango when r_a > r_b" true (futures > 100.0)

let test_linear_continuous_backwardation () =
  let futures = Pricing.price_linear_continuous
    ~kappa:1.0 ~iota:0.0 ~r_a:0.0 ~r_b:0.05 ~spot:100.0 in
  Alcotest.(check bool) "backwardation when r_b > r_a" true (futures < 100.0)

let test_linear_continuous_value () =
  (* f = (kappa - iota) / (kappa + r_b - r_a) * spot
     = (1.0 - 0.0) / (1.0 + 0.0 - 0.05) * 100 = 1/0.95 * 100 = 105.2632 *)
  let futures = Pricing.price_linear_continuous
    ~kappa:1.0 ~iota:0.0 ~r_a:0.05 ~r_b:0.0 ~spot:100.0 in
  Alcotest.(check float_t) "linear continuous value" 105.2632 futures

let test_linear_discrete_basic () =
  let futures = Pricing.price_linear_discrete
    ~kappa:1.0 ~iota:0.0 ~r_a:0.0 ~r_b:0.0 ~spot:100.0 in
  Alcotest.(check float_t) "discrete: f = spot when rates = 0" 100.0 futures

let test_linear_discrete_value () =
  (* f = (kappa - iota)(1 + r_b) / (r_b - r_a + kappa(1 + r_b)) * spot
     = (1.0)(1.02) / (0.02 - 0.05 + 1.0 * 1.02) * 100
     = 1.02 / 0.99 * 100 = 103.0303 *)
  let futures = Pricing.price_linear_discrete
    ~kappa:1.0 ~iota:0.0 ~r_a:0.05 ~r_b:0.02 ~spot:100.0 in
  Alcotest.(check float_t) "linear discrete value" 103.0303 futures

(* ── Inverse Pricing ── *)

let test_inverse_continuous_basic () =
  let futures = Pricing.price_inverse_continuous
    ~kappa:1.0 ~iota:0.0 ~r_a:0.0 ~r_b:0.0 ~spot:100.0 in
  Alcotest.(check float_t) "f = spot when rates = 0" 100.0 futures

let test_inverse_continuous_value () =
  (* f_I = (kappa + r_a - r_b) / (kappa - iota) * spot
     = (1.0 + 0.05 - 0.0) / (1.0 - 0.0) * 100 = 105.0 *)
  let futures = Pricing.price_inverse_continuous
    ~kappa:1.0 ~iota:0.0 ~r_a:0.05 ~r_b:0.0 ~spot:100.0 in
  Alcotest.(check float_t) "inverse continuous value" 105.0 futures

let test_inverse_discrete_basic () =
  let futures = Pricing.price_inverse_discrete
    ~kappa:1.0 ~iota:0.0 ~r_a:0.0 ~r_b:0.0 ~spot:100.0 in
  Alcotest.(check float_t) "discrete: f = spot when rates = 0" 100.0 futures

let test_inverse_discrete_value () =
  (* f = (r_a - r_b + kappa(1 + r_a)) / ((kappa - iota)(1 + r_a)) * spot
     = (0.05 - 0.0 + 1.0 * 1.05) / ((1.0 - 0.0) * 1.05) * 100
     = 1.10 / 1.05 * 100 = 104.7619 *)
  let futures = Pricing.price_inverse_discrete
    ~kappa:1.0 ~iota:0.0 ~r_a:0.05 ~r_b:0.0 ~spot:100.0 in
  Alcotest.(check float_t) "inverse discrete value" 104.7619 futures

(* ── Quanto Pricing ── *)

let test_quanto_basic () =
  (* f_q = (kappa - iota) / (r_c - sigma_x * sigma_z * rho - r_a + kappa) * spot_z
     = (1.0 - 0.0) / (0.0 - 0 - 0.0 + 1.0) * 100 = 100.0 *)
  let futures = Pricing.price_quanto
    ~kappa:1.0 ~iota:0.0 ~r_a:0.0 ~r_c:0.0
    ~sigma_x:0.3 ~sigma_z:0.3 ~rho:0.0 ~spot_z:100.0 in
  Alcotest.(check float_t) "quanto: f = spot with zero rates and zero correlation" 100.0 futures

let test_quanto_with_rates () =
  (* f_q = (1.0 - 0.0) / (0.03 - 0.3*0.3*0.5 - 0.05 + 1.0) * 100
     = 1.0 / (0.03 - 0.045 - 0.05 + 1.0) * 100
     = 1.0 / 0.935 * 100 = 106.9519 *)
  let futures = Pricing.price_quanto
    ~kappa:1.0 ~iota:0.0 ~r_a:0.05 ~r_c:0.03
    ~sigma_x:0.3 ~sigma_z:0.3 ~rho:0.5 ~spot_z:100.0 in
  Alcotest.(check float_t) "quanto with rates and correlation" 106.9519 futures

(* ── Perfect Anchoring ── *)

let test_perfect_iota_linear_continuous () =
  (* iota = r_a - r_b = 0.05 - 0.02 = 0.03 *)
  let iota = Pricing.perfect_iota_linear_continuous ~r_a:0.05 ~r_b:0.02 in
  Alcotest.(check float_precise) "linear continuous iota" 0.03 iota;
  (* Verify f = spot with perfect iota *)
  let futures = Pricing.price_linear_continuous
    ~kappa:1.0 ~iota ~r_a:0.05 ~r_b:0.02 ~spot:100.0 in
  Alcotest.(check float_t) "f = spot with perfect iota" 100.0 futures

let test_perfect_iota_inverse_continuous () =
  (* iota_I = r_b - r_a = 0.02 - 0.05 = -0.03 *)
  let iota = Pricing.perfect_iota_inverse_continuous ~r_a:0.05 ~r_b:0.02 in
  Alcotest.(check float_precise) "inverse continuous iota" (-0.03) iota

let test_perfect_iota_linear_discrete () =
  (* iota = (r_a - r_b) / (1 + r_b) = (0.05 - 0.02) / 1.02 = 0.029412 *)
  let iota = Pricing.perfect_iota_linear_discrete ~r_a:0.05 ~r_b:0.02 in
  Alcotest.(check float_t) "linear discrete iota" 0.02941 iota

let test_perfect_iota_inverse_discrete () =
  (* iota = (r_b - r_a) / (1 + r_a) = (0.02 - 0.05) / 1.05 = -0.02857 *)
  let iota = Pricing.perfect_iota_inverse_discrete ~r_a:0.05 ~r_b:0.02 in
  Alcotest.(check float_t) "inverse discrete iota" (-0.02857) iota

(* ── Funding Rates ── *)

let test_funding_annualization () =
  (* annual = 0.0001 * 3 * 365 = 0.1095 *)
  let annual = Pricing.annualize_funding_rate ~funding_8h:0.0001 in
  Alcotest.(check float_precise) "annualize funding" 0.1095 annual

let test_funding_deannualization () =
  let funding_8h = 0.0001 in
  let annual = Pricing.annualize_funding_rate ~funding_8h in
  let back = Pricing.funding_rate_8h ~annualized:annual in
  Alcotest.(check float_precise) "roundtrip funding" funding_8h back

let test_implied_iota () =
  (* iota = kappa - (f/x) * (kappa + r_b - r_a)
     = 1.0 - (105/100) * (1.0 + 0.0 - 0.05)
     = 1.0 - 1.05 * 0.95 = 1.0 - 0.9975 = 0.0025 *)
  let implied = Pricing.implied_iota
    ~kappa:1.0 ~r_a:0.05 ~r_b:0.0 ~futures:105.0 ~spot:100.0 in
  Alcotest.(check float_t) "implied iota" 0.0025 implied

let test_futures_spot_ratio () =
  (* ratio = kappa*(1+r_b) / (kappa*(1+r_b) - delta)
     delta = r_a - r_b = 0.05 - 0.02 = 0.03
     = 1.0 * 1.02 / (1.0 * 1.02 - 0.03) = 1.02 / 0.99 = 1.030303 *)
  let ratio = Pricing.futures_spot_ratio_linear ~kappa:1.0 ~r_a:0.05 ~r_b:0.02 in
  Alcotest.(check float_t) "futures/spot ratio" 1.030303 ratio

let test_annual_to_period () =
  (* 5% annual / 1095 periods = 0.00004566 *)
  let period = Pricing.annual_to_period ~annual_rate:0.05 ~periods_per_year:1095.0 in
  let expected = 0.05 /. 1095.0 in
  Alcotest.(check float_precise) "annual to period" expected period

let test_period_to_annual () =
  let period = 0.0001 in
  let annual = Pricing.period_to_annual ~period_rate:period ~periods_per_year:1095.0 in
  Alcotest.(check float_precise) "period to annual" 0.1095 annual

(* ── Random Maturity ── *)

let test_mean_random_maturity () =
  let mean_mat = Pricing.mean_random_maturity ~kappa:0.5 in
  Alcotest.(check float_t) "mean maturity = 1/kappa" 2.0 mean_mat

let test_mean_random_maturity_high_kappa () =
  let mean_mat = Pricing.mean_random_maturity ~kappa:10.0 in
  Alcotest.(check float_t) "high kappa = short maturity" 0.1 mean_mat

(* ── Contract Pricing ── *)

let test_price_contract_linear () =
  let contract : Types.perpetual_contract = {
    contract_type = Linear;
    pair = { base = "BTC"; quote = "USD"; terciary = None };
    rates = { r_a = 0.05; r_b = 0.0; r_c = None };
    funding = { kappa = 1.0; iota = 0.0 };
    volatility = None;
  } in
  let result = Pricing.price_contract contract ~spot:50000.0 in
  Alcotest.(check float_t) "contract spot" 50000.0 result.spot_price;
  Alcotest.(check bool) "futures > spot" true (result.futures_price > 50000.0);
  Alcotest.(check bool) "positive basis" true (result.basis > 0.0);
  Alcotest.(check float_t) "perfect iota = r_a - r_b" 0.05 result.perfect_iota

let test_price_contract_inverse () =
  let contract : Types.perpetual_contract = {
    contract_type = Inverse;
    pair = { base = "BTC"; quote = "USD"; terciary = None };
    rates = { r_a = 0.05; r_b = 0.02; r_c = None };
    funding = { kappa = 1.0; iota = 0.0 };
    volatility = None;
  } in
  let result = Pricing.price_contract contract ~spot:50000.0 in
  Alcotest.(check float_t) "inverse perfect iota = r_b - r_a" (-0.03) result.perfect_iota

let test_price_contract_quanto () =
  let contract : Types.perpetual_contract = {
    contract_type = Quanto;
    pair = { base = "BTC"; quote = "USD"; terciary = Some "ETH" };
    rates = { r_a = 0.05; r_b = 0.0; r_c = Some 0.03 };
    funding = { kappa = 1.0; iota = 0.0 };
    volatility = Some { sigma_x = 0.3; sigma_z = Some 0.4; rho_xz = Some 0.6 };
  } in
  let result = Pricing.price_contract contract ~spot:3000.0 in
  Alcotest.(check bool) "quanto futures > 0" true (result.futures_price > 0.0)

(* ── Everlasting Options ── *)

let test_everlasting_call_atm () =
  let price = Everlasting.price_everlasting_call
    ~kappa:1.0 ~r_a:0.05 ~r_b:0.0 ~sigma:0.3 ~strike:100.0 ~spot:100.0 in
  Alcotest.(check bool) "ATM call > 0" true (price > 0.0)

let test_everlasting_call_itm () =
  let price = Everlasting.price_everlasting_call
    ~kappa:1.0 ~r_a:0.05 ~r_b:0.0 ~sigma:0.3 ~strike:100.0 ~spot:150.0 in
  let intrinsic = 150.0 -. 100.0 in
  Alcotest.(check bool) "deep ITM call > intrinsic" true (price > intrinsic)

let test_everlasting_call_otm () =
  let price = Everlasting.price_everlasting_call
    ~kappa:1.0 ~r_a:0.05 ~r_b:0.0 ~sigma:0.3 ~strike:100.0 ~spot:50.0 in
  Alcotest.(check bool) "OTM call > 0 (time value)" true (price > 0.0)

let test_everlasting_put_atm () =
  let price = Everlasting.price_everlasting_put
    ~kappa:1.0 ~r_a:0.05 ~r_b:0.0 ~sigma:0.3 ~strike:100.0 ~spot:100.0 in
  Alcotest.(check bool) "ATM put > 0" true (price > 0.0)

let test_everlasting_put_itm () =
  let kappa = 1.0 and r_a = 0.05 and r_b = 0.0 and sigma = 0.3
  and strike = 100.0 and spot = 50.0 in
  let price = Everlasting.price_everlasting_put ~kappa ~r_a ~r_b ~sigma ~strike ~spot in
  (* Effective intrinsic for everlasting put is K - f(x), not K - spot,
     because the underlying is the perpetual futures *)
  let f_x = Everlasting.perpetual_futures ~kappa ~r_a ~r_b ~spot in
  let eff_intrinsic = max 0.0 (strike -. f_x) in
  Alcotest.(check bool) "deep ITM put > effective intrinsic" true (price > eff_intrinsic)

let test_everlasting_put_call_parity () =
  (* c - p = f(x) - K *)
  let kappa = 1.0 and r_a = 0.05 and r_b = 0.0 and sigma = 0.3
  and strike = 100.0 and spot = 120.0 in
  let call = Everlasting.price_everlasting_call ~kappa ~r_a ~r_b ~sigma ~strike ~spot in
  let put = Everlasting.price_everlasting_put ~kappa ~r_a ~r_b ~sigma ~strike ~spot in
  let f_x = Everlasting.perpetual_futures ~kappa ~r_a ~r_b ~spot in
  let lhs = call -. put in
  let rhs = f_x -. strike in
  Alcotest.(check float_t) "put-call parity" rhs lhs

let test_everlasting_call_delta_bounds () =
  let delta = Everlasting.delta_everlasting_call
    ~kappa:1.0 ~r_a:0.05 ~r_b:0.0 ~sigma:0.3 ~strike:100.0 ~spot:100.0 in
  Alcotest.(check bool) "call delta > 0" true (delta > 0.0);
  Alcotest.(check bool) "call delta < 2" true (delta < 2.0)

let test_everlasting_put_delta () =
  (* put delta = call delta - f'(x) where f'(x) = kappa / (kappa - r_a + r_b) *)
  let kappa = 1.0 and r_a = 0.05 and r_b = 0.0 and sigma = 0.3
  and strike = 100.0 and spot = 100.0 in
  let put_d = Everlasting.delta_everlasting_put ~kappa ~r_a ~r_b ~sigma ~strike ~spot in
  let call_d = Everlasting.delta_everlasting_call ~kappa ~r_a ~r_b ~sigma ~strike ~spot in
  let f_delta = kappa /. (kappa -. r_a +. r_b) in
  Alcotest.(check float_t) "put delta = call delta - f_delta" (call_d -. f_delta) put_d

let test_quadratic_roots () =
  let (pi_minus, theta_plus) = Everlasting.quadratic_roots
    ~r_a:0.05 ~r_b:0.0 ~sigma:0.3 ~kappa:1.0 in
  Alcotest.(check bool) "pi < 0" true (pi_minus < 0.0);
  Alcotest.(check bool) "theta > 1" true (theta_plus > 1.0)

let test_perpetual_futures_everlasting () =
  (* f(x) = kappa * x / (kappa - r_a + r_b)
     = 1.0 * 100.0 / (1.0 - 0.05 + 0.0) = 100 / 0.95 = 105.2632 *)
  let f = Everlasting.perpetual_futures
    ~kappa:1.0 ~r_a:0.05 ~r_b:0.0 ~spot:100.0 in
  Alcotest.(check float_t) "everlasting perpetual futures" 105.2632 f

let test_price_option_call () =
  let opt : Types.everlasting_option = {
    opt_type = Call; strike = 100.0; kappa = 1.0;
    r_a = 0.05; r_b = 0.0; sigma = 0.3;
  } in
  let result = Everlasting.price_option opt ~spot:110.0 in
  Alcotest.(check bool) "option_price > 0" true (result.option_price > 0.0);
  Alcotest.(check float_t) "underlying" 110.0 result.underlying;
  Alcotest.(check float_t) "intrinsic" 10.0 result.intrinsic;
  Alcotest.(check bool) "time_value > 0" true (result.time_value > 0.0)

let test_price_option_put () =
  let opt : Types.everlasting_option = {
    opt_type = Put; strike = 100.0; kappa = 1.0;
    r_a = 0.05; r_b = 0.0; sigma = 0.3;
  } in
  let result = Everlasting.price_option opt ~spot:90.0 in
  Alcotest.(check bool) "put price > 0" true (result.option_price > 0.0);
  Alcotest.(check float_t) "put intrinsic" 10.0 result.intrinsic;
  Alcotest.(check bool) "put delta < 0" true (result.delta < 0.0)

let test_option_price_grid () =
  let spots = [80.0; 90.0; 100.0; 110.0; 120.0] in
  let grid = Everlasting.option_price_grid
    ~kappa:1.0 ~r_a:0.05 ~r_b:0.0 ~sigma:0.3 ~strike:100.0 ~spots in
  Alcotest.(check int) "grid length" 5 (List.length grid);
  (* Call prices should increase with spot *)
  let calls = List.map (fun (_, c, _) -> c) grid in
  let rec is_increasing = function
    | [] | [_] -> true
    | a :: b :: rest -> a < b && is_increasing (b :: rest) in
  Alcotest.(check bool) "calls increase with spot" true (is_increasing calls);
  (* Put prices should decrease with spot *)
  let puts = List.map (fun (_, _, p) -> p) grid in
  let rec is_decreasing = function
    | [] | [_] -> true
    | a :: b :: rest -> a > b && is_decreasing (b :: rest) in
  Alcotest.(check bool) "puts decrease with spot" true (is_decreasing puts)

(* ── Type Helpers ── *)

let test_contract_type_to_string () =
  Alcotest.(check string) "Linear" "Linear" (Types.contract_type_to_string Linear);
  Alcotest.(check string) "Inverse" "Inverse" (Types.contract_type_to_string Inverse);
  Alcotest.(check string) "Quanto" "Quanto" (Types.contract_type_to_string Quanto)

let test_option_type_to_string () =
  Alcotest.(check string) "Call" "Call" (Types.option_type_to_string Call);
  Alcotest.(check string) "Put" "Put" (Types.option_type_to_string Put)

let test_string_to_contract_type () =
  Alcotest.(check bool) "linear" true (Types.string_to_contract_type "linear" = Some Linear);
  Alcotest.(check bool) "Linear" true (Types.string_to_contract_type "Linear" = Some Linear);
  Alcotest.(check bool) "inverse" true (Types.string_to_contract_type "inverse" = Some Inverse);
  Alcotest.(check bool) "quanto" true (Types.string_to_contract_type "quanto" = Some Quanto);
  Alcotest.(check bool) "unknown" true (Types.string_to_contract_type "foo" = None)

(* ── Test Suite ── *)

let () =
  let open Alcotest in
  run "Perpetual Futures" [
    "Linear Pricing", [
      test_case "Continuous basic" `Quick test_linear_continuous_basic;
      test_case "Continuous contango" `Quick test_linear_continuous_contango;
      test_case "Continuous backwardation" `Quick test_linear_continuous_backwardation;
      test_case "Continuous value" `Quick test_linear_continuous_value;
      test_case "Discrete basic" `Quick test_linear_discrete_basic;
      test_case "Discrete value" `Quick test_linear_discrete_value;
    ];
    "Inverse Pricing", [
      test_case "Continuous basic" `Quick test_inverse_continuous_basic;
      test_case "Continuous value" `Quick test_inverse_continuous_value;
      test_case "Discrete basic" `Quick test_inverse_discrete_basic;
      test_case "Discrete value" `Quick test_inverse_discrete_value;
    ];
    "Quanto Pricing", [
      test_case "Zero rates zero corr" `Quick test_quanto_basic;
      test_case "With rates and corr" `Quick test_quanto_with_rates;
    ];
    "Perfect Anchoring", [
      test_case "Linear continuous" `Quick test_perfect_iota_linear_continuous;
      test_case "Inverse continuous" `Quick test_perfect_iota_inverse_continuous;
      test_case "Linear discrete" `Quick test_perfect_iota_linear_discrete;
      test_case "Inverse discrete" `Quick test_perfect_iota_inverse_discrete;
    ];
    "Funding Rates", [
      test_case "Annualization" `Quick test_funding_annualization;
      test_case "Deannualization" `Quick test_funding_deannualization;
      test_case "Implied iota" `Quick test_implied_iota;
      test_case "Futures/spot ratio" `Quick test_futures_spot_ratio;
      test_case "Annual to period" `Quick test_annual_to_period;
      test_case "Period to annual" `Quick test_period_to_annual;
    ];
    "Random Maturity", [
      test_case "Mean maturity" `Quick test_mean_random_maturity;
      test_case "High kappa" `Quick test_mean_random_maturity_high_kappa;
    ];
    "Contract Pricing", [
      test_case "Linear contract" `Quick test_price_contract_linear;
      test_case "Inverse contract" `Quick test_price_contract_inverse;
      test_case "Quanto contract" `Quick test_price_contract_quanto;
    ];
    "Everlasting Options", [
      test_case "Call ATM" `Quick test_everlasting_call_atm;
      test_case "Call ITM" `Quick test_everlasting_call_itm;
      test_case "Call OTM" `Quick test_everlasting_call_otm;
      test_case "Put ATM" `Quick test_everlasting_put_atm;
      test_case "Put ITM" `Quick test_everlasting_put_itm;
      test_case "Put-call parity" `Quick test_everlasting_put_call_parity;
      test_case "Call delta bounds" `Quick test_everlasting_call_delta_bounds;
      test_case "Put delta" `Quick test_everlasting_put_delta;
      test_case "Quadratic roots" `Quick test_quadratic_roots;
      test_case "Perpetual futures" `Quick test_perpetual_futures_everlasting;
      test_case "Price option call" `Quick test_price_option_call;
      test_case "Price option put" `Quick test_price_option_put;
      test_case "Option price grid" `Quick test_option_price_grid;
    ];
    "Type Helpers", [
      test_case "Contract type to string" `Quick test_contract_type_to_string;
      test_case "Option type to string" `Quick test_option_type_to_string;
      test_case "String to contract type" `Quick test_string_to_contract_type;
    ];
  ]
