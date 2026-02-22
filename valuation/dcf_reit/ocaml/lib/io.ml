(** I/O functions for REIT valuation *)

open Types

(** Parse property sector from string *)
let property_sector_of_string = function
  | "retail" | "Retail" -> Retail
  | "office" | "Office" -> Office
  | "industrial" | "Industrial" -> Industrial
  | "residential" | "Residential" | "apartment" | "multifamily" -> Residential
  | "healthcare" | "Healthcare" -> Healthcare
  | "datacenter" | "DataCenter" | "data_center" -> DataCenter
  | "selfstorage" | "SelfStorage" | "self_storage" -> SelfStorage
  | "hotel" | "Hotel" | "lodging" -> Hotel
  | "specialty" | "Specialty" -> Specialty
  | "mortgage" | "Mortgage" | "mREIT" | "mreit" -> Mortgage
  | "diversified" | "Diversified" | _ -> Diversified

let string_of_property_sector = function
  | Retail -> "retail"
  | Office -> "office"
  | Industrial -> "industrial"
  | Residential -> "residential"
  | Healthcare -> "healthcare"
  | DataCenter -> "datacenter"
  | SelfStorage -> "selfstorage"
  | Hotel -> "hotel"
  | Specialty -> "specialty"
  | Mortgage -> "mortgage"
  | Diversified -> "diversified"

(** Parse REIT type from string *)
let reit_type_of_string = function
  | "equity" | "Equity" | "EquityREIT" -> EquityREIT
  | "mortgage" | "Mortgage" | "MortgageREIT" | "mREIT" | "mreit" -> MortgageREIT
  | "hybrid" | "Hybrid" | "HybridREIT" -> HybridREIT
  | _ -> EquityREIT  (* Default to equity REIT *)

let string_of_reit_type = function
  | EquityREIT -> "equity"
  | MortgageREIT -> "mortgage"
  | HybridREIT -> "hybrid"

(** Parse market data from JSON *)
let market_data_of_json json =
  let open Yojson.Basic.Util in
  let to_number v = match v with
    | `Int i -> float_of_int i
    | `Float f -> f
    | _ -> to_float v
  in
  let ticker = json |> member "ticker" |> to_string in
  let price = json |> member "price" |> to_number in
  let shares = json |> member "shares_outstanding" |> to_number in
  let market_cap = json |> member "market_cap" |> to_number in
  let div_yield = json |> member "dividend_yield" |> to_number in
  let div_ps = json |> member "dividend_per_share" |> to_number in
  let currency = json |> member "currency" |> to_string_option |> Option.value ~default:"USD" in
  let sector_str = json |> member "sector" |> to_string in
  let sector = property_sector_of_string sector_str in
  (* Infer reit_type from sector or explicit field *)
  let reit_type_str = json |> member "reit_type" |> to_string_option in
  let reit_type = match reit_type_str with
    | Some s -> reit_type_of_string s
    | None -> if sector = Mortgage then MortgageREIT else EquityREIT
  in
  {
    ticker;
    price;
    shares_outstanding = shares;
    market_cap;
    dividend_yield = div_yield;
    dividend_per_share = div_ps;
    currency;
    sector;
    reit_type;
  }

