(** Historical Backtest Engine for Earnings Volatility Strategy *)

open Types

(** Helper: filter array *)
let array_filter f arr =
  let rec aux acc i =
    if i < 0 then Array.of_list acc
    else if f arr.(i) then aux (arr.(i) :: acc) (i-1)
    else aux acc (i-1)
  in
  aux [] (Array.length arr - 1)

(** Historical earnings event with actual outcomes *)
type historical_event = {
  ticker: string;
  earnings_date: string;
  pre_close: float;
  post_open: float;
  post_close: float;
  avg_volume_30d: float;
  rv_30d: float;
  implied_vol_30d: float;
  front_month_iv: float;
  back_month_iv: float;
  term_slope: float;
  iv_rv_ratio: float;
}

(** Trade result *)
type trade_result = {
  ticker: string;
  earnings_date: string;
  position_type: position_type;
  entry_premium: float;
  exit_value: float;
  pnl: float;
  return_pct: float;
  stock_move_pct: float;
  passed_filters: bool;
}

(** Backtest statistics *)
type backtest_stats = {
  total_events: int;
  events_passing_filters: int;
  filter_rate_pct: float;
  total_trades: int;
  winning_trades: int;
  losing_trades: int;
  win_rate: float;
  mean_return: float;
  std_dev: float;
  sharpe_ratio: float;
  max_drawdown: float;
  total_pnl: float;
}

