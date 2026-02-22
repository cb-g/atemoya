(* Unit Tests for Skew Verticals *)

open Skew_verticals_lib

let float_eq ~eps a b = Float.abs (a -. b) < eps

let float_t =
  Alcotest.testable (fun fmt v -> Format.fprintf fmt "%.10f" v)
    (float_eq ~eps:0.001)

let float_precise =
  Alcotest.testable (fun fmt v -> Format.fprintf fmt "%.10f" v)
    (float_eq ~eps:0.0001)

(* ── Helper: make option_data ── *)

let mk_opt ~strike ~option_type ~iv ~delta ~mid =
  Types.{ strike; option_type; implied_vol = iv; delta; bid = mid -. 0.05;
          ask = mid +. 0.05; mid_price = mid }

(* ── Skew Tests ── *)

let test_find_option_by_delta () =
  let options = [|
    mk_opt ~strike:90.0  ~option_type:"call" ~iv:0.35 ~delta:0.80 ~mid:12.0;
    mk_opt ~strike:100.0 ~option_type:"call" ~iv:0.30 ~delta:0.50 ~mid:5.0;
    mk_opt ~strike:110.0 ~option_type:"call" ~iv:0.28 ~delta:0.25 ~mid:2.0;
    mk_opt ~strike:120.0 ~option_type:"call" ~iv:0.32 ~delta:0.10 ~mid:0.50;
  |] in
  let result = Skew.find_option_by_delta ~options ~target_delta:0.25 in
  Alcotest.(check bool) "found option" true (Option.is_some result);
  let opt = Option.get result in
  Alcotest.(check (float 0.01)) "strike 110" 110.0 opt.strike

let test_find_option_by_delta_empty () =
  let options = [||] in
  let result = Skew.find_option_by_delta ~options ~target_delta:0.25 in
  Alcotest.(check bool) "empty returns None" true (Option.is_none result)

let test_calculate_call_skew () =
  (* skew = (ATM_IV - 25D_Call_IV) / ATM_IV = (0.30 - 0.28) / 0.30 = 0.06667 *)
  let calls = [|
    mk_opt ~strike:100.0 ~option_type:"call" ~iv:0.30 ~delta:0.50 ~mid:5.0;
    mk_opt ~strike:110.0 ~option_type:"call" ~iv:0.28 ~delta:0.25 ~mid:2.0;
  |] in
  let skew = Skew.calculate_call_skew ~calls ~atm_iv:0.30 in
  Alcotest.(check float_t) "call skew" 0.0667 skew

let test_calculate_put_skew () =
  (* skew = (ATM_IV - 25D_Put_IV) / ATM_IV = (0.30 - 0.35) / 0.30 = -0.1667 *)
  let puts = [|
    mk_opt ~strike:100.0 ~option_type:"put" ~iv:0.30 ~delta:0.50 ~mid:5.0;
    mk_opt ~strike:90.0  ~option_type:"put" ~iv:0.35 ~delta:0.25 ~mid:3.0;
  |] in
  let skew = Skew.calculate_put_skew ~puts ~atm_iv:0.30 in
  Alcotest.(check float_t) "put skew (negative = puts expensive)" (-0.1667) skew

let test_skew_zero_atm_iv () =
  let calls = [| mk_opt ~strike:110.0 ~option_type:"call" ~iv:0.28 ~delta:0.25 ~mid:2.0 |] in
  let skew = Skew.calculate_call_skew ~calls ~atm_iv:0.0 in
  Alcotest.(check (float 0.001)) "zero ATM IV returns 0" 0.0 skew

let test_calculate_zscore () =
  (* history: [0.05; 0.06; 0.04; 0.05; 0.07] mean=0.054, std=0.01140
     current=0.02: z = (0.02 - 0.054) / 0.01140 = -2.983 *)
  let history = [| 0.05; 0.06; 0.04; 0.05; 0.07 |] in
  let z = Skew.calculate_zscore ~current:0.02 ~history in
  Alcotest.(check bool) "z-score is very negative" true (z < -2.0)

