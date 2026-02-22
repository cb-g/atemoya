(** Forward Factor Scanner and Recommendations *)

open Types
open Forward_vol
open Calendar

(** DTE pairs to scan (from backtest: 60-90 performed best) *)
let default_dte_pairs = [
  (30, 60);
  (30, 90);
  (60, 90);
]

(** Find expiration closest to target DTE *)
let find_closest_expiration
    ~(expirations : expiration_data list)
    ~(target_dte : int)
    : expiration_data option =

  let rec find_min acc_exp acc_diff = function
    | [] -> acc_exp
    | exp :: rest ->
        let diff = abs (exp.dte - target_dte) in
        if diff < acc_diff then
          find_min (Some exp) diff rest
        else
          find_min acc_exp acc_diff rest
  in

  match expirations with
  | [] -> None
  | first :: rest ->
      find_min (Some first) (abs (first.dte - target_dte)) rest

(** Scan single ticker for forward factor opportunities *)
let scan_ticker
    ~(expirations : expiration_data list)
    ~(dte_pairs : (int * int) list)
    ~(threshold : float)
    : recommendation list =

  let ticker = match expirations with
    | [] -> ""
    | exp :: _ -> exp.ticker
  in

  (* Scan each DTE pair *)
  let scan_pair (front_dte, back_dte) =
    match
      find_closest_expiration ~expirations ~target_dte:front_dte,
      find_closest_expiration ~expirations ~target_dte:back_dte
    with
    | Some front_exp, Some back_exp when front_exp.dte < back_exp.dte ->
        (* Calculate forward volatility *)
        let fv = calculate_forward_vol
          ~ticker
          ~front_exp:front_exp.expiration
          ~back_exp:back_exp.expiration
          ~front_dte:front_exp.dte
          ~back_dte:back_exp.dte
          ~front_iv:front_exp.atm_iv
          ~back_iv:back_exp.atm_iv
        in

        (* Check if passes threshold *)
        if fv.forward_factor >= threshold then
          (* Create ATM call calendar *)
          let spread = create_atm_call_calendar
            ~ticker
            ~front_exp
            ~back_exp
            ~forward_vol:fv
          in

          (* Calculate sizing and expected return *)
          let kelly = calculate_kelly_fraction ~ff:fv.forward_factor in
          let exp_return = calculate_expected_return ~ff:fv.forward_factor in

          (* Determine recommendation strength *)
          let recommendation =
            if fv.forward_factor >= 1.0 then
              "STRONG BUY"
            else if fv.forward_factor >= 0.5 then
              "BUY"
            else
              "CONSIDER"
          in

          let notes =
            if fv.forward_factor >= 1.0 then
              "Extreme backwardation - exceptional setup"
            else if fv.forward_factor >= 0.5 then
              "Strong backwardation - high quality setup"
            else
              "Moderate backwardation - valid entry"
          in

          Some {
            ticker;
            timestamp = "";  (* Set by caller *)
            spread;
            forward_factor = fv.forward_factor;
            passes_filter = true;
            kelly_fraction = kelly;
            suggested_size = kelly;
            max_loss = spread.max_loss;
            expected_return = exp_return;
            recommendation;
            notes;
          }
        else
          None
    | _ ->
        None  (* Invalid DTE pair or expirations not found *)
  in

  List.filter_map scan_pair dte_pairs

(** Scan multiple tickers and rank by forward factor *)
let scan_universe
    ~(universe : expiration_data list list)
    ~(dte_pairs : (int * int) list)
    ~(threshold : float)
    : recommendation list =

  (* Scan each ticker *)
  let all_recommendations =
    List.concat_map
      (fun expirations -> scan_ticker ~expirations ~dte_pairs ~threshold)
      universe
  in

  (* Sort by forward factor descending *)
  List.sort
    (fun r1 r2 -> compare r2.forward_factor r1.forward_factor)
    all_recommendations

(** Print recommendation *)
let print_recommendation (recom : recommendation) : unit =
  Printf.printf "\n╔════════════════════════════════════════════════════════════════╗\n";
  Printf.printf "║ %s: %s%-*s ║\n"
    recom.ticker
    recom.recommendation
    (48 - String.length recom.ticker - String.length recom.recommendation)
    "";
  Printf.printf "╚════════════════════════════════════════════════════════════════╝\n";

  Printf.printf "\nForward Factor: %.2f (%.0f%%) %s\n"
    recom.forward_factor
    (recom.forward_factor *. 100.0)
    (if recom.forward_factor >= 1.0 then "🔥 EXTREME"
     else if recom.forward_factor >= 0.5 then "⚡ STRONG"
     else "✓ VALID");

  Printf.printf "\nCalendar Spread:\n";
  Printf.printf "  Sell: %s %d-DTE ATM call @ $%.2f\n"
    recom.spread.front_exp
    recom.spread.front_dte
    (List.hd recom.spread.front_prices);
  Printf.printf "  Buy:  %s %d-DTE ATM call @ $%.2f\n"
    recom.spread.back_exp
    recom.spread.back_dte
    (List.hd recom.spread.back_prices);

  Printf.printf "\nEconomics:\n";
  Printf.printf "  Net Debit: $%.2f\n" recom.max_loss;
  Printf.printf "  Expected Return: %.0f%%\n" (recom.expected_return *. 100.0);
  Printf.printf "  Max Profit Potential: $%.2f (%.0f%%)\n"
    recom.spread.max_profit
    ((recom.spread.max_profit /. recom.spread.net_debit) *. 100.0);

  Printf.printf "\nPosition Sizing:\n";
  Printf.printf "  Suggested Size: %.1f%% of portfolio\n"
    (recom.suggested_size *. 100.0);
  Printf.printf "  Kelly Fraction: %.1f%% (quarter Kelly)\n"
    (recom.kelly_fraction *. 100.0);

  Printf.printf "\nRationale:\n";
  Printf.printf "  %s\n" recom.notes;
  Printf.printf "\n"

(** Print scanner results summary *)
let print_scanner_summary (recommendations : recommendation list) : unit =
  let total = List.length recommendations in

  if total = 0 then begin
    Printf.printf "\n╔════════════════════════════════════════════════════════════════╗\n";
    Printf.printf "║ No opportunities found meeting FF ≥ 0.20 threshold            ║\n";
    Printf.printf "╚════════════════════════════════════════════════════════════════╝\n"
  end else begin
    Printf.printf "\n╔════════════════════════════════════════════════════════════════╗\n";
    Printf.printf "║ Found %d Forward Factor Opportunities%-*s ║\n"
      total (35 - String.length (string_of_int total)) "";
    Printf.printf "╚════════════════════════════════════════════════════════════════╝\n";

    (* Summary table *)
    Printf.printf "\n%-10s %8s %12s %12s %12s\n"
      "Ticker" "FF" "Rec" "Size" "Exp Return";
    Printf.printf "%s\n" (String.make 64 '-');

    List.iter (fun recom ->
      Printf.printf "%-10s %7.1f%% %12s %11.1f%% %11.0f%%\n"
        recom.ticker
        (recom.forward_factor *. 100.0)
        recom.recommendation
        (recom.suggested_size *. 100.0)
        (recom.expected_return *. 100.0)
    ) recommendations;

    Printf.printf "\n"
  end
