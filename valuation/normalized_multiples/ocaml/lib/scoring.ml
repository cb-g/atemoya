(** Scoring and signal generation - Implementation *)

open Types

let composite_percentile comparisons =
  let valid = List.filter (fun c -> c.multiple.is_valid) comparisons in
  if List.length valid = 0 then 50.0
  else
    let sum = List.fold_left (fun acc c -> acc +. c.percentile_rank) 0.0 valid in
    sum /. float_of_int (List.length valid)

let quality_adjusted_percentile raw_pct quality_adj =
  (* Quality adjustment shifts the percentile down (better) if company has premium qualities *)
  (* A company with +16% quality premium should have its percentile reduced by ~16 points *)
  let adjusted = raw_pct -. quality_adj.total_fair_premium_pct in
  max 0.0 (min 100.0 adjusted)

let overall_signal pct =
  signal_of_percentile pct true

let confidence_score comparisons =
  (* Confidence based on:
     1. Number of valid multiples (more data = higher confidence)
     2. Agreement between multiples (lower std dev = higher confidence) *)
  let valid = List.filter (fun c -> c.multiple.is_valid) comparisons in
  let n = List.length valid in
  if n = 0 then 0.0
  else
    let data_score = min 50.0 (float_of_int n *. 5.0) in
    let percentiles = List.map (fun c -> c.percentile_rank) valid in
    let mean = List.fold_left (+.) 0.0 percentiles /. float_of_int n in
    let variance =
      List.fold_left (fun acc p -> acc +. (p -. mean) ** 2.0) 0.0 percentiles
      /. float_of_int n
    in
    let std_dev = sqrt variance in
    (* Lower std dev = higher agreement = higher confidence *)
    let agreement_score = max 0.0 (50.0 -. std_dev) in
    data_score +. agreement_score

let find_extremes comparisons =
  let valid = List.filter (fun c -> c.multiple.is_valid) comparisons in
  if List.length valid = 0 then ("N/A", "N/A")
  else
    let sorted = List.sort (fun a b -> compare a.percentile_rank b.percentile_rank) valid in
    let cheapest = List.hd sorted in
    let most_exp = List.hd (List.rev sorted) in
    let name_with_tw m =
      Printf.sprintf "%s (%s)" m.multiple.name (string_of_time_window m.multiple.time_window)
    in
    (name_with_tw cheapest, name_with_tw most_exp)

let generate_summary (company : company_multiples) (comparisons : multiple_vs_benchmark list) (quality_adj : quality_adjustment) (avg_implied : float option) : string list =
  let valid = List.filter (fun c -> c.multiple.is_valid) comparisons in
  let summaries = ref [] in

  (* Premium/discount summary *)
  let avg_premium =
    if List.length valid > 0 then
      let sum = List.fold_left (fun acc c -> acc +. c.premium_discount_pct) 0.0 valid in
      sum /. float_of_int (List.length valid)
    else 0.0
  in
  if abs_float avg_premium > 5.0 then begin
    let direction = if avg_premium > 0.0 then "premium" else "discount" in
    summaries := Printf.sprintf "Trading at %.0f%% %s on average vs sector"
      (abs_float avg_premium) direction :: !summaries
  end;

  (* Quality-adjusted commentary *)
  if abs_float quality_adj.total_fair_premium_pct > 5.0 then begin
    if quality_adj.total_fair_premium_pct > 0.0 then
      summaries := Printf.sprintf "Superior quality metrics justify %.0f%% premium"
        quality_adj.total_fair_premium_pct :: !summaries
    else
      summaries := Printf.sprintf "Below-average quality suggests %.0f%% discount warranted"
        (abs_float quality_adj.total_fair_premium_pct) :: !summaries
  end;

  (* Upside/downside *)
  (match avg_implied with
   | Some implied when implied > 0.0 ->
     let upside = (implied -. company.current_price) /. company.current_price *. 100.0 in
     if abs_float upside > 5.0 then begin
       let direction = if upside > 0.0 then "upside" else "downside" in
       summaries := Printf.sprintf "%.0f%% %s to average implied price of $%.2f"
         (abs_float upside) direction implied :: !summaries
     end
   | _ -> ());

  List.rev !summaries