let test_zscore_insufficient_data () =
  let history = [| 0.05 |] in
  let z = Skew.calculate_zscore ~current:0.02 ~history in
  Alcotest.(check (float 0.001)) "insufficient data returns 0" 0.0 z

let test_zscore_zero_std () =
  (* Use exactly representable values so variance is truly 0.0 *)
  let history = [| 0.0; 0.0; 0.0 |] in
  let z = Skew.calculate_zscore ~current:1.0 ~history in
  Alcotest.(check (float 0.001)) "zero std returns 0" 0.0 z

let test_compute_skew_metrics () =
  let calls = [|
    mk_opt ~strike:100.0 ~option_type:"call" ~iv:0.30 ~delta:0.50 ~mid:5.0;
    mk_opt ~strike:110.0 ~option_type:"call" ~iv:0.28 ~delta:0.25 ~mid:2.0;
  |] in
  let puts = [|
    mk_opt ~strike:100.0 ~option_type:"put" ~iv:0.30 ~delta:0.50 ~mid:5.0;
    mk_opt ~strike:90.0  ~option_type:"put" ~iv:0.35 ~delta:0.25 ~mid:3.0;
  |] in
  let metrics = Skew.compute_skew_metrics
    ~ticker:"TEST" ~calls ~puts ~atm_iv:0.30
    ~realized_vol:0.25 ~call_skew_history:[||] ~put_skew_history:[||] in
  Alcotest.(check string) "ticker" "TEST" metrics.ticker;
  Alcotest.(check float_t) "atm_iv" 0.30 metrics.atm_iv;
  Alcotest.(check float_t) "vrp = atm_iv - rv" 0.05 metrics.vrp;
  Alcotest.(check float_t) "25d call iv" 0.28 metrics.atm_call_25delta_iv;
  Alcotest.(check float_t) "25d put iv" 0.35 metrics.atm_put_25delta_iv

(* ── Momentum Tests ── *)

let test_calculate_returns () =
  (* Need >= 63 data points *)
  let prices = Array.init 100 (fun i ->
    let date = Printf.sprintf "2025-%03d" (i + 1) in
    let price = 100.0 *. (1.0 +. 0.002 *. float_of_int i) in
    (date, price)
  ) in
  let (r1w, r1m, r3m) = Momentum.calculate_returns ~prices in
  Alcotest.(check bool) "1W return > 0" true (r1w > 0.0);
  Alcotest.(check bool) "1M return > 0" true (r1m > 0.0);
  Alcotest.(check bool) "3M return > 0" true (r3m > 0.0);
  Alcotest.(check bool) "3M > 1M > 1W" true (r3m > r1m && r1m > r1w)

let test_calculate_returns_insufficient () =
  let prices = Array.init 10 (fun i -> (string_of_int i, 100.0 +. float_of_int i)) in
  let (r1w, r1m, r3m) = Momentum.calculate_returns ~prices in
  Alcotest.(check (float 0.001)) "1W = 0" 0.0 r1w;
  Alcotest.(check (float 0.001)) "1M = 0" 0.0 r1m;
  Alcotest.(check (float 0.001)) "3M = 0" 0.0 r3m

let test_pct_from_52w_high () =
  (* Last price is 90, 52w high is 100 → -10% *)
  let prices = [|
    ("d1", 100.0); ("d2", 95.0); ("d3", 90.0);
  |] in
  let pct = Momentum.pct_from_52w_high ~prices in
  Alcotest.(check float_t) "10% below high" (-10.0) pct

let test_pct_from_52w_high_at_high () =
  let prices = [| ("d1", 80.0); ("d2", 90.0); ("d3", 100.0) |] in
  let pct = Momentum.pct_from_52w_high ~prices in
  Alcotest.(check (float 0.001)) "at high = 0%" 0.0 pct

