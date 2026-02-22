open Pre_earnings_straddle_lib
open Types

let float_eq ~eps = Alcotest.testable
  (fun fmt f -> Format.fprintf fmt "%.6f" f)
  (fun a b -> Float.abs (a -. b) < eps)

(* ── Test data ── *)

let history = [|
  { ticker = "TEST"; date = "2025-01-01"; implied_move = 0.05; realized_move = 0.06 };
  { ticker = "TEST"; date = "2025-04-01"; implied_move = 0.04; realized_move = 0.03 };
  { ticker = "TEST"; date = "2025-07-01"; implied_move = 0.06; realized_move = 0.08 };
  { ticker = "TEST"; date = "2025-10-01"; implied_move = 0.05; realized_move = 0.04 };
|]

let sample_opp = {
  ticker = "TEST"; earnings_date = "2026-02-01"; days_to_earnings = 14;
  spot_price = 100.0; atm_strike = 100.0;
  atm_call_price = 4.0; atm_put_price = 3.5;
  straddle_cost = 7.5; current_implied_move = 0.045;
  expiration = "2026-02-20"; days_to_expiry = 33;
}

(* ── Signals Tests ── *)

let test_calculate_signals () =
  let result = Signals.calculate_signals
    ~ticker:"TEST" ~current_implied:0.045 ~historical_events:history in
  Alcotest.(check bool) "some signals" true (Option.is_some result);
  let s = Option.get result in
  Alcotest.(check int) "4 events" 4 s.num_historical_events;
  Alcotest.(check (float_eq ~eps:0.001)) "current" 0.045 s.current_implied

let test_signals_last_values () =
  let s = Option.get (Signals.calculate_signals
    ~ticker:"TEST" ~current_implied:0.045 ~historical_events:history) in
  (* Last event: implied=0.05, realized=0.04 *)
  Alcotest.(check (float_eq ~eps:0.001)) "last implied" 0.05 s.last_implied;
  Alcotest.(check (float_eq ~eps:0.001)) "last realized" 0.04 s.last_realized

let test_signals_averages () =
  let s = Option.get (Signals.calculate_signals
    ~ticker:"TEST" ~current_implied:0.045 ~historical_events:history) in
  (* avg_implied = (0.05+0.04+0.06+0.05)/4 = 0.20/4 = 0.05 *)
  Alcotest.(check (float_eq ~eps:0.001)) "avg implied" 0.05 s.avg_implied;
  (* avg_realized = (0.06+0.03+0.08+0.04)/4 = 0.21/4 = 0.0525 *)
  Alcotest.(check (float_eq ~eps:0.001)) "avg realized" 0.0525 s.avg_realized

let test_signal_1_ratio () =
  let s = Option.get (Signals.calculate_signals
    ~ticker:"TEST" ~current_implied:0.045 ~historical_events:history) in
  (* current/last_implied = 0.045/0.05 = 0.90 *)
  Alcotest.(check (float_eq ~eps:0.001)) "signal 1" 0.90 s.implied_vs_last_implied_ratio

let test_signal_2_gap () =
  let s = Option.get (Signals.calculate_signals
    ~ticker:"TEST" ~current_implied:0.045 ~historical_events:history) in
  (* current - last_realized = 0.045 - 0.04 = 0.005 *)
  Alcotest.(check (float_eq ~eps:0.001)) "signal 2" 0.005 s.implied_vs_last_realized_gap

let test_signal_3_ratio () =
  let s = Option.get (Signals.calculate_signals
    ~ticker:"TEST" ~current_implied:0.045 ~historical_events:history) in
  (* current/avg_implied = 0.045/0.05 = 0.90 *)
  Alcotest.(check (float_eq ~eps:0.001)) "signal 3" 0.90 s.implied_vs_avg_implied_ratio

let test_signal_4_gap () =
  let s = Option.get (Signals.calculate_signals
    ~ticker:"TEST" ~current_implied:0.045 ~historical_events:history) in
  (* current - avg_realized = 0.045 - 0.0525 = -0.0075 *)
  Alcotest.(check (float_eq ~eps:0.001)) "signal 4" (-0.0075) s.implied_vs_avg_realized_gap

let test_signals_empty_history () =
  let result = Signals.calculate_signals
    ~ticker:"TEST" ~current_implied:0.05 ~historical_events:[||] in
  Alcotest.(check bool) "none" true (Option.is_none result)

let test_signals_zero_last_implied () =
  let h = [| { ticker = "TEST"; date = "2025-01-01"; implied_move = 0.0; realized_move = 0.03 } |] in
  let s = Option.get (Signals.calculate_signals
    ~ticker:"TEST" ~current_implied:0.05 ~historical_events:h) in
  (* last_implied = 0.0, ratio defaults to 1.0 *)
  Alcotest.(check (float_eq ~eps:0.001)) "zero fallback" 1.0 s.implied_vs_last_implied_ratio

(* ── Model Tests ── *)

let make_signals ?(s1 = 1.0) ?(s2 = 0.0) ?(s3 = 1.0) ?(s4 = 0.0) () =
  { ticker = "TEST";
    implied_vs_last_implied_ratio = s1;
    implied_vs_last_realized_gap = s2;
    implied_vs_avg_implied_ratio = s3;
    implied_vs_avg_realized_gap = s4;
    current_implied = 0.05; last_implied = 0.05; last_realized = 0.05;
    avg_implied = 0.05; avg_realized = 0.05; num_historical_events = 10 }

let test_predict_return_default () =
  let sigs = make_signals () in
  let ret = Model.predict_return ~signals:sigs ~coefficients:default_coefficients in
  (* intercept + (-0.05)*1.0 + (-0.04)*0.0 + (-0.06)*1.0 + (-0.05)*0.0 *)
  (* = 0.033 - 0.05 + 0 - 0.06 + 0 = -0.077 *)
  Alcotest.(check (float_eq ~eps:0.001)) "predict" (-0.077) ret

let test_predict_return_cheap () =
  (* All signals favorable: low ratios, negative gaps *)
  let sigs = make_signals ~s1:0.8 ~s2:(-0.02) ~s3:0.8 ~s4:(-0.02) () in
  let ret = Model.predict_return ~signals:sigs ~coefficients:default_coefficients in
  (* 0.033 + (-0.05)*0.8 + (-0.04)*(-0.02) + (-0.06)*0.8 + (-0.05)*(-0.02) *)
  (* = 0.033 - 0.04 + 0.0008 - 0.048 + 0.001 = -0.0532 *)
  Alcotest.(check (float_eq ~eps:0.001)) "cheap" (-0.0532) ret

let test_predict_return_linear () =
  (* With zero coefficients, should just be intercept *)
  let zero_coefs = {
    intercept = 0.05;
    coef_implied_vs_last_implied = 0.0;
    coef_implied_vs_last_realized = 0.0;
    coef_implied_vs_avg_implied = 0.0;
    coef_implied_vs_avg_realized = 0.0;
  } in
  let sigs = make_signals ~s1:0.8 ~s2:(-0.02) ~s3:0.8 ~s4:(-0.02) () in
  let ret = Model.predict_return ~signals:sigs ~coefficients:zero_coefs in
  Alcotest.(check (float_eq ~eps:0.001)) "intercept only" 0.05 ret

let test_kelly_positive () =
  let k = Model.calculate_kelly ~predicted_return:0.05 ~max_loss:7.5 in
  Alcotest.(check bool) "non-negative" true (k >= 0.0);
  Alcotest.(check bool) "max 10%" true (k <= 0.10)

let test_kelly_zero_return () =
  let k = Model.calculate_kelly ~predicted_return:0.0 ~max_loss:7.5 in
  Alcotest.(check (float_eq ~eps:0.001)) "zero return = 0" 0.0 k

let test_kelly_negative_return () =
  let k = Model.calculate_kelly ~predicted_return:(-0.05) ~max_loss:7.5 in
  Alcotest.(check (float_eq ~eps:0.001)) "negative return = 0" 0.0 k

let test_kelly_capped () =
  let k = Model.calculate_kelly ~predicted_return:1.0 ~max_loss:7.5 in
  Alcotest.(check bool) "capped at 10%" true (k <= 0.10)

let test_default_coefficients () =
  Alcotest.(check (float_eq ~eps:0.001)) "intercept" 0.033 default_coefficients.intercept;
  Alcotest.(check (float_eq ~eps:0.001)) "coef1" (-0.05) default_coefficients.coef_implied_vs_last_implied;
  Alcotest.(check (float_eq ~eps:0.001)) "coef2" (-0.04) default_coefficients.coef_implied_vs_last_realized;
  Alcotest.(check (float_eq ~eps:0.001)) "coef3" (-0.06) default_coefficients.coef_implied_vs_avg_implied;
  Alcotest.(check (float_eq ~eps:0.001)) "coef4" (-0.05) default_coefficients.coef_implied_vs_avg_realized

(* ── Scanner Tests ── *)

let test_recommendation_strong_buy () =
  (* Need predicted_return >= 0.05 → "Strong Buy" *)
  let high_coefs = {
    intercept = 0.10;
    coef_implied_vs_last_implied = 0.0;
    coef_implied_vs_last_realized = 0.0;
    coef_implied_vs_avg_implied = 0.0;
    coef_implied_vs_avg_realized = 0.0;
  } in
  let sigs = make_signals () in
  let rec_opt = Scanner.make_recommendation
    ~opportunity:sample_opp ~signals:sigs ~coefficients:high_coefs
    ~min_predicted_return:0.0 ~target_kelly_fraction:0.04 in
  Alcotest.(check bool) "some" true (Option.is_some rec_opt);
  let r = Option.get rec_opt in
  Alcotest.(check string) "strong buy" "Strong Buy" r.recommendation;
  Alcotest.(check (float_eq ~eps:0.001)) "predicted 10%" 0.10 r.predicted_return

let test_recommendation_buy () =
  let med_coefs = {
    intercept = 0.03;
    coef_implied_vs_last_implied = 0.0;
    coef_implied_vs_last_realized = 0.0;
    coef_implied_vs_avg_implied = 0.0;
    coef_implied_vs_avg_realized = 0.0;
  } in
  let sigs = make_signals () in
  let r = Option.get (Scanner.make_recommendation
    ~opportunity:sample_opp ~signals:sigs ~coefficients:med_coefs
    ~min_predicted_return:0.0 ~target_kelly_fraction:0.04) in
  Alcotest.(check string) "buy" "Buy" r.recommendation

let test_recommendation_pass () =
  let low_coefs = {
    intercept = 0.01;
    coef_implied_vs_last_implied = 0.0;
    coef_implied_vs_last_realized = 0.0;
    coef_implied_vs_avg_implied = 0.0;
    coef_implied_vs_avg_realized = 0.0;
  } in
  let sigs = make_signals () in
  let r = Option.get (Scanner.make_recommendation
    ~opportunity:sample_opp ~signals:sigs ~coefficients:low_coefs
    ~min_predicted_return:0.0 ~target_kelly_fraction:0.04) in
  Alcotest.(check string) "pass" "Pass" r.recommendation

let test_recommendation_filtered () =
  let neg_coefs = {
    intercept = -0.05;
    coef_implied_vs_last_implied = 0.0;
    coef_implied_vs_last_realized = 0.0;
    coef_implied_vs_avg_implied = 0.0;
    coef_implied_vs_avg_realized = 0.0;
  } in
  let sigs = make_signals () in
  let rec_opt = Scanner.make_recommendation
    ~opportunity:sample_opp ~signals:sigs ~coefficients:neg_coefs
    ~min_predicted_return:0.0 ~target_kelly_fraction:0.04 in
  Alcotest.(check bool) "filtered out" true (Option.is_none rec_opt)

let test_recommendation_max_loss () =
  let high_coefs = {
    intercept = 0.10; coef_implied_vs_last_implied = 0.0;
    coef_implied_vs_last_realized = 0.0; coef_implied_vs_avg_implied = 0.0;
    coef_implied_vs_avg_realized = 0.0;
  } in
  let sigs = make_signals () in
  let r = Option.get (Scanner.make_recommendation
    ~opportunity:sample_opp ~signals:sigs ~coefficients:high_coefs
    ~min_predicted_return:0.0 ~target_kelly_fraction:0.04) in
  Alcotest.(check (float_eq ~eps:0.01)) "max loss = cost" 7.5 r.max_loss

