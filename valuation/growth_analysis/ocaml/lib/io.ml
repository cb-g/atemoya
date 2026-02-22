(** I/O functions for growth analysis *)

open Types

(** Read growth data from JSON file *)
let read_growth_data (filename : string) : growth_data =
  let json = Yojson.Basic.from_file filename in
  let open Yojson.Basic.Util in

  let to_float_safe j =
    match j with
    | `Float f -> f
    | `Int i -> float_of_int i
    | _ -> 0.0
  in

  let get_float key j = to_float_safe (j |> member key) in

  {
    ticker = json |> member "ticker" |> to_string;
    company_name = json |> member "company_name" |> to_string;
    sector = json |> member "sector" |> to_string;
    industry = json |> member "industry" |> to_string;
    current_price = get_float "current_price" json;
    market_cap = get_float "market_cap" json;
    enterprise_value = get_float "enterprise_value" json;
    shares_outstanding = get_float "shares_outstanding" json;
    revenue = get_float "revenue" json;
    revenue_growth = get_float "revenue_growth" json;
    revenue_growth_yoy = get_float "revenue_growth_yoy" json;
    revenue_cagr_3y = get_float "revenue_cagr_3y" json;
    revenue_per_share = get_float "revenue_per_share" json;
    trailing_eps = get_float "trailing_eps" json;
    forward_eps = get_float "forward_eps" json;
    earnings_growth = get_float "earnings_growth" json;
    eps_growth_fwd = get_float "eps_growth_fwd" json;
    gross_margin = get_float "gross_margin" json;
    operating_margin = get_float "operating_margin" json;
    ebitda_margin = get_float "ebitda_margin" json;
    profit_margin = get_float "profit_margin" json;
    fcf_margin = get_float "fcf_margin" json;
    ebitda = get_float "ebitda" json;
    free_cashflow = get_float "free_cashflow" json;
    operating_cashflow = get_float "operating_cashflow" json;
    fcf_per_share = get_float "fcf_per_share" json;
    ev_revenue = get_float "ev_revenue" json;
    ev_ebitda = get_float "ev_ebitda" json;
    trailing_pe = get_float "trailing_pe" json;
    forward_pe = get_float "forward_pe" json;
    rule_of_40 = get_float "rule_of_40" json;
    roe = get_float "roe" json;
    roa = get_float "roa" json;
    roic = get_float "roic" json;
    beta = get_float "beta" json;
    analyst_target_mean = get_float "analyst_target_mean" json;
    analyst_target_high = get_float "analyst_target_high" json;
    analyst_target_low = get_float "analyst_target_low" json;
    analyst_recommendation = json |> member "analyst_recommendation" |> to_string;
    num_analysts = json |> member "num_analysts" |> to_int;
  }