let test_calculate_beta () =
  (* Stock moves 2x the market *)
  let n = 30 in
  let market = Array.init n (fun i ->
    (string_of_int i, 100.0 *. (1.0 +. 0.01 *. float_of_int i))
  ) in
  let stock = Array.init n (fun i ->
    (string_of_int i, 100.0 *. (1.0 +. 0.02 *. float_of_int i))
  ) in
  let beta = Momentum.calculate_beta ~stock_prices:stock ~market_prices:market in
  Alcotest.(check bool) "beta > 1" true (beta > 1.0)

let test_calculate_beta_insufficient () =
  let stock = [| ("d1", 100.0); ("d2", 101.0) |] in
  let market = [| ("d1", 100.0); ("d2", 100.5) |] in
  let beta = Momentum.calculate_beta ~stock_prices:stock ~market_prices:market in
  Alcotest.(check (float 0.001)) "default beta = 1" 1.0 beta

let test_calculate_alpha () =
  (* stock return 10%, market return 5%, beta 1.2: alpha = 0.10 - 1.2*0.05 = 0.04 *)
  let alpha = Momentum.calculate_alpha ~stock_return:0.10 ~market_return:0.05 ~beta:1.2 in
  Alcotest.(check float_precise) "alpha" 0.04 alpha

let test_momentum_score_positive () =
  let score = Momentum.calculate_momentum_score
    ~return_1m:0.10 ~return_3m:0.25 ~pct_from_high:(-5.0) ~alpha:0.05 in
  Alcotest.(check bool) "positive momentum" true (score > 0.0);
  Alcotest.(check bool) "clamped <= 1" true (score <= 1.0)

let test_momentum_score_negative () =
  let score = Momentum.calculate_momentum_score
    ~return_1m:(-0.10) ~return_3m:(-0.25) ~pct_from_high:(-30.0) ~alpha:(-0.05) in
  Alcotest.(check bool) "negative momentum" true (score < 0.0);
  Alcotest.(check bool) "clamped >= -1" true (score >= -1.0)

let test_momentum_score_clamped () =
  (* Extreme values should still be in [-1, 1] *)
  let score = Momentum.calculate_momentum_score
    ~return_1m:1.0 ~return_3m:2.0 ~pct_from_high:0.0 ~alpha:1.0 in
  Alcotest.(check bool) "clamped to 1.0" true (score <= 1.0);
  let score2 = Momentum.calculate_momentum_score
    ~return_1m:(-1.0) ~return_3m:(-2.0) ~pct_from_high:(-100.0) ~alpha:(-1.0) in
  Alcotest.(check bool) "clamped to -1.0" true (score2 >= -1.0)

(* ── Spreads Tests ── *)

let test_bull_call_economics () =
  (* Buy 100 call at $5, sell 110 call at $2
     debit = 5 - 2 = 3, max_profit = 10 - 3 = 7, max_loss = 3,
     R/R = 7/3 = 2.333, breakeven = 100 + 3 = 103 *)
  let (debit, max_profit, max_loss, rr, breakeven) =
    Spreads.calculate_spread_economics
      ~long_price:5.0 ~short_price:2.0
      ~long_strike:100.0 ~short_strike:110.0
      ~spread_type:"bull_call" in
  Alcotest.(check float_t) "debit" 3.0 debit;
  Alcotest.(check float_t) "max profit" 7.0 max_profit;
  Alcotest.(check float_t) "max loss" 3.0 max_loss;
  Alcotest.(check float_t) "R/R" 2.333 rr;
  Alcotest.(check float_t) "breakeven" 103.0 breakeven

let test_bear_put_economics () =
  (* Buy 100 put at $5, sell 90 put at $2
     debit = 5 - 2 = 3, max_profit = (100-90) - 3 = 7, max_loss = 3,
     R/R = 7/3 = 2.333, breakeven = 100 - 3 = 97 *)
  let (debit, max_profit, max_loss, rr, breakeven) =
    Spreads.calculate_spread_economics
      ~long_price:5.0 ~short_price:2.0
      ~long_strike:100.0 ~short_strike:90.0
      ~spread_type:"bear_put" in
  Alcotest.(check float_t) "debit" 3.0 debit;
  Alcotest.(check float_t) "max profit" 7.0 max_profit;
  Alcotest.(check float_t) "max loss" 3.0 max_loss;
  Alcotest.(check float_t) "R/R" 2.333 rr;
  Alcotest.(check float_t) "breakeven" 97.0 breakeven