(** Parse financial data from JSON *)
let financial_data_of_json json =
  let open Yojson.Basic.Util in
  let get_number_or key default =
    let v = json |> member key in
    match v with
    | `Int i -> float_of_int i
    | `Float f -> f
    | _ -> default
  in
  {
    (* Income statement items *)
    revenue = get_number_or "revenue" 0.0;
    net_income = get_number_or "net_income" 0.0;
    depreciation = get_number_or "depreciation" 0.0;
    amortization = get_number_or "amortization" 0.0;
    gains_on_sales = get_number_or "gains_on_sales" 0.0;
    impairments = get_number_or "impairments" 0.0;

    (* FFO adjustments - equity REITs *)
    straight_line_rent_adj = get_number_or "straight_line_rent_adj" 0.0;
    stock_compensation = get_number_or "stock_compensation" 0.0;

    (* CapEx breakdown - equity REITs *)
    maintenance_capex = get_number_or "maintenance_capex" 0.0;
    development_capex = get_number_or "development_capex" 0.0;

    (* Balance sheet items *)
    total_debt = get_number_or "total_debt" 0.0;
    cash = get_number_or "cash" 0.0;
    total_assets = get_number_or "total_assets" 0.0;
    total_equity = get_number_or "total_equity" 0.0;
    book_value_per_share = get_number_or "book_value_per_share" 0.0;

    (* Property-level data - equity REITs *)
    noi = get_number_or "noi" 0.0;
    occupancy_rate = get_number_or "occupancy_rate" 0.95;
    same_store_noi_growth = get_number_or "same_store_noi_growth" 0.02;

    (* Lease data - equity REITs *)
    weighted_avg_lease_term = get_number_or "weighted_avg_lease_term" 5.0;
    lease_expiration_1yr = get_number_or "lease_expiration_1yr" 0.10;

    (* mREIT-specific data *)
    interest_income = get_number_or "interest_income" 0.0;
    interest_expense = get_number_or "interest_expense" 0.0;
    net_interest_income = get_number_or "net_interest_income" 0.0;
    earning_assets = get_number_or "earning_assets" 0.0;
    distributable_earnings = get_number_or "distributable_earnings" 0.0;
  }

(** Load REIT data from JSON file *)
let load_reit_data filename =
  let json = Yojson.Basic.from_file filename in
  let open Yojson.Basic.Util in
  let market = json |> member "market" |> market_data_of_json in
  let financial = json |> member "financial" |> financial_data_of_json in
  (market, financial)

(** Load config from JSON file *)
let load_config filename =
  let json = Yojson.Basic.from_file filename in
  let open Yojson.Basic.Util in
  let risk_free_rate = json |> member "risk_free_rate" |> to_float in
  let equity_risk_premium = json |> member "equity_risk_premium" |> to_float in
  (risk_free_rate, equity_risk_premium)

