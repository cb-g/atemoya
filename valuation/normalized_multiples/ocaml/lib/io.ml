(** JSON parsing and output formatting - Implementation *)

open Types

(* Handle both int and float JSON values *)
let to_number json =
  match json with
  | `Float f -> f
  | `Int i -> float_of_int i
  | _ -> 0.0

let parse_normalized_multiple json =
  let name = Yojson.Basic.Util.(json |> member "name" |> to_string) in
  let tw_str = Yojson.Basic.Util.(json |> member "time_window" |> to_string) in
  let time_window = match time_window_of_string tw_str with
    | Some tw -> tw
    | None -> TTM
  in
  let value = to_number Yojson.Basic.Util.(json |> member "value") in
  let underlying_metric = to_number Yojson.Basic.Util.(json |> member "underlying_metric") in
  let is_valid = Yojson.Basic.Util.(json |> member "is_valid" |> to_bool) in
  { name; time_window; value; is_valid; underlying_metric }

let read_multiples_data filename =
  let json = Yojson.Basic.from_file filename in
  let m = Yojson.Basic.Util.member in
  let s = Yojson.Basic.Util.to_string in
  {
    ticker = json |> m "ticker" |> s;
    company_name = json |> m "company_name" |> s;
    sector = json |> m "sector" |> s;
    industry = json |> m "industry" |> s;
    current_price = to_number (json |> m "current_price");
    market_cap = to_number (json |> m "market_cap");
    enterprise_value = to_number (json |> m "enterprise_value");
    shares_outstanding = to_number (json |> m "shares_outstanding");

    pe_ttm = json |> m "pe_ttm" |> parse_normalized_multiple;
    pe_ntm = json |> m "pe_ntm" |> parse_normalized_multiple;
    ps_ttm = json |> m "ps_ttm" |> parse_normalized_multiple;
    pb_ttm = json |> m "pb_ttm" |> parse_normalized_multiple;
    p_fcf_ttm = json |> m "p_fcf_ttm" |> parse_normalized_multiple;
    peg_ratio = json |> m "peg_ratio" |> parse_normalized_multiple;

    ev_ebitda_ttm = json |> m "ev_ebitda_ttm" |> parse_normalized_multiple;
    ev_ebit_ttm = json |> m "ev_ebit_ttm" |> parse_normalized_multiple;
    ev_sales_ttm = json |> m "ev_sales_ttm" |> parse_normalized_multiple;
    ev_fcf_ttm = json |> m "ev_fcf_ttm" |> parse_normalized_multiple;

    revenue_growth_ttm = to_number (json |> m "revenue_growth_ttm");
    eps_growth_ttm = to_number (json |> m "eps_growth_ttm");
    eps_growth_ntm = to_number (json |> m "eps_growth_ntm");

    gross_margin = to_number (json |> m "gross_margin");
    operating_margin = to_number (json |> m "operating_margin");
    ebitda_margin = to_number (json |> m "ebitda_margin");

    roe = to_number (json |> m "roe");
    roic = to_number (json |> m "roic");
  }

let default_benchmark sector =
  (* Default benchmarks when no sector file exists *)
  {
    sector;
    industry = None;
    sample_size = 0;

    pe_ttm_median = 20.0; pe_ttm_p25 = 15.0; pe_ttm_p75 = 30.0;
    pe_ntm_median = 18.0; pe_ntm_p25 = 13.0; pe_ntm_p75 = 25.0;

    ps_median = 3.0; ps_p25 = 1.5; ps_p75 = 6.0;
    pb_median = 3.0; pb_p25 = 1.5; pb_p75 = 5.0;
    p_fcf_median = 20.0; p_fcf_p25 = 12.0; p_fcf_p75 = 35.0;
    peg_median = 1.5; peg_p25 = 1.0; peg_p75 = 2.5;

    ev_ebitda_median = 12.0; ev_ebitda_p25 = 8.0; ev_ebitda_p75 = 18.0;
    ev_ebit_median = 15.0;
    ev_sales_median = 3.0;
    ev_fcf_median = 18.0;

    revenue_growth_median = 0.05;
    ebitda_margin_median = 0.15;
    roe_median = 0.12;
  }

