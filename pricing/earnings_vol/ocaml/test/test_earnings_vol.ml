open Earnings_vol_lib
open Types

let float_eq ~eps = Alcotest.testable
  (fun fmt f -> Format.fprintf fmt "%.6f" f)
  (fun a b -> Float.abs (a -. b) < eps)

(* ── Term Structure Tests ── *)

let obs_backwardated = [|
  { expiration_date = "2026-02-20"; days_to_expiry = 7;  atm_iv = 0.45; strike = 180.0 };
  { expiration_date = "2026-03-06"; days_to_expiry = 21; atm_iv = 0.38; strike = 180.0 };
  { expiration_date = "2026-03-20"; days_to_expiry = 35; atm_iv = 0.32; strike = 180.0 };
  { expiration_date = "2026-04-03"; days_to_expiry = 49; atm_iv = 0.30; strike = 180.0 };
|]

let obs_contango = [|
  { expiration_date = "2026-02-20"; days_to_expiry = 7;  atm_iv = 0.20; strike = 100.0 };
  { expiration_date = "2026-03-20"; days_to_expiry = 35; atm_iv = 0.25; strike = 100.0 };
  { expiration_date = "2026-04-03"; days_to_expiry = 49; atm_iv = 0.30; strike = 100.0 };
|]

let test_slope_backwardated_real () =
  let slope = Term_structure.calculate_slope obs_backwardated in
  (* front = obs.(0).atm_iv = 0.45, back closest to 45d = obs at 49d = 0.30 *)
  Alcotest.(check (float_eq ~eps:0.001)) "front - back" 0.15 slope

let test_slope_contango () =
  let slope = Term_structure.calculate_slope obs_contango in
  (* front = 0.20, back closest to 45d = obs at 49d = 0.30 *)
  Alcotest.(check (float_eq ~eps:0.001)) "front - back negative" (-0.10) slope

let test_slope_single () =
  let obs = [| { expiration_date = "2026-02-20"; days_to_expiry = 7; atm_iv = 0.30; strike = 100.0 } |] in
  let slope = Term_structure.calculate_slope obs in
  Alcotest.(check (float_eq ~eps:0.001)) "single obs = 0" 0.0 slope

let test_slope_empty () =
  let slope = Term_structure.calculate_slope [||] in
  Alcotest.(check (float_eq ~eps:0.001)) "empty = 0" 0.0 slope

let test_ratio_contango () =
  let ratio = Term_structure.calculate_ratio obs_contango in
  (* front=0.20, back closest to 45d = 0.30, ratio = 0.20/0.30 *)
  Alcotest.(check (float_eq ~eps:0.001)) "ratio < 1" 0.667 ratio

let test_ratio_single () =
  let obs = [| { expiration_date = "2026-02-20"; days_to_expiry = 7; atm_iv = 0.30; strike = 100.0 } |] in
  let ratio = Term_structure.calculate_ratio obs in
  Alcotest.(check (float_eq ~eps:0.001)) "single = 1.0" 1.0 ratio

let test_build_term_structure () =
  let ts = Term_structure.build_term_structure ~ticker:"TEST" ~observations:obs_contango in
  Alcotest.(check string) "ticker" "TEST" ts.ticker;
  Alcotest.(check (float_eq ~eps:0.001)) "front IV" 0.20 ts.front_month_iv;
  (* back = closest to 45d = 49d obs = 0.30 *)
  Alcotest.(check (float_eq ~eps:0.001)) "back IV" 0.30 ts.back_month_iv;
  Alcotest.(check (float_eq ~eps:0.001)) "slope" (-0.10) ts.term_structure_slope;
  Alcotest.(check (float_eq ~eps:0.001)) "ratio" 0.667 ts.term_structure_ratio

