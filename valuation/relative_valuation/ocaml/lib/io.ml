(** I/O functions for relative valuation *)

open Types

(** Read company data from JSON *)
let read_company_data (json : Yojson.Basic.t) : company_data =
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
    trailing_eps = get_float "trailing_eps" json;
    forward_eps = get_float "forward_eps" json;
    trailing_pe = get_float "trailing_pe" json;
    forward_pe = get_float "forward_pe" json;
    book_value = get_float "book_value" json;
    pb_ratio = get_float "pb_ratio" json;
    revenue = get_float "revenue" json;
    revenue_per_share = get_float "revenue_per_share" json;
    ps_ratio = get_float "ps_ratio" json;
    free_cashflow = get_float "free_cashflow" json;
    fcf_per_share = get_float "fcf_per_share" json;
    p_fcf = get_float "p_fcf" json;
    ebitda = get_float "ebitda" json;
    operating_income = get_float "operating_income" json;
    ev_ebitda = get_float "ev_ebitda" json;
    ev_ebit = get_float "ev_ebit" json;
    ev_revenue = get_float "ev_revenue" json;
    revenue_growth = get_float "revenue_growth" json;
    earnings_growth = get_float "earnings_growth" json;
    gross_margin = get_float "gross_margin" json;
    operating_margin = get_float "operating_margin" json;
    ebitda_margin = get_float "ebitda_margin" json;
    profit_margin = get_float "profit_margin" json;
    roe = get_float "roe" json;
    roa = get_float "roa" json;
    roic = get_float "roic" json;
    beta = get_float "beta" json;
    dividend_yield = get_float "dividend_yield" json;
  }

(** Read peer data from JSON file *)
let read_peer_data (filename : string) : peer_data =
  let json = Yojson.Basic.from_file filename in
  let open Yojson.Basic.Util in
  let target = read_company_data (json |> member "target") in
  let peers = json |> member "peers" |> to_list |> List.map read_company_data in
  let peer_count = json |> member "peer_count" |> to_int in
  { target; peers; peer_count }

(** Write result to JSON file *)
let write_result (filename : string) (result : relative_result) : unit =
  let opt_to_json = function
    | Some v -> `Float v
    | None -> `Null
  in

  let json = `Assoc [
    ("ticker", `String result.ticker);
    ("company_name", `String result.company_name);
    ("sector", `String result.sector);
    ("current_price", `Float result.current_price);
    ("peer_count", `Int result.peer_count);
    ("peer_similarities", `List (List.map (fun (s : similarity_score) ->
      `Assoc [
        ("ticker", `String s.ticker);
        ("total_score", `Float s.total_score);
        ("industry_score", `Float s.industry_score);
        ("size_score", `Float s.size_score);
        ("growth_score", `Float s.growth_score);
        ("profitability_score", `Float s.profitability_score);
      ]
    ) result.peer_similarities));
    ("multiple_comparisons", `List (List.map (fun c ->
      `Assoc [
        ("multiple", `String c.multiple_name);
        ("target_value", `Float c.target_value);
        ("peer_median", `Float c.peer_stats.median);
        ("premium_pct", `Float c.premium_pct);
        ("implied_value", opt_to_json c.implied_value);
      ]
    ) result.multiple_comparisons));
    ("implied_valuations", `List (List.map (fun v ->
      `Assoc [
        ("method", `String v.method_name);
        ("implied_price", `Float v.implied_price);
        ("upside_pct", `Float v.upside_downside_pct);
      ]
    ) result.implied_valuations));
    ("average_implied_price", opt_to_json result.average_implied_price);
    ("relative_score", `Float result.relative_score);
    ("assessment", `String (string_of_relative_assessment result.assessment));
    ("signal", `String (string_of_relative_signal result.signal));
  ] in
  Yojson.Basic.to_file filename json

(** Print result to stdout *)
let print_result (result : relative_result) : unit =
  Printf.printf "\n";
  Printf.printf "============================================================\n";
  Printf.printf "Relative Valuation: %s (%s)\n" result.ticker result.company_name;
  Printf.printf "============================================================\n";
  Printf.printf "\n";

  Printf.printf "PEER GROUP (%d companies)\n" result.peer_count;
  Printf.printf "------------------------------------------------------------\n";
  Printf.printf "%-8s %10s %10s %10s %10s %10s\n"
    "Ticker" "Total" "Industry" "Size" "Growth" "Margin";
  Printf.printf "------------------------------------------------------------\n";
  List.iter (fun (s : similarity_score) ->
    Printf.printf "%-8s %9.0f %9.0f %9.0f %9.0f %9.0f\n"
      s.ticker s.total_score s.industry_score s.size_score s.growth_score s.profitability_score
  ) (List.filteri (fun i _ -> i < 6) result.peer_similarities);
  Printf.printf "\n";

  Printf.printf "MULTIPLE ANALYSIS\n";
  Printf.printf "------------------------------------------------------------\n";
  Printf.printf "%-15s %10s %10s %10s %10s\n"
    "Multiple" "Target" "Peer Med" "Premium" "Implied$";
  Printf.printf "------------------------------------------------------------\n";
  List.iter (fun c ->
    let implied_str = match c.implied_value with
      | Some v -> Printf.sprintf "$%.2f" v
      | None -> "N/A"
    in
    Printf.printf "%-15s %9.1fx %9.1fx %9.0f%% %10s\n"
      c.multiple_name c.target_value c.peer_stats.median c.premium_pct implied_str
  ) result.multiple_comparisons;
  Printf.printf "\n";

  Printf.printf "IMPLIED VALUATIONS\n";
  Printf.printf "------------------------------------------------------------\n";
  List.iter (fun v ->
    let direction = if v.upside_downside_pct >= 0.0 then "Upside" else "Downside" in
    Printf.printf "  %-15s → $%.2f (%s %.0f%%)\n"
      v.method_name v.implied_price direction (abs_float v.upside_downside_pct)
  ) result.implied_valuations;

  (match result.average_implied_price with
   | Some avg ->
       let pct = (avg -. result.current_price) /. result.current_price *. 100.0 in
       Printf.printf "\n  Average Implied: $%.2f " avg;
       if pct >= 0.0 then Printf.printf "(%.0f%% upside)\n" pct
       else Printf.printf "(%.0f%% downside)\n" (abs_float pct)
   | None -> ());
  Printf.printf "\n";

  Printf.printf "RELATIVE SCORE: %.0f/100\n" result.relative_score;
  Printf.printf "------------------------------------------------------------\n";
  Printf.printf "  Assessment:  %s\n" (string_of_relative_assessment result.assessment);
  Printf.printf "  Signal:      %s\n" (string_of_relative_signal result.signal);
  Printf.printf "  Current:     $%.2f\n" result.current_price;
  Printf.printf "\n";
  Printf.printf "============================================================\n";
  Printf.printf "\n"
