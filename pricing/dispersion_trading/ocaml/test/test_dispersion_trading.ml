(** Unit tests for dispersion trading model *)

open Dispersion_trading_lib

(* ========== Helper: make option contract ========== *)

let make_option ?(ticker="TEST") ?(option_type=Types.Call)
    ?(strike=100.0) ?(expiry=30.0) ?(spot=100.0) ?(implied_vol=0.20)
    ?(price=5.0) ?(delta=0.5) ?(gamma=0.02) ?(vega=0.15) ?(theta= -0.05) ()
    : Types.option_contract =
  { ticker; option_type; strike; expiry; spot; implied_vol; price;
    delta; gamma; vega; theta }

(* ========== Correlation Tests ========== *)

let test_mean () =
  let m = Correlation.mean [| 10.0; 20.0; 30.0 |] in
  Alcotest.(check (float 0.01)) "mean = 20" 20.0 m

let test_mean_empty () =
  let m = Correlation.mean [||] in
  Alcotest.(check (float 0.01)) "empty mean = 0" 0.0 m

let test_std () =
  (* Sample std of [10,20,30]: mean=20, var=(100+0+100)/2=100, std=10 *)
  let s = Correlation.std [| 10.0; 20.0; 30.0 |] in
  Alcotest.(check (float 0.01)) "std = 10" 10.0 s

let test_std_insufficient () =
  let s = Correlation.std [| 5.0 |] in
  Alcotest.(check (float 0.01)) "single element std = 0" 0.0 s

let test_returns () =
  let r = Correlation.returns [| 100.0; 110.0; 99.0 |] in
  Alcotest.(check int) "two returns" 2 (Array.length r);
  (* (110-100)/100 = 0.10 *)
  Alcotest.(check (float 0.001)) "first return" 0.10 r.(0);
  (* (99-110)/110 = -0.10 *)
  Alcotest.(check (float 0.001)) "second return" (-0.10) r.(1)

let test_returns_single () =
  let r = Correlation.returns [| 100.0 |] in
  Alcotest.(check int) "single price = no returns" 0 (Array.length r)