let test_build_term_structure_empty () =
  let ts = Term_structure.build_term_structure ~ticker:"EMPTY" ~observations:[||] in
  Alcotest.(check (float_eq ~eps:0.001)) "front 0" 0.0 ts.front_month_iv;
  Alcotest.(check (float_eq ~eps:0.001)) "back 0" 0.0 ts.back_month_iv;
  Alcotest.(check (float_eq ~eps:0.001)) "slope 0" 0.0 ts.term_structure_slope;
  Alcotest.(check (float_eq ~eps:0.001)) "ratio 1" 1.0 ts.term_structure_ratio

let test_realized_vol () =
  (* Constant prices = zero vol *)
  let prices = [| 100.0; 100.0; 100.0; 100.0; 100.0 |] in
  let rv = Term_structure.calculate_realized_vol ~prices ~annualization_factor:252.0 in
  Alcotest.(check (float_eq ~eps:0.001)) "constant = 0 vol" 0.0 rv.rv

let test_realized_vol_trending () =
  (* Prices with varying daily returns *)
  let prices = [| 100.0; 102.0; 101.0; 103.0; 105.0 |] in
  let rv = Term_structure.calculate_realized_vol ~prices ~annualization_factor:252.0 in
  Alcotest.(check bool) "positive rv" true (rv.rv > 0.0);
  Alcotest.(check bool) "variance positive" true (rv.variance > 0.0)

let test_realized_vol_insufficient () =
  let prices = [| 100.0 |] in
  let rv = Term_structure.calculate_realized_vol ~prices ~annualization_factor:252.0 in
  Alcotest.(check (float_eq ~eps:0.001)) "insufficient = 0" 0.0 rv.rv

let test_iv_rv_ratio () =
  let rv = { ticker = "TEST"; lookback_days = 30; rv = 0.25; variance = 0.0625 } in
  let result = Term_structure.calculate_iv_rv_ratio ~implied_vol:0.30 ~realized_vol:rv in
  Alcotest.(check (float_eq ~eps:0.001)) "ratio 1.2" 1.2 result.iv_rv_ratio;
  Alcotest.(check (float_eq ~eps:0.001)) "spread 0.05" 0.05 result.iv_minus_rv

let test_iv_rv_ratio_zero_rv () =
  let rv = { ticker = "TEST"; lookback_days = 30; rv = 0.0; variance = 0.0 } in
  let result = Term_structure.calculate_iv_rv_ratio ~implied_vol:0.30 ~realized_vol:rv in
  Alcotest.(check (float_eq ~eps:0.001)) "zero rv = 1.0" 1.0 result.iv_rv_ratio

(* ── Filter Tests ── *)

let make_ts slope =
  { ticker = "TEST"; observations = [||];
    front_month_iv = 0.0; back_month_iv = 0.0;
    term_structure_slope = slope; term_structure_ratio = 1.0 }

let make_iv_rv ratio =
  { ticker = "TEST"; implied_vol_30d = 0.0; realized_vol_30d = 0.0;
    iv_rv_ratio = ratio; iv_minus_rv = 0.0 }

let test_filters_all_pass () =
  let result = Filters.apply_filters
    ~term_structure:(make_ts (-0.10))
    ~volume:2_000_000.0
    ~iv_rv:(make_iv_rv 1.5)
    ~criteria:default_criteria in
  Alcotest.(check string) "recommended" "Recommended" result.recommendation;
  Alcotest.(check bool) "slope passes" true result.passes_term_slope;
  Alcotest.(check bool) "volume passes" true result.passes_volume;
  Alcotest.(check bool) "iv_rv passes" true result.passes_iv_rv

let test_filters_slope_plus_volume () =
  let result = Filters.apply_filters
    ~term_structure:(make_ts (-0.10))
    ~volume:2_000_000.0
    ~iv_rv:(make_iv_rv 0.9)  (* fails iv_rv *)
    ~criteria:default_criteria in
  Alcotest.(check string) "consider" "Consider" result.recommendation

let test_filters_slope_plus_ivrv () =
  let result = Filters.apply_filters
    ~term_structure:(make_ts (-0.10))
    ~volume:500_000.0  (* fails volume *)
    ~iv_rv:(make_iv_rv 1.5)
    ~criteria:default_criteria in
  Alcotest.(check string) "consider" "Consider" result.recommendation

