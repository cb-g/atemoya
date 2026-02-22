(** Unit tests for normalized multiples model *)

open Normalized_multiples

(* ========== Types Tests ========== *)

let test_string_of_time_window () =
  Alcotest.(check string) "TTM" "TTM" (Types.string_of_time_window Types.TTM);
  Alcotest.(check string) "NTM" "NTM" (Types.string_of_time_window Types.NTM);
  Alcotest.(check string) "FY0" "FY0" (Types.string_of_time_window Types.FY0)

let test_time_window_of_string () =
  Alcotest.(check bool) "TTM parses"
    true (Types.time_window_of_string "TTM" = Some Types.TTM);
  Alcotest.(check bool) "NTM parses"
    true (Types.time_window_of_string "NTM" = Some Types.NTM);
  Alcotest.(check bool) "invalid returns None"
    true (Types.time_window_of_string "XYZ" = None)

let test_category_of_multiple () =
  Alcotest.(check bool) "EV/EBITDA is EV"
    true (Types.category_of_multiple "EV/EBITDA" = Types.EVMultiple);
  Alcotest.(check bool) "P/E is Price"
    true (Types.category_of_multiple "P/E" = Types.PriceMultiple)

let test_signal_of_percentile () =
  Alcotest.(check string) "deep value"
    "Deep Value" (Types.string_of_signal (Types.signal_of_percentile 15.0 true));
  Alcotest.(check string) "undervalued"
    "Undervalued" (Types.string_of_signal (Types.signal_of_percentile 30.0 true));
  Alcotest.(check string) "fair value"
    "Fair Value" (Types.string_of_signal (Types.signal_of_percentile 50.0 true));
  Alcotest.(check string) "overvalued"
    "Overvalued" (Types.string_of_signal (Types.signal_of_percentile 65.0 true));
  Alcotest.(check string) "expensive"
    "Expensive" (Types.string_of_signal (Types.signal_of_percentile 80.0 true));
  Alcotest.(check string) "invalid"
    "N/A" (Types.string_of_signal (Types.signal_of_percentile 50.0 false))

(* ========== Multiples Tests ========== *)

let test_make_multiple_valid () =
  let m = Multiples.make_multiple ~name:"P/E" ~time_window:Types.TTM
    ~value:15.0 ~underlying_metric:6.67 in
  Alcotest.(check bool) "valid multiple" true m.is_valid;
  Alcotest.(check (float 0.01)) "value" 15.0 m.value

let test_make_multiple_invalid () =
  let m = Multiples.make_multiple ~name:"P/E" ~time_window:Types.TTM
    ~value:(-5.0) ~underlying_metric:6.67 in
  Alcotest.(check bool) "negative value is invalid" false m.is_valid

let test_make_multiple_zero_metric () =
  let m = Multiples.make_multiple ~name:"P/E" ~time_window:Types.TTM
    ~value:15.0 ~underlying_metric:0.0 in
  Alcotest.(check bool) "zero metric is invalid" false m.is_valid

(* ========== Benchmarks Tests ========== *)

let test_percentile_rank_at_median () =
  let pct = Benchmarks.percentile_rank 15.0 10.0 15.0 20.0 in
  Alcotest.(check (float 0.01)) "at median = 50" 50.0 pct

let test_percentile_rank_at_p25 () =
  let pct = Benchmarks.percentile_rank 10.0 10.0 15.0 20.0 in
  Alcotest.(check (float 0.01)) "at p25 = 25" 25.0 pct

let test_percentile_rank_at_p75 () =
  let pct = Benchmarks.percentile_rank 20.0 10.0 15.0 20.0 in
  Alcotest.(check (float 0.01)) "at p75 = 75" 75.0 pct

let test_percentile_rank_below_p25 () =
  let pct = Benchmarks.percentile_rank 5.0 10.0 15.0 20.0 in
  Alcotest.(check bool) "below p25" true (pct < 25.0);
  Alcotest.(check bool) "above 0" true (pct >= 0.0)

let test_percentile_rank_above_p75 () =
  let pct = Benchmarks.percentile_rank 25.0 10.0 15.0 20.0 in
  Alcotest.(check bool) "above p75" true (pct > 75.0);
  Alcotest.(check bool) "capped at 100" true (pct <= 100.0)

let test_percentile_rank_between_p25_median () =
  let pct = Benchmarks.percentile_rank 12.5 10.0 15.0 20.0 in
  Alcotest.(check bool) "between 25 and 50" true (pct > 25.0 && pct < 50.0)

let test_get_benchmark_for_multiple () =
  let bm : Types.benchmark_stats = {
    sector = "Technology"; industry = None; sample_size = 50;
    pe_ttm_median = 25.0; pe_ttm_p25 = 18.0; pe_ttm_p75 = 32.0;
    pe_ntm_median = 22.0; pe_ntm_p25 = 16.0; pe_ntm_p75 = 28.0;
    ps_median = 5.0; ps_p25 = 3.0; ps_p75 = 7.0;
    pb_median = 4.0; pb_p25 = 2.5; pb_p75 = 6.0;
    p_fcf_median = 20.0; p_fcf_p25 = 15.0; p_fcf_p75 = 28.0;
    peg_median = 1.5; peg_p25 = 1.0; peg_p75 = 2.0;
    ev_ebitda_median = 15.0; ev_ebitda_p25 = 10.0; ev_ebitda_p75 = 20.0;
    ev_ebit_median = 18.0; ev_sales_median = 5.0; ev_fcf_median = 22.0;
    revenue_growth_median = 0.12; ebitda_margin_median = 0.25; roe_median = 0.18;
  } in
  match Benchmarks.get_benchmark_for_multiple "P/E" Types.TTM bm with
  | Some (med, p25, p75) ->
    Alcotest.(check (float 0.01)) "P/E TTM median" 25.0 med;
    Alcotest.(check (float 0.01)) "P/E TTM p25" 18.0 p25;
    Alcotest.(check (float 0.01)) "P/E TTM p75" 32.0 p75
  | None -> Alcotest.fail "Expected Some benchmark"

