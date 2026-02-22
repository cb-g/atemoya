(** Calendar Spread Pricing and Construction *)

open Types

(** Construct ATM call calendar spread *)
let create_atm_call_calendar
    ~(ticker : string)
    ~(front_exp : expiration_data)
    ~(back_exp : expiration_data)
    ~(forward_vol : forward_vol)
    : calendar_spread =

  (* Sell front month ATM call *)
  let front_strike = front_exp.atm_strike in
  let front_price = front_exp.atm_call_price in

  (* Buy back month ATM call at same strike *)
  let back_strike = back_exp.atm_strike in
  let back_price = back_exp.atm_call_price in

  (* Net debit = buy back - sell front *)
  let net_debit = back_price -. front_price in

  (* Max loss = net debit (if price moves far from strike) *)
  let max_loss = net_debit in

  (* Max profit estimation: typically 50-100% of debit for ATM calendars *)
  (* Conservative: use 75% of debit as theoretical max *)
  let max_profit = 0.75 *. net_debit in

  {
    ticker;
    spread_type = "atm_call";
    front_exp = front_exp.expiration;
    front_dte = front_exp.dte;
    front_strikes = [front_strike];
    front_prices = [front_price];
    back_exp = back_exp.expiration;
    back_dte = back_exp.dte;
    back_strikes = [back_strike];
    back_prices = [back_price];
    net_debit;
    max_profit;
    max_loss;
    forward_vol;
  }

(** Construct double calendar spread (35-delta call and put) *)
let create_double_calendar
    ~(ticker : string)
    ~(front_exp : expiration_data)
    ~(back_exp : expiration_data)
    ~(forward_vol : forward_vol)
    : calendar_spread =

  (* Call calendar: sell front 35-delta call, buy back 35-delta call *)
  let call_front_strike = front_exp.delta_35_call_strike in
  let call_front_price = front_exp.delta_35_call_price in
  let call_back_strike = back_exp.delta_35_call_strike in
  let call_back_price = back_exp.delta_35_call_price in
  let call_debit = call_back_price -. call_front_price in

  (* Put calendar: sell front 35-delta put, buy back 35-delta put *)
  let put_front_strike = front_exp.delta_35_put_strike in
  let put_front_price = front_exp.delta_35_put_price in
  let put_back_strike = back_exp.delta_35_put_strike in
  let put_back_price = back_exp.delta_35_put_price in
  let put_debit = put_back_price -. put_front_price in

  (* Total debit = both calendars *)
  let net_debit = call_debit +. put_debit in

  (* Max loss = net debit *)
  let max_loss = net_debit in

  (* Max profit: double calendar has wider profit zone *)
  (* Conservative: use 100% of debit as theoretical max *)
  let max_profit = net_debit in

  {
    ticker;
    spread_type = "double_calendar";
    front_exp = front_exp.expiration;
    front_dte = front_exp.dte;
    front_strikes = [call_front_strike; put_front_strike];
    front_prices = [call_front_price; put_front_price];
    back_exp = back_exp.expiration;
    back_dte = back_exp.dte;
    back_strikes = [call_back_strike; put_back_strike];
    back_prices = [call_back_price; put_back_price];
    net_debit;
    max_profit;
    max_loss;
    forward_vol;
  }

(** Calculate Kelly fraction based on backtest stats *)
let calculate_kelly_fraction ~(ff : float) : float =
  (* From backtest: FF ≥ 0.20 → 66% win rate, 1.5:1 avg win/loss ratio *)
  let win_prob = 0.66 in
  let win_loss_ratio = 1.5 in

  (* Kelly = (p × b - q) / b, where:
     p = win probability
     q = loss probability
     b = win/loss ratio *)
  let loss_prob = 1.0 -. win_prob in
  let kelly = (win_prob *. win_loss_ratio -. loss_prob) /. win_loss_ratio in

  (* Use quarter Kelly as per video (conservative) *)
  let quarter_kelly = kelly /. 4.0 in

  (* Adjust based on FF strength - higher FF gets slightly higher allocation *)
  let adjusted_kelly =
    if ff >= 1.0 then quarter_kelly *. 1.5  (* Scale up for extreme setups *)
    else quarter_kelly
  in

  (* Clamp to reasonable range: 2-8% *)
  max min_position_size (min max_position_size adjusted_kelly)

(** Calculate expected return based on backtest *)
let calculate_expected_return ~(ff : float) : float =
  (* Backtest results by FF bucket:
     FF ≥ 1.00: ~80% avg return
     FF ≥ 0.50: ~50% avg return
     FF ≥ 0.20: ~30% avg return *)
  if ff >= 1.0 then
    0.80
  else if ff >= 0.50 then
    0.50
  else if ff >= 0.20 then
    0.30
  else
    0.0  (* Below threshold *)

(** Print calendar spread details *)
let print_calendar_spread (cs : calendar_spread) : unit =
  Printf.printf "\n=== Calendar Spread: %s ===\n" cs.ticker;
  Printf.printf "Type: %s\n" cs.spread_type;
  Printf.printf "\nFront Leg (Sell): %s (%d DTE)\n" cs.front_exp cs.front_dte;
  List.iter2
    (fun strike price ->
       Printf.printf "  Strike: %.2f | Premium: $%.2f\n" strike price)
    cs.front_strikes cs.front_prices;

  Printf.printf "\nBack Leg (Buy): %s (%d DTE)\n" cs.back_exp cs.back_dte;
  List.iter2
    (fun strike price ->
       Printf.printf "  Strike: %.2f | Premium: $%.2f\n" strike price)
    cs.back_strikes cs.back_prices;

  Printf.printf "\nEconomics:\n";
  Printf.printf "  Net Debit: $%.2f\n" cs.net_debit;
  Printf.printf "  Max Loss: $%.2f\n" cs.max_loss;
  Printf.printf "  Max Profit: $%.2f (%.0f%%)\n"
    cs.max_profit ((cs.max_profit /. cs.net_debit) *. 100.0);

  Printf.printf "\nForward Factor: %.2f (%.0f%%)\n"
    cs.forward_vol.forward_factor
    (cs.forward_vol.forward_factor *. 100.0)
