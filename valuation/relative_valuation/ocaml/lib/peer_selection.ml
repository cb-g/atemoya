(** Peer selection and similarity scoring *)

open Types

(** Score industry similarity (0-30)
    Same sub-industry = 30
    Same industry = 20
    Same sector = 10 *)
let score_industry (target : company_data) (peer : company_data) : float =
  if target.industry = peer.industry then 30.0
  else if target.sector = peer.sector then 15.0
  else 0.0

(** Score size similarity (0-25)
    Based on market cap ratio *)
let score_size (target : company_data) (peer : company_data) : float =
  if target.market_cap <= 0.0 || peer.market_cap <= 0.0 then 0.0
  else
    let ratio = peer.market_cap /. target.market_cap in
    if ratio >= 0.5 && ratio <= 2.0 then 25.0
    else if ratio >= 0.25 && ratio <= 4.0 then 18.0
    else if ratio >= 0.1 && ratio <= 10.0 then 10.0
    else 5.0

(** Score growth similarity (0-25)
    Based on revenue growth difference *)
let score_growth (target : company_data) (peer : company_data) : float =
  let growth_diff = abs_float (peer.revenue_growth -. target.revenue_growth) *. 100.0 in
  if growth_diff < 5.0 then 25.0
  else if growth_diff < 10.0 then 18.0
  else if growth_diff < 20.0 then 10.0
  else if growth_diff < 30.0 then 5.0
  else 0.0

(** Score profitability similarity (0-20)
    Based on margin difference *)
let score_profitability (target : company_data) (peer : company_data) : float =
  let margin_diff = abs_float (peer.ebitda_margin -. target.ebitda_margin) *. 100.0 in
  if margin_diff < 5.0 then 20.0
  else if margin_diff < 10.0 then 14.0
  else if margin_diff < 15.0 then 8.0
  else if margin_diff < 25.0 then 4.0
  else 0.0

(** Calculate overall peer similarity score *)
let calculate_similarity (target : company_data) (peer : company_data) : similarity_score =
  let industry_score = score_industry target peer in
  let size_score = score_size target peer in
  let growth_score = score_growth target peer in
  let profitability_score = score_profitability target peer in
  let total_score = industry_score +. size_score +. growth_score +. profitability_score in
  {
    ticker = peer.ticker;
    total_score;
    industry_score;
    size_score;
    growth_score;
    profitability_score;
  }

(** Score all peers and sort by similarity *)
let score_peers (target : company_data) (peers : company_data list) : similarity_score list =
  let scores = List.map (calculate_similarity target) peers in
  List.sort (fun a b -> compare b.total_score a.total_score) scores

(** Filter peers by minimum similarity score *)
let filter_by_similarity (min_score : float) (scores : similarity_score list) : similarity_score list =
  List.filter (fun s -> s.total_score >= min_score) scores

(** Get best n peers by similarity *)
let top_peers (n : int) (scores : similarity_score list) : similarity_score list =
  let rec take acc count = function
    | [] -> List.rev acc
    | _ when count = 0 -> List.rev acc
    | h :: t -> take (h :: acc) (count - 1) t
  in
  take [] n scores

(** Calculate average similarity score *)
let average_similarity (scores : similarity_score list) : float =
  if List.length scores = 0 then 0.0
  else
    let sum = List.fold_left (fun acc s -> acc +. s.total_score) 0.0 scores in
    sum /. float_of_int (List.length scores)

(** Classify peer quality *)
let classify_peer_quality (avg_score : float) : string =
  if avg_score >= 75.0 then "Excellent"
  else if avg_score >= 60.0 then "Good"
  else if avg_score >= 45.0 then "Adequate"
  else if avg_score >= 30.0 then "Marginal"
  else "Poor"