let test_filters_no_slope () =
  let result = Filters.apply_filters
    ~term_structure:(make_ts 0.05)  (* fails slope: positive, not <= -0.05 *)
    ~volume:2_000_000.0
    ~iv_rv:(make_iv_rv 1.5)
    ~criteria:default_criteria in
  Alcotest.(check string) "avoid no slope" "Avoid" result.recommendation

let test_filters_slope_only () =
  let result = Filters.apply_filters
    ~term_structure:(make_ts (-0.10))
    ~volume:500_000.0  (* fails *)
    ~iv_rv:(make_iv_rv 0.9)  (* fails *)
    ~criteria:default_criteria in
  (* slope passes but neither volume nor iv_rv → not (passes_volume || passes_iv_rv) → Avoid *)
  Alcotest.(check string) "avoid slope only" "Avoid" result.recommendation

let test_filters_boundary_slope () =
  let result = Filters.apply_filters
    ~term_structure:(make_ts (-0.05))
    ~volume:1_000_000.0
    ~iv_rv:(make_iv_rv 1.1)
    ~criteria:default_criteria in
  (* slope <= -0.05 = true, volume >= 1M = true, iv_rv >= 1.1 = true *)
  Alcotest.(check string) "boundary recommended" "Recommended" result.recommendation

(* ── Kelly Sizing Tests ── *)

let test_kelly_fraction () =
  let f = Kelly_sizing.calculate_kelly_fraction ~mean_return:0.09 ~std_dev:0.48 in
  (* f = 0.09 / (0.48^2) = 0.09 / 0.2304 = 0.390625 *)
  Alcotest.(check (float_eq ~eps:0.001)) "kelly fraction" 0.3906 f

let test_kelly_fraction_zero_std () =
  let f = Kelly_sizing.calculate_kelly_fraction ~mean_return:0.09 ~std_dev:0.0 in
  Alcotest.(check (float_eq ~eps:0.001)) "zero std = 0" 0.0 f

let test_kelly_fraction_negative_std () =
  let f = Kelly_sizing.calculate_kelly_fraction ~mean_return:0.09 ~std_dev:(-0.1) in
  Alcotest.(check (float_eq ~eps:0.001)) "negative std = 0" 0.0 f

let test_size_straddle () =
  let pos = Kelly_sizing.size_straddle
    ~account_size:100_000.0
    ~fractional_kelly:0.30
    ~straddle_premium:500.0 in
  Alcotest.(check bool) "is straddle" true
    (match pos.position_type with ShortStraddle -> true | _ -> false);
  (* full kelly = 0.09 / 0.48^2 = 0.3906, capped at 0.20 *)
  Alcotest.(check (float_eq ~eps:0.001)) "kelly capped" 0.20 (min pos.kelly_fraction 0.20);
  (* frac_kelly = 0.20 * 0.30 = 0.06 *)
  Alcotest.(check (float_eq ~eps:0.01)) "frac kelly" 0.06 pos.fractional_kelly;
  (* position_size = 100000 * 0.06 = 6000 *)
  Alcotest.(check (float_eq ~eps:1.0)) "position size" 6000.0 pos.max_position_size;
  (* contracts = 6000 / 500 = 12 *)
  Alcotest.(check int) "contracts" 12 pos.num_contracts;
  Alcotest.(check (float_eq ~eps:0.001)) "expected return" 0.09 pos.expected_return;
  Alcotest.(check (float_eq ~eps:0.001)) "max loss" 1.30 pos.max_loss_pct

