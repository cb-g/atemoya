(** Derivatives-Based ETF Analysis *)

open Types

(** Convert derivatives type to string *)
let derivatives_type_to_string (dt : derivatives_type) : string =
  match dt with
  | Standard -> "Standard"
  | CoveredCall -> "Covered Call"
  | Buffer -> "Buffer/Defined Outcome"
  | Volatility -> "Volatility"
  | PutWrite -> "Put-Write"
  | Leveraged -> "Leveraged/Inverse"

(** Analyze covered call ETF *)
let analyze_covered_call (data : etf_data) : covered_call_analysis option =
  match data.distribution_analysis, data.capture_ratios with
  | Some dist, Some capture ->
    (* Calculate yield vs typical benchmark dividend yield (assume ~1.5% for S&P) *)
    let benchmark_yield = 1.5 in
    let yield_vs_benchmark = dist.distribution_yield_pct /. benchmark_yield in

    (* Capture efficiency: difference between upside and downside capture *)
    (* Positive is good: captures less downside than upside *)
    let capture_efficiency = capture.upside_capture_pct -. capture.downside_capture_pct in

    Some {
      distribution_yield_pct = dist.distribution_yield_pct;
      upside_capture = capture.upside_capture_pct;
      downside_capture = capture.downside_capture_pct;
      yield_vs_benchmark;
      capture_efficiency;
    }
  | Some dist, None ->
    Some {
      distribution_yield_pct = dist.distribution_yield_pct;
      upside_capture = 0.0;
      downside_capture = 0.0;
      yield_vs_benchmark = dist.distribution_yield_pct /. 1.5;
      capture_efficiency = 0.0;
    }
  | _ -> None

(** Score covered call ETF (0-50 for derivatives-specific) *)
let score_covered_call (analysis : covered_call_analysis) : float =
  let score = ref 0.0 in

  (* Yield score (0-20): Higher yield is better, but watch for unsustainability *)
  if analysis.distribution_yield_pct >= 10.0 then
    score := !score +. 15.0  (* Very high yields may be unsustainable *)
  else if analysis.distribution_yield_pct >= 7.0 then
    score := !score +. 20.0  (* Sweet spot *)
  else if analysis.distribution_yield_pct >= 5.0 then
    score := !score +. 15.0
  else if analysis.distribution_yield_pct >= 3.0 then
    score := !score +. 10.0
  else
    score := !score +. 5.0;

  (* Upside capture score (0-15): Higher is better *)
  if analysis.upside_capture >= 70.0 then
    score := !score +. 15.0
  else if analysis.upside_capture >= 60.0 then
    score := !score +. 12.0
  else if analysis.upside_capture >= 50.0 then
    score := !score +. 9.0
  else if analysis.upside_capture >= 40.0 then
    score := !score +. 6.0
  else if analysis.upside_capture > 0.0 then
    score := !score +. 3.0;

  (* Capture efficiency score (0-15): Positive is better *)
  if analysis.capture_efficiency > 0.0 then
    score := !score +. 15.0  (* Captures more upside than downside *)
  else if analysis.capture_efficiency > -10.0 then
    score := !score +. 10.0
  else if analysis.capture_efficiency > -20.0 then
    score := !score +. 5.0;

  !score

(** Generate covered call recommendations *)
let covered_call_recommendations (analysis : covered_call_analysis) : string list =
  let recs = ref [] in

  (* Yield assessment *)
  if analysis.distribution_yield_pct > 12.0 then
    recs := "Very high yield - may include return of capital" :: !recs
  else if analysis.distribution_yield_pct > 8.0 then
    recs := "High yield - suitable for income-focused investors" :: !recs
  else if analysis.distribution_yield_pct < 5.0 then
    recs := "Moderate yield - consider if income need justifies strategy" :: !recs;

  (* Upside capture assessment *)
  if analysis.upside_capture < 50.0 && analysis.upside_capture > 0.0 then
    recs := Printf.sprintf "Limited upside capture (%.0f%%) - will lag in strong rallies" analysis.upside_capture :: !recs
  else if analysis.upside_capture >= 70.0 then
    recs := "Good upside capture - balanced income/growth approach" :: !recs;

  (* Capture efficiency *)
  if analysis.capture_efficiency < -15.0 then
    recs := "Poor capture efficiency - captures more downside than upside" :: !recs;

  (* Suitability *)
  if analysis.distribution_yield_pct > 6.0 && analysis.upside_capture > 55.0 then
    recs := "Well-balanced covered call strategy for income with participation" :: !recs;

  List.rev !recs

(** Analyze buffer ETF - simplified without real-time outcome data *)
let analyze_buffer (_data : etf_data) : buffer_analysis option =
  (* Buffer ETF analysis requires outcome period data not available from yfinance *)
  (* This would need direct issuer data (Innovator, First Trust, etc.) *)
  Some {
    buffer_level = 0.0;  (* Would need issuer data *)
    cap_level = 0.0;
    remaining_buffer = 0.0;
    remaining_cap = 0.0;
    days_to_outcome = 0;
    buffer_status = "Data requires issuer lookup";
  }