let test_get_benchmark_unknown () =
  let bm : Types.benchmark_stats = {
    sector = "Technology"; industry = None; sample_size = 50;
    pe_ttm_median = 25.0; pe_ttm_p25 = 18.0; pe_ttm_p75 = 32.0;
    pe_ntm_median = 22.0; pe_ntm_p25 = 16.0; pe_ntm_p75 = 28.0;
    ps_median = 5.0; ps_p25 = 3.0; ps_p75 = 7.0;
    pb_median = 4.0; pb_p25 = 2.5; pb_p75 = 6.0;
    p_fcf_median = 20.0; p_fcf_p25 = 15.0; p_fcf_p75 = 28.0;
    peg_median = 1.5; peg_p25 = 1.0; peg_p75 = 2.0;
    ev_ebitda_median = 15.0; ev_ebitda_p25 = 10.0; ev_ebitda_p75 = 20.0;
    ev_ebit_median = 18.0; ev_sales_median = 5.0; ev_fcf_median = 22.0;
    revenue_growth_median = 0.12; ebitda_margin_median = 0.25; roe_median = 0.18;
  } in
  let result = Benchmarks.get_benchmark_for_multiple "UNKNOWN" Types.TTM bm in
  Alcotest.(check bool) "unknown returns None" true (result = None)

(* ========== Scoring Tests ========== *)

let test_composite_percentile_empty () =
  let pct = Scoring.composite_percentile [] in
  Alcotest.(check (float 0.01)) "empty = 50" 50.0 pct

let test_quality_adjusted_percentile () =
  let adj : Types.quality_adjustment = {
    growth_premium_pct = 5.0;
    margin_premium_pct = 3.0;
    return_premium_pct = 2.0;
    total_fair_premium_pct = 10.0;
  } in
  let result = Scoring.quality_adjusted_percentile 60.0 adj in
  (* 60 - 10 = 50 *)
  Alcotest.(check (float 0.01)) "adjusted down by premium" 50.0 result

let test_quality_adjusted_percentile_clamped () =
  let adj : Types.quality_adjustment = {
    growth_premium_pct = 10.0;
    margin_premium_pct = 10.0;
    return_premium_pct = 10.0;
    total_fair_premium_pct = 30.0;
  } in
  let result = Scoring.quality_adjusted_percentile 20.0 adj in
  Alcotest.(check (float 0.01)) "clamped to 0" 0.0 result

let test_overall_signal () =
  Alcotest.(check string) "deep value"
    "Deep Value" (Types.string_of_signal (Scoring.overall_signal 15.0));
  Alcotest.(check string) "fair value"
    "Fair Value" (Types.string_of_signal (Scoring.overall_signal 50.0));
  Alcotest.(check string) "expensive"
    "Expensive" (Types.string_of_signal (Scoring.overall_signal 80.0))

(* ========== Test Suite ========== *)

let () =
  Alcotest.run "Normalized Multiples Tests" [
    "types", [
      Alcotest.test_case "Time window to string" `Quick test_string_of_time_window;
      Alcotest.test_case "Time window of string" `Quick test_time_window_of_string;
      Alcotest.test_case "Category of multiple" `Quick test_category_of_multiple;
      Alcotest.test_case "Signal of percentile" `Quick test_signal_of_percentile;
    ];
    "multiples", [
      Alcotest.test_case "Make valid multiple" `Quick test_make_multiple_valid;
      Alcotest.test_case "Make invalid multiple" `Quick test_make_multiple_invalid;
      Alcotest.test_case "Make zero metric multiple" `Quick test_make_multiple_zero_metric;
    ];
    "benchmarks", [
      Alcotest.test_case "Percentile at median" `Quick test_percentile_rank_at_median;
      Alcotest.test_case "Percentile at p25" `Quick test_percentile_rank_at_p25;
      Alcotest.test_case "Percentile at p75" `Quick test_percentile_rank_at_p75;
      Alcotest.test_case "Percentile below p25" `Quick test_percentile_rank_below_p25;
      Alcotest.test_case "Percentile above p75" `Quick test_percentile_rank_above_p75;
      Alcotest.test_case "Percentile interpolation" `Quick test_percentile_rank_between_p25_median;
      Alcotest.test_case "Get benchmark P/E" `Quick test_get_benchmark_for_multiple;
      Alcotest.test_case "Get benchmark unknown" `Quick test_get_benchmark_unknown;
    ];
    "scoring", [
      Alcotest.test_case "Composite percentile empty" `Quick test_composite_percentile_empty;
      Alcotest.test_case "Quality adjusted percentile" `Quick test_quality_adjusted_percentile;
      Alcotest.test_case "Quality adjusted clamped" `Quick test_quality_adjusted_percentile_clamped;
      Alcotest.test_case "Overall signal" `Quick test_overall_signal;
    ];
  ]
