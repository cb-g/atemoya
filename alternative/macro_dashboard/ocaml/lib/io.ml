(** IO for Macro Dashboard *)

open Types

(** Helper to extract float from JSON *)
let get_float_opt json key =
  try
    match Yojson.Basic.Util.member key json with
    | `Float f -> Some f
    | `Int i -> Some (float_of_int i)
    | `Null -> None
    | _ -> None
  with _ -> None

(** Find FRED series by ID from list *)
let find_fred_series series_list series_id =
  List.find_opt (fun item ->
    match Yojson.Basic.Util.member "series_id" item with
    | `String s -> s = series_id
    | _ -> false
  ) series_list

(** Get latest value from FRED series *)
let get_fred_value series_list series_id =
  match find_fred_series series_list series_id with
  | Some item -> get_float_opt item "latest_value"
  | None -> None

(** Get YoY change from FRED series *)
let get_fred_yoy series_list series_id =
  match find_fred_series series_list series_id with
  | Some item -> get_float_opt item "yoy_change"
  | None -> None

(** Get MoM change from FRED series *)
let get_fred_mom series_list series_id =
  match find_fred_series series_list series_id with
  | Some item -> get_float_opt item "mom_change"
  | None -> None

(** Find market ticker from list *)
let find_market_ticker market_list ticker =
  List.find_opt (fun item ->
    match Yojson.Basic.Util.member "ticker" item with
    | `String s -> s = ticker
    | _ -> false
  ) market_list

(** Get market price *)
let get_market_price market_list ticker =
  match find_market_ticker market_list ticker with
  | Some item -> get_float_opt item "latest_price"
  | None -> None

(** Get market YTD change *)
let get_market_ytd market_list ticker =
  match find_market_ticker market_list ticker with
  | Some item -> get_float_opt item "ytd_change_pct"
  | None -> None

(** Load macro data from JSON file *)
let load_macro_data filename : macro_snapshot =
  let json = Yojson.Basic.from_file filename in

  let timestamp =
    match Yojson.Basic.Util.member "timestamp" json with
    | `String s -> s
    | _ -> ""
  in

  let fred_list =
    match Yojson.Basic.Util.member "fred" json with
    | `List l -> l
    | _ -> []
  in

  let market_list =
    match Yojson.Basic.Util.member "market" json with
    | `List l -> l
    | _ -> []
  in

  let rates = {
    fed_funds = get_fred_value fred_list "DFF";
    treasury_3m = get_fred_value fred_list "DGS3MO";
    treasury_2y = get_fred_value fred_list "DGS2";
    treasury_10y = get_fred_value fred_list "DGS10";
    spread_10y2y = get_fred_value fred_list "T10Y2Y";
    spread_10y3m = get_fred_value fred_list "T10Y3M";
  } in

  let inflation = {
    cpi_yoy = get_fred_yoy fred_list "CPIAUCSL";
    core_cpi_yoy = get_fred_yoy fred_list "CPILFESL";
    pce_yoy = get_fred_yoy fred_list "PCEPI";
    core_pce_yoy = get_fred_yoy fred_list "PCEPILFE";
    ppi_yoy = get_fred_yoy fred_list "PPIFIS";
  } in

  let employment = {
    unemployment_rate = get_fred_value fred_list "UNRATE";
    nfp_change = get_fred_mom fred_list "PAYEMS";
    initial_claims = get_fred_value fred_list "ICSA";
    continued_claims = get_fred_value fred_list "CCSA";
    job_openings = get_fred_value fred_list "JTSJOL";
  } in

  let growth = {
    gdp_growth = get_fred_value fred_list "A191RL1Q225SBEA";
    industrial_production_yoy = get_fred_yoy fred_list "INDPRO";
    retail_sales_yoy = get_fred_yoy fred_list "RSAFS";
  } in

  let market = {
    vix = get_market_price market_list "^VIX";
    move_index = get_market_price market_list "^MOVE";
    dollar_index = get_market_price market_list "DX-Y.NYB";
    gold = get_market_price market_list "GC=F";
    oil = get_market_price market_list "CL=F";
    copper = get_market_price market_list "HG=F";
    sp500_ytd = get_market_ytd market_list "^GSPC";
  } in

  let consumer = {
    retail_sales_yoy = get_fred_yoy fred_list "RSAFS";
  } in

  let housing = {
    housing_starts = get_fred_value fred_list "HOUST";
    building_permits = get_fred_value fred_list "PERMIT";
    existing_home_sales = get_fred_value fred_list "EXHOSLUSM495S";
    mortgage_rate = get_fred_value fred_list "MORTGAGE30US";
  } in

  { timestamp; rates; inflation; employment; growth; market; consumer; housing }

(** Print optional float *)
let print_opt_float fmt = function
  | Some v -> Printf.sprintf fmt v
  | None -> "N/A"

(** Print dashboard to stdout *)
let print_dashboard (snapshot : macro_snapshot) (env : macro_environment) (impl : investment_implications) =
  Printf.printf "\n";
  Printf.printf "════════════════════════════════════════════════════════════════════════\n";
  Printf.printf "                     MACRO ECONOMIC DASHBOARD\n";
  Printf.printf "════════════════════════════════════════════════════════════════════════\n";
  Printf.printf "  As of: %s\n" (String.sub snapshot.timestamp 0 10);
  Printf.printf "\n";

  Printf.printf "ECONOMIC REGIME\n";
  Printf.printf "────────────────────────────────────────────────────────────────────────\n";
  Printf.printf "  Cycle Phase:      %s\n" (string_of_cycle_phase env.cycle_phase);
  Printf.printf "  Yield Curve:      %s\n" (string_of_yield_curve env.yield_curve);
  Printf.printf "  Inflation:        %s\n" (string_of_inflation_regime env.inflation_regime);
  Printf.printf "  Labor Market:     %s\n" (string_of_labor_state env.labor_state);
  Printf.printf "  Risk Sentiment:   %s\n" (string_of_risk_sentiment env.risk_sentiment);
  Printf.printf "  Fed Stance:       %s\n" (string_of_fed_stance env.fed_stance);
  Printf.printf "  Recession Prob:   %.0f%%\n" (env.recession_probability *. 100.0);
  Printf.printf "  Confidence:       %.0f%%\n" (env.confidence *. 100.0);
  Printf.printf "\n";

  Printf.printf "INTEREST RATES\n";
  Printf.printf "────────────────────────────────────────────────────────────────────────\n";
  Printf.printf "  Fed Funds:        %s\n" (print_opt_float "%.2f%%" snapshot.rates.fed_funds);
  Printf.printf "  3M Treasury:      %s\n" (print_opt_float "%.2f%%" snapshot.rates.treasury_3m);
  Printf.printf "  2Y Treasury:      %s\n" (print_opt_float "%.2f%%" snapshot.rates.treasury_2y);
  Printf.printf "  10Y Treasury:     %s\n" (print_opt_float "%.2f%%" snapshot.rates.treasury_10y);
  Printf.printf "  10Y-2Y Spread:    %s\n" (print_opt_float "%+.2f%%" snapshot.rates.spread_10y2y);
  Printf.printf "  10Y-3M Spread:    %s\n" (print_opt_float "%+.2f%%" snapshot.rates.spread_10y3m);
  Printf.printf "\n";

  Printf.printf "INFLATION (YoY)\n";
  Printf.printf "────────────────────────────────────────────────────────────────────────\n";
  Printf.printf "  CPI:              %s\n" (print_opt_float "%.1f%%" snapshot.inflation.cpi_yoy);
  Printf.printf "  Core CPI:         %s\n" (print_opt_float "%.1f%%" snapshot.inflation.core_cpi_yoy);
  Printf.printf "  PCE:              %s\n" (print_opt_float "%.1f%%" snapshot.inflation.pce_yoy);
  Printf.printf "  Core PCE:         %s\n" (print_opt_float "%.1f%%" snapshot.inflation.core_pce_yoy);
  Printf.printf "  PPI:              %s\n" (print_opt_float "%.1f%%" snapshot.inflation.ppi_yoy);
  Printf.printf "\n";

  Printf.printf "EMPLOYMENT\n";
  Printf.printf "────────────────────────────────────────────────────────────────────────\n";
  Printf.printf "  Unemployment:     %s\n" (print_opt_float "%.1f%%" snapshot.employment.unemployment_rate);
  Printf.printf "  NFP Change:       %s\n" (print_opt_float "%+.0fK" snapshot.employment.nfp_change);
  Printf.printf "  Initial Claims:   %s\n" (print_opt_float "%.0fK" snapshot.employment.initial_claims);
  Printf.printf "  Continued Claims: %s\n" (print_opt_float "%.0fK" snapshot.employment.continued_claims);
  Printf.printf "  Job Openings:     %s\n" (print_opt_float "%.0fK" snapshot.employment.job_openings);
  Printf.printf "\n";

  Printf.printf "GROWTH\n";
  Printf.printf "────────────────────────────────────────────────────────────────────────\n";
  Printf.printf "  GDP Growth (QoQ): %s\n" (print_opt_float "%.1f%%" snapshot.growth.gdp_growth);
  Printf.printf "  Industrial Prod:  %s\n" (print_opt_float "%+.1f%% YoY" snapshot.growth.industrial_production_yoy);
  Printf.printf "  Retail Sales:     %s\n" (print_opt_float "%+.1f%% YoY" snapshot.growth.retail_sales_yoy);
  Printf.printf "\n";

  Printf.printf "MARKET INDICATORS\n";
  Printf.printf "────────────────────────────────────────────────────────────────────────\n";
  Printf.printf "  VIX:              %s\n" (print_opt_float "%.1f" snapshot.market.vix);
  Printf.printf "  Dollar Index:     %s\n" (print_opt_float "%.1f" snapshot.market.dollar_index);
  Printf.printf "  Gold:             %s\n" (print_opt_float "$%.0f" snapshot.market.gold);
  Printf.printf "  Oil (WTI):        %s\n" (print_opt_float "$%.1f" snapshot.market.oil);
  Printf.printf "  Copper:           %s\n" (print_opt_float "$%.2f" snapshot.market.copper);
  Printf.printf "  S&P 500 YTD:      %s\n" (print_opt_float "%+.1f%%" snapshot.market.sp500_ytd);
  Printf.printf "\n";

  Printf.printf "CONSUMER & HOUSING\n";
  Printf.printf "────────────────────────────────────────────────────────────────────────\n";
  Printf.printf "  Housing Starts:   %s\n" (print_opt_float "%.0fK" snapshot.housing.housing_starts);
  Printf.printf "  30Y Mortgage:     %s\n" (print_opt_float "%.2f%%" snapshot.housing.mortgage_rate);
  Printf.printf "\n";

  Printf.printf "INVESTMENT IMPLICATIONS\n";
  Printf.printf "────────────────────────────────────────────────────────────────────────\n";
  Printf.printf "  Equity Outlook:   %s\n" impl.equity_outlook;
  Printf.printf "  Bond Outlook:     %s\n" impl.bond_outlook;
  Printf.printf "  Risk Level:       %s\n" impl.risk_level;
  Printf.printf "\n";
  Printf.printf "  Sector Tilts:\n";
  List.iter (fun s -> Printf.printf "    • %s\n" s) impl.sector_tilts;
  Printf.printf "\n";
  Printf.printf "  Key Risks:\n";
  List.iter (fun r -> Printf.printf "    ⚠ %s\n" r) impl.key_risks;

  Printf.printf "\n────────────────────────────────────────────────────────────────────────\n";
  Printf.printf "  Source: Federal Reserve Board, BLS, BEA, U.S. Census Bureau, via FRED\n";
  Printf.printf "  This product uses the FRED® API but is not endorsed or certified by\n";
  Printf.printf "  the Federal Reserve Bank of St. Louis.\n";
  Printf.printf "════════════════════════════════════════════════════════════════════════\n"

(** Save environment to JSON *)
let save_environment filename (snapshot : macro_snapshot) (env : macro_environment) (impl : investment_implications) =
  let json = `Assoc [
    ("timestamp", `String snapshot.timestamp);
    ("regime", `Assoc [
      ("cycle_phase", `String (string_of_cycle_phase env.cycle_phase));
      ("yield_curve", `String (string_of_yield_curve env.yield_curve));
      ("inflation", `String (string_of_inflation_regime env.inflation_regime));
      ("labor_market", `String (string_of_labor_state env.labor_state));
      ("risk_sentiment", `String (string_of_risk_sentiment env.risk_sentiment));
      ("fed_stance", `String (string_of_fed_stance env.fed_stance));
      ("recession_probability", `Float env.recession_probability);
      ("confidence", `Float env.confidence);
    ]);
    ("rates", `Assoc [
      ("fed_funds", match snapshot.rates.fed_funds with Some v -> `Float v | None -> `Null);
      ("treasury_2y", match snapshot.rates.treasury_2y with Some v -> `Float v | None -> `Null);
      ("treasury_10y", match snapshot.rates.treasury_10y with Some v -> `Float v | None -> `Null);
      ("spread_10y2y", match snapshot.rates.spread_10y2y with Some v -> `Float v | None -> `Null);
    ]);
    ("inflation", `Assoc [
      ("core_pce_yoy", match snapshot.inflation.core_pce_yoy with Some v -> `Float v | None -> `Null);
      ("core_cpi_yoy", match snapshot.inflation.core_cpi_yoy with Some v -> `Float v | None -> `Null);
    ]);
    ("employment", `Assoc [
      ("unemployment", match snapshot.employment.unemployment_rate with Some v -> `Float v | None -> `Null);
      ("initial_claims", match snapshot.employment.initial_claims with Some v -> `Float v | None -> `Null);
    ]);
    ("market", `Assoc [
      ("vix", match snapshot.market.vix with Some v -> `Float v | None -> `Null);
      ("sp500_ytd", match snapshot.market.sp500_ytd with Some v -> `Float v | None -> `Null);
    ]);
    ("implications", `Assoc [
      ("equity_outlook", `String impl.equity_outlook);
      ("bond_outlook", `String impl.bond_outlook);
      ("risk_level", `String impl.risk_level);
      ("sector_tilts", `List (List.map (fun s -> `String s) impl.sector_tilts));
      ("key_risks", `List (List.map (fun s -> `String s) impl.key_risks));
    ]);
  ] in

  let oc = open_out filename in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc
