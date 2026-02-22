(** I/O functions for GARP/PEG analysis *)

open Types

(** Helper to get float from JSON with default *)
let get_float json key default =
  match Yojson.Basic.Util.member key json with
  | `Float f -> f
  | `Int i -> float_of_int i
  | _ -> default


(** Helper to get string from JSON with default *)
let get_string json key default =
  match Yojson.Basic.Util.member key json with
  | `String s -> s
  | _ -> default


(** Read GARP data from JSON file *)
let read_garp_data (filename : string) : garp_data =
  let json = Yojson.Basic.from_file filename in
  {
    ticker = get_string json "ticker" "UNKNOWN";
    price = get_float json "price" 0.0;
    market_cap = get_float json "market_cap" 0.0;
    shares_outstanding = get_float json "shares_outstanding" 0.0;

    eps_trailing = get_float json "eps_trailing" 0.0;
    eps_forward = get_float json "eps_forward" 0.0;

    pe_trailing = get_float json "pe_trailing" 0.0;
    pe_forward = get_float json "pe_forward" 0.0;

    earnings_growth = get_float json "earnings_growth" 0.0;
    earnings_quarterly_growth = get_float json "earnings_quarterly_growth" 0.0;
    revenue_growth = get_float json "revenue_growth" 0.0;
    eps_growth_1y = get_float json "eps_growth_1y" 0.0;
    growth_estimate_5y = get_float json "growth_estimate_5y" 0.0;

    peg_ratio_yf = get_float json "peg_ratio_yf" 0.0;

    free_cash_flow = get_float json "free_cash_flow" 0.0;
    operating_cash_flow = get_float json "operating_cash_flow" 0.0;
    net_income = get_float json "net_income" 0.0;
    total_revenue = get_float json "total_revenue" 0.0;

    total_debt = get_float json "total_debt" 0.0;
    total_equity = get_float json "total_equity" 0.0;
    total_cash = get_float json "total_cash" 0.0;
    debt_to_equity = get_float json "debt_to_equity" 0.0;

    roe = get_float json "roe" 0.0;
    roa = get_float json "roa" 0.0;

    fcf_conversion = get_float json "fcf_conversion" 0.0;
    fcf_per_share = get_float json "fcf_per_share" 0.0;
    book_value_per_share = get_float json "book_value_per_share" 0.0;
    net_cash_per_share = get_float json "net_cash_per_share" 0.0;

    dividend_yield = get_float json "dividend_yield" 0.0;
    dividend_rate = get_float json "dividend_rate" 0.0;

    sector = get_string json "sector" "Unknown";
    industry = get_string json "industry" "Unknown";
  }


(** Convert garp_signal to string *)
let signal_to_string (signal : garp_signal) : string =
  match signal with
  | StrongBuy -> "Strong Buy"
  | Buy -> "Buy"
  | Hold -> "Hold"
  | Caution -> "Caution"
  | Avoid -> "Avoid"
  | NotApplicable -> "N/A"


(** Convert option float to JSON *)
let option_float_to_json (opt : float option) : Yojson.Basic.t =
  match opt with
  | Some f -> `Float f
  | None -> `Null


(** Write GARP result to JSON *)
let write_garp_result (filename : string) (result : garp_result) : unit =
  let json = `Assoc [
    ("ticker", `String result.ticker);
    ("price", `Float result.price);

    ("peg_metrics", `Assoc [
      ("pe_trailing", `Float result.peg_metrics.pe_trailing);
      ("pe_forward", `Float result.peg_metrics.pe_forward);
      ("growth_rate_used", `Float result.peg_metrics.growth_rate_used);
      ("growth_source", `String result.peg_metrics.growth_source);
      ("peg_trailing", `Float result.peg_metrics.peg_trailing);
      ("peg_forward", `Float result.peg_metrics.peg_forward);
      ("pegy", `Float result.peg_metrics.pegy);
      ("peg_assessment", `String result.peg_metrics.peg_assessment);
    ]);

    ("quality_metrics", `Assoc [
      ("fcf_conversion", `Float result.quality_metrics.fcf_conversion);
      ("debt_to_equity", `Float result.quality_metrics.debt_to_equity);
      ("roe", `Float result.quality_metrics.roe);
      ("roa", `Float result.quality_metrics.roa);
      ("earnings_quality", `String result.quality_metrics.earnings_quality);
      ("balance_sheet_strength", `String result.quality_metrics.balance_sheet_strength);
    ]);

    ("garp_score", `Assoc [
      ("total_score", `Float result.garp_score.total_score);
      ("grade", `String result.garp_score.grade);
      ("peg_score", `Float result.garp_score.peg_score);
      ("growth_score", `Float result.garp_score.growth_score);
      ("quality_score", `Float result.garp_score.quality_score);
      ("balance_sheet_score", `Float result.garp_score.balance_sheet_score);
      ("roe_score", `Float result.garp_score.roe_score);
    ]);

    ("signal", `String (signal_to_string result.signal));
    ("implied_fair_pe", option_float_to_json result.implied_fair_pe);
    ("implied_fair_price", option_float_to_json result.implied_fair_price);
    ("upside_downside_pct", option_float_to_json result.upside_downside);
  ] in

  let oc = open_out filename in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc


(** Write comparison results to JSON *)
let write_comparison (filename : string) (comp : garp_comparison) : unit =
  let result_to_json r = `Assoc [
    ("ticker", `String r.ticker);
    ("price", `Float r.price);
    ("peg_forward", `Float r.peg_metrics.peg_forward);
    ("peg_trailing", `Float r.peg_metrics.peg_trailing);
    ("growth_rate", `Float r.peg_metrics.growth_rate_used);
    ("total_score", `Float r.garp_score.total_score);
    ("grade", `String r.garp_score.grade);
    ("signal", `String (signal_to_string r.signal));
  ] in

  let json = `Assoc [
    ("results", `List (List.map result_to_json comp.results));
    ("best_peg", match comp.best_peg with Some t -> `String t | None -> `Null);
    ("best_score", match comp.best_score with Some t -> `String t | None -> `Null);
    ("ranking", `List (List.map (fun (t, s) ->
      `Assoc [("ticker", `String t); ("score", `Float s)]
    ) comp.ranking));
  ] in

  let oc = open_out filename in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc


(** Print GARP result to stdout in formatted style *)
let print_result (result : garp_result) : unit =
  let p = Printf.printf in
  let divider = String.make 60 '=' in
  let subdiv = String.make 60 '-' in

  p "\n%s\n" divider;
  p "GARP Analysis: %s\n" result.ticker;
  p "%s\n\n" divider;

  p "PRICE & VALUATION\n";
  p "%s\n" subdiv;
  p "  Current Price:     $%.2f\n" result.price;
  p "  P/E (Trailing):    %.1fx\n" result.peg_metrics.pe_trailing;
  p "  P/E (Forward):     %.1fx\n" result.peg_metrics.pe_forward;
  p "\n";

  p "PEG ANALYSIS\n";
  p "%s\n" subdiv;
  p "  Growth Rate Used:  %.1f%% (%s)\n"
    result.peg_metrics.growth_rate_used
    result.peg_metrics.growth_source;
  p "  PEG (Trailing):    %.2f\n" result.peg_metrics.peg_trailing;
  p "  PEG (Forward):     %.2f\n" result.peg_metrics.peg_forward;
  p "  PEGY:              %.2f\n" result.peg_metrics.pegy;
  p "  Assessment:        %s\n" result.peg_metrics.peg_assessment;
  p "\n";

  p "QUALITY METRICS\n";
  p "%s\n" subdiv;
  p "  FCF Conversion:    %.1f%%\n" (result.quality_metrics.fcf_conversion *. 100.0);
  p "  Debt/Equity:       %.2f\n" result.quality_metrics.debt_to_equity;
  p "  ROE:               %.1f%%\n" (result.quality_metrics.roe *. 100.0);
  p "  Earnings Quality:  %s\n" result.quality_metrics.earnings_quality;
  p "  Balance Sheet:     %s\n" result.quality_metrics.balance_sheet_strength;
  p "\n";

  p "GARP SCORE: %.0f/100 (Grade: %s)\n"
    result.garp_score.total_score
    result.garp_score.grade;
  p "%s\n" subdiv;
  p "  PEG Score:         %.0f/30\n" result.garp_score.peg_score;
  p "  Growth Score:      %.0f/25\n" result.garp_score.growth_score;
  p "  Quality Score:     %.0f/20\n" result.garp_score.quality_score;
  p "  Balance Sheet:     %.0f/15\n" result.garp_score.balance_sheet_score;
  p "  ROE Score:         %.0f/10\n" result.garp_score.roe_score;
  p "\n";

  p "SIGNAL: %s\n" (signal_to_string result.signal);
  p "%s\n" subdiv;

  (match result.implied_fair_pe with
   | Some pe -> p "  Implied Fair P/E (PEG=1): %.1fx\n" pe
   | None -> ());

  (match result.implied_fair_price with
   | Some fp -> p "  Implied Fair Price:       $%.2f\n" fp
   | None -> ());

  (match result.upside_downside with
   | Some ud ->
     let direction = if ud >= 0.0 then "Upside" else "Downside" in
     p "  %s to Fair Value:   %.1f%%\n" direction (abs_float ud)
   | None -> ());

  p "\n%s\n" divider;
  ()


(** Print comparison results *)
let print_comparison (comp : garp_comparison) : unit =
  let p = Printf.printf in
  let divider = String.make 80 '=' in

  p "\n%s\n" divider;
  p "GARP COMPARISON\n";
  p "%s\n\n" divider;

  p "%-8s %8s %8s %8s %8s %6s %s\n"
    "Ticker" "Price" "PEG Fwd" "Growth%" "Score" "Grade" "Signal";
  p "%s\n" (String.make 80 '-');

  List.iter (fun r ->
    p "%-8s %8.2f %8.2f %8.1f %8.0f %6s %s\n"
      r.ticker
      r.price
      r.peg_metrics.peg_forward
      r.peg_metrics.growth_rate_used
      r.garp_score.total_score
      r.garp_score.grade
      (signal_to_string r.signal)
  ) comp.results;

  p "\n";
  (match comp.best_peg with
   | Some t -> p "Best PEG:   %s\n" t
   | None -> ());
  (match comp.best_score with
   | Some t -> p "Best Score: %s\n" t
   | None -> ());

  p "\n%s\n" divider;
  ()
