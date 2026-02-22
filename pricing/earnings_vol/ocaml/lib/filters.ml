(** Filter Engine for Earnings Trades *)

open Types

(** Apply filter criteria to an earnings event *)
let apply_filters
    ~(term_structure : iv_term_structure)
    ~(volume : float)
    ~(iv_rv : iv_rv_ratio)
    ~(criteria : filter_criteria) : filter_result =
  (* Check each criterion *)
  let passes_slope = term_structure.term_structure_slope <= criteria.min_term_slope in
  let passes_volume = volume >= criteria.min_volume in
  let passes_iv_rv = iv_rv.iv_rv_ratio >= criteria.min_iv_rv_ratio in
  
  (* Determine recommendation *)
  let recommendation =
    if passes_slope && passes_volume && passes_iv_rv then
      "Recommended"  (* All 3 criteria met - GREEN *)
    else if passes_slope && (passes_volume || passes_iv_rv) then
      "Consider"     (* Slope + 1 other - YELLOW *)
    else if (not passes_slope) then
      "Avoid"        (* No slope = automatic avoid - RED *)
    else
      "Avoid"        (* Doesn't meet minimum criteria *)
  in
  
  {
    ticker = term_structure.ticker;
    passes_term_slope = passes_slope;
    passes_volume = passes_volume;
    passes_iv_rv = passes_iv_rv;
    recommendation;
    term_slope = term_structure.term_structure_slope;
    volume;
    iv_rv_ratio = iv_rv.iv_rv_ratio;
  }

(** Print filter results *)
let print_filter_result (result : filter_result) : unit =
  Printf.printf "\n=== Filter Results: %s ===\n" result.ticker;
  Printf.printf "Term Structure Slope: %.4f %s\n" 
    result.term_slope 
    (if result.passes_term_slope then "✓" else "✗");
  Printf.printf "30-Day Volume: %.0f %s\n" 
    result.volume 
    (if result.passes_volume then "✓" else "✗");
  Printf.printf "IV/RV Ratio: %.2f %s\n" 
    result.iv_rv_ratio 
    (if result.passes_iv_rv then "✓" else "✗");
  Printf.printf "\nRecommendation: %s\n" result.recommendation
