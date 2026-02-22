(** Trade Scanner with Filters *)

open Types

(** Check if skew filter passes *)
let passes_skew_filter ~(skew : skew_metrics) ~(threshold : float) : bool =
  (* Extreme skew = z-score < threshold (e.g., -2.0) *)
  skew.call_skew_zscore < threshold || skew.put_skew_zscore < threshold

(** Check if IV/RV filter passes *)
let passes_ivrv_filter ~(skew : skew_metrics) ~(spread_type : string) : bool =
  (* Want positive VRP (IV > RV) meaning options are overpriced relative to realized vol.
     For vertical spreads, we're selling the OTM leg, so we want OTM IV to be expensive.
     VRP > 0 means we're collecting excess premium by selling options. *)
  let rv = skew.realized_vol_30d in
  let vrp = skew.vrp in  (* vrp = atm_iv - realized_vol *)

  match spread_type with
  | "bull_call" ->
      let otm_iv = skew.atm_call_25delta_iv in
      (* Positive VRP (options overpriced) AND OTM IV elevated vs ATM *)
      vrp > 0.0 && otm_iv > rv
  | "bear_put" ->
      let otm_iv = skew.atm_put_25delta_iv in
      vrp > 0.0 && otm_iv > rv
  | "bull_put" | "bear_call" ->
      (* Credit spreads: just need positive VRP *)
      vrp > 0.0
  | _ -> false

(** Check if momentum filter passes *)
let passes_momentum_filter ~(momentum : momentum) ~(spread_type : string) : bool =
  match spread_type with
  | "bull_call" -> momentum.momentum_score > 0.3  (* Need positive momentum *)
  | "bear_put" -> momentum.momentum_score < -0.3  (* Need negative momentum *)
  | _ -> false

(** Calculate edge score (0-100) *)
let calculate_edge_score
    ~(skew : skew_metrics)
    ~(momentum : momentum)
    ~(spread : vertical_spread)
    : float =

  (* Component scores *)
  let skew_score = match spread.spread_type with
    | "bull_call" ->
        (* More negative z-score = better *)
        max 0.0 (min 40.0 (abs_float skew.call_skew_zscore *. 10.0))
    | "bear_put" ->
        max 0.0 (min 40.0 (abs_float skew.put_skew_zscore *. 10.0))
    | _ -> 0.0
  in

  let momentum_score_pts = abs_float momentum.momentum_score *. 20.0 in

  let reward_risk_score =
    if spread.reward_risk_ratio >= 10.0 then 30.0
    else if spread.reward_risk_ratio >= 7.0 then 25.0
    else if spread.reward_risk_ratio >= 5.0 then 20.0
    else if spread.reward_risk_ratio >= 3.0 then 10.0
    else 0.0
  in

  let ev_score =
    if spread.expected_return_pct > 50.0 then 10.0
    else if spread.expected_return_pct > 20.0 then 7.0
    else if spread.expected_return_pct > 0.0 then 5.0
    else 0.0
  in

  (* Total (max 100) *)
  min 100.0 (skew_score +. momentum_score_pts +. reward_risk_score +. ev_score)

(** Generate recommendation *)
let make_recommendation
    ~(chain : options_chain)
    ~(skew : skew_metrics)
    ~(momentum : momentum)
    ~(spread : vertical_spread option)
    ~(skew_threshold : float)
    : trade_recommendation option =

  match spread with
  | None -> None
  | Some spread ->
      let passes_skew = passes_skew_filter ~skew ~threshold:skew_threshold in
      let passes_ivrv = passes_ivrv_filter ~skew ~spread_type:spread.spread_type in
      let passes_momentum = passes_momentum_filter ~momentum ~spread_type:spread.spread_type in

      let edge_score = calculate_edge_score ~skew ~momentum ~spread in

      let recommendation =
        if passes_skew && passes_ivrv && passes_momentum && edge_score >= 60.0 then
          "Strong Buy"
        else if passes_skew && passes_ivrv && passes_momentum && edge_score >= 40.0 then
          "Buy"
        else
          "Pass"
      in

      let expected_win_rate = spread.prob_profit in

      let notes =
        let parts = [] in
        let parts = if not passes_skew then "Failed skew filter" :: parts else parts in
        let parts = if not passes_ivrv then "Failed IV/RV filter" :: parts else parts in
        let parts = if not passes_momentum then "Failed momentum filter" :: parts else parts in
        let parts = if List.length parts = 0 then ["All filters passed"] else parts in
        String.concat "; " (List.rev parts)
      in

      Some {
        ticker = chain.ticker;
        timestamp = "";  (* Will be filled by caller *)
        spread;
        skew;
        momentum;
        passes_skew_filter = passes_skew;
        passes_ivrv_filter = passes_ivrv;
        passes_momentum_filter = passes_momentum;
        recommendation;
        edge_score;
        expected_win_rate;
        notes;
      }

(** Check for trade quality issues and return warnings *)
let check_trade_quality (spread : vertical_spread) ~(spot : float) : string list =
  let warnings = [] in

  (* Warning 1: Strikes too far from spot (> 60% away) *)
  let short_distance_pct = abs_float ((spread.short_strike -. spot) /. spot) *. 100.0 in
  let warnings =
    if short_distance_pct > 60.0 then
      (Printf.sprintf "Short strike ($%.2f) is %.1f%% from spot - may have wide spreads or stale pricing"
        spread.short_strike short_distance_pct) :: warnings
    else warnings
  in

  (* Warning 2: Suspiciously high reward/risk (> 50:1) *)
  let warnings =
    if spread.reward_risk_ratio > 50.0 then
      (Printf.sprintf "Extremely high reward/risk (%.1f:1) suggests short strike is unrealistic"
        spread.reward_risk_ratio) :: warnings
    else warnings
  in

  (* Warning 3: Very low probability of profit (< 15%) *)
  let warnings =
    if spread.prob_profit < 0.15 then
      (Printf.sprintf "Low probability of profit (%.1f%%) - this is a lottery-ticket trade"
        (spread.prob_profit *. 100.0)) :: warnings
    else warnings
  in

  (* Warning 4: Short option price very low (< $0.05) suggesting poor liquidity *)
  let warnings =
    if spread.short_price < 0.05 then
      (Printf.sprintf "Short option priced at $%.2f - likely illiquid, check bid/ask spread"
        spread.short_price) :: warnings
    else warnings
  in

  (* Warning 5: Debit very low (< $0.25) suggesting execution risk *)
  let warnings =
    if spread.debit < 0.25 then
      (Printf.sprintf "Spread debit only $%.2f - commissions may eat into profit"
        spread.debit) :: warnings
    else warnings
  in

  (* Warning 6: Expected return too good to be true (> 500%) *)
  let warnings =
    if spread.expected_return_pct > 500.0 then
      (Printf.sprintf "Expected return of %.0f%% is unrealistic - verify pricing data"
        spread.expected_return_pct) :: warnings
    else warnings
  in

  List.rev warnings

(** Print trade recommendation *)
let print_recommendation (rec_opt : trade_recommendation option) ~(spot : float) : unit =
  match rec_opt with
  | None ->
      Printf.printf "\n✗ No valid spread found\n"
  | Some recommendation ->
      Printf.printf "\n" ;
      Printf.printf "╔════════════════════════════════════════════════════╗\n";
      Printf.printf "║  TRADE RECOMMENDATION: %s\n" recommendation.ticker;
      Printf.printf "╚════════════════════════════════════════════════════╝\n";
      Printf.printf "\n" ;

      (* Recommendation *)
      let color = match recommendation.recommendation with
        | "Strong Buy" -> "\027[1;32m"  (* Bold green *)
        | "Buy" -> "\027[32m"            (* Green *)
        | _ -> "\027[31m"                (* Red *)
      in
      Printf.printf "%s>>> %s <<<\027[0m\n" color recommendation.recommendation;
      Printf.printf "Edge Score: %.0f/100\n" recommendation.edge_score;
      Printf.printf "\n";

      (* Spread details *)
      Spreads.print_vertical_spread recommendation.spread;

      (* Trade quality warnings *)
      let warnings = check_trade_quality recommendation.spread ~spot in
      if List.length warnings > 0 then begin
        Printf.printf "\n\027[1;33m⚠ TRADE QUALITY WARNINGS:\027[0m\n";
        List.iter (fun w -> Printf.printf "  ⚠ %s\n" w) warnings;
      end;

      (* Filters *)
      Printf.printf "\n=== Filters ===\n";
      Printf.printf "Skew filter: %s\n" (if recommendation.passes_skew_filter then "✓ PASS" else "✗ FAIL");
      Printf.printf "IV/RV filter: %s\n" (if recommendation.passes_ivrv_filter then "✓ PASS" else "✗ FAIL");
      Printf.printf "Momentum filter: %s\n" (if recommendation.passes_momentum_filter then "✓ PASS" else "✗ FAIL");
      Printf.printf "\nNotes: %s\n" recommendation.notes;

      (* Key metrics *)
      Printf.printf "\n=== Key Metrics ===\n";
      Skew.print_skew_metrics recommendation.skew;
      Momentum.print_momentum recommendation.momentum;

      Printf.printf "\n";
      if recommendation.recommendation = "Strong Buy" || recommendation.recommendation = "Buy" then begin
        Printf.printf "╔════════════════════════════════════════════════════╗\n";
        Printf.printf "║  ACTIONABLE TRADE                                  ║\n";
        Printf.printf "╚════════════════════════════════════════════════════╝\n";
        Printf.printf "Expected win rate: %.1f%%\n" (recommendation.expected_win_rate *. 100.0);
        Printf.printf "Target reward/risk: %.1f:1\n" recommendation.spread.reward_risk_ratio;
      end

(** Save recommendation to JSON file *)
let save_to_json (rec_opt : trade_recommendation option) ~(output_dir : string) : unit =
  match rec_opt with
  | None -> ()
  | Some recommendation ->
      (* Get timestamp *)
      let timestamp =
        let tm = Unix.localtime (Unix.time ()) in
        Printf.sprintf "%04d-%02d-%02d_%02d-%02d-%02d"
          (tm.Unix.tm_year + 1900)
          (tm.Unix.tm_mon + 1)
          tm.Unix.tm_mday
          tm.Unix.tm_hour
          tm.Unix.tm_min
          tm.Unix.tm_sec
      in

      (* Build JSON string manually (simple approach) *)
      let json = Printf.sprintf {|{
  "ticker": "%s",
  "timestamp": "%s",
  "recommendation": "%s",
  "edge_score": %.2f,
  "spread": {
    "type": "%s",
    "expiration": "%s",
    "days_to_expiry": %d,
    "long_strike": %.2f,
    "long_delta": %.4f,
    "long_iv": %.4f,
    "long_price": %.2f,
    "short_strike": %.2f,
    "short_delta": %.4f,
    "short_iv": %.4f,
    "short_price": %.2f,
    "debit": %.2f,
    "max_profit": %.2f,
    "max_loss": %.2f,
    "reward_risk_ratio": %.2f,
    "breakeven": %.2f,
    "prob_profit": %.4f,
    "expected_value": %.2f,
    "expected_return_pct": %.2f
  },
  "skew": {
    "call_skew": %.4f,
    "call_skew_zscore": %.2f,
    "put_skew": %.4f,
    "put_skew_zscore": %.2f,
    "atm_iv": %.4f,
    "atm_call_25delta_iv": %.4f,
    "atm_put_25delta_iv": %.4f,
    "realized_vol_30d": %.4f,
    "vrp": %.4f
  },
  "momentum": {
    "return_1w": %.4f,
    "return_1m": %.4f,
    "return_3m": %.4f,
    "rank_1m": %d,
    "rank_3m": %d,
    "percentile": %.2f,
    "beta": %.4f,
    "alpha_1m": %.4f,
    "pct_from_52w_high": %.4f,
    "momentum_score": %.4f
  },
  "filters": {
    "passes_skew_filter": %s,
    "passes_ivrv_filter": %s,
    "passes_momentum_filter": %s
  },
  "expected_win_rate": %.4f,
  "notes": "%s"
}|}
        recommendation.ticker
        timestamp
        recommendation.recommendation
        recommendation.edge_score
        recommendation.spread.spread_type
        recommendation.spread.expiration
        recommendation.spread.days_to_expiry
        recommendation.spread.long_strike
        recommendation.spread.long_delta
        recommendation.spread.long_iv
        recommendation.spread.long_price
        recommendation.spread.short_strike
        recommendation.spread.short_delta
        recommendation.spread.short_iv
        recommendation.spread.short_price
        recommendation.spread.debit
        recommendation.spread.max_profit
        recommendation.spread.max_loss
        recommendation.spread.reward_risk_ratio
        recommendation.spread.breakeven
        recommendation.spread.prob_profit
        recommendation.spread.expected_value
        recommendation.spread.expected_return_pct
        recommendation.skew.call_skew
        recommendation.skew.call_skew_zscore
        recommendation.skew.put_skew
        recommendation.skew.put_skew_zscore
        recommendation.skew.atm_iv
        recommendation.skew.atm_call_25delta_iv
        recommendation.skew.atm_put_25delta_iv
        recommendation.skew.realized_vol_30d
        recommendation.skew.vrp
        recommendation.momentum.return_1w
        recommendation.momentum.return_1m
        recommendation.momentum.return_3m
        recommendation.momentum.rank_1m
        recommendation.momentum.rank_3m
        recommendation.momentum.percentile
        recommendation.momentum.beta
        recommendation.momentum.alpha_1m
        recommendation.momentum.pct_from_52w_high
        recommendation.momentum.momentum_score
        (if recommendation.passes_skew_filter then "true" else "false")
        (if recommendation.passes_ivrv_filter then "true" else "false")
        (if recommendation.passes_momentum_filter then "true" else "false")
        recommendation.expected_win_rate
        recommendation.notes
      in

      (* Ensure output directory exists *)
      let _ = Sys.command (Printf.sprintf "mkdir -p %s" output_dir) in

      (* Write to file *)
      let filename = Printf.sprintf "%s/%s_scan_%s.json"
        output_dir recommendation.ticker timestamp in
      let oc = open_out filename in
      output_string oc json;
      close_out oc;

      Printf.printf "\n✓ Results saved to: %s\n" filename