let test_size_calendar () =
  let pos = Kelly_sizing.size_calendar
    ~account_size:100_000.0
    ~fractional_kelly:0.30
    ~calendar_debit:200.0 in
  Alcotest.(check bool) "is calendar" true
    (match pos.position_type with LongCalendar -> true | _ -> false);
  (* full kelly = 0.073 / 0.28^2 = 0.073 / 0.0784 = 0.9311, capped at 0.60 *)
  Alcotest.(check (float_eq ~eps:0.01)) "frac kelly" 0.18 pos.fractional_kelly;
  (* position_size = 100000 * 0.18 = 18000 *)
  Alcotest.(check (float_eq ~eps:1.0)) "position size" 18000.0 pos.max_position_size;
  (* contracts = 18000 / 200 = 90 *)
  Alcotest.(check int) "contracts" 90 pos.num_contracts;
  Alcotest.(check (float_eq ~eps:0.001)) "expected return" 0.073 pos.expected_return;
  Alcotest.(check (float_eq ~eps:0.001)) "max loss" 1.05 pos.max_loss_pct

let test_size_zero_premium () =
  let pos = Kelly_sizing.size_straddle
    ~account_size:100_000.0
    ~fractional_kelly:0.30
    ~straddle_premium:0.0 in
  Alcotest.(check int) "zero premium = 0 contracts" 0 pos.num_contracts

(* ── Backtest Tests ── *)

let make_event ?(slope = -0.10) ?(volume = 2_000_000.0) ?(iv_rv = 1.5)
    ?(front_iv = 0.40) ?(pre_close = 100.0) post_close =
  Backtest.{ ticker = "TEST"; earnings_date = "2026-01-01";
    pre_close; post_open = post_close; post_close;
    avg_volume_30d = volume; rv_30d = 0.25;
    implied_vol_30d = 0.30; front_month_iv = front_iv;
    back_month_iv = 0.30; term_slope = slope; iv_rv_ratio = iv_rv }

let test_calendar_pnl_small_move () =
  (* Small move: < 0.5 * expected_move *)
  let pnl = Backtest.calculate_calendar_pnl
    ~spot:100.0 ~post_close:100.1 ~front_iv:0.40 ~back_iv:0.30 in
  Alcotest.(check (float_eq ~eps:0.001)) "small move profit" 0.073 pnl

let test_calendar_pnl_moderate_move () =
  (* expected_move = 0.40 * sqrt(7/365) = 0.0554 *)
  (* moderate = move_pct between 0.5*EM and EM *)
  (* 0.5 * 0.0554 = 0.0277, EM = 0.0554 *)
  (* Need move_pct ~ 0.04, so post_close ~ 104.0 *)
  let pnl = Backtest.calculate_calendar_pnl
    ~spot:100.0 ~post_close:104.0 ~front_iv:0.40 ~back_iv:0.30 in
  Alcotest.(check (float_eq ~eps:0.001)) "moderate move" 0.04 pnl

let test_calendar_pnl_large_move () =
  (* large = move_pct between EM and 1.5*EM *)
  (* EM = 0.0554, 1.5*EM = 0.0831 *)
  (* Need move_pct ~ 0.07 → post_close ~ 107.0 *)
  let pnl = Backtest.calculate_calendar_pnl
    ~spot:100.0 ~post_close:107.0 ~front_iv:0.40 ~back_iv:0.30 in
  Alcotest.(check (float_eq ~eps:0.001)) "large move loss" (-0.03) pnl

let test_calendar_pnl_huge_move () =
  (* huge = move_pct > 1.5*EM = 0.0831 *)
  (* Need move_pct > 0.0831 → post_close ~ 110.0 *)
  let pnl = Backtest.calculate_calendar_pnl
    ~spot:100.0 ~post_close:110.0 ~front_iv:0.40 ~back_iv:0.30 in
  Alcotest.(check (float_eq ~eps:0.001)) "huge move loss" (-0.15) pnl

let test_straddle_pnl_small_move () =
  let pnl = Backtest.calculate_straddle_pnl
    ~spot:100.0 ~post_close:100.1 ~front_iv:0.40 in
  Alcotest.(check (float_eq ~eps:0.001)) "small move profit" 0.09 pnl