let test_bull_put_economics () =
  (* Credit spread: sell 95 put at $3, buy 90 put at $1
     credit = 3 - 1 = 2, max_profit = 2, max_loss = (95-90) - 2 = 3,
     R/R = 2/3 = 0.667, breakeven = 95 - 2 = 93
     debit = -credit = -2 *)
  let (debit, max_profit, max_loss, rr, breakeven) =
    Spreads.calculate_spread_economics
      ~long_price:1.0 ~short_price:3.0
      ~long_strike:90.0 ~short_strike:95.0
      ~spread_type:"bull_put" in
  Alcotest.(check float_t) "debit (negative = credit)" (-2.0) debit;
  Alcotest.(check float_t) "max profit" 2.0 max_profit;
  Alcotest.(check float_t) "max loss" 3.0 max_loss;
  Alcotest.(check float_t) "R/R" 0.667 rr;
  Alcotest.(check float_t) "breakeven" 93.0 breakeven

let test_bear_call_economics () =
  (* Credit spread: sell 105 call at $3, buy 110 call at $1
     credit = 3 - 1 = 2, max_profit = 2, max_loss = (110-105) - 2 = 3,
     R/R = 2/3 = 0.667, breakeven = 105 + 2 = 107 *)
  let (debit, max_profit, max_loss, rr, breakeven) =
    Spreads.calculate_spread_economics
      ~long_price:1.0 ~short_price:3.0
      ~long_strike:110.0 ~short_strike:105.0
      ~spread_type:"bear_call" in
  Alcotest.(check float_t) "debit (negative = credit)" (-2.0) debit;
  Alcotest.(check float_t) "max profit" 2.0 max_profit;
  Alcotest.(check float_t) "max loss" 3.0 max_loss;
  Alcotest.(check float_t) "R/R" 0.667 rr;
  Alcotest.(check float_t) "breakeven" 107.0 breakeven

let test_unknown_spread_type () =
  let (d, mp, ml, rr, be) =
    Spreads.calculate_spread_economics
      ~long_price:5.0 ~short_price:2.0
      ~long_strike:100.0 ~short_strike:110.0
      ~spread_type:"unknown" in
  Alcotest.(check (float 0.001)) "all zeros" 0.0 (d +. mp +. ml +. rr +. be)

let test_prob_profit_bull_call () =
  (* ATM breakeven: prob should be ~50% *)
  let prob = Spreads.estimate_prob_profit
    ~spot:100.0 ~breakeven:100.0 ~iv:0.30
    ~days_to_expiry:30 ~spread_type:"bull_call" in
  Alcotest.(check bool) "~50% for ATM breakeven" true (prob > 0.4 && prob < 0.6)

let test_prob_profit_bear_put () =
  let prob = Spreads.estimate_prob_profit
    ~spot:100.0 ~breakeven:100.0 ~iv:0.30
    ~days_to_expiry:30 ~spread_type:"bear_put" in
  Alcotest.(check bool) "~50% for ATM breakeven" true (prob > 0.4 && prob < 0.6)

let test_prob_profit_zero_dte () =
  let prob = Spreads.estimate_prob_profit
    ~spot:100.0 ~breakeven:105.0 ~iv:0.30
    ~days_to_expiry:0 ~spread_type:"bull_call" in
  Alcotest.(check (float 0.001)) "zero DTE = 0" 0.0 prob

let test_prob_profit_deep_otm () =
  (* Breakeven far OTM: low probability *)
  let prob = Spreads.estimate_prob_profit
    ~spot:100.0 ~breakeven:130.0 ~iv:0.20
    ~days_to_expiry:30 ~spread_type:"bull_call" in
  Alcotest.(check bool) "deep OTM = low prob" true (prob < 0.15)

