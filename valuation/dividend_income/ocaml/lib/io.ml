(** I/O functions for dividend income analysis *)

open Types

(** Read dividend data from JSON file *)
let read_dividend_data (filename : string) : dividend_data =
  let json = Yojson.Basic.from_file filename in
  let open Yojson.Basic.Util in

  (* Helper to get float from JSON that might be int or float *)
  let to_float_safe json =
    match json with
    | `Float f -> f
    | `Int i -> float_of_int i
    | _ -> 0.0
  in

  let get_float key json =
    to_float_safe (json |> member key)
  in

  let get_string_opt key json =
    try Some (json |> member key |> to_string)
    with _ -> None
  in

  {
    ticker = json |> member "ticker" |> to_string;
    company_name = json |> member "company_name" |> to_string;
    sector = json |> member "sector" |> to_string;
    industry = json |> member "industry" |> to_string;
    current_price = get_float "current_price" json;
    market_cap = get_float "market_cap" json;
    beta = get_float "beta" json;
    dividend_rate = get_float "dividend_rate" json;
    dividend_yield = get_float "dividend_yield" json;
    ex_dividend_date = get_string_opt "ex_dividend_date" json;
    payout_ratio_eps = get_float "payout_ratio_eps" json;
    payout_ratio_fcf = get_float "payout_ratio_fcf" json;
    eps_coverage = get_float "eps_coverage" json;
    fcf_coverage = get_float "fcf_coverage" json;
    trailing_eps = get_float "trailing_eps" json;
    forward_eps = get_float "forward_eps" json;
    fcf_per_share = get_float "fcf_per_share" json;
    dgr_1y = get_float "dgr_1y" json;
    dgr_3y = get_float "dgr_3y" json;
    dgr_5y = get_float "dgr_5y" json;
    dgr_10y = get_float "dgr_10y" json;
    consecutive_increases = json |> member "consecutive_increases" |> to_int;
    dividend_status = json |> member "dividend_status" |> to_string;
    chowder_number = get_float "chowder_number" json;
    debt_to_equity = get_float "debt_to_equity" json;
    current_ratio = get_float "current_ratio" json;
    roe = get_float "roe" json;
    roa = get_float "roa" json;
    profit_margin = get_float "profit_margin" json;
    history_years = json |> member "history_years" |> to_int;
  }