(** Convert valuation method to JSON *)
let valuation_method_to_json = function
  | PriceToFFO { p_ffo; sector_avg; implied_value } ->
      `Assoc [
        ("method", `String "P/FFO");
        ("p_ffo", `Float p_ffo);
        ("sector_avg", `Float sector_avg);
        ("implied_value", `Float implied_value);
      ]
  | PriceToAFFO { p_affo; sector_avg; implied_value } ->
      `Assoc [
        ("method", `String "P/AFFO");
        ("p_affo", `Float p_affo);
        ("sector_avg", `Float sector_avg);
        ("implied_value", `Float implied_value);
      ]
  | NAVMethod { nav_per_share; premium_discount; target_premium; implied_value } ->
      `Assoc [
        ("method", `String "NAV");
        ("nav_per_share", `Float nav_per_share);
        ("premium_discount", `Float premium_discount);
        ("target_premium", `Float target_premium);
        ("implied_value", `Float implied_value);
      ]
  | DividendDiscount { intrinsic_value; dividend_yield; implied_growth } ->
      `Assoc [
        ("method", `String "DDM");
        ("intrinsic_value", `Float intrinsic_value);
        ("dividend_yield", `Float dividend_yield);
        ("implied_growth", `Float implied_growth);
      ]
  | PriceToBook { p_bv; sector_avg; implied_value } ->
      `Assoc [
        ("method", `String "P/BV");
        ("p_bv", `Float p_bv);
        ("sector_avg", `Float sector_avg);
        ("implied_value", `Float implied_value);
      ]
  | PriceToDE { p_de; sector_avg; implied_value } ->
      `Assoc [
        ("method", `String "P/DE");
        ("p_de", `Float p_de);
        ("sector_avg", `Float sector_avg);
        ("implied_value", `Float implied_value);
      ]

let string_of_signal = function
  | StrongBuy -> "STRONG BUY"
  | Buy -> "BUY"
  | Hold -> "HOLD"
  | Sell -> "SELL"
  | StrongSell -> "STRONG SELL"
  | Caution -> "CAUTION"

(** Convert valuation result to JSON *)
let result_to_json (result : valuation_result) =
  let base_fields = [
    ("ticker", `String result.ticker);
    ("price", `Float result.price);
    ("reit_type", `String (string_of_reit_type result.reit_type));
    ("fair_value", `Float result.fair_value);
    ("upside_potential", `Float result.upside_potential);
    ("signal", `String (string_of_signal result.signal));
    ("ffo_metrics", `Assoc [
      ("ffo", `Float result.ffo_metrics.ffo);
      ("affo", `Float result.ffo_metrics.affo);
      ("ffo_per_share", `Float result.ffo_metrics.ffo_per_share);
      ("affo_per_share", `Float result.ffo_metrics.affo_per_share);
      ("ffo_payout_ratio", `Float result.ffo_metrics.ffo_payout_ratio);
      ("affo_payout_ratio", `Float result.ffo_metrics.affo_payout_ratio);
    ]);
    ("nav", `Assoc [
      ("property_value", `Float result.nav.property_value);
      ("nav", `Float result.nav.nav);
      ("nav_per_share", `Float result.nav.nav_per_share);
      ("premium_discount", `Float result.nav.premium_discount);
    ]);
    ("cost_of_capital", `Assoc [
      ("cost_of_equity", `Float result.cost_of_capital.cost_of_equity);
      ("cost_of_debt", `Float result.cost_of_capital.cost_of_debt);
      ("wacc", `Float result.cost_of_capital.wacc);
      ("reit_beta", `Float result.cost_of_capital.reit_beta);
    ]);
    ("valuations", `Assoc [
      ("p_ffo", valuation_method_to_json result.p_ffo_valuation);
      ("p_affo", valuation_method_to_json result.p_affo_valuation);
      ("nav", valuation_method_to_json result.nav_valuation);
      ("ddm", valuation_method_to_json result.ddm_valuation);
    ]);
    ("quality", `Assoc [
      ("occupancy_score", `Float result.quality.occupancy_score);
      ("lease_quality_score", `Float result.quality.lease_quality_score);
      ("balance_sheet_score", `Float result.quality.balance_sheet_score);
      ("growth_score", `Float result.quality.growth_score);
      ("dividend_safety_score", `Float result.quality.dividend_safety_score);
      ("overall_quality", `Float result.quality.overall_quality);
    ]);
  ] in
  (* Add mREIT-specific fields if present *)
  let mreit_fields = match result.mreit_metrics with
    | Some m -> [
        ("mreit_metrics", `Assoc [
          ("net_interest_income", `Float m.net_interest_income);
          ("nii_per_share", `Float m.nii_per_share);
          ("net_interest_margin", `Float m.net_interest_margin);
          ("book_value_per_share", `Float m.book_value_per_share);
          ("price_to_book", `Float m.price_to_book);
          ("distributable_earnings", `Float m.distributable_earnings);
          ("de_per_share", `Float m.de_per_share);
          ("de_payout_ratio", `Float m.de_payout_ratio);
          ("leverage_ratio", `Float m.leverage_ratio);
          ("interest_coverage", `Float m.interest_coverage);
        ]);
      ]
    | None -> []
  in
  let mreit_valuations = match result.p_bv_valuation, result.p_de_valuation with
    | Some pbv, Some pde -> [
        ("mreit_valuations", `Assoc [
          ("p_bv", valuation_method_to_json pbv);
          ("p_de", valuation_method_to_json pde);
        ]);
      ]
    | _ -> []
  in
  `Assoc (base_fields @ mreit_fields @ mreit_valuations)

(** Save result to JSON file *)
let save_result filename result =
  let json = result_to_json result in
  let out_channel = open_out filename in
  Yojson.Basic.pretty_to_channel out_channel json;
  close_out out_channel

(** Convert income metrics to JSON *)
let income_metrics_to_json (m : Income.income_metrics) =
  let base_fields = [
    ("dividend_yield", `Float m.dividend_yield);
    ("dividend_per_share", `Float m.dividend_per_share);
    ("coverage_ratio", `Float m.coverage_ratio);
    ("coverage_status", `String m.coverage_status);
    ("earnings_per_share", `Float m.earnings_per_share);
    ("payout_ratio", `Float m.payout_ratio);
    ("payout_status", `String m.payout_status);
    ("yield_vs_sector", `Float m.yield_vs_sector);
    ("yield_vs_10yr", `Float m.yield_vs_10yr);
    ("yield_percentile", `Float m.yield_percentile);
    ("income_score", `Float m.income_score);
    ("income_grade", `String m.income_grade);
    ("income_recommendation", `String m.income_recommendation);
  ] in
  let quality_fields = match m.quality_factors with
    | Some qf -> [
        ("quality_factors", `Assoc [
          ("occupancy_premium", `Float qf.occupancy_premium);
          ("lease_structure_premium", `Float qf.lease_structure_premium);
          ("dividend_track_record", `Float qf.dividend_track_record);
          ("rate_environment_bonus", `Float qf.rate_environment_bonus);
          ("monthly_dividend_bonus", `Float qf.monthly_dividend_bonus);
        ])
      ]
    | None -> []
  in
  `Assoc (base_fields @ quality_fields)

(** Save result with income metrics to JSON file *)
let save_result_with_income filename result income_metrics_opt =
  let base_json = result_to_json result in
  let json = match base_json, income_metrics_opt with
    | `Assoc fields, Some im ->
        `Assoc (fields @ [("income_metrics", income_metrics_to_json im)])
    | _ -> base_json
  in
  let out_channel = open_out filename in
  Yojson.Basic.pretty_to_channel out_channel json;
  close_out out_channel

(** Print valuation summary to stdout *)
let print_summary (result : valuation_result) =
  let reit_type_str = match result.reit_type with
    | EquityREIT -> "Equity"
    | MortgageREIT -> "Mortgage"
    | HybridREIT -> "Hybrid"
  in
  Printf.printf "\n%s %s REIT VALUATION SUMMARY\n" result.ticker reit_type_str;
  Printf.printf "════════════════════════════════════════════\n\n";

  Printf.printf "MARKET DATA\n";
  Printf.printf "  Price:              $%.2f\n" result.price;
  Printf.printf "  Fair Value:         $%.2f\n" result.fair_value;
  Printf.printf "  Upside:             %.1f%%\n" (result.upside_potential *. 100.0);
  Printf.printf "  Signal:             %s\n\n" (string_of_signal result.signal);

  (* Show mREIT metrics if available *)
  (match result.mreit_metrics with
   | Some m ->
       Printf.printf "mREIT METRICS\n";
       Printf.printf "  NII/Share:          $%.2f\n" m.nii_per_share;
       Printf.printf "  Net Interest Margin: %.2f%%\n" (m.net_interest_margin *. 100.0);
       Printf.printf "  Book Value/Share:   $%.2f\n" m.book_value_per_share;
       Printf.printf "  Price/Book:         %.2fx\n" m.price_to_book;
       Printf.printf "  DE/Share:           $%.2f\n" m.de_per_share;
       Printf.printf "  DE Payout:          %.1f%%\n" (m.de_payout_ratio *. 100.0);
       Printf.printf "  Leverage:           %.1fx\n" m.leverage_ratio;
       Printf.printf "  Interest Coverage:  %.2fx\n\n" m.interest_coverage
   | None ->
       Printf.printf "FFO METRICS\n";
       Printf.printf "  FFO/Share:          $%.2f\n" result.ffo_metrics.ffo_per_share;
       Printf.printf "  AFFO/Share:         $%.2f\n" result.ffo_metrics.affo_per_share;
       Printf.printf "  FFO Payout:         %.1f%%\n" (result.ffo_metrics.ffo_payout_ratio *. 100.0);
       Printf.printf "  AFFO Payout:        %.1f%%\n\n" (result.ffo_metrics.affo_payout_ratio *. 100.0);

       Printf.printf "NAV ANALYSIS\n";
       Printf.printf "  NAV/Share:          $%.2f\n" result.nav.nav_per_share;
       Printf.printf "  Premium/Discount:   %.1f%%\n\n" (result.nav.premium_discount *. 100.0));

  Printf.printf "COST OF CAPITAL\n";
  Printf.printf "  Cost of Equity:     %.2f%%\n" (result.cost_of_capital.cost_of_equity *. 100.0);
  Printf.printf "  WACC:               %.2f%%\n" (result.cost_of_capital.wacc *. 100.0);
  Printf.printf "  REIT Beta:          %.2f\n\n" result.cost_of_capital.reit_beta;

  Printf.printf "VALUATION METHODS\n";
  (* Show mREIT-specific valuations or equity REIT valuations *)
  (match result.p_bv_valuation, result.p_de_valuation with
   | Some pbv, Some pde ->
       Printf.printf "  P/BV Value:         $%.2f\n" (Valuation.implied_value_of pbv);
       Printf.printf "  P/DE Value:         $%.2f\n" (Valuation.implied_value_of pde);
       Printf.printf "  DDM Value:          $%.2f\n\n" (Valuation.implied_value_of result.ddm_valuation)
   | _ ->
       Printf.printf "  P/FFO Value:        $%.2f\n" (Valuation.implied_value_of result.p_ffo_valuation);
       Printf.printf "  P/AFFO Value:       $%.2f\n" (Valuation.implied_value_of result.p_affo_valuation);
       Printf.printf "  NAV Value:          $%.2f\n" (Valuation.implied_value_of result.nav_valuation);
       Printf.printf "  DDM Value:          $%.2f\n\n" (Valuation.implied_value_of result.ddm_valuation));

  Printf.printf "QUALITY SCORES (0-1)\n";
  (match result.reit_type with
   | MortgageREIT ->
       Printf.printf "  Balance Sheet:      %.2f\n" result.quality.balance_sheet_score;
       Printf.printf "  NIM Quality:        %.2f\n" result.quality.growth_score;
       Printf.printf "  Dividend Safety:    %.2f\n" result.quality.dividend_safety_score;
       Printf.printf "  Overall:            %.2f\n" result.quality.overall_quality
   | _ ->
       Printf.printf "  Occupancy:          %.2f\n" result.quality.occupancy_score;
       Printf.printf "  Lease Quality:      %.2f\n" result.quality.lease_quality_score;
       Printf.printf "  Balance Sheet:      %.2f\n" result.quality.balance_sheet_score;
       Printf.printf "  Growth:             %.2f\n" result.quality.growth_score;
       Printf.printf "  Dividend Safety:    %.2f\n" result.quality.dividend_safety_score;
       Printf.printf "  Overall:            %.2f\n" result.quality.overall_quality);

  Printf.printf "\n════════════════════════════════════════════\n"

(** Print income investor metrics *)
let print_income_metrics (m : Income.income_metrics) =
  Printf.printf "\n";
  Printf.printf "INCOME INVESTOR VIEW\n";
  Printf.printf "────────────────────────────────────────────\n";
  Printf.printf "  Dividend Yield:     %.2f%%\n" (m.dividend_yield *. 100.0);
  Printf.printf "  Dividend/Share:     $%.2f\n" m.dividend_per_share;
  Printf.printf "  Coverage Ratio:     %.2f (%s)\n" m.coverage_ratio m.coverage_status;
  Printf.printf "  Payout Ratio:       %.0f%% (%s)\n" (m.payout_ratio *. 100.0) m.payout_status;
  Printf.printf "  Yield vs Sector:    %+.1f%%\n" m.yield_vs_sector;
  Printf.printf "  Yield vs 10Y:       %+.1f%%\n" m.yield_vs_10yr;
  (* Print quality bonuses if present *)
  (match m.quality_factors with
   | Some qf ->
       Printf.printf "  Quality Bonuses:\n";
       if qf.occupancy_premium > 0.0 then
         Printf.printf "    Occupancy:        +%.0f pts\n" qf.occupancy_premium;
       if qf.dividend_track_record > 0.0 then
         Printf.printf "    Track Record:     +%.0f pts\n" qf.dividend_track_record;
       if qf.rate_environment_bonus > 0.0 then
         Printf.printf "    Rate Spread:      +%.0f pts\n" qf.rate_environment_bonus;
       if qf.monthly_dividend_bonus > 0.0 then
         Printf.printf "    Monthly Div:      +%.0f pts\n" qf.monthly_dividend_bonus
   | None -> ());
  Printf.printf "  Income Score:       %.0f/100 (Grade: %s)\n" m.income_score m.income_grade;
  Printf.printf "  Recommendation:     %s\n" m.income_recommendation;
  Printf.printf "────────────────────────────────────────────\n"