(* ── Scanner Tests ── *)

let mk_skew ?(call_z = 0.0) ?(put_z = 0.0) ?(atm_iv = 0.30) ?(rv = 0.25)
    ?(call_25d = 0.28) ?(put_25d = 0.35) () : Types.skew_metrics =
  { ticker = "TEST"; date = "";
    call_skew = (atm_iv -. call_25d) /. atm_iv;
    call_skew_zscore = call_z;
    put_skew = (atm_iv -. put_25d) /. atm_iv;
    put_skew_zscore = put_z;
    atm_iv; atm_call_25delta_iv = call_25d; atm_put_25delta_iv = put_25d;
    realized_vol_30d = rv; vrp = atm_iv -. rv }

let mk_momentum ?(score = 0.5) () : Types.momentum =
  { ticker = "TEST"; return_1w = 0.02; return_1m = 0.05; return_3m = 0.10;
    rank_1m = 1; rank_3m = 1; percentile = 80.0; beta = 1.1;
    alpha_1m = 0.02; pct_from_52w_high = -5.0; momentum_score = score }

let mk_spread ?(spread_type = "bull_call") ?(rr = 5.0)
    ?(ev = 0.50) ?(ev_pct = 25.0) ?(prob = 0.40) () : Types.vertical_spread =
  { ticker = "TEST"; expiration = "2026-03-20"; days_to_expiry = 30;
    spread_type;
    long_strike = 100.0; long_delta = 0.50; long_iv = 0.30; long_price = 5.0;
    short_strike = 110.0; short_delta = 0.25; short_iv = 0.28; short_price = 2.0;
    debit = 3.0; max_profit = 7.0; max_loss = 3.0;
    reward_risk_ratio = rr; breakeven = 103.0;
    prob_profit = prob; expected_value = ev; expected_return_pct = ev_pct }

let test_passes_skew_filter_call () =
  let skew = mk_skew ~call_z:(-2.5) () in
  Alcotest.(check bool) "extreme call skew passes" true
    (Scanner.passes_skew_filter ~skew ~threshold:(-2.0))

let test_passes_skew_filter_put () =
  let skew = mk_skew ~put_z:(-3.0) () in
  Alcotest.(check bool) "extreme put skew passes" true
    (Scanner.passes_skew_filter ~skew ~threshold:(-2.0))

let test_fails_skew_filter () =
  let skew = mk_skew ~call_z:(-1.0) ~put_z:(-0.5) () in
  Alcotest.(check bool) "normal skew fails" false
    (Scanner.passes_skew_filter ~skew ~threshold:(-2.0))

let test_ivrv_filter_bull_call () =
  (* Need vrp > 0 AND otm_iv > rv *)
  let skew = mk_skew ~atm_iv:0.30 ~rv:0.25 ~call_25d:0.28 () in
  Alcotest.(check bool) "bull call: vrp>0 and otm>rv" true
    (Scanner.passes_ivrv_filter ~skew ~spread_type:"bull_call")

let test_ivrv_filter_fails () =
  (* rv > atm_iv → vrp < 0 *)
  let skew = mk_skew ~atm_iv:0.20 ~rv:0.25 () in
  Alcotest.(check bool) "negative vrp fails" false
    (Scanner.passes_ivrv_filter ~skew ~spread_type:"bull_call")

let test_ivrv_filter_credit () =
  (* Credit spreads just need positive VRP *)
  let skew = mk_skew ~atm_iv:0.30 ~rv:0.25 () in
  Alcotest.(check bool) "bull_put: positive vrp passes" true
    (Scanner.passes_ivrv_filter ~skew ~spread_type:"bull_put");
  Alcotest.(check bool) "bear_call: positive vrp passes" true
    (Scanner.passes_ivrv_filter ~skew ~spread_type:"bear_call")

let test_momentum_filter_bull () =
  let mom = mk_momentum ~score:0.5 () in
  Alcotest.(check bool) "positive momentum for bull" true
    (Scanner.passes_momentum_filter ~momentum:mom ~spread_type:"bull_call")