let load_sector_benchmark data_dir sector =
  let filename = Printf.sprintf "%s/sector_benchmarks/benchmark_%s.json"
    data_dir (String.map (fun c -> if c = ' ' then '_' else c) sector) in
  if Sys.file_exists filename then begin
    let json = Yojson.Basic.from_file filename in
    let open Yojson.Basic.Util in
    {
      sector = json |> member "sector" |> to_string;
      industry = None;
      sample_size = json |> member "sample_size" |> to_int;

      pe_ttm_median = json |> member "pe_ttm_median" |> to_float;
      pe_ttm_p25 = json |> member "pe_ttm_p25" |> to_float;
      pe_ttm_p75 = json |> member "pe_ttm_p75" |> to_float;
      pe_ntm_median = json |> member "pe_ntm_median" |> to_float;
      pe_ntm_p25 = json |> member "pe_ntm_p25" |> to_float;
      pe_ntm_p75 = json |> member "pe_ntm_p75" |> to_float;

      ps_median = json |> member "ps_median" |> to_float;
      ps_p25 = json |> member "ps_p25" |> to_float;
      ps_p75 = json |> member "ps_p75" |> to_float;
      pb_median = json |> member "pb_median" |> to_float;
      pb_p25 = json |> member "pb_p25" |> to_float;
      pb_p75 = json |> member "pb_p75" |> to_float;
      p_fcf_median = json |> member "p_fcf_median" |> to_float;
      p_fcf_p25 = json |> member "p_fcf_p25" |> to_float;
      p_fcf_p75 = json |> member "p_fcf_p75" |> to_float;
      peg_median = json |> member "peg_median" |> to_float;
      peg_p25 = json |> member "peg_p25" |> to_float;
      peg_p75 = json |> member "peg_p75" |> to_float;

      ev_ebitda_median = json |> member "ev_ebitda_median" |> to_float;
      ev_ebitda_p25 = json |> member "ev_ebitda_p25" |> to_float;
      ev_ebitda_p75 = json |> member "ev_ebitda_p75" |> to_float;
      ev_ebit_median = json |> member "ev_ebit_median" |> to_float;
      ev_sales_median = json |> member "ev_sales_median" |> to_float;
      ev_fcf_median = json |> member "ev_fcf_median" |> to_float;

      revenue_growth_median = json |> member "revenue_growth_median" |> to_float;
      ebitda_margin_median = json |> member "ebitda_margin_median" |> to_float;
      roe_median = json |> member "roe_median" |> to_float;
    }
  end else
    default_benchmark sector

(* Console output helpers *)
let signal_color signal =
  match signal with
  | DeepValue -> "\027[32m"      (* Green *)
  | Undervalued -> "\027[32m"
  | FairValue -> "\027[33m"      (* Yellow *)
  | Overvalued -> "\027[33m"
  | Expensive -> "\027[31m"      (* Red *)
  | NotMeaningful -> "\027[90m"  (* Gray *)

let reset_color = "\027[0m"
let bold = "\027[1m"

let percentile_bar pct =
  (* Create a visual bar showing position in distribution *)
  let pos = int_of_float (pct /. 10.0) in
  let bar = String.init 10 (fun i ->
    if i = pos then '|' else if i < pos then '=' else ' '
  ) in
  Printf.sprintf "[%s]" bar

let print_multiple_row c =
  let m = c.multiple in
  if m.is_valid then begin
    let name = Printf.sprintf "%s (%s)" m.name (string_of_time_window m.time_window) in
    let signal = signal_of_percentile c.percentile_rank true in
    let color = signal_color signal in
    Printf.printf "%-16s %6.1fx  %s  %3.0fth %%ile  %s%s%s\n"
      name m.value
      (percentile_bar c.percentile_rank)
      c.percentile_rank
      color (string_of_signal signal) reset_color
  end