(** Write dividend result to JSON file *)
let write_result (filename : string) (result : dividend_result) : unit =
  let opt_to_json = function
    | Some v -> `Float v
    | None -> `Null
  in

  let json = `Assoc [
    ("ticker", `String result.ticker);
    ("company_name", `String result.company_name);
    ("sector", `String result.sector);
    ("current_price", `Float result.current_price);
    ("dividend_metrics", `Assoc [
      ("yield_pct", `Float result.dividend_metrics.yield_pct);
      ("yield_tier", `String (string_of_yield_tier result.dividend_metrics.yield_tier));
      ("annual_dividend", `Float result.dividend_metrics.annual_dividend);
      ("payout_ratio_eps", `Float result.dividend_metrics.payout_ratio_eps);
      ("payout_ratio_fcf", `Float result.dividend_metrics.payout_ratio_fcf);
      ("payout_assessment", `String (string_of_payout_assessment result.dividend_metrics.payout_assessment));
      ("eps_coverage", `Float result.dividend_metrics.eps_coverage);
      ("fcf_coverage", `Float result.dividend_metrics.fcf_coverage);
      ("coverage_quality", `String result.dividend_metrics.coverage_quality);
    ]);
    ("growth_metrics", `Assoc [
      ("dgr_1y", `Float result.growth_metrics.dgr_1y);
      ("dgr_3y", `Float result.growth_metrics.dgr_3y);
      ("dgr_5y", `Float result.growth_metrics.dgr_5y);
      ("dgr_10y", `Float result.growth_metrics.dgr_10y);
      ("consecutive_increases", `Int result.growth_metrics.consecutive_increases);
      ("dividend_status", `String (string_of_dividend_status result.growth_metrics.dividend_status));
      ("chowder_number", `Float result.growth_metrics.chowder_number);
      ("chowder_assessment", `String result.growth_metrics.chowder_assessment);
    ]);
    ("ddm_valuation", `Assoc [
      ("gordon_growth_value", opt_to_json result.ddm_valuation.gordon_growth_value);
      ("two_stage_value", opt_to_json result.ddm_valuation.two_stage_value);
      ("h_model_value", opt_to_json result.ddm_valuation.h_model_value);
      ("yield_based_value", opt_to_json result.ddm_valuation.yield_based_value);
      ("average_fair_value", opt_to_json result.ddm_valuation.average_fair_value);
      ("upside_downside_pct", opt_to_json result.ddm_valuation.upside_downside_pct);
    ]);
    ("safety_score", `Assoc [
      ("total_score", `Float result.safety_score.total_score);
      ("grade", `String result.safety_score.grade);
      ("payout_score", `Float result.safety_score.payout_score);
      ("coverage_score", `Float result.safety_score.coverage_score);
      ("streak_score", `Float result.safety_score.streak_score);
      ("balance_sheet_score", `Float result.safety_score.balance_sheet_score);
      ("stability_score", `Float result.safety_score.stability_score);
    ]);
    ("signal", `String (string_of_income_signal result.signal));
  ] in

  Yojson.Basic.to_file filename json

(** Print dividend result to stdout *)
let print_result (result : dividend_result) : unit =
  let dm = result.dividend_metrics in
  let gm = result.growth_metrics in
  let ddm = result.ddm_valuation in
  let ss = result.safety_score in

  Printf.printf "\n";
  Printf.printf "============================================================\n";
  Printf.printf "Dividend Analysis: %s (%s)\n" result.ticker result.company_name;
  Printf.printf "============================================================\n";
  Printf.printf "\n";

  Printf.printf "PRICE & YIELD\n";
  Printf.printf "------------------------------------------------------------\n";
  Printf.printf "  Current Price:     $%.2f\n" result.current_price;
  Printf.printf "  Dividend Yield:    %.2f%% (%s)\n" dm.yield_pct (string_of_yield_tier dm.yield_tier);
  Printf.printf "  Annual Dividend:   $%.2f\n" dm.annual_dividend;
  Printf.printf "\n";

  Printf.printf "PAYOUT ANALYSIS\n";
  Printf.printf "------------------------------------------------------------\n";
  Printf.printf "  Payout (EPS):      %.1f%%\n" (dm.payout_ratio_eps *. 100.0);
  Printf.printf "  Payout (FCF):      %.1f%%\n" (dm.payout_ratio_fcf *. 100.0);
  Printf.printf "  Assessment:        %s\n" (string_of_payout_assessment dm.payout_assessment);
  Printf.printf "  EPS Coverage:      %.1fx\n" dm.eps_coverage;
  Printf.printf "  FCF Coverage:      %.1fx (%s)\n" dm.fcf_coverage dm.coverage_quality;
  Printf.printf "\n";

  Printf.printf "DIVIDEND GROWTH\n";
  Printf.printf "------------------------------------------------------------\n";
  Printf.printf "  1-Year Growth:     %.1f%%\n" (gm.dgr_1y *. 100.0);
  Printf.printf "  3-Year CAGR:       %.1f%%\n" (gm.dgr_3y *. 100.0);
  Printf.printf "  5-Year CAGR:       %.1f%%\n" (gm.dgr_5y *. 100.0);
  Printf.printf "  10-Year CAGR:      %.1f%%\n" (gm.dgr_10y *. 100.0);
  Printf.printf "  Consecutive Years: %d (%s)\n" gm.consecutive_increases (string_of_dividend_status gm.dividend_status);
  Printf.printf "  Chowder Number:    %.1f (%s)\n" gm.chowder_number gm.chowder_assessment;
  Printf.printf "\n";

  Printf.printf "DDM VALUATION (8%% required return, 3%% terminal growth)\n";
  Printf.printf "------------------------------------------------------------\n";
  (match ddm.gordon_growth_value with
   | Some v -> Printf.printf "  Gordon Growth:     $%.2f\n" v
   | None -> Printf.printf "  Gordon Growth:     N/A\n");
  (match ddm.two_stage_value with
   | Some v -> Printf.printf "  Two-Stage DDM:     $%.2f\n" v
   | None -> Printf.printf "  Two-Stage DDM:     N/A\n");
  (match ddm.h_model_value with
   | Some v -> Printf.printf "  H-Model:           $%.2f\n" v
   | None -> Printf.printf "  H-Model:           N/A\n");
  (match ddm.yield_based_value with
   | Some v -> Printf.printf "  Yield-Based:       $%.2f\n" v
   | None -> Printf.printf "  Yield-Based:       N/A\n");
  (match ddm.average_fair_value with
   | Some v -> Printf.printf "  Average Fair Val:  $%.2f\n" v
   | None -> Printf.printf "  Average Fair Val:  N/A\n");
  (match ddm.upside_downside_pct with
   | Some v when v >= 0.0 -> Printf.printf "  Upside:            %.1f%%\n" v
   | Some v -> Printf.printf "  Downside:          %.1f%%\n" (abs_float v)
   | None -> ());
  Printf.printf "\n";

  Printf.printf "DIVIDEND SAFETY SCORE: %.0f/100 (Grade: %s)\n" ss.total_score ss.grade;
  Printf.printf "------------------------------------------------------------\n";
  Printf.printf "  Payout Score:      %.0f/25\n" ss.payout_score;
  Printf.printf "  Coverage Score:    %.0f/25\n" ss.coverage_score;
  Printf.printf "  Streak Score:      %.0f/25\n" ss.streak_score;
  Printf.printf "  Balance Sheet:     %.0f/15\n" ss.balance_sheet_score;
  Printf.printf "  Stability:         %.0f/10\n" ss.stability_score;
  Printf.printf "\n";

  Printf.printf "SIGNAL: %s\n" (string_of_income_signal result.signal);
  Printf.printf "============================================================\n";
  Printf.printf "\n"

(** Print comparison table for multiple stocks *)
let print_comparison (results : dividend_result list) : unit =
  Printf.printf "\n";
  Printf.printf "================================================================================\n";
  Printf.printf "DIVIDEND STOCK COMPARISON\n";
  Printf.printf "================================================================================\n";
  Printf.printf "\n";
  Printf.printf "%-8s %8s %8s %8s %8s %8s %-20s\n"
    "Ticker" "Price" "Yield%" "Payout%" "Score" "Grade" "Signal";
  Printf.printf "--------------------------------------------------------------------------------\n";

  List.iter (fun r ->
    Printf.printf "%-8s %8.2f %7.2f%% %7.1f%% %8.0f %8s %-20s\n"
      r.ticker
      r.current_price
      r.dividend_metrics.yield_pct
      (r.dividend_metrics.payout_ratio_eps *. 100.0)
      r.safety_score.total_score
      r.safety_score.grade
      (string_of_income_signal r.signal)
  ) results;

  Printf.printf "\n";

  (* Find best by various criteria *)
  let sorted_by_yield = List.sort (fun a b ->
    compare b.dividend_metrics.yield_pct a.dividend_metrics.yield_pct
  ) results in

  let sorted_by_safety = List.sort (fun a b ->
    compare b.safety_score.total_score a.safety_score.total_score
  ) results in

  let sorted_by_growth = List.sort (fun a b ->
    compare b.growth_metrics.dgr_5y a.growth_metrics.dgr_5y
  ) results in

  (match sorted_by_yield with
   | best :: _ -> Printf.printf "Highest Yield:  %s (%.2f%%)\n" best.ticker best.dividend_metrics.yield_pct
   | [] -> ());

  (match sorted_by_safety with
   | best :: _ -> Printf.printf "Safest:         %s (Score: %.0f)\n" best.ticker best.safety_score.total_score
   | [] -> ());

  (match sorted_by_growth with
   | best :: _ when best.growth_metrics.dgr_5y > 0.0 ->
       Printf.printf "Best Growth:    %s (%.1f%% 5Y CAGR)\n" best.ticker (best.growth_metrics.dgr_5y *. 100.0)
   | _ -> ());

  Printf.printf "\n";
  Printf.printf "================================================================================\n"