let analyze_single (company : company_multiples) (benchmark : benchmark_stats) : single_ticker_result =
  let now = Unix.gettimeofday () |> Unix.gmtime in
  let analysis_date = Printf.sprintf "%04d-%02d-%02d"
    (now.Unix.tm_year + 1900) (now.Unix.tm_mon + 1) now.Unix.tm_mday
  in

  (* Compare each multiple to benchmark *)
  let compare_multiple m =
    match Benchmarks.get_benchmark_for_multiple m.name m.time_window benchmark with
    | Some (median, p25, p75) ->
      Some (Benchmarks.compare_to_benchmark m
              ~benchmark_median:median ~benchmark_p25:p25 ~benchmark_p75:p75
              ~current_price:company.current_price
              ~market_cap:company.market_cap
              ~enterprise_value:company.enterprise_value)
    | None -> None
  in

  let price_mults = Multiples.get_price_multiples company in
  let ev_mults = Multiples.get_ev_multiples company in

  let price_comparisons = List.filter_map compare_multiple price_mults in
  let ev_comparisons = List.filter_map compare_multiple ev_mults in
  let all_comparisons = price_comparisons @ ev_comparisons in

  (* Quality adjustment *)
  let quality_adj = Benchmarks.calculate_quality_adjustment company benchmark in

  (* Composite scores *)
  let raw_percentile = composite_percentile all_comparisons in
  let adj_percentile = quality_adjusted_percentile raw_percentile quality_adj in

  (* Implied prices *)
  let implied_list = List.filter_map (fun c ->
    match c.implied_price with
    | Some p when p > 0.0 ->
      let name = Printf.sprintf "%s (%s)"
        c.multiple.name (string_of_time_window c.multiple.time_window) in
      Some (name, p)
    | _ -> None
  ) all_comparisons in

  let avg_implied =
    if List.length implied_list > 0 then
      let sum = List.fold_left (fun acc (_, p) -> acc +. p) 0.0 implied_list in
      Some (sum /. float_of_int (List.length implied_list))
    else None
  in

  let median_implied =
    if List.length implied_list > 0 then
      let sorted = List.sort (fun (_, a) (_, b) -> compare a b) implied_list in
      let n = List.length sorted in
      Some (snd (List.nth sorted (n / 2)))
    else None
  in

  let (cheapest, most_exp) = find_extremes all_comparisons in
  let signal = overall_signal adj_percentile in
  let conf = confidence_score all_comparisons in
  let summary = generate_summary company all_comparisons quality_adj avg_implied in

  {
    ticker = company.ticker;
    company_name = company.company_name;
    sector = company.sector;
    industry = company.industry;
    current_price = company.current_price;
    analysis_date;
    price_multiples = price_comparisons;
    ev_multiples = ev_comparisons;
    benchmark;
    quality_adj;
    composite_percentile = raw_percentile;
    quality_adjusted_percentile = adj_percentile;
    implied_prices = implied_list;
    average_implied_price = avg_implied;
    median_implied_price = median_implied;
    overall_signal = signal;
    confidence = conf;
    cheapest_multiple = cheapest;
    most_expensive_multiple = most_exp;
    summary;
  }

let rank_by_multiple (get_multiple : company_multiples -> normalized_multiple) (companies : company_multiples list) : ranking_entry list =
  let entries = List.map (fun (c : company_multiples) ->
    let m = get_multiple c in
    let signal = signal_of_percentile 50.0 m.is_valid in
    { ticker = c.ticker; value = m.value; signal }
  ) companies in
  List.sort (fun a b -> compare a.value b.value) entries

let analyze_comparative (companies : company_multiples list) (benchmark : benchmark_stats) : comparative_result =
  let now = Unix.gettimeofday () |> Unix.gmtime in
  let analysis_date = Printf.sprintf "%04d-%02d-%02d"
    (now.Unix.tm_year + 1900) (now.Unix.tm_mon + 1) now.Unix.tm_mday
  in

  (* Analyze each company individually *)
  let individual = List.map (fun c -> analyze_single c benchmark) companies in

  (* Rankings *)
  let pe_ttm_rank = rank_by_multiple (fun c -> c.pe_ttm) companies in
  let pe_ntm_rank = rank_by_multiple (fun c -> c.pe_ntm) companies in
  let ev_ebitda_rank = rank_by_multiple (fun c -> c.ev_ebitda_ttm) companies in
  let peg_rank = rank_by_multiple (fun c -> c.peg_ratio) companies in

  (* Value score (inverse of average percentile - lower percentile = higher value score) *)
  let value_scores = List.map (fun (r : single_ticker_result) ->
    (r.ticker, 100.0 -. r.composite_percentile)
  ) individual in
  let value_sorted = List.sort (fun (_, a) (_, b) -> compare b a) value_scores in

  (* Quality-adjusted scores *)
  let qa_scores = List.map (fun (r : single_ticker_result) ->
    (r.ticker, 100.0 -. r.quality_adjusted_percentile)
  ) individual in
  let qa_sorted = List.sort (fun (_, a) (_, b) -> compare b a) qa_scores in

  let best_value = match value_sorted with (t, _) :: _ -> Some t | [] -> None in
  let best_qa = match qa_sorted with (t, _) :: _ -> Some t | [] -> None in
  let best_peg = match peg_rank with
    | { ticker; value; _ } :: _ when value > 0.0 -> Some ticker
    | _ -> None
  in

  {
    tickers = List.map (fun (c : company_multiples) -> c.ticker) companies;
    sector = benchmark.sector;
    analysis_date;
    pe_ttm_ranking = pe_ttm_rank;
    pe_ntm_ranking = pe_ntm_rank;
    ev_ebitda_ranking = ev_ebitda_rank;
    peg_ranking = peg_rank;
    value_score_ranking = value_sorted;
    quality_adjusted_ranking = qa_sorted;
    best_value;
    best_quality_adjusted = best_qa;
    best_peg;
    individual_results = individual;
  }
