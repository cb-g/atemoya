(** Kelly Criterion Position Sizing for Earnings Trades *)

open Types

(** Calculate Kelly fraction
    Formula: f* = (mean / variance)
    For earnings: use backtest statistics
*)
let calculate_kelly_fraction ~mean_return ~std_dev : float =
  if std_dev <= 0.0 then 0.0
  else
    let variance = std_dev *. std_dev in
    mean_return /. variance

(** Calculate position size for straddle *)
let size_straddle 
    ~account_size 
    ~fractional_kelly 
    ~straddle_premium 
    : kelly_position =
  
  (* Use backtest stats from video *)
  let mean_ret = 0.09 in
  let std_dev = 0.48 in
  let full_kelly = calculate_kelly_fraction ~mean_return:mean_ret ~std_dev in
  
  (* Cap full Kelly at reasonable level *)
  let capped_kelly = min full_kelly 0.20 in  (* Never more than 20% *)
  let frac_kelly = capped_kelly *. fractional_kelly in
  
  (* Position size = Account × Fractional Kelly *)
  let position_size = account_size *. frac_kelly in
  
  (* Calculate number of contracts *)
  let num_contracts = 
    if straddle_premium > 0.0 then
      int_of_float (position_size /. straddle_premium)
    else 0
  in
  
  {
    position_type = ShortStraddle;
    kelly_fraction = full_kelly;
    fractional_kelly = frac_kelly;
    max_position_size = position_size;
    num_contracts;
    expected_return = mean_ret;
    expected_std = std_dev;
    max_loss_pct = 1.30;  (* 130% from backtest *)
  }

(** Calculate position size for calendar *)
let size_calendar 
    ~account_size 
    ~fractional_kelly 
    ~calendar_debit 
    : kelly_position =
  
  (* Use backtest stats from video *)
  let mean_ret = 0.073 in
  let std_dev = 0.28 in
  let full_kelly = calculate_kelly_fraction ~mean_return:mean_ret ~std_dev in
  
  (* Cap full Kelly *)
  let capped_kelly = min full_kelly 0.60 in  (* Calendar can handle higher *)
  let frac_kelly = capped_kelly *. fractional_kelly in
  
  (* Position size *)
  let position_size = account_size *. frac_kelly in
  
  (* Number of contracts *)
  let num_contracts = 
    if calendar_debit > 0.0 then
      int_of_float (position_size /. calendar_debit)
    else 0
  in
  
  {
    position_type = LongCalendar;
    kelly_fraction = full_kelly;
    fractional_kelly = frac_kelly;
    max_position_size = position_size;
    num_contracts;
    expected_return = mean_ret;
    expected_std = std_dev;
    max_loss_pct = 1.05;  (* 105% from backtest *)
  }

(** Print Kelly sizing results *)
let print_kelly_sizing (sizing : kelly_position) : unit =
  let structure_name = match sizing.position_type with
    | ShortStraddle -> "Short Straddle"
    | LongCalendar -> "Long Calendar"
  in
  
  Printf.printf "\n=== Kelly Position Sizing: %s ===\n" structure_name;
  Printf.printf "Full Kelly: %.2f%%\n" (sizing.kelly_fraction *. 100.0);
  Printf.printf "Fractional Kelly: %.2f%%\n" (sizing.fractional_kelly *. 100.0);
  Printf.printf "Max Position Size: $%.2f\n" sizing.max_position_size;
  Printf.printf "Recommended Contracts: %d\n" sizing.num_contracts;
  Printf.printf "Expected Return: %.1f%%\n" (sizing.expected_return *. 100.0);
  Printf.printf "Expected Std Dev: %.1f%%\n" (sizing.expected_std *. 100.0);
  Printf.printf "Max Loss: %.0f%%\n" (sizing.max_loss_pct *. 100.0)