(** Write growth result to JSON file *)
let write_result (filename : string) (result : growth_result) : unit =
  let opt_to_json = function
    | Some v -> `Float v
    | None -> `Null
  in

  let json = `Assoc [
    ("ticker", `String result.ticker);
    ("company_name", `String result.company_name);
    ("sector", `String result.sector);
    ("current_price", `Float result.current_price);
    ("growth_metrics", `Assoc [
      ("revenue_growth_pct", `Float result.growth_metrics.revenue_growth_pct);
      ("revenue_cagr_3y_pct", `Float result.growth_metrics.revenue_cagr_3y_pct);
      ("earnings_growth_pct", `Float result.growth_metrics.earnings_growth_pct);
      ("growth_tier", `String (string_of_growth_tier result.growth_metrics.growth_tier));
      ("rule_of_40", `Float result.growth_metrics.rule_of_40);
      ("rule_of_40_tier", `String (string_of_rule_of_40_tier result.growth_metrics.rule_of_40_tier));
      ("ev_revenue_per_growth", `Float result.growth_metrics.ev_revenue_per_growth);
      ("peg_ratio", opt_to_json result.growth_metrics.peg_ratio);
    ]);
    ("margin_analysis", `Assoc [
      ("gross_margin_pct", `Float result.margin_analysis.gross_margin_pct);
      ("operating_margin_pct", `Float result.margin_analysis.operating_margin_pct);
      ("fcf_margin_pct", `Float result.margin_analysis.fcf_margin_pct);
      ("margin_trajectory", `String (string_of_margin_trajectory result.margin_analysis.margin_trajectory));
      ("operating_leverage", `Float result.margin_analysis.operating_leverage);
    ]);
    ("valuation", `Assoc [
      ("ev_revenue", `Float result.valuation.ev_revenue);
      ("ev_ebitda", `Float result.valuation.ev_ebitda);
      ("forward_pe", `Float result.valuation.forward_pe);
      ("implied_growth", opt_to_json result.valuation.implied_growth);
      ("analyst_upside_pct", opt_to_json result.valuation.analyst_upside_pct);
    ]);
    ("score", `Assoc [
      ("total_score", `Float result.score.total_score);
      ("grade", `String result.score.grade);
      ("revenue_growth_score", `Float result.score.revenue_growth_score);
      ("earnings_growth_score", `Float result.score.earnings_growth_score);
      ("margin_score", `Float result.score.margin_score);
      ("efficiency_score", `Float result.score.efficiency_score);
      ("quality_score", `Float result.score.quality_score);
    ]);
    ("signal", `String (string_of_growth_signal result.signal));
  ] in

  Yojson.Basic.to_file filename json

(** Print growth result to stdout *)
let print_result (result : growth_result) : unit =
  let gm = result.growth_metrics in
  let ma = result.margin_analysis in
  let v = result.valuation in
  let s = result.score in

  Printf.printf "\n";
  Printf.printf "============================================================\n";
  Printf.printf "Growth Analysis: %s (%s)\n" result.ticker result.company_name;
  Printf.printf "============================================================\n";
  Printf.printf "\n";

  Printf.printf "GROWTH METRICS\n";
  Printf.printf "------------------------------------------------------------\n";
  Printf.printf "  Revenue Growth:    %.1f%% (%s)\n" gm.revenue_growth_pct (string_of_growth_tier gm.growth_tier);
  Printf.printf "  Revenue CAGR (3Y): %.1f%%\n" gm.revenue_cagr_3y_pct;
  Printf.printf "  Earnings Growth:   %.1f%%\n" gm.earnings_growth_pct;
  (match gm.peg_ratio with
   | Some peg -> Printf.printf "  PEG Ratio:         %.2f\n" peg
   | None -> ());
  Printf.printf "\n";

  Printf.printf "MARGIN ANALYSIS\n";
  Printf.printf "------------------------------------------------------------\n";
  Printf.printf "  Gross Margin:      %.1f%%\n" ma.gross_margin_pct;
  Printf.printf "  Operating Margin:  %.1f%%\n" ma.operating_margin_pct;
  Printf.printf "  FCF Margin:        %.1f%%\n" ma.fcf_margin_pct;
  Printf.printf "  Trajectory:        %s\n" (string_of_margin_trajectory ma.margin_trajectory);
  Printf.printf "  Op. Leverage:      %.2fx\n" ma.operating_leverage;
  Printf.printf "\n";

  Printf.printf "EFFICIENCY\n";
  Printf.printf "------------------------------------------------------------\n";
  Printf.printf "  Rule of 40:        %.1f (%s)\n" gm.rule_of_40 (string_of_rule_of_40_tier gm.rule_of_40_tier);
  Printf.printf "  EV/Rev per Growth: %.2fx\n" gm.ev_revenue_per_growth;
  Printf.printf "\n";

  Printf.printf "VALUATION\n";
  Printf.printf "------------------------------------------------------------\n";
  Printf.printf "  Current Price:     $%.2f\n" result.current_price;
  Printf.printf "  EV/Revenue:        %.1fx\n" v.ev_revenue;
  Printf.printf "  EV/EBITDA:         %.1fx\n" v.ev_ebitda;
  Printf.printf "  Forward P/E:       %.1fx\n" v.forward_pe;
  (match v.implied_growth with
   | Some g -> Printf.printf "  Implied Growth:    %.1f%%\n" g
   | None -> ());
  (match v.analyst_upside_pct with
   | Some u when u >= 0.0 -> Printf.printf "  Analyst Upside:    %.1f%%\n" u
   | Some u -> Printf.printf "  Analyst Downside:  %.1f%%\n" (abs_float u)
   | None -> ());
  Printf.printf "\n";

  Printf.printf "GROWTH SCORE: %.0f/100 (Grade: %s)\n" s.total_score s.grade;
  Printf.printf "------------------------------------------------------------\n";
  Printf.printf "  Revenue Growth:    %.0f/25\n" s.revenue_growth_score;
  Printf.printf "  Earnings Growth:   %.0f/20\n" s.earnings_growth_score;
  Printf.printf "  Margins:           %.0f/20\n" s.margin_score;
  Printf.printf "  Efficiency:        %.0f/20\n" s.efficiency_score;
  Printf.printf "  Quality:           %.0f/15\n" s.quality_score;
  Printf.printf "\n";

  Printf.printf "SIGNAL: %s\n" (string_of_growth_signal result.signal);
  Printf.printf "============================================================\n";
  Printf.printf "\n"

(** Print comparison table *)
let print_comparison (results : growth_result list) : unit =
  Printf.printf "\n";
  Printf.printf "================================================================================\n";
  Printf.printf "GROWTH STOCK COMPARISON\n";
  Printf.printf "================================================================================\n";
  Printf.printf "\n";
  Printf.printf "%-8s %8s %10s %10s %10s %8s %-18s\n"
    "Ticker" "Price" "Rev Grth" "Rule40" "Score" "Grade" "Signal";
  Printf.printf "--------------------------------------------------------------------------------\n";

  List.iter (fun r ->
    Printf.printf "%-8s %8.2f %9.1f%% %10.1f %8.0f %8s %-18s\n"
      r.ticker
      r.current_price
      r.growth_metrics.revenue_growth_pct
      r.growth_metrics.rule_of_40
      r.score.total_score
      r.score.grade
      (string_of_growth_signal r.signal)
  ) results;

  Printf.printf "\n";

  (* Find best by various criteria *)
  let sorted_by_growth = List.sort (fun a b ->
    compare b.growth_metrics.revenue_growth_pct a.growth_metrics.revenue_growth_pct
  ) results in

  let sorted_by_score = List.sort (fun a b ->
    compare b.score.total_score a.score.total_score
  ) results in

  (match sorted_by_growth with
   | best :: _ -> Printf.printf "Highest Growth: %s (%.1f%%)\n" best.ticker best.growth_metrics.revenue_growth_pct
   | [] -> ());

  (match sorted_by_score with
   | best :: _ -> Printf.printf "Best Score:     %s (%.0f)\n" best.ticker best.score.total_score
   | [] -> ());

  Printf.printf "\n";
  Printf.printf "================================================================================\n"
