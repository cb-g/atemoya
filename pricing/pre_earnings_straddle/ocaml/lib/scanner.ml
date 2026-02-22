(** Scanner Module *)

open Types

(** Make trade recommendation *)
let make_recommendation
    ~(opportunity : straddle_opportunity)
    ~(signals : signals)
    ~(coefficients : model_coefficients)
    ~(min_predicted_return : float)
    ~(target_kelly_fraction : float)
    : recommendation option =

  (* Predict return *)
  let predicted_return = Model.predict_return ~signals ~coefficients in

  (* Filter: only recommend if predicted return > threshold *)
  if predicted_return < min_predicted_return then
    None
  else
    (* Calculate Kelly fraction *)
    let max_loss = opportunity.straddle_cost in
    let kelly_fraction = Model.calculate_kelly ~predicted_return ~max_loss in

    (* Use target Kelly fraction (e.g., 2-6% of full Kelly) *)
    let suggested_size = kelly_fraction *. target_kelly_fraction in

    (* Determine recommendation strength *)
    let recommendation =
      if predicted_return >= 0.05 then "Strong Buy"  (* ≥5% predicted *)
      else if predicted_return >= 0.02 then "Buy"    (* ≥2% predicted *)
      else "Pass"
    in

    (* Rank score for portfolio construction *)
    let rank_score = predicted_return in

    (* Notes *)
    let notes =
      let parts = [] in
      let parts = if signals.num_historical_events < 4 then
        "Limited history (< 4 events)" :: parts else parts in
      let parts = if signals.implied_vs_avg_implied_ratio < 0.8 then
        "Very cheap vs history" :: parts else parts in
      let parts = if signals.implied_vs_avg_implied_ratio > 1.2 then
        "Expensive vs history" :: parts else parts in
      let parts = if List.length parts = 0 then ["Signals look good"] else parts in
      String.concat "; " (List.rev parts)
    in

    Some {
      ticker = opportunity.ticker;
      earnings_date = opportunity.earnings_date;
      opportunity;
      signals;
      predicted_return;
      recommendation;
      rank_score;
      kelly_fraction;
      suggested_size;
      max_loss;
      notes;
    }

(** Print recommendation *)
let print_recommendation (rec_opt : recommendation option) : unit =
  match rec_opt with
  | None ->
      Printf.printf "\n✗ Does not pass filter (predicted return too low)\n"
  | Some r ->
      Printf.printf "\n";
      Printf.printf "╔════════════════════════════════════════════════════╗\n";
      Printf.printf "║  PRE-EARNINGS STRADDLE: %s\n" r.ticker;
      Printf.printf "╚════════════════════════════════════════════════════╝\n";
      Printf.printf "\n";

      (* Recommendation *)
      let color = match r.recommendation with
        | "Strong Buy" -> "\027[1;32m"  (* Bold green *)
        | "Buy" -> "\027[32m"            (* Green *)
        | _ -> "\027[33m"                (* Yellow *)
      in
      Printf.printf "%s>>> %s <<<\027[0m\n" color r.recommendation;
      Printf.printf "Predicted Return: %.2f%%\n" (r.predicted_return *. 100.0);
      Printf.printf "Rank Score: %.2f\n" r.rank_score;
      Printf.printf "\n";

      (* Opportunity details *)
      Printf.printf "=== Trade Details ===\n";
      Printf.printf "Earnings Date: %s (%d days)\n" r.earnings_date r.opportunity.days_to_earnings;
      Printf.printf "Expiration: %s (%d DTE)\n" r.opportunity.expiration r.opportunity.days_to_expiry;
      Printf.printf "Spot: $%.2f | ATM Strike: $%.2f\n"
        r.opportunity.spot_price r.opportunity.atm_strike;
      Printf.printf "Call: $%.2f | Put: $%.2f\n"
        r.opportunity.atm_call_price r.opportunity.atm_put_price;
      Printf.printf "Straddle Cost: $%.2f\n" r.opportunity.straddle_cost;
      Printf.printf "Current Implied Move: %.2f%%\n"
        (r.opportunity.current_implied_move *. 100.0);
      Printf.printf "\n";

      (* Signals *)
      Signals.print_signals r.signals;

      (* Sizing *)
      Printf.printf "\n=== Position Sizing ===\n";
      Printf.printf "Max Loss: $%.2f (debit paid)\n" r.max_loss;
      Printf.printf "Kelly Fraction: %.2f%%\n" (r.kelly_fraction *. 100.0);
      Printf.printf "Suggested Size: %.2f%% of portfolio\n" (r.suggested_size *. 100.0);
      Printf.printf "\n";

      (* Notes *)
      Printf.printf "Notes: %s\n" r.notes;

      if r.recommendation = "Strong Buy" || r.recommendation = "Buy" then begin
        Printf.printf "\n";
        Printf.printf "╔════════════════════════════════════════════════════╗\n";
        Printf.printf "║  ACTIONABLE TRADE                                  ║\n";
        Printf.printf "╚════════════════════════════════════════════════════╝\n";
        Printf.printf "Entry: Buy ATM straddle (~14 days before earnings)\n";
        Printf.printf "Exit: Day before earnings announcement\n";
        Printf.printf "Expected: Many small losses, occasional big winners\n";
      end