let print_single_result (result : single_ticker_result) =
  Printf.printf "\n%s%s%s\n" bold (String.make 65 '=') reset_color;
  Printf.printf "%s              NORMALIZED MULTIPLES - %s%s\n"
    bold result.ticker reset_color;
  Printf.printf "%s%s%s\n\n" bold (String.make 65 '=') reset_color;

  Printf.printf "Price: $%.2f | Sector: %s | Date: %s\n\n"
    result.current_price result.sector result.analysis_date;

  (* Price multiples *)
  Printf.printf "%sPRICE MULTIPLES%s                                vs Sector\n" bold reset_color;
  Printf.printf "%s\n" (String.make 65 '-');
  List.iter print_multiple_row result.price_multiples;
  Printf.printf "\n";

  (* EV multiples *)
  Printf.printf "%sEV MULTIPLES%s\n" bold reset_color;
  Printf.printf "%s\n" (String.make 65 '-');
  List.iter print_multiple_row result.ev_multiples;
  Printf.printf "\n";

  (* Quality adjustment *)
  Printf.printf "%sQUALITY ADJUSTMENT%s\n" bold reset_color;
  Printf.printf "%s\n" (String.make 65 '-');
  Printf.printf "Growth premium:     %+.0f%%\n" result.quality_adj.growth_premium_pct;
  Printf.printf "Margin premium:     %+.0f%%\n" result.quality_adj.margin_premium_pct;
  Printf.printf "Return premium:     %+.0f%%\n" result.quality_adj.return_premium_pct;
  Printf.printf "Total adjustment:   %+.0f%%\n\n" result.quality_adj.total_fair_premium_pct;

  let raw_signal = signal_of_percentile result.composite_percentile true in
  let adj_signal = result.overall_signal in
  Printf.printf "Raw percentile: %.0fth (%s%s%s) -> Quality-adjusted: %.0fth (%s%s%s)\n\n"
    result.composite_percentile
    (signal_color raw_signal) (string_of_signal raw_signal) reset_color
    result.quality_adjusted_percentile
    (signal_color adj_signal) (string_of_signal adj_signal) reset_color;

  (* Implied valuations *)
  if List.length result.implied_prices > 0 then begin
    Printf.printf "%sIMPLIED VALUATIONS%s\n" bold reset_color;
    Printf.printf "%s\n" (String.make 65 '-');
    Printf.printf "%-20s %15s %15s\n" "Method" "Implied Price" "Upside/Down";
    List.iter (fun (name, price) ->
      let upside = (price -. result.current_price) /. result.current_price *. 100.0 in
      let color = if upside >= 0.0 then "\027[32m" else "\027[31m" in
      Printf.printf "%-20s %14s $%.2f %s%+.1f%%%s\n"
        name "" price color upside reset_color
    ) result.implied_prices;
    Printf.printf "%s\n" (String.make 65 '-');
    (match result.average_implied_price with
     | Some avg ->
       let upside = (avg -. result.current_price) /. result.current_price *. 100.0 in
       Printf.printf "%-20s %14s $%.2f %+.1f%%\n" "Average" "" avg upside
     | None -> ());
    (match result.median_implied_price with
     | Some med ->
       let upside = (med -. result.current_price) /. result.current_price *. 100.0 in
       Printf.printf "%-20s %14s $%.2f %+.1f%%\n" "Median" "" med upside
     | None -> ());
    Printf.printf "\n"
  end;

  (* Summary *)
  if List.length result.summary > 0 then begin
    Printf.printf "%sSUMMARY%s\n" bold reset_color;
    List.iter (fun s -> Printf.printf "  - %s\n" s) result.summary;
    Printf.printf "\n"
  end;

  Printf.printf "Confidence: %.0f%% | Cheapest: %s | Most Expensive: %s\n"
    result.confidence result.cheapest_multiple result.most_expensive_multiple

let print_comparative_result result =
  Printf.printf "\n%s%s%s\n" bold (String.make 65 '=') reset_color;
  Printf.printf "%s          COMPARATIVE MULTIPLES ANALYSIS%s\n" bold reset_color;
  Printf.printf "%s%s%s\n\n" bold (String.make 65 '=') reset_color;

  Printf.printf "Tickers: %s | Sector: %s | Date: %s\n\n"
    (String.concat ", " result.tickers) result.sector result.analysis_date;

  (* Rankings *)
  let print_ranking title entries =
    Printf.printf "%s%s%s\n" bold title reset_color;
    List.iteri (fun i e ->
      let color = signal_color e.signal in
      Printf.printf "  %d. %s: %.1fx %s%s%s\n"
        (i + 1) e.ticker e.value color (string_of_signal e.signal) reset_color
    ) entries;
    Printf.printf "\n"
  in

  print_ranking "P/E (TTM) Ranking" result.pe_ttm_ranking;
  print_ranking "EV/EBITDA Ranking" result.ev_ebitda_ranking;
  print_ranking "PEG Ranking" result.peg_ranking;

  (* Best picks *)
  Printf.printf "%sBEST PICKS%s\n" bold reset_color;
  (match result.best_value with
   | Some t -> Printf.printf "  Best Value: %s\n" t
   | None -> ());
  (match result.best_quality_adjusted with
   | Some t -> Printf.printf "  Best Quality-Adjusted: %s\n" t
   | None -> ());
  (match result.best_peg with
   | Some t -> Printf.printf "  Best PEG: %s\n" t
   | None -> ());
  Printf.printf "\n"

