(** Valuation multiples calculations and statistics *)

open Types

(** Calculate statistics for a list of values *)
let calculate_stats (values : float list) : peer_stats option =
  let valid = List.filter (fun v -> v > 0.0 && v < 1000.0) values in
  if List.length valid < 2 then None
  else
    let sorted = List.sort compare valid in
    let n = List.length sorted in
    let sum = List.fold_left ( +. ) 0.0 sorted in
    let mean = sum /. float_of_int n in

    (* Median *)
    let median =
      if n mod 2 = 0 then
        let mid = n / 2 in
        (List.nth sorted (mid - 1) +. List.nth sorted mid) /. 2.0
      else
        List.nth sorted (n / 2)
    in

    (* Min/Max *)
    let min_val = List.hd sorted in
    let max_val = List.nth sorted (n - 1) in

    (* Standard deviation *)
    let variance =
      List.fold_left (fun acc v -> acc +. (v -. mean) ** 2.0) 0.0 sorted /. float_of_int n
    in
    let std_dev = sqrt variance in

    Some { median; mean; min = min_val; max = max_val; std_dev }

(** Extract a specific multiple from company data *)
let get_multiple (name : string) (data : company_data) : float =
  match name with
  | "P/E (Trailing)" -> data.trailing_pe
  | "P/E (Forward)" -> data.forward_pe
  | "P/B" -> data.pb_ratio
  | "P/S" -> data.ps_ratio
  | "P/FCF" -> data.p_fcf
  | "EV/EBITDA" -> data.ev_ebitda
  | "EV/EBIT" -> data.ev_ebit
  | "EV/Revenue" -> data.ev_revenue
  | _ -> 0.0

(** Get the metric used for implied value calculation *)
let get_metric_for_multiple (name : string) (data : company_data) : float =
  match name with
  | "P/E (Trailing)" -> data.trailing_eps
  | "P/E (Forward)" -> data.forward_eps
  | "P/B" -> data.book_value
  | "P/S" -> data.revenue_per_share
  | "P/FCF" -> data.fcf_per_share
  | "EV/EBITDA" -> data.ebitda /. data.shares_outstanding
  | "EV/EBIT" -> data.operating_income /. data.shares_outstanding
  | "EV/Revenue" -> data.revenue /. data.shares_outstanding
  | _ -> 0.0

(** Calculate implied price from peer multiple *)
let calculate_implied_price (multiple_name : string) (target : company_data) (peer_median : float) : float option =
  let metric = get_metric_for_multiple multiple_name target in
  if metric <= 0.0 || peer_median <= 0.0 then None
  else
    (* For EV multiples, need to convert back to equity value *)
    let is_ev_multiple = String.sub multiple_name 0 2 = "EV" in
    if is_ev_multiple then
      let ev_per_share = metric *. peer_median in
      let debt_per_share = (target.enterprise_value -. target.market_cap) /. target.shares_outstanding in
      let equity_per_share = ev_per_share -. debt_per_share in
      if equity_per_share > 0.0 then Some equity_per_share else None
    else
      Some (metric *. peer_median)

(** Calculate premium/discount vs peer median *)
let calculate_premium (target_multiple : float) (peer_median : float) : float =
  if peer_median <= 0.0 then 0.0
  else (target_multiple -. peer_median) /. peer_median *. 100.0

(** Calculate percentile of target in peer range *)
let calculate_percentile (target_value : float) (stats : peer_stats) : float =
  if stats.max <= stats.min then 50.0
  else
    let pct = (target_value -. stats.min) /. (stats.max -. stats.min) *. 100.0 in
    max 0.0 (min 100.0 pct)

(** Compare target to peers for a specific multiple *)
let compare_multiple (multiple_name : string) (target : company_data) (peers : company_data list) : multiple_comparison option =
  let target_value = get_multiple multiple_name target in
  let peer_values = List.map (get_multiple multiple_name) peers in

  match calculate_stats peer_values with
  | None -> None
  | Some _ when target_value <= 0.0 -> None
  | Some stats ->
      let premium_pct = calculate_premium target_value stats.median in
      let percentile = calculate_percentile target_value stats in
      let implied_value = calculate_implied_price multiple_name target stats.median in
      Some {
        multiple_name;
        target_value;
        peer_stats = stats;
        premium_pct;
        percentile;
        implied_value;
      }

(** List of all multiples to analyze *)
let all_multiples = [
  "P/E (Trailing)";
  "P/E (Forward)";
  "P/B";
  "P/S";
  "P/FCF";
  "EV/EBITDA";
  "EV/EBIT";
  "EV/Revenue";
]

(** Sector-aware multiple selection.
    Excludes multiples that are meaningless or misleading for certain sectors. *)
let multiples_for_sector (sector : string) (industry : string) : string list =
  let s = String.lowercase_ascii sector in
  let ind = String.lowercase_ascii industry in
  (* Banks and diversified financials *)
  if s = "financial services"
     && (  String.length ind >= 4 && String.sub ind 0 4 = "bank"
        || ind = "capital markets"
        || ind = "diversified financial services"
        || ind = "financial data & stock exchanges") then
    ["P/E (Trailing)"; "P/E (Forward)"; "P/B"; "P/S"]
  (* Insurance *)
  else if s = "financial services"
          && (  String.length ind >= 9 && String.sub ind 0 9 = "insurance"
             || ind = "insurance-diversified"
             || ind = "insurance-life"
             || ind = "insurance-property & casualty"
             || ind = "insurance brokers") then
    ["P/E (Trailing)"; "P/E (Forward)"; "P/B"; "P/S"]
  (* REITs *)
  else if s = "real estate" then
    ["P/B"; "P/FCF"; "EV/EBITDA"; "EV/Revenue"]
  (* Oil & Gas *)
  else if ind = "oil & gas integrated"
          || ind = "oil & gas e&p"
          || ind = "oil & gas exploration & production"
          || ind = "oil & gas midstream"
          || ind = "oil & gas refining & marketing"
          || ind = "oil & gas equipment & services" then
    ["EV/EBITDA"; "EV/EBIT"; "EV/Revenue"; "P/B"; "P/E (Forward)"]
  (* Utilities *)
  else if s = "utilities" then
    ["EV/EBITDA"; "EV/Revenue"; "P/E (Trailing)"; "P/E (Forward)"; "P/B"]
  (* Default: all multiples *)
  else
    all_multiples

(** Compare target to peers across sector-appropriate multiples *)
let compare_all_multiples (target : company_data) (peers : company_data list) : multiple_comparison list =
  let multiples = multiples_for_sector target.sector target.industry in
  List.filter_map (fun name ->
    compare_multiple name target peers
  ) multiples

(** Calculate implied valuations from peer multiples *)
let calculate_implied_valuations (target : company_data) (comparisons : multiple_comparison list) : implied_valuation list =
  List.filter_map (fun comp ->
    match comp.implied_value with
    | None -> None
    | Some implied_price ->
        let upside = (implied_price -. target.current_price) /. target.current_price *. 100.0 in
        Some {
          method_name = comp.multiple_name;
          peer_multiple = comp.peer_stats.median;
          target_metric = get_metric_for_multiple comp.multiple_name target;
          implied_price;
          upside_downside_pct = upside;
        }
  ) comparisons

(** Calculate average implied price from multiple methods *)
let average_implied_price (valuations : implied_valuation list) : float option =
  let valid = List.filter (fun v -> v.implied_price > 0.0) valuations in
  if List.length valid = 0 then None
  else
    let sum = List.fold_left (fun acc v -> acc +. v.implied_price) 0.0 valid in
    Some (sum /. float_of_int (List.length valid))
