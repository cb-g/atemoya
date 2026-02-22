(** Tests for Portfolio Tracker *)

open Watchlist
open Types

(* ═══════════════════════════════════════════════════════════════════════════════
   Test Helpers
   ═══════════════════════════════════════════════════════════════════════════════ *)

let make_position
    ?(pos_type = Long)
    ?(shares = 100.0)
    ?(avg_cost = 100.0)
    ?(buy_target = None)
    ?(sell_target = None)
    ?(stop_loss = None)
    ?(bull = [])
    ?(bear = [])
    ticker
  =
  {
    ticker;
    name = ticker;
    position = { pos_type; shares; avg_cost };
    levels = { buy_target; sell_target; stop_loss };
    bull;
    bear;
    catalysts = [];
    notes = "";
  }

let make_market_data ?(change_1d = 0.0) ?(change_5d = 0.0) price =
  {
    current_price = price;
    prev_close = price *. (1.0 -. change_1d /. 100.0);
    change_1d_pct = change_1d;
    change_5d_pct = change_5d;
    high_52w = price *. 1.2;
    low_52w = price *. 0.8;
    fetch_time = "2026-01-18T12:00:00Z";
  }

(* ═══════════════════════════════════════════════════════════════════════════════
   Thesis Score Tests
   ═══════════════════════════════════════════════════════════════════════════════ *)

let test_thesis_score_neutral () =
  let bull = [] in
  let bear = [] in
  let score = Analysis.calculate_thesis_score bull bear in
  Alcotest.(check int) "bull_score" 0 score.bull_score;
  Alcotest.(check int) "bear_score" 0 score.bear_score;
  Alcotest.(check int) "net_score" 0 score.net_score;
  Alcotest.(check string) "conviction" "neutral" score.conviction

let test_thesis_score_bullish () =
  let bull = [{ arg = "Strong growth"; weight = 9 }; { arg = "Good margin"; weight = 7 }] in
  let bear = [{ arg = "Competition"; weight = 5 }] in
  let score = Analysis.calculate_thesis_score bull bear in
  Alcotest.(check int) "bull_score" 16 score.bull_score;
  Alcotest.(check int) "bear_score" 5 score.bear_score;
  Alcotest.(check int) "net_score" 11 score.net_score;
  Alcotest.(check string) "conviction" "strong bull" score.conviction

let test_thesis_score_bearish () =
  let bull = [{ arg = "Brand"; weight = 4 }] in
  let bear = [{ arg = "Declining sales"; weight = 9 }; { arg = "Debt"; weight = 8 }] in
  let score = Analysis.calculate_thesis_score bull bear in
  Alcotest.(check int) "bull_score" 4 score.bull_score;
  Alcotest.(check int) "bear_score" 17 score.bear_score;
  Alcotest.(check int) "net_score" (-13) score.net_score;
  Alcotest.(check string) "conviction" "strong bear" score.conviction

let test_thesis_score_slightly_bullish () =
  let bull = [{ arg = "Growth"; weight = 6 }] in
  let bear = [{ arg = "Risk"; weight = 4 }] in
  let score = Analysis.calculate_thesis_score bull bear in
  Alcotest.(check int) "net_score" 2 score.net_score;
  Alcotest.(check string) "conviction" "slightly bullish" score.conviction

let thesis_score_tests = [
  Alcotest.test_case "neutral" `Quick test_thesis_score_neutral;
  Alcotest.test_case "strong bullish" `Quick test_thesis_score_bullish;
  Alcotest.test_case "strong bearish" `Quick test_thesis_score_bearish;
  Alcotest.test_case "slightly bullish" `Quick test_thesis_score_slightly_bullish;
]

(* ═══════════════════════════════════════════════════════════════════════════════
   Price Alert Tests
   ═══════════════════════════════════════════════════════════════════════════════ *)

let test_no_alerts_no_market () =
  let pos = make_position "AAPL" in
  let alerts = Analysis.check_price_alerts pos None in
  Alcotest.(check int) "no alerts" 0 (List.length alerts)

let test_stop_loss_hit () =
  let pos = make_position "AAPL" ~avg_cost:150.0 ~stop_loss:(Some 130.0) in
  let market = make_market_data 125.0 in  (* Below stop loss *)
  let alerts = Analysis.check_price_alerts pos (Some market) in
  Alcotest.(check bool) "has alerts" true (List.length alerts > 0);
  let has_stop_loss = List.exists (fun a ->
    match a.alert with HitStopLoss _ -> true | _ -> false
  ) alerts in
  Alcotest.(check bool) "stop loss alert" true has_stop_loss

let test_near_stop_loss () =
  let pos = make_position "AAPL" ~avg_cost:150.0 ~stop_loss:(Some 130.0) in
  let market = make_market_data 133.0 in  (* Within 5% of stop loss *)
  let alerts = Analysis.check_price_alerts pos (Some market) in
  let has_near_stop = List.exists (fun a ->
    match a.alert with NearStopLoss _ -> true | _ -> false
  ) alerts in
  Alcotest.(check bool) "near stop loss alert" true has_near_stop