let test_momentum_filter_bear () =
  let mom = mk_momentum ~score:(-0.5) () in
  Alcotest.(check bool) "negative momentum for bear" true
    (Scanner.passes_momentum_filter ~momentum:mom ~spread_type:"bear_put")

let test_momentum_filter_fails () =
  let mom = mk_momentum ~score:0.1 () in
  Alcotest.(check bool) "weak momentum fails bull" false
    (Scanner.passes_momentum_filter ~momentum:mom ~spread_type:"bull_call")

let test_edge_score_bull_call () =
  let skew = mk_skew ~call_z:(-3.0) () in
  let mom = mk_momentum ~score:0.8 () in
  let spread = mk_spread ~rr:7.0 ~ev_pct:30.0 () in
  let score = Scanner.calculate_edge_score ~skew ~momentum:mom ~spread in
  (* skew: min(40, 3.0*10) = 30, momentum: 0.8*20 = 16,
     rr: 7.0 → 25, ev: 30% → 7. Total = 78 *)
  Alcotest.(check float_t) "edge score" 78.0 score

let test_edge_score_capped () =
  let skew = mk_skew ~call_z:(-5.0) () in
  let mom = mk_momentum ~score:1.0 () in
  let spread = mk_spread ~rr:10.0 ~ev_pct:60.0 () in
  let score = Scanner.calculate_edge_score ~skew ~momentum:mom ~spread in
  Alcotest.(check bool) "capped at 100" true (score <= 100.0)

let test_make_recommendation_strong_buy () =
  let chain : Types.options_chain = {
    ticker = "TEST"; spot_price = 100.0; expiration = "2026-03-20";
    days_to_expiry = 30; calls = [||]; puts = [||]; atm_strike = 100.0;
  } in
  let skew = mk_skew ~call_z:(-3.0) () in
  let mom = mk_momentum ~score:0.8 () in
  let spread = mk_spread ~rr:7.0 ~ev_pct:30.0 () in
  let rec_opt = Scanner.make_recommendation
    ~chain ~skew ~momentum:mom ~spread:(Some spread)
    ~skew_threshold:(-2.0) in
  Alcotest.(check bool) "got recommendation" true (Option.is_some rec_opt);
  let r = Option.get rec_opt in
  Alcotest.(check string) "Strong Buy" "Strong Buy" r.recommendation;
  Alcotest.(check bool) "all filters pass" true
    (r.passes_skew_filter && r.passes_ivrv_filter && r.passes_momentum_filter);
  Alcotest.(check string) "notes" "All filters passed" r.notes

let test_make_recommendation_pass () =
  let chain : Types.options_chain = {
    ticker = "TEST"; spot_price = 100.0; expiration = "2026-03-20";
    days_to_expiry = 30; calls = [||]; puts = [||]; atm_strike = 100.0;
  } in
  let skew = mk_skew ~call_z:(-1.0) () in (* fails skew filter *)
  let mom = mk_momentum ~score:0.1 () in  (* fails momentum filter *)
  let spread = mk_spread ~rr:2.0 () in
  let rec_opt = Scanner.make_recommendation
    ~chain ~skew ~momentum:mom ~spread:(Some spread)
    ~skew_threshold:(-2.0) in
  let r = Option.get rec_opt in
  Alcotest.(check string) "Pass" "Pass" r.recommendation

let test_make_recommendation_none () =
  let chain : Types.options_chain = {
    ticker = "TEST"; spot_price = 100.0; expiration = "2026-03-20";
    days_to_expiry = 30; calls = [||]; puts = [||]; atm_strike = 100.0;
  } in
  let skew = mk_skew () in
  let mom = mk_momentum () in
  let rec_opt = Scanner.make_recommendation
    ~chain ~skew ~momentum:mom ~spread:None
    ~skew_threshold:(-2.0) in
  Alcotest.(check bool) "None when no spread" true (Option.is_none rec_opt)

