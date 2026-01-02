(** Statistical analysis for probabilistic DCF *)

open Types

(** Helper: Compute percentile from sorted array *)
let percentile arr p =
  let n = Array.length arr in
  if n = 0 then 0.0
  else
    let sorted = Array.copy arr in
    Array.sort compare sorted;
    let idx = int_of_float (p *. float_of_int (n - 1)) in
    sorted.(idx)

(** Filter out inf, -inf, and nan values *)
let filter_valid arr =
  Array.of_list (
    Array.fold_left (fun acc x ->
      if classify_float x = FP_normal || classify_float x = FP_zero then x :: acc
      else acc
    ) [] arr
  )

(** Compute valuation statistics *)
let compute_statistics simulations =
  (* Filter out inf/-inf/nan values that can occur in extreme regime scenarios *)
  let valid_sims = filter_valid simulations in
  let n = Array.length valid_sims in

  if n = 0 then {
    mean = 0.0;
    std = 0.0;
    min = 0.0;
    max = 0.0;
    percentile_5 = 0.0;
    percentile_25 = 0.0;
    percentile_50 = 0.0;
    percentile_75 = 0.0;
    percentile_95 = 0.0;
  }
  else
    let mean = Sampling.mean valid_sims in
    let std = Sampling.std valid_sims in
    let min = Array.fold_left min infinity valid_sims in
    let max = Array.fold_left max neg_infinity valid_sims in

    {
      mean;
      std;
      min;
      max;
      percentile_5 = percentile valid_sims 0.05;
      percentile_25 = percentile valid_sims 0.25;
      percentile_50 = percentile valid_sims 0.50;
      percentile_75 = percentile valid_sims 0.75;
      percentile_95 = percentile valid_sims 0.95;
    }

(** Compute probability metrics *)
let compute_probability_metrics ~simulations ~price =
  (* Filter out inf/-inf/nan values *)
  let valid_sims = filter_valid simulations in
  let n = float_of_int (Array.length valid_sims) in

  if n = 0.0 then {
    prob_undervalued = 0.0;
    prob_overvalued = 0.0;
    expected_surplus = 0.0;
    expected_surplus_pct = 0.0;
  }
  else
    (* Count simulations where intrinsic > price *)
    let count_undervalued = Array.fold_left (fun acc ivps ->
      if ivps > price then acc +. 1.0 else acc
    ) 0.0 valid_sims in

    let count_overvalued = Array.fold_left (fun acc ivps ->
      if ivps < price then acc +. 1.0 else acc
    ) 0.0 valid_sims in

    (* Expected surplus *)
    let total_surplus = Array.fold_left (fun acc ivps -> acc +. (ivps -. price)) 0.0 valid_sims in
    let expected_surplus = total_surplus /. n in

    (* Expected surplus percentage *)
    let expected_surplus_pct = if price = 0.0 then 0.0 else expected_surplus /. price in

    {
      prob_undervalued = count_undervalued /. n;
      prob_overvalued = count_overvalued /. n;
      expected_surplus;
      expected_surplus_pct;
    }

(** Compute tail risk metrics (VaR, CVaR, etc.) *)
let compute_tail_risk_metrics ~simulations ~price =
  let open Types in
  let valid_sims = filter_valid simulations in
  let n = Array.length valid_sims in

  if n = 0 then {
    var_1 = 0.0;
    var_5 = 0.0;
    cvar_1 = 0.0;
    cvar_5 = 0.0;
    max_drawdown = 0.0;
    downside_deviation = 0.0;
  }
  else
    (* Sort simulations for percentile calculations *)
    let sorted = Array.copy valid_sims in
    Array.sort compare sorted;

    (* Median for drawdown calculation *)
    let median_idx = n / 2 in
    let median = sorted.(median_idx) in

    (* VaR: Loss at given percentile (from price) *)
    let idx_1 = max 0 (int_of_float (0.01 *. float_of_int n)) in
    let idx_5 = max 0 (int_of_float (0.05 *. float_of_int n)) in
    let var_1 = price -. sorted.(idx_1) in  (* Loss if IVPS is in worst 1% *)
    let var_5 = price -. sorted.(idx_5) in  (* Loss if IVPS is in worst 5% *)

    (* CVaR: Expected loss in worst X% *)
    let tail_1 = Array.sub sorted 0 (max 1 idx_1) in
    let tail_5 = Array.sub sorted 0 (max 1 idx_5) in
    let cvar_1 = if Array.length tail_1 > 0 then
      price -. (Sampling.mean tail_1)
    else var_1 in
    let cvar_5 = if Array.length tail_5 > 0 then
      price -. (Sampling.mean tail_5)
    else var_5 in

    (* Maximum drawdown from median *)
    let max_drawdown = max 0.0 (median -. sorted.(0)) in

    (* Downside deviation: std dev of returns below median *)
    let below_median = Array.of_list (
      Array.fold_left (fun acc x ->
        if x < median then x :: acc else acc
      ) [] valid_sims
    ) in
    let downside_deviation = if Array.length below_median > 0 then
      Sampling.std below_median
    else 0.0 in

    {
      var_1;
      var_5;
      cvar_1;
      cvar_5;
      max_drawdown;
      downside_deviation;
    }

(** Classify valuation *)
let classify_valuation ~mean_ivps ~price ~tolerance =
  let ratio = mean_ivps /. price in
  if ratio > (1.0 +. tolerance) then Undervalued
  else if ratio < (1.0 -. tolerance) then Overvalued
  else FairlyValued

(** Generate investment signal *)
let generate_signal ~fcfe_class ~fcff_class =
  match fcfe_class, fcff_class with
  | Undervalued, Undervalued -> StrongBuy
  | Undervalued, FairlyValued | FairlyValued, Undervalued -> Buy
  | Overvalued, Overvalued -> Avoid
  | _ -> Hold  (* Mixed or fairly valued *)

(** Convert signal to string *)
let signal_to_string = function
  | StrongBuy -> "Strong Buy"
  | Buy -> "Buy"
  | Hold -> "Hold"
  | Avoid -> "Avoid/Sell"

(** Convert signal to colored string using ANSI codes *)
let signal_to_colored_string signal =
  (* ANSI color codes *)
  let bold_green = "\027[1;32m" in      (* Strong Buy *)
  let green = "\027[0;32m" in           (* Buy *)
  let bright_yellow = "\027[0;93m" in   (* Hold *)
  let bold_red = "\027[1;31m" in        (* Avoid *)
  let reset = "\027[0m" in

  let color_code = match signal with
    | StrongBuy -> bold_green
    | Buy -> green
    | Hold -> bright_yellow
    | Avoid -> bold_red
  in

  Printf.sprintf "%s%s%s" color_code (signal_to_string signal) reset

(** Signal explanation *)
let signal_explanation = function
  | StrongBuy ->
      "Both FCFE and FCFF valuations indicate undervaluation with high probability."
  | Buy ->
      "One valuation method shows undervaluation, the other is fairly valued."
  | Hold ->
      "Mixed signals or fair valuation. Market price aligns with probabilistic estimates."
  | Avoid ->
      "Both valuation methods suggest overvaluation. High probability of downside."

(** Convert class to string *)
let class_to_string = function
  | Undervalued -> "Undervalued"
  | FairlyValued -> "Fairly Valued"
  | Overvalued -> "Overvalued"