let test_buy_target_hit () =
  let pos = make_position "AAPL" ~pos_type:Watching ~avg_cost:0.0 ~buy_target:(Some 140.0) in
  let market = make_market_data 138.0 in  (* Below buy target *)
  let alerts = Analysis.check_price_alerts pos (Some market) in
  let has_buy_target = List.exists (fun a ->
    match a.alert with HitBuyTarget _ -> true | _ -> false
  ) alerts in
  Alcotest.(check bool) "buy target alert" true has_buy_target

let test_sell_target_hit () =
  let pos = make_position "AAPL" ~avg_cost:150.0 ~sell_target:(Some 200.0) in
  let market = make_market_data 205.0 in  (* Above sell target *)
  let alerts = Analysis.check_price_alerts pos (Some market) in
  let has_sell_target = List.exists (fun a ->
    match a.alert with HitSellTarget _ -> true | _ -> false
  ) alerts in
  Alcotest.(check bool) "sell target alert" true has_sell_target

let test_pnl_gain_alert () =
  let pos = make_position "AAPL" ~avg_cost:100.0 in
  let market = make_market_data 125.0 in  (* 25% gain *)
  let alerts = Analysis.check_price_alerts pos (Some market) in
  let has_gain_alert = List.exists (fun a ->
    match a.alert with AboveCostBasis _ -> true | _ -> false
  ) alerts in
  Alcotest.(check bool) "gain alert" true has_gain_alert

let test_pnl_loss_alert () =
  let pos = make_position "AAPL" ~avg_cost:100.0 in
  let market = make_market_data 85.0 in  (* 15% loss *)
  let alerts = Analysis.check_price_alerts pos (Some market) in
  let has_loss_alert = List.exists (fun a ->
    match a.alert with BelowCostBasis _ -> true | _ -> false
  ) alerts in
  Alcotest.(check bool) "loss alert" true has_loss_alert

(* Short position: stop loss triggers when price rises ABOVE stop *)
let test_short_stop_loss_hit () =
  let pos = make_position "SMCI" ~pos_type:Short ~avg_cost:35.0 ~stop_loss:(Some 55.0) in
  let market = make_market_data 58.0 in  (* Above stop loss for short *)
  let alerts = Analysis.check_price_alerts pos (Some market) in
  let has_stop_loss = List.exists (fun a ->
    match a.alert with HitStopLoss _ -> true | _ -> false
  ) alerts in
  Alcotest.(check bool) "short stop loss alert" true has_stop_loss

(* Short position: stop loss does NOT trigger when price is below stop *)
let test_short_stop_loss_not_hit () =
  let pos = make_position "SMCI" ~pos_type:Short ~avg_cost:35.0 ~stop_loss:(Some 55.0) in
  let market = make_market_data 30.0 in  (* Well below stop — short is profitable *)
  let alerts = Analysis.check_price_alerts pos (Some market) in
  let has_stop_loss = List.exists (fun a ->
    match a.alert with HitStopLoss _ | NearStopLoss _ -> true | _ -> false
  ) alerts in
  Alcotest.(check bool) "no stop loss alert for profitable short" false has_stop_loss

(* Short position: sell target triggers when price drops BELOW target *)
let test_short_sell_target_hit () =
  let pos = make_position "SMCI" ~pos_type:Short ~avg_cost:35.0 ~sell_target:(Some 20.0) in
  let market = make_market_data 18.0 in  (* Below cover target for short *)
  let alerts = Analysis.check_price_alerts pos (Some market) in
  let has_sell_target = List.exists (fun a ->
    match a.alert with HitSellTarget _ -> true | _ -> false
  ) alerts in
  Alcotest.(check bool) "short sell target (cover) alert" true has_sell_target

(* Short position: PnL gain alert when price drops significantly *)
let test_short_pnl_gain () =
  let pos = make_position "SMCI" ~pos_type:Short ~avg_cost:100.0 ~shares:30.0 in
  let market = make_market_data 70.0 in  (* 30% gain on short *)
  let alerts = Analysis.check_price_alerts pos (Some market) in
  let has_gain_alert = List.exists (fun a ->
    match a.alert with AboveCostBasis _ -> true | _ -> false
  ) alerts in
  Alcotest.(check bool) "short gain alert" true has_gain_alert