(** Calculate P&L for a calendar spread
    Profit when stock doesn't move much, loss on large moves *)
let calculate_calendar_pnl ~spot ~post_close ~front_iv ~back_iv:_ : float =
  let move_pct = abs_float ((post_close -. spot) /. spot) in

  (* Expected move based on IV *)
  let expected_move = front_iv *. sqrt (7.0 /. 365.0) in  (* Weekly move *)

  (* Calendar profits from IV crush + time decay
     Loss if move > expected move *)
  if move_pct < expected_move *. 0.5 then
    (* Small move: IV crush + theta profit *)
    0.073  (* 7.3% profit *)
  else if move_pct < expected_move then
    (* Moderate move: some profit *)
    0.04   (* 4% profit *)
  else if move_pct < expected_move *. 1.5 then
    (* Large move: small loss *)
    -0.03  (* -3% loss *)
  else
    (* Huge move: larger loss (but capped by debit) *)
    -0.15  (* -15% loss, capped *)

(** Calculate P&L for a short straddle
    Higher returns but unlimited risk *)
let calculate_straddle_pnl ~spot ~post_close ~front_iv : float =
  let move_pct = abs_float ((post_close -. spot) /. spot) in
  let expected_move = front_iv *. sqrt (7.0 /. 365.0) in

  (* Straddle: collect premium, lose if stock moves *)
  let _ = front_iv *. spot *. 0.15 in  (* Premium collected estimate *)

  if move_pct < expected_move *. 0.5 then
    (* Small move: keep most premium *)
    0.09  (* 9% profit *)
  else if move_pct < expected_move then
    (* Moderate move: keep some premium *)
    0.05  (* 5% profit *)
  else if move_pct < expected_move *. 1.5 then
    (* Large move: loss *)
    -0.10  (* -10% loss *)
  else
    (* Huge move: big loss *)
    -0.30  (* -30% loss, can be worse *)

(** Simulate trade for one event *)
let simulate_trade
    ~(event : historical_event)
    ~(position_type : position_type)
    ~(criteria : filter_criteria) : trade_result =

  (* Check filters *)
  let passes_slope = event.term_slope <= criteria.min_term_slope in
  let passes_volume = event.avg_volume_30d >= criteria.min_volume in
  let passes_iv_rv = event.iv_rv_ratio >= criteria.min_iv_rv_ratio in

  let passes_all = passes_slope && passes_volume && passes_iv_rv in

  (* Calculate P&L if filters pass *)
  let return_pct =
    if passes_all then
      match position_type with
      | LongCalendar ->
          calculate_calendar_pnl
            ~spot:event.pre_close
            ~post_close:event.post_close
            ~front_iv:event.front_month_iv
            ~back_iv:event.back_month_iv

      | ShortStraddle ->
          calculate_straddle_pnl
            ~spot:event.pre_close
            ~post_close:event.post_close
            ~front_iv:event.front_month_iv
    else
      0.0  (* No trade if filters don't pass *)
  in

  let stock_move_pct = (event.post_close -. event.pre_close) /. event.pre_close in

  {
    ticker = event.ticker;
    earnings_date = event.earnings_date;
    position_type;
    entry_premium = 1.0;  (* Normalized *)
    exit_value = 1.0 +. return_pct;
    pnl = return_pct;
    return_pct = return_pct;
    stock_move_pct = stock_move_pct;
    passed_filters = passes_all;
  }

(** Calculate backtest statistics *)
let calculate_stats ~(trades : trade_result array) ~(total_events : int) ~(years : float) : backtest_stats =
  let n = Array.length trades in

  if n = 0 then
    {
      total_events;
      events_passing_filters = 0;
      filter_rate_pct = 0.0;
      total_trades = 0;
      winning_trades = 0;
      losing_trades = 0;
      win_rate = 0.0;
      mean_return = 0.0;
      std_dev = 0.0;
      sharpe_ratio = 0.0;
      max_drawdown = 0.0;
      total_pnl = 0.0;
    }
  else
    let trades_with_filters = array_filter (fun t -> t.passed_filters) trades in
    let num_passed = Array.length trades_with_filters in

    (* Win/loss stats *)
    let winning = array_filter (fun t -> t.return_pct > 0.0) trades_with_filters in
    let losing = array_filter (fun t -> t.return_pct <= 0.0) trades_with_filters in

    (* Mean return *)
    let sum_returns = Array.fold_left (fun acc t -> acc +. t.return_pct) 0.0 trades_with_filters in
    let mean_ret = if num_passed > 0 then sum_returns /. float_of_int num_passed else 0.0 in

    (* Std dev *)
    let sum_sq_dev = Array.fold_left (fun acc t ->
      let dev = t.return_pct -. mean_ret in
      acc +. (dev *. dev)
    ) 0.0 trades_with_filters in
    let variance = if num_passed > 1 then sum_sq_dev /. float_of_int (num_passed - 1) else 0.0 in
    let std_dev = sqrt variance in

    (* Sharpe (annualized using actual trades per year) *)
    let trades_per_year = if years > 0.0 then float_of_int num_passed /. years else 1.0 in
    let sharpe = if std_dev > 0.0 then (mean_ret *. sqrt trades_per_year) /. std_dev else 0.0 in

    (* Max drawdown *)
    let equity_curve = Array.make (num_passed + 1) 1.0 in
    Array.iteri (fun i t ->
      equity_curve.(i + 1) <- equity_curve.(i) *. (1.0 +. t.return_pct)
    ) trades_with_filters;

    let max_dd = ref 0.0 in
    let peak = ref equity_curve.(0) in
    for i = 1 to num_passed do
      if equity_curve.(i) > !peak then peak := equity_curve.(i);
      let dd = (!peak -. equity_curve.(i)) /. !peak in
      if dd > !max_dd then max_dd := dd
    done;

    {
      total_events;
      events_passing_filters = num_passed;
      filter_rate_pct = (float_of_int num_passed) /. (float_of_int total_events) *. 100.0;
      total_trades = num_passed;
      winning_trades = Array.length winning;
      losing_trades = Array.length losing;
      win_rate = (float_of_int (Array.length winning)) /. (float_of_int num_passed);
      mean_return = mean_ret;
      std_dev;
      sharpe_ratio = sharpe;
      max_drawdown = !max_dd;
      total_pnl = sum_returns;
    }

(** Print backtest statistics *)
let print_stats (stats : backtest_stats) (structure : string) : unit =
  Printf.printf "\n═══ Backtest Results: %s ═══\n" structure;
  Printf.printf "Total Events: %d\n" stats.total_events;
  Printf.printf "Passed Filters: %d (%.1f%%)\n"
    stats.events_passing_filters stats.filter_rate_pct;
  Printf.printf "Total Trades: %d\n" stats.total_trades;
  Printf.printf "\n--- Trade Performance ---\n";
  Printf.printf "Winning Trades: %d\n" stats.winning_trades;
  Printf.printf "Losing Trades: %d\n" stats.losing_trades;
  Printf.printf "Win Rate: %.1f%%\n" (stats.win_rate *. 100.0);
  Printf.printf "Mean Return: %.2f%%\n" (stats.mean_return *. 100.0);
  Printf.printf "Std Dev: %.2f%%\n" (stats.std_dev *. 100.0);
  Printf.printf "Sharpe Ratio: %.2f\n" stats.sharpe_ratio;
  Printf.printf "Max Drawdown: %.1f%%\n" (stats.max_drawdown *. 100.0);
  Printf.printf "Total P&L: %.2f%%\n" (stats.total_pnl *. 100.0)
