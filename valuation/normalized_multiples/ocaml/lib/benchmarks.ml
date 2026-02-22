(** Sector and industry benchmark operations - Implementation *)

open Types

let percentile_rank value p25 median p75 =
  (* Estimate percentile using linear interpolation between known points *)
  if value <= p25 then
    25.0 *. (value /. p25)
  else if value <= median then
    25.0 +. 25.0 *. ((value -. p25) /. (median -. p25))
  else if value <= p75 then
    50.0 +. 25.0 *. ((value -. median) /. (p75 -. median))
  else
    (* Extrapolate above p75 *)
    let range = p75 -. median in
    if range > 0.0 then
      min 100.0 (75.0 +. 25.0 *. ((value -. p75) /. range))
    else
      75.0

let compare_to_benchmark
    (multiple : normalized_multiple) ~benchmark_median ~benchmark_p25 ~benchmark_p75
    ~current_price ~market_cap ~enterprise_value =
  let premium_discount_pct =
    if benchmark_median > 0.0 then
      (multiple.value -. benchmark_median) /. benchmark_median *. 100.0
    else 0.0
  in
  let pct_rank =
    if multiple.is_valid && benchmark_p25 > 0.0 then
      percentile_rank multiple.value benchmark_p25 benchmark_median benchmark_p75
    else 0.0
  in
  (* Calculate implied price at benchmark median *)
  let implied_price =
    if multiple.is_valid && benchmark_median > 0.0 && multiple.underlying_metric > 0.0 then
      let is_ev_multiple = String.length multiple.name >= 2 &&
                           String.sub multiple.name 0 2 = "EV" in
      if is_ev_multiple then
        (* EV multiple: implied_EV = metric * benchmark_multiple *)
        (* implied_equity = implied_EV - debt + cash *)
        (* implied_price = implied_equity / shares *)
        let implied_ev = multiple.underlying_metric *. benchmark_median in
        let debt = enterprise_value -. market_cap in
        let implied_equity = implied_ev -. debt in
        if implied_equity > 0.0 && current_price > 0.0 then
          Some (implied_equity /. market_cap *. current_price)
        else None
      else
        (* Price multiple: implied_price = metric * benchmark_multiple *)
        Some (multiple.underlying_metric *. benchmark_median)
    else None
  in
  {
    multiple;
    benchmark_median;
    benchmark_p25;
    benchmark_p75;
    premium_discount_pct;
    percentile_rank = pct_rank;
    implied_price;
  }

let calculate_quality_adjustment company benchmark =
  (* Growth premium: +/- based on revenue growth vs sector *)
  let growth_premium_pct =
    if benchmark.revenue_growth_median > 0.0 then
      let growth_diff = company.revenue_growth_ttm -. benchmark.revenue_growth_median in
      growth_diff /. benchmark.revenue_growth_median *. 10.0  (* Scale to reasonable % *)
    else 0.0
  in
  (* Margin premium: +/- based on EBITDA margin vs sector *)
  let margin_premium_pct =
    if benchmark.ebitda_margin_median > 0.0 then
      let margin_diff = company.ebitda_margin -. benchmark.ebitda_margin_median in
      margin_diff /. benchmark.ebitda_margin_median *. 10.0
    else 0.0
  in
  (* Return premium: +/- based on ROE vs sector *)
  let return_premium_pct =
    if benchmark.roe_median > 0.0 then
      let roe_diff = company.roe -. benchmark.roe_median in
      roe_diff /. benchmark.roe_median *. 5.0
    else 0.0
  in
  (* Clamp adjustments to reasonable range *)
  let clamp v = max (-20.0) (min 20.0 v) in
  let g = clamp growth_premium_pct in
  let m = clamp margin_premium_pct in
  let r = clamp return_premium_pct in
  {
    growth_premium_pct = g;
    margin_premium_pct = m;
    return_premium_pct = r;
    total_fair_premium_pct = g +. m +. r;
  }

let get_benchmark_for_multiple name tw benchmark =
  match name, tw with
  | "P/E", TTM -> Some (benchmark.pe_ttm_median, benchmark.pe_ttm_p25, benchmark.pe_ttm_p75)
  | "P/E", NTM -> Some (benchmark.pe_ntm_median, benchmark.pe_ntm_p25, benchmark.pe_ntm_p75)
  | "P/S", TTM -> Some (benchmark.ps_median, benchmark.ps_p25, benchmark.ps_p75)
  | "P/B", TTM -> Some (benchmark.pb_median, benchmark.pb_p25, benchmark.pb_p75)
  | "P/FCF", TTM -> Some (benchmark.p_fcf_median, benchmark.p_fcf_p25, benchmark.p_fcf_p75)
  | "PEG", _ -> Some (benchmark.peg_median, benchmark.peg_p25, benchmark.peg_p75)
  | "EV/EBITDA", TTM -> Some (benchmark.ev_ebitda_median, benchmark.ev_ebitda_p25, benchmark.ev_ebitda_p75)
  | "EV/EBIT", TTM -> Some (benchmark.ev_ebit_median, benchmark.ev_ebit_median *. 0.7, benchmark.ev_ebit_median *. 1.3)
  | "EV/Sales", TTM -> Some (benchmark.ev_sales_median, benchmark.ev_sales_median *. 0.7, benchmark.ev_sales_median *. 1.3)
  | "EV/FCF", TTM -> Some (benchmark.ev_fcf_median, benchmark.ev_fcf_median *. 0.7, benchmark.ev_fcf_median *. 1.3)
  | _ -> None