let test_covariance () =
  let x = [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  let y = [| 2.0; 4.0; 6.0; 8.0; 10.0 |] in
  let cov = Correlation.covariance x y in
  (* Perfect positive linear: cov = 2 * var(x) = 2 * 2.5 = 5.0 *)
  Alcotest.(check (float 0.01)) "covariance" 5.0 cov

let test_correlation_perfect () =
  let x = [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  let y = [| 2.0; 4.0; 6.0; 8.0; 10.0 |] in
  let corr = Correlation.correlation x y in
  Alcotest.(check (float 0.01)) "perfect correlation" 1.0 corr

let test_correlation_negative () =
  let x = [| 1.0; 2.0; 3.0; 4.0; 5.0 |] in
  let y = [| 10.0; 8.0; 6.0; 4.0; 2.0 |] in
  let corr = Correlation.correlation x y in
  Alcotest.(check (float 0.01)) "negative correlation" (-1.0) corr

let test_correlation_zero_std () =
  let x = [| 5.0; 5.0; 5.0 |] in
  let y = [| 1.0; 2.0; 3.0 |] in
  let corr = Correlation.correlation x y in
  Alcotest.(check (float 0.01)) "zero std = 0 corr" 0.0 corr

let test_correlation_matrix_diagonal () =
  let returns = [| [| 0.01; -0.02; 0.03 |]; [| 0.02; -0.01; 0.02 |] |] in
  let m = Correlation.correlation_matrix returns in
  Alcotest.(check (float 0.001)) "diagonal = 1" 1.0 m.(0).(0);
  Alcotest.(check (float 0.001)) "diagonal = 1" 1.0 m.(1).(1)

let test_correlation_matrix_symmetric () =
  let returns = [| [| 0.01; -0.02; 0.03 |]; [| 0.02; -0.01; 0.02 |] |] in
  let m = Correlation.correlation_matrix returns in
  Alcotest.(check (float 0.001)) "symmetric" m.(0).(1) m.(1).(0)

let test_avg_pairwise_correlation () =
  let m = [| [| 1.0; 0.5; 0.3 |]; [| 0.5; 1.0; 0.7 |]; [| 0.3; 0.7; 1.0 |] |] in
  let avg = Correlation.avg_pairwise_correlation m in
  (* (0.5 + 0.3 + 0.7) / 3 = 0.5 *)
  Alcotest.(check (float 0.01)) "avg pairwise = 0.5" 0.5 avg

let test_avg_pairwise_single () =
  let m = [| [| 1.0 |] |] in
  let avg = Correlation.avg_pairwise_correlation m in
  Alcotest.(check (float 0.01)) "single = 0" 0.0 avg

let test_implied_correlation () =
  let index_vol = 0.15 in
  let constituent_vols = [| 0.25; 0.30; 0.20 |] in
  let weights = [| 0.40; 0.35; 0.25 |] in
  let ic = Correlation.implied_correlation ~index_vol ~constituent_vols ~weights in
  (* Should be between -1 and 1 *)
  Alcotest.(check bool) "implied corr in range" true (ic >= -1.0 && ic <= 1.0)

let test_implied_correlation_high_index_vol () =
  (* When index vol equals weighted avg vol, correlation ~ 1 *)
  let vols = [| 0.20; 0.20 |] in
  let weights = [| 0.50; 0.50 |] in
  (* σ_index = √(Σw²σ² + 2ρΣwwσσ). If ρ=1, σ_index = Σwσ = 0.20 *)
  let ic = Correlation.implied_correlation ~index_vol:0.20 ~constituent_vols:vols ~weights in
  Alcotest.(check (float 0.01)) "equal vols → corr ~ 1" 1.0 ic

(* ========== Dispersion Tests ========== *)

let test_weighted_avg_iv () =
  let vols = [| 0.25; 0.30; 0.20 |] in
  let weights = [| 0.40; 0.35; 0.25 |] in
  (* 0.25*0.40 + 0.30*0.35 + 0.20*0.25 = 0.10 + 0.105 + 0.05 = 0.255 *)
  let avg = Dispersion.weighted_avg_iv ~constituent_vols:vols ~weights in
  Alcotest.(check (float 0.001)) "weighted avg iv" 0.255 avg

let test_dispersion_level () =
  let vols = [| 0.25; 0.30; 0.20 |] in
  let weights = [| 0.40; 0.35; 0.25 |] in
  let disp = Dispersion.dispersion_level ~index_iv:0.15 ~constituent_vols:vols ~weights in
  (* 0.255 - 0.15 = 0.105 *)
  Alcotest.(check (float 0.001)) "dispersion level" 0.105 disp

let test_dispersion_zscore () =
  let current = 0.10 in
  let historical = [| 0.05; 0.06; 0.07; 0.08; 0.09 |] in
  (* mean = 0.07, std = sample std *)
  let z = Dispersion.dispersion_zscore ~current_dispersion:current
    ~historical_dispersion:historical in
  Alcotest.(check bool) "z-score positive" true (z > 0.0)

let test_dispersion_zscore_zero_std () =
  (* Use exact floats to avoid IEEE 754 precision issues *)
  let z = Dispersion.dispersion_zscore ~current_dispersion:1.0
    ~historical_dispersion:[| 1.0; 1.0; 1.0 |] in
  Alcotest.(check (float 0.01)) "zero std = 0 zscore" 0.0 z

let test_signal_long () =
  (* Z-score > 1.5 → LONG. Use varied historical so std is well-defined *)
  let historical = [| 0.04; 0.05; 0.06; 0.05; 0.04 |] in
  let metrics = Dispersion.calculate_dispersion_metrics
    ~index_iv:0.15
    ~constituent_vols:[| 0.40; 0.40 |]
    ~weights:[| 0.50; 0.50 |]
    ~historical_dispersion:historical
    ~implied_corr:0.3 in
  (* dispersion = 0.40 - 0.15 = 0.25, way above historical mean ~0.048 *)
  Alcotest.(check string) "long signal" "LONG" metrics.signal

let test_signal_short () =
  (* Z-score < -1.5 → SHORT. Use varied historical so std is well-defined *)
  let historical = [| 0.18; 0.20; 0.22; 0.20; 0.19 |] in
  let metrics = Dispersion.calculate_dispersion_metrics
    ~index_iv:0.15
    ~constituent_vols:[| 0.10; 0.10 |]
    ~weights:[| 0.50; 0.50 |]
    ~historical_dispersion:historical
    ~implied_corr:0.8 in
  (* dispersion = 0.10 - 0.15 = -0.05, way below historical mean ~0.198 *)
  Alcotest.(check string) "short signal" "SHORT" metrics.signal

let test_signal_neutral () =
  (* Z-score near 0 → NEUTRAL *)
  let historical = [| 0.10; 0.10; 0.10; 0.10; 0.10 |] in
  let metrics = Dispersion.calculate_dispersion_metrics
    ~index_iv:0.15
    ~constituent_vols:[| 0.25; 0.25 |]
    ~weights:[| 0.50; 0.50 |]
    ~historical_dispersion:historical
    ~implied_corr:0.5 in
  (* dispersion = 0.25 - 0.15 = 0.10, equal to historical mean *)
  Alcotest.(check string) "neutral signal" "NEUTRAL" metrics.signal

(* ========== Position Tests ========== *)

let test_position_delta_long () =
  let index_opt = make_option ~delta:0.50 ~price:5.0 () in
  let sn1_opt = make_option ~delta:0.60 ~price:3.0 () in
  let sn2_opt = make_option ~delta:0.55 ~price:4.0 () in
  let pos = Dispersion.build_dispersion_position
    ~position_type:LongDispersion
    ~index:(Dispersion.build_index_position ~ticker:"SPY" ~spot:450.0 ~option:index_opt ~notional:1.0)
    ~single_names:[|
      Dispersion.build_single_name ~ticker:"AAPL" ~weight:0.5 ~spot:180.0 ~option:sn1_opt ~notional:1.0;
      Dispersion.build_single_name ~ticker:"MSFT" ~weight:0.5 ~spot:400.0 ~option:sn2_opt ~notional:1.0;
    |]
    ~entry_date:0.0 ~expiry_date:30.0 in
  let delta = Dispersion.position_delta pos in
  (* Long: single_delta - index_delta = (0.60 + 0.55) - 0.50 = 0.65 *)
  Alcotest.(check (float 0.001)) "long delta" 0.65 delta

let test_position_delta_short () =
  let index_opt = make_option ~delta:0.50 ~price:5.0 () in
  let sn1_opt = make_option ~delta:0.60 ~price:3.0 () in
  let pos = Dispersion.build_dispersion_position
    ~position_type:ShortDispersion
    ~index:(Dispersion.build_index_position ~ticker:"SPY" ~spot:450.0 ~option:index_opt ~notional:1.0)
    ~single_names:[|
      Dispersion.build_single_name ~ticker:"AAPL" ~weight:1.0 ~spot:180.0 ~option:sn1_opt ~notional:1.0;
    |]
    ~entry_date:0.0 ~expiry_date:30.0 in
  let delta = Dispersion.position_delta pos in
  (* Short: index_delta - single_delta = 0.50 - 0.60 = -0.10 *)
  Alcotest.(check (float 0.001)) "short delta" (-0.10) delta

let test_position_vega_long () =
  let index_opt = make_option ~vega:0.20 () in
  let sn1_opt = make_option ~vega:0.15 () in
  let sn2_opt = make_option ~vega:0.10 () in
  let pos = Dispersion.build_dispersion_position
    ~position_type:LongDispersion
    ~index:(Dispersion.build_index_position ~ticker:"SPY" ~spot:450.0 ~option:index_opt ~notional:1.0)
    ~single_names:[|
      Dispersion.build_single_name ~ticker:"AAPL" ~weight:0.5 ~spot:180.0 ~option:sn1_opt ~notional:1.0;
      Dispersion.build_single_name ~ticker:"MSFT" ~weight:0.5 ~spot:400.0 ~option:sn2_opt ~notional:1.0;
    |]
    ~entry_date:0.0 ~expiry_date:30.0 in
  let vega = Dispersion.position_vega pos in
  (* Long: single_vega - index_vega = (0.15 + 0.10) - 0.20 = 0.05 *)
  Alcotest.(check (float 0.001)) "long vega" 0.05 vega

let test_position_pnl_long () =
  let index_opt = make_option ~price:5.0 () in
  let sn1_opt = make_option ~price:3.0 () in
  let pos = Dispersion.build_dispersion_position
    ~position_type:LongDispersion
    ~index:(Dispersion.build_index_position ~ticker:"SPY" ~spot:450.0 ~option:index_opt ~notional:1.0)
    ~single_names:[|
      Dispersion.build_single_name ~ticker:"AAPL" ~weight:1.0 ~spot:180.0 ~option:sn1_opt ~notional:1.0;
    |]
    ~entry_date:0.0 ~expiry_date:30.0 in
  (* Single name option goes from 3 to 5 (+2), index goes from 5 to 6 (+1) *)
  let pnl = Dispersion.position_pnl ~position:pos
    ~new_index_price:6.0 ~new_single_prices:[| 5.0 |]
    ~new_index_iv:0.18 ~new_single_ivs:[| 0.22 |] in
  (* Long: single_pnl - index_pnl = 2*1 - 1*1 = 1.0 *)
  Alcotest.(check (float 0.001)) "long pnl" 1.0 pnl

let test_position_pnl_short () =
  let index_opt = make_option ~price:5.0 () in
  let sn1_opt = make_option ~price:3.0 () in
  let pos = Dispersion.build_dispersion_position
    ~position_type:ShortDispersion
    ~index:(Dispersion.build_index_position ~ticker:"SPY" ~spot:450.0 ~option:index_opt ~notional:1.0)
    ~single_names:[|
      Dispersion.build_single_name ~ticker:"AAPL" ~weight:1.0 ~spot:180.0 ~option:sn1_opt ~notional:1.0;
    |]
    ~entry_date:0.0 ~expiry_date:30.0 in
  let pnl = Dispersion.position_pnl ~position:pos
    ~new_index_price:6.0 ~new_single_prices:[| 5.0 |]
    ~new_index_iv:0.18 ~new_single_ivs:[| 0.22 |] in
  (* Short: index_pnl - single_pnl = 1 - 2 = -1.0 *)
  Alcotest.(check (float 0.001)) "short pnl" (-1.0) pnl

(* ========== Types Tests ========== *)

let test_option_type_to_string () =
  Alcotest.(check string) "call" "Call" (Types.option_type_to_string Call);
  Alcotest.(check string) "put" "Put" (Types.option_type_to_string Put)

let test_option_type_of_string () =
  Alcotest.(check bool) "parse call" true (Types.option_type_of_string "Call" = Call);
  Alcotest.(check bool) "parse put" true (Types.option_type_of_string "put" = Put);
  Alcotest.(check bool) "parse C" true (Types.option_type_of_string "C" = Call)

let test_dispersion_type_to_string () =
  Alcotest.(check string) "long" "Long" (Types.dispersion_type_to_string LongDispersion);
  Alcotest.(check string) "short" "Short" (Types.dispersion_type_to_string ShortDispersion)

(* ========== Test Suite ========== *)

let () =
  Alcotest.run "Dispersion Trading Tests" [
    "correlation", [
      Alcotest.test_case "Mean" `Quick test_mean;
      Alcotest.test_case "Mean empty" `Quick test_mean_empty;
      Alcotest.test_case "Std" `Quick test_std;
      Alcotest.test_case "Std insufficient" `Quick test_std_insufficient;
      Alcotest.test_case "Returns" `Quick test_returns;
      Alcotest.test_case "Returns single" `Quick test_returns_single;
      Alcotest.test_case "Covariance" `Quick test_covariance;
      Alcotest.test_case "Perfect correlation" `Quick test_correlation_perfect;
      Alcotest.test_case "Negative correlation" `Quick test_correlation_negative;
      Alcotest.test_case "Zero std correlation" `Quick test_correlation_zero_std;
      Alcotest.test_case "Correlation matrix diagonal" `Quick test_correlation_matrix_diagonal;
      Alcotest.test_case "Correlation matrix symmetric" `Quick test_correlation_matrix_symmetric;
      Alcotest.test_case "Avg pairwise correlation" `Quick test_avg_pairwise_correlation;
      Alcotest.test_case "Avg pairwise single" `Quick test_avg_pairwise_single;
      Alcotest.test_case "Implied correlation range" `Quick test_implied_correlation;
      Alcotest.test_case "Implied correlation equal vols" `Quick test_implied_correlation_high_index_vol;
    ];
    "dispersion", [
      Alcotest.test_case "Weighted avg IV" `Quick test_weighted_avg_iv;
      Alcotest.test_case "Dispersion level" `Quick test_dispersion_level;
      Alcotest.test_case "Z-score positive" `Quick test_dispersion_zscore;
      Alcotest.test_case "Z-score zero std" `Quick test_dispersion_zscore_zero_std;
      Alcotest.test_case "Signal LONG" `Quick test_signal_long;
      Alcotest.test_case "Signal SHORT" `Quick test_signal_short;
      Alcotest.test_case "Signal NEUTRAL" `Quick test_signal_neutral;
    ];
    "positions", [
      Alcotest.test_case "Long delta" `Quick test_position_delta_long;
      Alcotest.test_case "Short delta" `Quick test_position_delta_short;
      Alcotest.test_case "Long vega" `Quick test_position_vega_long;
      Alcotest.test_case "Long P&L" `Quick test_position_pnl_long;
      Alcotest.test_case "Short P&L" `Quick test_position_pnl_short;
    ];
    "types", [
      Alcotest.test_case "Option type to string" `Quick test_option_type_to_string;
      Alcotest.test_case "Option type of string" `Quick test_option_type_of_string;
      Alcotest.test_case "Dispersion type to string" `Quick test_dispersion_type_to_string;
    ];
  ]