let test_straddle_pnl_huge_move () =
  let pnl = Backtest.calculate_straddle_pnl
    ~spot:100.0 ~post_close:110.0 ~front_iv:0.40 in
  Alcotest.(check (float_eq ~eps:0.001)) "huge move loss" (-0.30) pnl

let test_simulate_trade_passes () =
  let event = make_event 100.1 in
  let result = Backtest.simulate_trade ~event ~position_type:LongCalendar
    ~criteria:default_criteria in
  Alcotest.(check bool) "passed filters" true result.passed_filters;
  Alcotest.(check (float_eq ~eps:0.001)) "calendar pnl" 0.073 result.return_pct

let test_simulate_trade_fails_filters () =
  let event = make_event ~slope:0.05 100.1 in  (* slope fails *)
  let result = Backtest.simulate_trade ~event ~position_type:LongCalendar
    ~criteria:default_criteria in
  Alcotest.(check bool) "failed filters" false result.passed_filters;
  Alcotest.(check (float_eq ~eps:0.001)) "no trade = 0 pnl" 0.0 result.return_pct

let test_calculate_stats_empty () =
  let stats = Backtest.calculate_stats ~trades:[||] ~total_events:10 ~years:1.0 in
  Alcotest.(check int) "total events" 10 stats.total_events;
  Alcotest.(check int) "no trades" 0 stats.total_trades;
  Alcotest.(check (float_eq ~eps:0.001)) "zero win rate" 0.0 stats.win_rate

let test_calculate_stats () =
  let trades = [|
    Backtest.{ ticker="A"; earnings_date="2026-01-01"; position_type=LongCalendar;
      entry_premium=1.0; exit_value=1.073; pnl=0.073; return_pct=0.073;
      stock_move_pct=0.001; passed_filters=true };
    Backtest.{ ticker="B"; earnings_date="2026-01-15"; position_type=LongCalendar;
      entry_premium=1.0; exit_value=1.04; pnl=0.04; return_pct=0.04;
      stock_move_pct=0.03; passed_filters=true };
    Backtest.{ ticker="C"; earnings_date="2026-02-01"; position_type=LongCalendar;
      entry_premium=1.0; exit_value=0.85; pnl=(-0.15); return_pct=(-0.15);
      stock_move_pct=0.10; passed_filters=true };
  |] in
  let stats = Backtest.calculate_stats ~trades ~total_events:10 ~years:1.0 in
  Alcotest.(check int) "3 trades" 3 stats.total_trades;
  Alcotest.(check int) "2 winning" 2 stats.winning_trades;
  Alcotest.(check int) "1 losing" 1 stats.losing_trades;
  (* win_rate = 2/3 *)
  Alcotest.(check (float_eq ~eps:0.01)) "win rate" 0.667 stats.win_rate;
  (* mean_return = (0.073 + 0.04 - 0.15) / 3 = -0.037 / 3 = -0.01233 *)
  Alcotest.(check (float_eq ~eps:0.001)) "mean return" (-0.01233) stats.mean_return;
  Alcotest.(check bool) "positive std" true (stats.std_dev > 0.0);
  Alcotest.(check bool) "has drawdown" true (stats.max_drawdown > 0.0)

let test_calculate_stats_skips_failed_filters () =
  let trades = [|
    Backtest.{ ticker="A"; earnings_date="2026-01-01"; position_type=LongCalendar;
      entry_premium=1.0; exit_value=1.073; pnl=0.073; return_pct=0.073;
      stock_move_pct=0.001; passed_filters=true };
    Backtest.{ ticker="B"; earnings_date="2026-01-15"; position_type=LongCalendar;
      entry_premium=1.0; exit_value=1.0; pnl=0.0; return_pct=0.0;
      stock_move_pct=0.03; passed_filters=false };
  |] in
  let stats = Backtest.calculate_stats ~trades ~total_events:5 ~years:1.0 in
  (* Only trade A passed filters *)
  Alcotest.(check int) "1 passing" 1 stats.events_passing_filters;
  Alcotest.(check int) "1 winning" 1 stats.winning_trades

