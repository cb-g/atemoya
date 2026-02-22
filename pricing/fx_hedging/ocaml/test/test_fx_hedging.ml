(* Tests for FX hedging *)

open Fx_hedging_lib

let test_forwards () =
  Printf.printf "Testing forward pricing (covered interest parity)...\n";

  let spot = 1.10 in
  let domestic_rate = 0.05 in  (* USD 5% *)
  let foreign_rate = 0.03 in   (* EUR 3% *)
  let maturity = 1.0 in        (* 1 year *)

  let forward = Forwards.forward_rate ~spot ~domestic_rate ~foreign_rate ~maturity in

  Printf.printf "  Spot: %.4f\n" spot;
  Printf.printf "  Forward (1y): %.4f\n" forward;
  Printf.printf "  Forward Points: %.6f\n" (forward -. spot);

  (* Check CIP *)
  let cip_holds = Forwards.check_covered_interest_parity
    ~spot ~forward ~domestic_rate ~foreign_rate ~maturity ~tolerance:0.0001
  in

  if cip_holds then
    Printf.printf "  ✓ Covered interest parity holds\n"
  else
    Printf.printf "  ✗ Covered interest parity violated!\n";

  Printf.printf "\n"

let test_futures () =
  Printf.printf "Testing futures pricing and basis...\n";

  let spot = 1.10 in
  let futures_price = 1.1222 in
  let domestic_rate = 0.05 in
  let foreign_rate = 0.03 in
  let maturity = 1.0 in

  let theoretical_futures = Futures.futures_price ~spot ~domestic_rate ~foreign_rate ~maturity in
  let basis = Futures.basis ~futures_price ~spot_price:spot in

  Printf.printf "  Spot: %.4f\n" spot;
  Printf.printf "  Futures (market): %.4f\n" futures_price;
  Printf.printf "  Futures (theoretical): %.4f\n" theoretical_futures;
  Printf.printf "  Basis: %.6f\n" basis;

  if Futures.is_contango ~futures_price ~spot_price:spot then
    Printf.printf "  ✓ Market is in contango\n"
  else
    Printf.printf "  ✓ Market is in backwardation\n";

  Printf.printf "\n"

let test_black_model () =
  Printf.printf "Testing Black-76 model for futures options...\n";

  let futures_price = 1.10 in
  let strike = 1.10 in  (* ATM *)
  let expiry = 90.0 /. 365.0 in
  let rate = 0.05 in
  let volatility = 0.12 in

  let call_price = Futures_options.black_price
    ~option_type:Types.Call
    ~futures_price
    ~strike
    ~expiry
    ~rate
    ~volatility
  in

  let put_price = Futures_options.black_price
    ~option_type:Types.Put
    ~futures_price
    ~strike
    ~expiry
    ~rate
    ~volatility
  in

  Printf.printf "  ATM Call (F=%.2f, K=%.2f, T=90d, σ=12%%): $%.6f\n" futures_price strike call_price;
  Printf.printf "  ATM Put (F=%.2f, K=%.2f, T=90d, σ=12%%): $%.6f\n" futures_price strike put_price;

  (* Greeks *)
  let greeks = Futures_options.black_greeks
    ~option_type:Types.Call
    ~futures_price
    ~strike
    ~expiry
    ~rate
    ~volatility
  in

  Printf.printf "  Delta: %.4f\n" greeks.delta;
  Printf.printf "  Gamma: %.6f\n" greeks.gamma;
  Printf.printf "  Theta: %.4f (per day)\n" greeks.theta;
  Printf.printf "  Vega: %.4f (per 1%% vol)\n" greeks.vega;

  if greeks.delta > 0.0 && greeks.delta < 1.0 then
    Printf.printf "  ✓ Delta in valid range for ATM call\n"
  else
    Printf.printf "  ✗ Delta out of range!\n";

  if greeks.gamma > 0.0 then
    Printf.printf "  ✓ Gamma positive (long option)\n"
  else
    Printf.printf "  ✗ Gamma should be positive!\n";

  if greeks.theta < 0.0 then
    Printf.printf "  ✓ Theta negative (time decay)\n"
  else
    Printf.printf "  ✗ Theta should be negative!\n";

  Printf.printf "\n"

let test_optimization () =
  Printf.printf "Testing hedge ratio optimization...\n";

  (* Simulated returns *)
  let exposure_returns = [| 0.01; -0.02; 0.015; -0.01; 0.02 |] in
  let futures_returns = [| -0.01; 0.02; -0.015; 0.01; -0.02 |] in

  let h_min_var = Optimization.min_variance_hedge_ratio ~exposure_returns ~futures_returns in
  let correlation = Optimization.correlation ~series1:exposure_returns ~series2:futures_returns in

  Printf.printf "  Minimum variance hedge ratio: %.4f\n" h_min_var;
  Printf.printf "  Correlation: %.4f\n" correlation;

  if abs_float (h_min_var +. 1.0) < 0.3 then
    Printf.printf "  ✓ Hedge ratio reasonable (near -1.0 for perfect negative correlation)\n"
  else
    Printf.printf "  ⚠ Hedge ratio = %.4f (expected near -1.0 for typical FX hedge)\n" h_min_var;

  Printf.printf "\n"

let () =
  Printf.printf "\n=== FX Hedging Tests ===\n\n";
  test_forwards ();
  test_futures ();
  test_black_model ();
  test_optimization ();
  Printf.printf "=== Tests Complete ===\n"
