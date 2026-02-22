(** Relative valuation scoring and signal generation *)

open Types

(** Calculate relative valuation score (0-100, higher = more undervalued)
    Based on average premium/discount vs peers *)
let calculate_relative_score (comparisons : multiple_comparison list) : float =
  if List.length comparisons = 0 then 50.0
  else
    (* Calculate average premium across all multiples *)
    let valid_comps = List.filter (fun c -> c.target_value > 0.0) comparisons in
    if List.length valid_comps = 0 then 50.0
    else
      let sorted_premiums =
        List.map (fun c -> c.premium_pct) valid_comps
        |> List.sort compare
      in
      let n = List.length sorted_premiums in
      let median_premium =
        if n mod 2 = 1 then List.nth sorted_premiums (n / 2)
        else
          let lo = List.nth sorted_premiums (n / 2 - 1) in
          let hi = List.nth sorted_premiums (n / 2) in
          (lo +. hi) /. 2.0
      in
      (* Convert premium to score: -50% premium = 100, +50% premium = 0 *)
      let score = 50.0 -. median_premium in
      max 0.0 (min 100.0 score)

(** Determine relative assessment based on score *)
let determine_assessment (score : float) : relative_assessment =
  if score >= 75.0 then VeryUndervalued
  else if score >= 60.0 then Undervalued
  else if score >= 40.0 then FairlyValued
  else if score >= 25.0 then Overvalued
  else VeryOvervalued

(** Determine signal based on score and fundamentals *)
let determine_signal (target : company_data) (score : float) : relative_signal =
  (* Check for fundamental quality *)
  let has_good_growth = target.revenue_growth > 0.10 in
  let has_good_margins = target.ebitda_margin > 0.15 in
  let has_good_roe = target.roe > 0.12 in
  let quality_count =
    (if has_good_growth then 1 else 0) +
    (if has_good_margins then 1 else 0) +
    (if has_good_roe then 1 else 0)
  in

  if score >= 70.0 && quality_count >= 2 then StrongBuy
  else if score >= 60.0 then Buy
  else if score >= 40.0 then Hold
  else if score >= 25.0 then Caution
  else Sell

(** Calculate fair premium based on growth/margin advantage *)
let calculate_fair_premium (target : company_data) (peer_median_growth : float) (peer_median_margin : float) : float =
  let growth_diff = (target.revenue_growth -. peer_median_growth) *. 100.0 in
  let margin_diff = (target.ebitda_margin -. peer_median_margin) *. 100.0 in

  (* Each 5pp growth advantage = 10% fair premium *)
  let growth_premium = (growth_diff /. 5.0) *. 10.0 in

  (* Each 5pp margin advantage = 5% fair premium *)
  let margin_premium = (margin_diff /. 5.0) *. 5.0 in

  (* Cap total fair premium at 50% *)
  min 50.0 (max (-30.0) (growth_premium +. margin_premium))

(** Generate analysis summary *)
let generate_summary (target : company_data) (comparisons : multiple_comparison list) (avg_implied : float option) : string list =
  let current = target.current_price in

  let upside_text =
    match avg_implied with
    | Some implied ->
        let pct = (implied -. current) /. current *. 100.0 in
        if pct > 0.0 then Printf.sprintf "%.0f%% upside to peer-implied value ($%.2f)" pct implied
        else Printf.sprintf "%.0f%% downside to peer-implied value ($%.2f)" (abs_float pct) implied
    | None -> "Insufficient data for implied value"
  in

  (* Count premiums/discounts *)
  let at_premium = List.filter (fun c -> c.premium_pct > 10.0) comparisons in
  let at_discount = List.filter (fun c -> c.premium_pct < -10.0) comparisons in

  let premium_text =
    if List.length at_premium > List.length at_discount then
      Printf.sprintf "Trading at premium on %d of %d multiples" (List.length at_premium) (List.length comparisons)
    else if List.length at_discount > List.length at_premium then
      Printf.sprintf "Trading at discount on %d of %d multiples" (List.length at_discount) (List.length comparisons)
    else
      "Mixed valuation signals vs peers"
  in

  [upside_text; premium_text]

(** Full analysis combining all components *)
let analyze (peer_data : peer_data) : relative_result =
  let target = peer_data.target in
  let peers = peer_data.peers in

  (* Score peer similarities *)
  let similarities = Peer_selection.score_peers target peers in

  (* Compare multiples *)
  let comparisons = Multiples.compare_all_multiples target peers in

  (* Calculate implied valuations *)
  let implied_vals = Multiples.calculate_implied_valuations target comparisons in
  let avg_implied = Multiples.average_implied_price implied_vals in

  (* Calculate score and signals *)
  let score = calculate_relative_score comparisons in
  let assessment = determine_assessment score in
  let signal = determine_signal target score in

  {
    ticker = target.ticker;
    company_name = target.company_name;
    sector = target.sector;
    current_price = target.current_price;
    peer_count = List.length peers;
    peer_similarities = similarities;
    multiple_comparisons = comparisons;
    implied_valuations = implied_vals;
    average_implied_price = avg_implied;
    relative_score = score;
    assessment;
    signal;
  }
