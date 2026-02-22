(** Main liquidity analysis orchestration *)

open Types

let array_mean arr =
  let n = Array.length arr in
  if n = 0 then 0.0
  else Array.fold_left ( +. ) 0.0 arr /. float_of_int n

let array_tail arr n =
  let len = Array.length arr in
  if n >= len then arr
  else Array.sub arr (len - n) n

(** Analyze a single ticker *)
let analyze_ticker (data : ticker_data) ~window : analysis_result option =
  let ohlcv = data.ohlcv in
  let n = Array.length ohlcv.close in
  if n < 30 then None
  else begin
    let price = ohlcv.close.(n - 1) in
    let avg_vol = array_mean (array_tail ohlcv.volume window) in
    let avg_dollar_vol = array_mean (Array.init window (fun i ->
      let idx = n - window + i in
      ohlcv.close.(idx) *. ohlcv.volume.(idx))) in

    let liquidity = Scoring.compute_metrics data ~window in
    let signals = Signals.compute_signals data ~window in

    Some {
      ticker = data.ticker;
      price;
      market_cap = data.market_cap;
      avg_volume = avg_vol;
      avg_dollar_volume = avg_dollar_vol;
      liquidity;
      signals;
    }
  end

(** Analyze all tickers *)
let analyze_all (data_list : ticker_data list) ~window : analysis_result list =
  List.filter_map (analyze_ticker ~window) data_list

(** Sort results by liquidity score (descending) *)
let sort_by_liquidity results =
  List.sort (fun a b ->
    compare b.liquidity.liquidity_score a.liquidity.liquidity_score) results

(** Format currency for display *)
let format_currency value =
  if abs_float value >= 1e12 then Printf.sprintf "$%.2fT" (value /. 1e12)
  else if abs_float value >= 1e9 then Printf.sprintf "$%.2fB" (value /. 1e9)
  else if abs_float value >= 1e6 then Printf.sprintf "$%.2fM" (value /. 1e6)
  else Printf.sprintf "$%.0f" value

(** Print single result *)
let print_result (r : analysis_result) =
  let green = "\027[0;32m" in
  let yellow = "\027[0;33m" in
  let red = "\027[1;31m" in
  let reset = "\027[0m" in

  let tier_color = match r.liquidity.liquidity_tier with
    | "Excellent" | "Good" -> green
    | "Fair" -> yellow
    | _ -> red
  in

  let sig_color = match r.signals.composite_signal with
    | "Strong Bullish" | "Bullish" -> green
    | "Strong Bearish" | "Bearish" -> red
    | _ -> yellow
  in

  Printf.printf "\n================================================================================\n";
  Printf.printf "Liquidity Analysis: %s\n" r.ticker;
  Printf.printf "================================================================================\n\n";

  Printf.printf "Market Data:\n";
  Printf.printf "  Price: $%.2f\n" r.price;
  Printf.printf "  Market Cap: %s\n" (format_currency r.market_cap);
  Printf.printf "  Avg Daily Volume: %.0f\n" r.avg_volume;
  Printf.printf "  Avg Dollar Volume: %s\n" (format_currency r.avg_dollar_volume);

  Printf.printf "\nLiquidity Scoring:\n";
  Printf.printf "  Liquidity Score: %s%.0f/100 (%s)%s\n"
    tier_color r.liquidity.liquidity_score r.liquidity.liquidity_tier reset;
  Printf.printf "  Amihud Ratio: %.4f (lower = more liquid)\n" r.liquidity.amihud_ratio;
  Printf.printf "  Turnover Ratio: %.4f (higher = more liquid)\n" r.liquidity.turnover_ratio;
  Printf.printf "  Relative Volume: %.2fx average\n" r.liquidity.relative_volume;
  Printf.printf "  Volume Volatility: %.2f (lower = more stable)\n" r.liquidity.volume_volatility;
  Printf.printf "  Spread Proxy: %.2f%% (lower = tighter spread)\n" r.liquidity.spread_proxy;

  Printf.printf "\nPredictive Signals:\n";
  Printf.printf "  OBV Signal: %s (strength: %.1f)\n" r.signals.obv_signal r.signals.obv_strength;
  Printf.printf "  Volume Surge: %s (%.2fx)\n"
    (if r.signals.volume_surge then "YES" else "No") r.signals.surge_magnitude;
  Printf.printf "  Volume Trend: %s (%+.1f%%/day)\n" r.signals.volume_trend r.signals.volume_trend_slope;
  Printf.printf "  Vol-Price Confirm: %s (r=%.2f)\n" r.signals.vp_confirmation r.signals.vp_correlation;
  Printf.printf "  Smart Money: %s (%+.2f)\n" r.signals.smart_money_signal r.signals.smart_money_flow;

  Printf.printf "\nComposite Signal: %s%s%s (score: %+.1f)\n"
    sig_color r.signals.composite_signal reset r.signals.signal_score

(** Print summary table *)
let print_summary results =
  let green = "\027[0;32m" in
  let yellow = "\027[0;33m" in
  let red = "\027[1;31m" in
  let reset = "\027[0m" in

  Printf.printf "\n%s\n" (String.make 110 '=');
  Printf.printf "Liquidity Analysis Summary\n";
  Printf.printf "%s\n" (String.make 110 '=');
  Printf.printf "%-8s %10s %10s %-10s %8s %18s %-15s\n"
    "Ticker" "Price" "Liq Score" "Tier" "RelVol" "OBV" "Signal";
  Printf.printf "%s\n" (String.make 110 '-');

  List.iter (fun r ->
    let tier_str = match r.liquidity.liquidity_tier with
      | "Excellent" | "Good" -> Printf.sprintf "%s%-10s%s" green r.liquidity.liquidity_tier reset
      | "Fair" -> Printf.sprintf "%s%-10s%s" yellow r.liquidity.liquidity_tier reset
      | _ -> Printf.sprintf "%s%-10s%s" red r.liquidity.liquidity_tier reset
    in
    let sig_str = match r.signals.composite_signal with
      | "Strong Bullish" | "Bullish" -> Printf.sprintf "%s%-15s%s" green r.signals.composite_signal reset
      | "Strong Bearish" | "Bearish" -> Printf.sprintf "%s%-15s%s" red r.signals.composite_signal reset
      | _ -> Printf.sprintf "%s%-15s%s" yellow r.signals.composite_signal reset
    in
    Printf.printf "%-8s $%8.2f %9.0f %s %7.2fx %18s %s\n"
      r.ticker r.price r.liquidity.liquidity_score tier_str
      r.liquidity.relative_volume r.signals.obv_signal sig_str
  ) results;

  Printf.printf "%s\n" (String.make 110 '=')