(* ── Types Tests ── *)

let test_default_criteria () =
  Alcotest.(check (float_eq ~eps:0.001)) "min slope" (-0.05) default_criteria.min_term_slope;
  Alcotest.(check (float_eq ~eps:0.1)) "min volume" 1_000_000.0 default_criteria.min_volume;
  Alcotest.(check (float_eq ~eps:0.001)) "min iv_rv" 1.1 default_criteria.min_iv_rv_ratio

let () =
  Alcotest.run "Earnings Vol Tests" [
    ("term_structure", [
      Alcotest.test_case "Slope backwardated" `Quick test_slope_backwardated_real;
      Alcotest.test_case "Slope contango" `Quick test_slope_contango;
      Alcotest.test_case "Slope single obs" `Quick test_slope_single;
      Alcotest.test_case "Slope empty" `Quick test_slope_empty;
      Alcotest.test_case "Ratio contango" `Quick test_ratio_contango;
      Alcotest.test_case "Ratio single" `Quick test_ratio_single;
      Alcotest.test_case "Build term structure" `Quick test_build_term_structure;
      Alcotest.test_case "Build empty" `Quick test_build_term_structure_empty;
      Alcotest.test_case "Realized vol constant" `Quick test_realized_vol;
      Alcotest.test_case "Realized vol trending" `Quick test_realized_vol_trending;
      Alcotest.test_case "Realized vol insufficient" `Quick test_realized_vol_insufficient;
      Alcotest.test_case "IV/RV ratio" `Quick test_iv_rv_ratio;
      Alcotest.test_case "IV/RV zero RV" `Quick test_iv_rv_ratio_zero_rv;
    ]);
    ("filters", [
      Alcotest.test_case "All pass" `Quick test_filters_all_pass;
      Alcotest.test_case "Slope + volume" `Quick test_filters_slope_plus_volume;
      Alcotest.test_case "Slope + IV/RV" `Quick test_filters_slope_plus_ivrv;
      Alcotest.test_case "No slope" `Quick test_filters_no_slope;
      Alcotest.test_case "Slope only" `Quick test_filters_slope_only;
      Alcotest.test_case "Boundary values" `Quick test_filters_boundary_slope;
    ]);
    ("kelly_sizing", [
      Alcotest.test_case "Kelly fraction" `Quick test_kelly_fraction;
      Alcotest.test_case "Kelly zero std" `Quick test_kelly_fraction_zero_std;
      Alcotest.test_case "Kelly negative std" `Quick test_kelly_fraction_negative_std;
      Alcotest.test_case "Size straddle" `Quick test_size_straddle;
      Alcotest.test_case "Size calendar" `Quick test_size_calendar;
      Alcotest.test_case "Zero premium" `Quick test_size_zero_premium;
    ]);
    ("backtest", [
      Alcotest.test_case "Calendar small move" `Quick test_calendar_pnl_small_move;
      Alcotest.test_case "Calendar moderate move" `Quick test_calendar_pnl_moderate_move;
      Alcotest.test_case "Calendar large move" `Quick test_calendar_pnl_large_move;
      Alcotest.test_case "Calendar huge move" `Quick test_calendar_pnl_huge_move;
      Alcotest.test_case "Straddle small move" `Quick test_straddle_pnl_small_move;
      Alcotest.test_case "Straddle huge move" `Quick test_straddle_pnl_huge_move;
      Alcotest.test_case "Simulate passes" `Quick test_simulate_trade_passes;
      Alcotest.test_case "Simulate fails" `Quick test_simulate_trade_fails_filters;
      Alcotest.test_case "Stats empty" `Quick test_calculate_stats_empty;
      Alcotest.test_case "Stats calculation" `Quick test_calculate_stats;
      Alcotest.test_case "Stats skip failed" `Quick test_calculate_stats_skips_failed_filters;
    ]);
    ("types", [
      Alcotest.test_case "Default criteria" `Quick test_default_criteria;
    ]);
  ]
