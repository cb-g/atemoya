(** ETF Analysis I/O Functions *)

open Types

(** Safe float extraction from JSON *)
let to_float_safe j =
  match j with
  | `Float f -> f
  | `Int i -> float_of_int i
  | _ -> 0.0

(** Safe int extraction from JSON *)
let to_int_safe j =
  match j with
  | `Int i -> i
  | `Float f -> int_of_float f
  | _ -> 0

(** Safe string extraction from JSON *)
let to_string_safe j =
  match j with
  | `String s -> s
  | _ -> ""

(** Parse derivatives type from string *)
let parse_derivatives_type (s : string) : derivatives_type =
  match String.lowercase_ascii s with
  | "standard" -> Standard
  | "covered_call" -> CoveredCall
  | "buffer" -> Buffer
  | "volatility" -> Volatility
  | "put_write" -> PutWrite
  | "leveraged" -> Leveraged
  | _ -> Standard

(** Parse returns from JSON *)
let parse_returns (json : Yojson.Basic.t) : returns option =
  match json with
  | `Assoc fields ->
    let get_field name = to_float_safe (List.assoc_opt name fields |> Option.value ~default:`Null) in
    Some {
      ytd = get_field "ytd";
      one_month = get_field "one_month";
      three_month = get_field "three_month";
      one_year = get_field "one_year";
      volatility_1y = get_field "volatility_1y";
    }
  | _ -> None

(** Parse tracking metrics from JSON *)
let parse_tracking (json : Yojson.Basic.t) : tracking_metrics option =
  match json with
  | `Assoc fields when List.length fields > 0 ->
    let get_field name = to_float_safe (List.assoc_opt name fields |> Option.value ~default:`Null) in
    Some {
      tracking_error_pct = get_field "tracking_error_pct";
      tracking_difference_pct = get_field "tracking_difference_pct";
      correlation = get_field "correlation";
      beta = get_field "beta";
    }
  | _ -> None

(** Parse capture ratios from JSON *)
let parse_capture_ratios (json : Yojson.Basic.t) : capture_ratios option =
  match json with
  | `Assoc fields when List.length fields > 0 ->
    let get_field name = to_float_safe (List.assoc_opt name fields |> Option.value ~default:`Null) in
    Some {
      upside_capture_pct = get_field "upside_capture_pct";
      downside_capture_pct = get_field "downside_capture_pct";
    }
  | _ -> None

(** Parse distribution analysis from JSON *)
let parse_distribution_analysis (json : Yojson.Basic.t) : distribution_analysis option =
  match json with
  | `Assoc fields when List.length fields > 0 ->
    let get_float name = to_float_safe (List.assoc_opt name fields |> Option.value ~default:`Null) in
    let get_int name = to_int_safe (List.assoc_opt name fields |> Option.value ~default:`Null) in
    let get_string name = to_string_safe (List.assoc_opt name fields |> Option.value ~default:`Null) in
    Some {
      total_12m = get_float "total_12m";
      distribution_yield_pct = get_float "distribution_yield_pct";
      distribution_count_12m = get_int "distribution_count_12m";
      frequency = get_string "frequency";
      avg_distribution = get_float "avg_distribution";
      min_distribution = get_float "min_distribution";
      max_distribution = get_float "max_distribution";
      distribution_variability_pct = get_float "distribution_variability_pct";
    }
  | _ -> None

(** Parse a single holding from JSON *)
let parse_holding (json : Yojson.Basic.t) : holding option =
  match json with
  | `Assoc fields ->
    let get_string name = to_string_safe (List.assoc_opt name fields |> Option.value ~default:`Null) in
    let get_float name = to_float_safe (List.assoc_opt name fields |> Option.value ~default:`Null) in
    let symbol = get_string "symbol" in
    let weight = get_float "weight" in
    if symbol <> "" && weight > 0.0 then
      Some {
        symbol;
        holding_name = get_string "name";
        weight;
      }
    else None
  | _ -> None

(** Parse top holdings from JSON array *)
let parse_top_holdings (json : Yojson.Basic.t) : holding list =
  match json with
  | `List items ->
    List.filter_map parse_holding items
  | _ -> []

(** Parse ETF data from JSON file *)
let parse_etf_data (filename : string) : etf_data =
  let json = Yojson.Basic.from_file filename in
  let open Yojson.Basic.Util in

  let get_float name = to_float_safe (json |> member name) in
  let get_int name = to_int_safe (json |> member name) in
  let get_string name = to_string_safe (json |> member name) in

  {
    ticker = get_string "ticker";
    name = get_string "name";
    category = get_string "category";
    benchmark_ticker = get_string "benchmark_ticker";
    derivatives_type = parse_derivatives_type (get_string "derivatives_type");

    current_price = get_float "current_price";
    nav = get_float "nav";
    previous_close = get_float "previous_close";
    fifty_two_week_high = get_float "fifty_two_week_high";
    fifty_two_week_low = get_float "fifty_two_week_low";

    expense_ratio = get_float "expense_ratio";

    aum = get_float "aum";
    avg_volume = get_float "avg_volume";
    bid_ask_spread = get_float "bid_ask_spread";
    bid_ask_spread_pct = get_float "bid_ask_spread_pct";

    premium_discount = get_float "premium_discount";
    premium_discount_pct = get_float "premium_discount_pct";

    distribution_yield =
      (let y = get_float "yield" in
       if y > 0.0 then y *. 100.0  (* Convert from decimal to % *)
       else get_float "trailing_annual_dividend_yield" *. 100.0);

    holdings_count = get_int "holdings_count";
    top_holdings = parse_top_holdings (json |> member "top_holdings");

    returns = parse_returns (json |> member "returns");
    tracking = parse_tracking (json |> member "tracking");
    capture_ratios = parse_capture_ratios (json |> member "capture_ratios");
    distribution_analysis = parse_distribution_analysis (json |> member "distribution_analysis");
  }

(** Format currency amount *)
let format_currency (amount : float) : string =
  if amount >= 1_000_000_000_000.0 then
    Printf.sprintf "$%.2fT" (amount /. 1_000_000_000_000.0)
  else if amount >= 1_000_000_000.0 then
    Printf.sprintf "$%.2fB" (amount /. 1_000_000_000.0)
  else if amount >= 1_000_000.0 then
    Printf.sprintf "$%.2fM" (amount /. 1_000_000.0)
  else if amount >= 1_000.0 then
    Printf.sprintf "$%.2fK" (amount /. 1_000.0)
  else
    Printf.sprintf "$%.2f" amount

(** Print ETF analysis result *)
let print_result ?(max_holdings = 10) (result : etf_result) : unit =
  let data = result.data in

  Printf.printf "\nETF Analysis: %s (%s)\n" data.name data.ticker;
  Printf.printf "%s\n" (String.make 60 '=');

  (* Basic info *)
  Printf.printf "\nBASIC INFO\n";
  Printf.printf "  Category:           %s\n" data.category;
  Printf.printf "  Type:               %s\n" (Derivatives.derivatives_type_to_string data.derivatives_type);
  Printf.printf "  Benchmark:          %s\n" data.benchmark_ticker;
  Printf.printf "  AUM:                %s\n" (format_currency data.aum);
  Printf.printf "  Holdings:           %d\n" data.holdings_count;

  (* Price and NAV *)
  Printf.printf "\nPRICE & NAV\n";
  Printf.printf "  Current Price:      $%.2f\n" data.current_price;
  if data.nav > 0.0 then begin
    Printf.printf "  NAV:                $%.2f\n" data.nav;
    Printf.printf "  Premium/Discount:   %s\n" (Premium_discount.nav_status_to_string result.nav_status);
  end;
  Printf.printf "  52-Week Range:      $%.2f - $%.2f\n" data.fifty_two_week_low data.fifty_two_week_high;

  (* Cost metrics *)
  Printf.printf "\nCOST METRICS\n";
  Printf.printf "  Expense Ratio:      %.2f%%\n" (data.expense_ratio *. 100.0);
  Printf.printf "  Cost Tier:          %s\n" (Costs.cost_tier_to_string result.cost_tier);
  Printf.printf "  Bid-Ask Spread:     %.2f%%\n" data.bid_ask_spread_pct;
  Printf.printf "  Liquidity:          %s\n" (Costs.liquidity_tier_to_string result.liquidity_tier);

  (* Tracking metrics *)
  (match data.tracking with
   | Some t ->
     Printf.printf "\nTRACKING (vs %s)\n" data.benchmark_ticker;
     Printf.printf "  Tracking Error:     %.2f%%\n" t.tracking_error_pct;
     Printf.printf "  Tracking Diff:      %.2f%%\n" t.tracking_difference_pct;
     Printf.printf "  Correlation:        %.3f\n" t.correlation;
     Printf.printf "  Beta:               %.2f\n" t.beta;
     (match result.tracking_quality with
      | Some q -> Printf.printf "  Quality:            %s\n" (Premium_discount.tracking_quality_to_string q)
      | None -> ())
   | None -> ());

  (* Returns *)
  (match data.returns with
   | Some r ->
     Printf.printf "\nRETURNS\n";
     Printf.printf "  YTD:                %.2f%%\n" r.ytd;
     Printf.printf "  1-Month:            %.2f%%\n" r.one_month;
     Printf.printf "  3-Month:            %.2f%%\n" r.three_month;
     Printf.printf "  1-Year:             %.2f%%\n" r.one_year;
     Printf.printf "  Volatility (1Y):    %.2f%%\n" r.volatility_1y
   | None -> ());

  (* Derivatives-specific analysis *)
  (match result.derivatives_analysis with
   | CoveredCallAnalysis cc ->
     Printf.printf "\nCOVERED CALL ANALYSIS\n";
     Printf.printf "  Distribution Yield: %.2f%%\n" cc.distribution_yield_pct;
     if cc.upside_capture > 0.0 then begin
       Printf.printf "  Upside Capture:     %.1f%%\n" cc.upside_capture;
       Printf.printf "  Downside Capture:   %.1f%%\n" cc.downside_capture;
       Printf.printf "  Capture Efficiency: %.1f%%\n" cc.capture_efficiency;
     end;
     Printf.printf "  Yield vs Benchmark: %.1fx\n" cc.yield_vs_benchmark
   | BufferAnalysis buf ->
     Printf.printf "\nBUFFER ETF ANALYSIS\n";
     Printf.printf "  Status:             %s\n" buf.buffer_status
   | VolatilityAnalysis vol ->
     Printf.printf "\nVOLATILITY ETF ANALYSIS\n";
     Printf.printf "  Term Structure:     %s\n" vol.term_structure;
     Printf.printf "  Est. Monthly Decay: %.2f%%\n" vol.roll_yield_monthly_pct;
     Printf.printf "  Est. Annual Decay:  %.2f%%\n" vol.roll_yield_annual_pct;
     if vol.decay_warning then
       Printf.printf "  WARNING:            SEVERE DECAY - NOT FOR BUY-AND-HOLD\n"
   | NoDerivatives -> ());

  (* Distribution analysis for income ETFs *)
  (match data.distribution_analysis with
   | Some dist when data.derivatives_type = CoveredCall || data.derivatives_type = PutWrite ->
     Printf.printf "\nDISTRIBUTION DETAILS\n";
     Printf.printf "  12-Month Total:     $%.2f\n" dist.total_12m;
     Printf.printf "  Frequency:          %s (%d payments)\n" dist.frequency dist.distribution_count_12m;
     Printf.printf "  Avg Distribution:   $%.4f\n" dist.avg_distribution;
     Printf.printf "  Range:              $%.4f - $%.4f\n" dist.min_distribution dist.max_distribution;
     Printf.printf "  Variability:        %.1f%%\n" dist.distribution_variability_pct
   | _ -> ());

  (* Score *)
  Printf.printf "\nETF QUALITY SCORE\n";
  Printf.printf "  Total Score:        %.0f/100\n" result.score.total_score;
  Printf.printf "  Grade:              %s\n" result.score.grade;
  Printf.printf "  Signal:             %s\n" (Scoring.signal_to_string result.signal);
  Printf.printf "\n  Breakdown:\n";
  Printf.printf "    Cost:             %.0f/25\n" result.score.cost_score;
  (match data.derivatives_type with
   | Standard -> Printf.printf "    Tracking:         %.0f/25\n" result.score.tracking_score
   | _ -> Printf.printf "    Derivatives:      %.0f/25\n" result.score.tracking_score);
  Printf.printf "    Liquidity:        %.0f/25\n" result.score.liquidity_score;
  Printf.printf "    Size:             %.0f/25\n" result.score.size_score;

  (* Top Holdings *)
  if List.length data.top_holdings > 0 then begin
    let display_count = min max_holdings (List.length data.top_holdings) in
    Printf.printf "\nTOP HOLDINGS (showing %d)\n" display_count;
    Printf.printf "  %-8s %6s  %s\n" "Symbol" "Weight" "Name";
    Printf.printf "  %s\n" (String.make 50 '-');
    List.iteri (fun i (h : holding) ->
        if i < max_holdings then
          let name_truncated =
            if String.length h.holding_name > 30 then
              String.sub h.holding_name 0 27 ^ "..."
            else h.holding_name
          in
          Printf.printf "  %-8s %5.2f%%  %s\n" h.symbol h.weight name_truncated
      ) data.top_holdings;
    (* Show tickers for easy copy-paste *)
    let displayed_holdings = List.filteri (fun i _ -> i < max_holdings) data.top_holdings in
    let symbols = List.map (fun (h : holding) -> h.symbol) displayed_holdings in
    let symbols_str = String.concat "," symbols in
    Printf.printf "\n  Tickers: %s\n" symbols_str
  end;

  (* Recommendations *)
  if List.length result.recommendations > 0 then begin
    Printf.printf "\nRECOMMENDATIONS\n";
    List.iter (fun r -> Printf.printf "  - %s\n" r) result.recommendations
  end

(** Print comparison results *)
let print_comparison ?(max_holdings = 10) (comparison : etf_comparison) : unit =
  Printf.printf "\nETF Comparison\n";
  Printf.printf "%s\n" (String.make 80 '=');

  Printf.printf "\n%-8s %8s %10s %10s %8s %8s %6s\n"
    "Ticker" "Price" "AUM" "ER" "Spread" "Score" "Grade";
  Printf.printf "%s\n" (String.make 80 '-');

  List.iter (fun (r : etf_result) ->
      Printf.printf "%-8s %8.2f %10s %9.2f%% %7.2f%% %8.0f %6s\n"
        r.data.ticker
        r.data.current_price
        (format_currency r.data.aum)
        (r.data.expense_ratio *. 100.0)
        r.data.bid_ask_spread_pct
        r.score.total_score
        r.score.grade
    ) comparison.results;

  Printf.printf "\nBest in Category:\n";
  Printf.printf "  Lowest Cost:        %s\n" comparison.best_cost;
  Printf.printf "  Best Tracking:      %s\n" comparison.best_tracking;
  Printf.printf "  Best Liquidity:     %s\n" comparison.best_liquidity;
  Printf.printf "  Best Overall:       %s\n" comparison.best_overall;

  (* Collect all unique holdings across all ETFs, respecting max_holdings per ETF *)
  let all_holdings =
    List.fold_left (fun acc (r : etf_result) ->
        let limited_holdings = List.filteri (fun i _ -> i < max_holdings) r.data.top_holdings in
        List.fold_left (fun acc2 (h : holding) ->
            if List.exists (fun (h2 : holding) -> h2.symbol = h.symbol) acc2 then acc2
            else h :: acc2
          ) acc limited_holdings
      ) [] comparison.results
    |> List.rev
  in
  if List.length all_holdings > 0 then begin
    Printf.printf "\n%s\n" (String.make 80 '=');
    Printf.printf "AGGREGATE TOP HOLDINGS (for portfolio analysis)\n";
    Printf.printf "%s\n" (String.make 80 '=');
    let symbols = List.map (fun (h : holding) -> h.symbol) all_holdings in
    Printf.printf "\n  All unique tickers (%d): %s\n" (List.length symbols) (String.concat "," symbols);
    Printf.printf "\n  Use these tickers with:\n";
    Printf.printf "  Valuation:\n";
    Printf.printf "    - DCF Deterministic (intrinsic value per share)\n";
    Printf.printf "    - DCF Probabilistic (Monte Carlo valuation + efficient frontier)\n";
    Printf.printf "    - Relative Valuation (peer comparison)\n";
    Printf.printf "    - Normalized Multiples (comparative analysis)\n";
    Printf.printf "    - GARP / PEG (growth at a reasonable price)\n";
    Printf.printf "    - Growth Analysis (revenue growth, Rule of 40)\n";
    Printf.printf "    - Dividend Income (DDM fair value, safety scoring)\n";
    Printf.printf "  Risk & Portfolio:\n";
    Printf.printf "    - Regime-Aware Downside Optimization (portfolio risk)\n";
    Printf.printf "    - Tail Risk Forecast (HAR-RV volatility, VaR/ES)\n";
    Printf.printf "    - Liquidity Analysis (volume, OBV, smart money flow)\n"
  end

(** Serialize derivatives analysis to JSON *)
let derivatives_analysis_to_json (da : derivatives_analysis) : Yojson.Basic.t =
  match da with
  | CoveredCallAnalysis cc ->
    `Assoc [
      ("type", `String "covered_call");
      ("distribution_yield_pct", `Float cc.distribution_yield_pct);
      ("upside_capture", `Float cc.upside_capture);
      ("downside_capture", `Float cc.downside_capture);
      ("yield_vs_benchmark", `Float cc.yield_vs_benchmark);
      ("capture_efficiency", `Float cc.capture_efficiency);
    ]
  | BufferAnalysis buf ->
    `Assoc [
      ("type", `String "buffer");
      ("buffer_level", `Float buf.buffer_level);
      ("cap_level", `Float buf.cap_level);
      ("remaining_buffer", `Float buf.remaining_buffer);
      ("days_to_outcome", `Int buf.days_to_outcome);
      ("buffer_status", `String buf.buffer_status);
    ]
  | VolatilityAnalysis vol ->
    `Assoc [
      ("type", `String "volatility");
      ("term_structure", `String vol.term_structure);
      ("roll_yield_monthly_pct", `Float vol.roll_yield_monthly_pct);
      ("roll_yield_annual_pct", `Float vol.roll_yield_annual_pct);
      ("decay_warning", `Bool vol.decay_warning);
    ]
  | NoDerivatives -> `Null

(** Serialize result to JSON *)
let result_to_json (result : etf_result) : Yojson.Basic.t =
  let data = result.data in
  let score = result.score in

  let nav_status_str = Premium_discount.nav_status_to_string result.nav_status in
  let signal_str = Scoring.signal_to_string result.signal in

  `Assoc [
    ("ticker", `String data.ticker);
    ("name", `String data.name);
    ("category", `String data.category);
    ("derivatives_type", `String (Derivatives.derivatives_type_to_string data.derivatives_type));
    ("current_price", `Float data.current_price);
    ("aum", `Float data.aum);
    ("expense_ratio_pct", `Float (data.expense_ratio *. 100.0));
    ("bid_ask_spread_pct", `Float data.bid_ask_spread_pct);
    ("distribution_yield_pct", `Float data.distribution_yield);
    ("premium_discount_pct", `Float data.premium_discount_pct);
    ("nav_status", `String nav_status_str);
    ("liquidity_tier", `String (Costs.liquidity_tier_to_string result.liquidity_tier));
    ("cost_tier", `String (Costs.cost_tier_to_string result.cost_tier));
    ("size_tier", `String (Costs.size_tier_to_string result.size_tier));
    ("tracking", (match data.tracking with
      | Some t -> `Assoc [
          ("tracking_error_pct", `Float t.tracking_error_pct);
          ("tracking_difference_pct", `Float t.tracking_difference_pct);
          ("correlation", `Float t.correlation);
          ("beta", `Float t.beta);
        ]
      | None -> `Null));
    ("capture_ratios", (match data.capture_ratios with
      | Some cr -> `Assoc [
          ("upside_capture_pct", `Float cr.upside_capture_pct);
          ("downside_capture_pct", `Float cr.downside_capture_pct);
        ]
      | None -> `Null));
    ("derivatives_analysis", derivatives_analysis_to_json result.derivatives_analysis);
    ("score", `Assoc [
        ("total_score", `Float score.total_score);
        ("grade", `String score.grade);
        ("cost_score", `Float score.cost_score);
        ("tracking_score", `Float score.tracking_score);
        ("liquidity_score", `Float score.liquidity_score);
        ("size_score", `Float score.size_score);
      ]);
    ("signal", `String signal_str);
    ("recommendations", `List (List.map (fun r -> `String r) result.recommendations));
    ("top_holdings", `List (List.map (fun (h : holding) ->
        `Assoc [
          ("symbol", `String h.symbol);
          ("name", `String h.holding_name);
          ("weight", `Float h.weight);
        ]
      ) data.top_holdings));
    ("top_holdings_tickers", `String (String.concat "," (List.map (fun (h : holding) -> h.symbol) data.top_holdings)));
  ]

(** Save result to JSON file *)
let save_result (result : etf_result) (filename : string) : unit =
  let json = result_to_json result in
  let out_channel = open_out filename in
  Yojson.Basic.pretty_to_channel out_channel json;
  close_out out_channel

(** Save comparison to JSON file *)
let save_comparison (comparison : etf_comparison) (filename : string) : unit =
  let json = `Assoc [
      ("results", `List (List.map result_to_json comparison.results));
      ("best_cost", `String comparison.best_cost);
      ("best_tracking", `String comparison.best_tracking);
      ("best_liquidity", `String comparison.best_liquidity);
      ("best_overall", `String comparison.best_overall);
    ]
  in
  let out_channel = open_out filename in
  Yojson.Basic.pretty_to_channel out_channel json;
  close_out out_channel