let test_recommendation_notes_limited () =
  let high_coefs = {
    intercept = 0.10; coef_implied_vs_last_implied = 0.0;
    coef_implied_vs_last_realized = 0.0; coef_implied_vs_avg_implied = 0.0;
    coef_implied_vs_avg_realized = 0.0;
  } in
  (* Create signals with limited history *)
  let sigs = { (make_signals ()) with num_historical_events = 2 } in
  let r = Option.get (Scanner.make_recommendation
    ~opportunity:sample_opp ~signals:sigs ~coefficients:high_coefs
    ~min_predicted_return:0.0 ~target_kelly_fraction:0.04) in
  Alcotest.(check bool) "has limited note" true
    (String.length r.notes > 0 && r.notes <> "Signals look good")

let test_recommendation_notes_cheap () =
  let high_coefs = {
    intercept = 0.10; coef_implied_vs_last_implied = 0.0;
    coef_implied_vs_last_realized = 0.0; coef_implied_vs_avg_implied = 0.0;
    coef_implied_vs_avg_realized = 0.0;
  } in
  (* Very cheap: implied_vs_avg_implied_ratio < 0.8 *)
  let sigs = { (make_signals ~s3:0.7 ()) with num_historical_events = 10 } in
  let r = Option.get (Scanner.make_recommendation
    ~opportunity:sample_opp ~signals:sigs ~coefficients:high_coefs
    ~min_predicted_return:0.0 ~target_kelly_fraction:0.04) in
  Alcotest.(check bool) "cheap note" true
    (String.sub r.notes 0 (min 4 (String.length r.notes)) = "Very")

let () =
  Alcotest.run "Pre-Earnings Straddle Tests" [
    ("signals", [
      Alcotest.test_case "Calculate signals" `Quick test_calculate_signals;
      Alcotest.test_case "Last values" `Quick test_signals_last_values;
      Alcotest.test_case "Averages" `Quick test_signals_averages;
      Alcotest.test_case "Signal 1 ratio" `Quick test_signal_1_ratio;
      Alcotest.test_case "Signal 2 gap" `Quick test_signal_2_gap;
      Alcotest.test_case "Signal 3 ratio" `Quick test_signal_3_ratio;
      Alcotest.test_case "Signal 4 gap" `Quick test_signal_4_gap;
      Alcotest.test_case "Empty history" `Quick test_signals_empty_history;
      Alcotest.test_case "Zero last implied" `Quick test_signals_zero_last_implied;
    ]);
    ("model", [
      Alcotest.test_case "Predict default" `Quick test_predict_return_default;
      Alcotest.test_case "Predict cheap" `Quick test_predict_return_cheap;
      Alcotest.test_case "Predict intercept only" `Quick test_predict_return_linear;
      Alcotest.test_case "Kelly positive" `Quick test_kelly_positive;
      Alcotest.test_case "Kelly zero return" `Quick test_kelly_zero_return;
      Alcotest.test_case "Kelly negative return" `Quick test_kelly_negative_return;
      Alcotest.test_case "Kelly capped" `Quick test_kelly_capped;
      Alcotest.test_case "Default coefficients" `Quick test_default_coefficients;
    ]);
    ("scanner", [
      Alcotest.test_case "Strong Buy" `Quick test_recommendation_strong_buy;
      Alcotest.test_case "Buy" `Quick test_recommendation_buy;
      Alcotest.test_case "Pass" `Quick test_recommendation_pass;
      Alcotest.test_case "Filtered out" `Quick test_recommendation_filtered;
      Alcotest.test_case "Max loss" `Quick test_recommendation_max_loss;
      Alcotest.test_case "Notes limited" `Quick test_recommendation_notes_limited;
      Alcotest.test_case "Notes cheap" `Quick test_recommendation_notes_cheap;
    ]);
  ]