let price_alert_tests = [
  Alcotest.test_case "no market data" `Quick test_no_alerts_no_market;
  Alcotest.test_case "stop loss hit" `Quick test_stop_loss_hit;
  Alcotest.test_case "near stop loss" `Quick test_near_stop_loss;
  Alcotest.test_case "buy target hit" `Quick test_buy_target_hit;
  Alcotest.test_case "sell target hit" `Quick test_sell_target_hit;
  Alcotest.test_case "gain alert" `Quick test_pnl_gain_alert;
  Alcotest.test_case "loss alert" `Quick test_pnl_loss_alert;
  Alcotest.test_case "short stop loss hit" `Quick test_short_stop_loss_hit;
  Alcotest.test_case "short stop loss not hit" `Quick test_short_stop_loss_not_hit;
  Alcotest.test_case "short sell target hit" `Quick test_short_sell_target_hit;
  Alcotest.test_case "short pnl gain" `Quick test_short_pnl_gain;
]

(* ═══════════════════════════════════════════════════════════════════════════════
   Position Analysis Tests
   ═══════════════════════════════════════════════════════════════════════════════ *)

let test_analyze_position_long () =
  let pos = make_position "AAPL" ~avg_cost:100.0 ~shares:50.0 in
  let market_data = [("AAPL", make_market_data 120.0)] in
  let analysis = Analysis.analyze_position pos market_data in
  Alcotest.(check (option (float 0.1))) "pnl_pct" (Some 20.0) analysis.pnl_pct;
  Alcotest.(check (option (float 0.1))) "pnl_abs" (Some 1000.0) analysis.pnl_abs

let test_analyze_position_short () =
  let pos = make_position "AAPL" ~pos_type:Short ~avg_cost:100.0 ~shares:50.0 in
  let market_data = [("AAPL", make_market_data 90.0)] in
  let analysis = Analysis.analyze_position pos market_data in
  (* Short: profit when price goes down *)
  Alcotest.(check (option (float 0.1))) "pnl_pct" (Some 10.0) analysis.pnl_pct;
  Alcotest.(check (option (float 0.1))) "pnl_abs" (Some 500.0) analysis.pnl_abs

let test_analyze_position_watching () =
  let pos = make_position "AAPL" ~pos_type:Watching ~avg_cost:0.0 ~shares:0.0 in
  let market_data = [("AAPL", make_market_data 150.0)] in
  let analysis = Analysis.analyze_position pos market_data in
  (* Watching positions have no PnL *)
  Alcotest.(check (option (float 0.1))) "pnl_pct" None analysis.pnl_pct;
  Alcotest.(check (option (float 0.1))) "pnl_abs" None analysis.pnl_abs

let position_analysis_tests = [
  Alcotest.test_case "long position" `Quick test_analyze_position_long;
  Alcotest.test_case "short position" `Quick test_analyze_position_short;
  Alcotest.test_case "watching position" `Quick test_analyze_position_watching;
]

(* ═══════════════════════════════════════════════════════════════════════════════
   Portfolio Analysis Tests
   ═══════════════════════════════════════════════════════════════════════════════ *)

let test_portfolio_totals () =
  let positions = [
    make_position "AAPL" ~avg_cost:100.0 ~shares:10.0;
    make_position "NVDA" ~avg_cost:200.0 ~shares:5.0;
  ] in
  let market_data = [
    ("AAPL", make_market_data 110.0);
    ("NVDA", make_market_data 220.0);
  ] in
  let result = Analysis.run_analysis positions market_data in
  (* Total cost: 100*10 + 200*5 = 1000 + 1000 = 2000 *)
  Alcotest.(check (option (float 0.1))) "total_cost" (Some 2000.0) result.total_cost;
  (* Total value: 110*10 + 220*5 = 1100 + 1100 = 2200 *)
  Alcotest.(check (option (float 0.1))) "total_value" (Some 2200.0) result.total_value;
  (* PnL: (2200-2000)/2000 = 10% *)
  Alcotest.(check (option (float 0.1))) "total_pnl_pct" (Some 10.0) result.total_pnl_pct

let test_portfolio_excludes_watching () =
  let positions = [
    make_position "AAPL" ~avg_cost:100.0 ~shares:10.0;
    make_position "NVDA" ~pos_type:Watching ~avg_cost:0.0 ~shares:0.0;
  ] in
  let market_data = [
    ("AAPL", make_market_data 110.0);
    ("NVDA", make_market_data 220.0);
  ] in
  let result = Analysis.run_analysis positions market_data in
  (* Only AAPL counts toward totals *)
  Alcotest.(check (option (float 0.1))) "total_cost" (Some 1000.0) result.total_cost;
  Alcotest.(check (option (float 0.1))) "total_value" (Some 1100.0) result.total_value

let portfolio_analysis_tests = [
  Alcotest.test_case "portfolio totals" `Quick test_portfolio_totals;
  Alcotest.test_case "excludes watching" `Quick test_portfolio_excludes_watching;
]

(* ═══════════════════════════════════════════════════════════════════════════════
   Run All Tests
   ═══════════════════════════════════════════════════════════════════════════════ *)

let () =
  Alcotest.run "Watchlist" [
    ("thesis_score", thesis_score_tests);
    ("price_alerts", price_alert_tests);
    ("position_analysis", position_analysis_tests);
    ("portfolio_analysis", portfolio_analysis_tests);
  ]