let test_check_trade_quality_clean () =
  let spread = mk_spread ~rr:5.0 () in
  let warnings = Scanner.check_trade_quality spread ~spot:100.0 in
  Alcotest.(check int) "no warnings" 0 (List.length warnings)

let test_check_trade_quality_warnings () =
  let spread = { (mk_spread ~rr:60.0 ()) with
    short_strike = 200.0; short_price = 0.02;
    prob_profit = 0.10; debit = 0.10; expected_return_pct = 600.0 } in
  let warnings = Scanner.check_trade_quality spread ~spot:100.0 in
  Alcotest.(check bool) "multiple warnings" true (List.length warnings >= 4)

(* ── Test Suite ── *)

let () =
  let open Alcotest in
  run "Skew Verticals" [
    "Skew", [
      test_case "Find by delta" `Quick test_find_option_by_delta;
      test_case "Find by delta empty" `Quick test_find_option_by_delta_empty;
      test_case "Call skew" `Quick test_calculate_call_skew;
      test_case "Put skew" `Quick test_calculate_put_skew;
      test_case "Zero ATM IV" `Quick test_skew_zero_atm_iv;
      test_case "Z-score" `Quick test_calculate_zscore;
      test_case "Z-score insufficient" `Quick test_zscore_insufficient_data;
      test_case "Z-score zero std" `Quick test_zscore_zero_std;
      test_case "Compute metrics" `Quick test_compute_skew_metrics;
    ];
    "Momentum", [
      test_case "Calculate returns" `Quick test_calculate_returns;
      test_case "Returns insufficient" `Quick test_calculate_returns_insufficient;
      test_case "Pct from 52w high" `Quick test_pct_from_52w_high;
      test_case "At 52w high" `Quick test_pct_from_52w_high_at_high;
      test_case "Beta" `Quick test_calculate_beta;
      test_case "Beta insufficient" `Quick test_calculate_beta_insufficient;
      test_case "Alpha" `Quick test_calculate_alpha;
      test_case "Score positive" `Quick test_momentum_score_positive;
      test_case "Score negative" `Quick test_momentum_score_negative;
      test_case "Score clamped" `Quick test_momentum_score_clamped;
    ];
    "Spreads", [
      test_case "Bull call" `Quick test_bull_call_economics;
      test_case "Bear put" `Quick test_bear_put_economics;
      test_case "Bull put (credit)" `Quick test_bull_put_economics;
      test_case "Bear call (credit)" `Quick test_bear_call_economics;
      test_case "Unknown type" `Quick test_unknown_spread_type;
      test_case "Prob profit bull" `Quick test_prob_profit_bull_call;
      test_case "Prob profit bear" `Quick test_prob_profit_bear_put;
      test_case "Prob profit 0 DTE" `Quick test_prob_profit_zero_dte;
      test_case "Prob profit deep OTM" `Quick test_prob_profit_deep_otm;
    ];
    "Scanner", [
      test_case "Skew filter call" `Quick test_passes_skew_filter_call;
      test_case "Skew filter put" `Quick test_passes_skew_filter_put;
      test_case "Skew filter fails" `Quick test_fails_skew_filter;
      test_case "IVRV filter bull" `Quick test_ivrv_filter_bull_call;
      test_case "IVRV filter fails" `Quick test_ivrv_filter_fails;
      test_case "IVRV filter credit" `Quick test_ivrv_filter_credit;
      test_case "Momentum bull" `Quick test_momentum_filter_bull;
      test_case "Momentum bear" `Quick test_momentum_filter_bear;
      test_case "Momentum fails" `Quick test_momentum_filter_fails;
      test_case "Edge score" `Quick test_edge_score_bull_call;
      test_case "Edge score capped" `Quick test_edge_score_capped;
      test_case "Strong Buy" `Quick test_make_recommendation_strong_buy;
      test_case "Pass" `Quick test_make_recommendation_pass;
      test_case "None spread" `Quick test_make_recommendation_none;
      test_case "Quality clean" `Quick test_check_trade_quality_clean;
      test_case "Quality warnings" `Quick test_check_trade_quality_warnings;
    ];
  ]