let write_single_result_json output_dir (result : single_ticker_result) =
  let multiple_to_json c =
    `Assoc [
      ("name", `String c.multiple.name);
      ("time_window", `String (string_of_time_window c.multiple.time_window));
      ("value", `Float c.multiple.value);
      ("is_valid", `Bool c.multiple.is_valid);
      ("benchmark_median", `Float c.benchmark_median);
      ("premium_discount_pct", `Float c.premium_discount_pct);
      ("percentile_rank", `Float c.percentile_rank);
      ("signal", `String (string_of_signal (signal_of_percentile c.percentile_rank c.multiple.is_valid)));
      ("implied_price", match c.implied_price with Some p -> `Float p | None -> `Null);
    ]
  in
  let json = `Assoc [
    ("ticker", `String result.ticker);
    ("company_name", `String result.company_name);
    ("sector", `String result.sector);
    ("industry", `String result.industry);
    ("current_price", `Float result.current_price);
    ("analysis_date", `String result.analysis_date);
    ("price_multiples", `List (List.map multiple_to_json result.price_multiples));
    ("ev_multiples", `List (List.map multiple_to_json result.ev_multiples));
    ("quality_adjustment", `Assoc [
      ("growth_premium_pct", `Float result.quality_adj.growth_premium_pct);
      ("margin_premium_pct", `Float result.quality_adj.margin_premium_pct);
      ("return_premium_pct", `Float result.quality_adj.return_premium_pct);
      ("total_fair_premium_pct", `Float result.quality_adj.total_fair_premium_pct);
    ]);
    ("composite_percentile", `Float result.composite_percentile);
    ("quality_adjusted_percentile", `Float result.quality_adjusted_percentile);
    ("overall_signal", `String (string_of_signal result.overall_signal));
    ("confidence", `Float result.confidence);
    ("implied_prices", `Assoc (List.map (fun (n, p) -> (n, `Float p)) result.implied_prices));
    ("average_implied_price", match result.average_implied_price with Some p -> `Float p | None -> `Null);
    ("median_implied_price", match result.median_implied_price with Some p -> `Float p | None -> `Null);
    ("cheapest_multiple", `String result.cheapest_multiple);
    ("most_expensive_multiple", `String result.most_expensive_multiple);
    ("summary", `List (List.map (fun s -> `String s) result.summary));
  ] in
  let filename = Printf.sprintf "%s/multiples_result_%s.json" output_dir result.ticker in
  let oc = open_out filename in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc;
  Printf.printf "Result written to: %s\n" filename

let write_comparative_result_json output_dir result =
  let ranking_to_json entries =
    `List (List.map (fun e ->
      `Assoc [
        ("ticker", `String e.ticker);
        ("value", `Float e.value);
        ("signal", `String (string_of_signal e.signal));
      ]
    ) entries)
  in
  let json = `Assoc [
    ("tickers", `List (List.map (fun t -> `String t) result.tickers));
    ("sector", `String result.sector);
    ("analysis_date", `String result.analysis_date);
    ("pe_ttm_ranking", ranking_to_json result.pe_ttm_ranking);
    ("pe_ntm_ranking", ranking_to_json result.pe_ntm_ranking);
    ("ev_ebitda_ranking", ranking_to_json result.ev_ebitda_ranking);
    ("peg_ranking", ranking_to_json result.peg_ranking);
    ("value_score_ranking", `List (List.map (fun (t, s) ->
      `Assoc [("ticker", `String t); ("score", `Float s)]
    ) result.value_score_ranking));
    ("quality_adjusted_ranking", `List (List.map (fun (t, s) ->
      `Assoc [("ticker", `String t); ("score", `Float s)]
    ) result.quality_adjusted_ranking));
    ("best_value", match result.best_value with Some t -> `String t | None -> `Null);
    ("best_quality_adjusted", match result.best_quality_adjusted with Some t -> `String t | None -> `Null);
    ("best_peg", match result.best_peg with Some t -> `String t | None -> `Null);
  ] in
  let filename = Printf.sprintf "%s/multiples_comparison.json" output_dir in
  let oc = open_out filename in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc;
  Printf.printf "Comparison written to: %s\n" filename