(** Score buffer ETF *)
let score_buffer (_analysis : buffer_analysis) : float =
  (* Without real outcome data, default to base score *)
  25.0

(** Buffer recommendations *)
let buffer_recommendations (_analysis : buffer_analysis) : string list =
  [
    "Buffer ETF - check issuer website for current buffer/cap levels";
    "Mid-period entry may have different effective buffer/cap";
    "Best entered near outcome period start for full protection";
  ]

(** Analyze volatility ETF *)
let analyze_volatility (data : etf_data) : volatility_analysis option =
  (* Volatility ETFs have severe decay in contango *)
  (* Without VIX futures data, use historical decay as proxy *)
  match data.returns with
  | Some returns ->
    (* If 1-year return is very negative, likely contango decay *)
    let is_decaying = returns.one_year < -30.0 in
    let estimated_monthly_decay =
      if returns.one_year < 0.0 then returns.one_year /. 12.0
      else 0.0
    in
    Some {
      term_structure = if is_decaying then "Contango (estimated)" else "Unknown";
      roll_yield_monthly_pct = estimated_monthly_decay;
      roll_yield_annual_pct = returns.one_year;
      decay_warning = is_decaying;
    }
  | None -> None

(** Score volatility ETF *)
let score_volatility (analysis : volatility_analysis) : float =
  (* Volatility ETFs score low due to structural decay *)
  if analysis.decay_warning then 15.0
  else if analysis.term_structure = "Backwardation" then 35.0
  else 25.0

(** Volatility ETF recommendations *)
let volatility_recommendations (analysis : volatility_analysis) : string list =
  let recs = ref [] in

  if analysis.decay_warning then begin
    recs := "SEVERE DECAY WARNING - not suitable for buy-and-hold" :: !recs;
    recs := Printf.sprintf "Estimated annual decay: %.1f%%" analysis.roll_yield_annual_pct :: !recs;
  end;

  recs := "Use only for short-term tactical hedging" :: !recs;
  recs := "Consider VIX options for defined-risk volatility exposure" :: !recs;

  List.rev !recs

(** Analyze leveraged ETF *)
let score_leveraged (data : etf_data) : float =
  (* Leveraged ETFs have volatility decay *)
  match data.returns with
  | Some returns ->
    if returns.volatility_1y > 50.0 then 15.0  (* High vol = high decay *)
    else if returns.volatility_1y > 30.0 then 20.0
    else 30.0
  | None -> 20.0

(** Leveraged ETF recommendations *)
let leveraged_recommendations (data : etf_data) : string list =
  let recs = ref [
    "Leveraged/inverse ETF - daily rebalancing causes decay";
    "Suitable only for short-term tactical trades";
    "NOT suitable for buy-and-hold strategies";
  ] in

  (match data.returns with
   | Some returns when returns.volatility_1y > 40.0 ->
     recs := "High volatility amplifies decay - use extreme caution" :: !recs
   | _ -> ());

  List.rev !recs

(** Main derivatives analysis function *)
let analyze_derivatives (data : etf_data) : derivatives_analysis =
  match data.derivatives_type with
  | CoveredCall ->
    (match analyze_covered_call data with
     | Some analysis -> CoveredCallAnalysis analysis
     | None -> NoDerivatives)
  | Buffer ->
    (match analyze_buffer data with
     | Some analysis -> BufferAnalysis analysis
     | None -> NoDerivatives)
  | Volatility ->
    (match analyze_volatility data with
     | Some analysis -> VolatilityAnalysis analysis
     | None -> NoDerivatives)
  | PutWrite ->
    (* Put-write similar to covered call *)
    (match analyze_covered_call data with
     | Some analysis -> CoveredCallAnalysis analysis
     | None -> NoDerivatives)
  | Standard | Leveraged -> NoDerivatives

(** Score derivatives component *)
let score_derivatives (data : etf_data) (analysis : derivatives_analysis) : float =
  match analysis with
  | CoveredCallAnalysis cc -> score_covered_call cc
  | BufferAnalysis buf -> score_buffer buf
  | VolatilityAnalysis vol -> score_volatility vol
  | NoDerivatives ->
    match data.derivatives_type with
    | Leveraged -> score_leveraged data
    | _ -> 0.0  (* No derivatives component to score *)

(** Generate derivatives-specific recommendations *)
let derivatives_recommendations (data : etf_data) (analysis : derivatives_analysis) : string list =
  match analysis with
  | CoveredCallAnalysis cc -> covered_call_recommendations cc
  | BufferAnalysis buf -> buffer_recommendations buf
  | VolatilityAnalysis vol -> volatility_recommendations vol
  | NoDerivatives ->
    match data.derivatives_type with
    | Leveraged -> leveraged_recommendations data
    | _ -> []
