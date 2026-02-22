(** I/O operations for configuration and data files *)

open Yojson.Basic.Util

(** Helper to convert JSON number (int or float) to float *)
let to_number json =
  try to_float json
  with Yojson.Basic.Util.Type_error _ -> float_of_int (to_int json)

let load_params filename =
  let json = Yojson.Basic.from_file filename in
  let open Types in

  (* Parse mean reversion settings with defaults for backward compatibility *)
  let mean_reversion_json = json |> member "mean_reversion" in
  let mean_reversion_enabled =
    try mean_reversion_json |> member "enabled" |> to_bool
    with Yojson.Basic.Util.Type_error _ -> false  (* Default: disabled for backward compatibility *)
  in
  let mean_reversion_lambda =
    try mean_reversion_json |> member "lambda" |> to_number
    with Yojson.Basic.Util.Type_error _ -> 0.25  (* Default: moderate reversion speed *)
  in

  (* Parse ERP settings with defaults for backward compatibility *)
  let erp_json = json |> member "erp" in
  let erp_mode =
    try
      let mode_str = erp_json |> member "mode" |> to_string in
      if mode_str = "dynamic" then ERPDynamic else ERPStatic
    with Yojson.Basic.Util.Type_error _ -> ERPStatic  (* Default: static Damodaran ERP *)
  in
  let erp_vix_mean =
    try erp_json |> member "vix_mean" |> to_number
    with Yojson.Basic.Util.Type_error _ -> 19.5  (* Default: historical VIX mean *)
  in
  let erp_vix_sensitivity =
    try erp_json |> member "vix_sensitivity" |> to_number
    with Yojson.Basic.Util.Type_error _ -> 0.4  (* Default: moderate sensitivity *)
  in

  {
    projection_years = json |> member "projection_years" |> to_int;
    terminal_growth_rate =
      json |> member "terminal_growth_rate" |> member "default" |> to_number;
    growth_clamp_upper =
      json |> member "growth_clamp" |> member "upper" |> to_number;
    growth_clamp_lower =
      json |> member "growth_clamp" |> member "lower" |> to_number;
    rfr_duration = json |> member "rfr_duration" |> to_int;
    mean_reversion_enabled;
    mean_reversion_lambda;
    erp_params = {
      mode = erp_mode;
      vix_mean = erp_vix_mean;
      vix_sensitivity = erp_vix_sensitivity;
    };
  }

let load_risk_free_rates filename =
  let json = Yojson.Basic.from_file filename in
  json |> to_assoc |> List.map (fun (country, rates_json) ->
    let rates = rates_json |> to_assoc |> List.map (fun (duration_str, rate) ->
      let duration = int_of_string (String.sub duration_str 0 (String.length duration_str - 1)) in
      (duration, to_number rate)
    ) in
    (country, rates)
  )

let load_equity_risk_premiums filename =
  let json = Yojson.Basic.from_file filename in
  json |> to_assoc |> List.map (fun (country, erp) ->
    (country, to_number erp)
  )

let load_industry_betas filename =
  let json = Yojson.Basic.from_file filename in
  json |> to_assoc |> List.map (fun (industry, beta) ->
    (industry, to_number beta)
  )

let load_tax_rates filename =
  let json = Yojson.Basic.from_file filename in
  json |> to_assoc |> List.map (fun (country, rate) ->
    (country, to_number rate)
  )

let load_config data_dir =
  let open Types in
  {
    risk_free_rates = load_risk_free_rates (Filename.concat data_dir "risk_free_rates.json");
    equity_risk_premiums = load_equity_risk_premiums (Filename.concat data_dir "equity_risk_premiums.json");
    industry_betas = load_industry_betas (Filename.concat data_dir "industry_betas.json");
    tax_rates = load_tax_rates (Filename.concat data_dir "tax_rates.json");
    params = load_params (Filename.concat data_dir "params.json");
  }

let load_market_data filename =
  let json = Yojson.Basic.from_file filename in
  let open Types in
  {
    ticker = json |> member "ticker" |> to_string;
    price = json |> member "price" |> to_number;
    mve = json |> member "mve" |> to_number;
    mvb = json |> member "mvb" |> to_number;
    shares_outstanding = json |> member "shares_outstanding" |> to_number;
    currency = json |> member "currency" |> to_string;
    country = json |> member "country" |> to_string;
    industry = json |> member "industry" |> to_string;
  }

(** Helper to safely get optional float with default *)
let to_number_opt json ~default =
  try to_number json with _ -> default

let load_financial_data filename =
  let json = Yojson.Basic.from_file filename in
  let open Types in
  let is_bank =
    try json |> member "is_bank" |> to_bool
    with _ -> false
  in
  let is_insurance =
    try json |> member "is_insurance" |> to_bool
    with _ -> false
  in
  {
    ebit = json |> member "ebit" |> to_number;
    net_income = json |> member "net_income" |> to_number;
    interest_expense = json |> member "interest_expense" |> to_number;
    taxes = json |> member "taxes" |> to_number;
    capex = json |> member "capex" |> to_number;
    depreciation = json |> member "depreciation" |> to_number;
    delta_wc = json |> member "delta_wc" |> to_number;
    book_value_equity = json |> member "book_value_equity" |> to_number;
    invested_capital = json |> member "invested_capital" |> to_number;
    is_bank;
    is_insurance;
    (* Bank-specific fields - default to 0.0 for non-banks *)
    net_interest_income = to_number_opt (json |> member "net_interest_income") ~default:0.0;
    non_interest_income = to_number_opt (json |> member "non_interest_income") ~default:0.0;
    non_interest_expense = to_number_opt (json |> member "non_interest_expense") ~default:0.0;
    provision_for_loan_losses = to_number_opt (json |> member "provision_for_loan_losses") ~default:0.0;
    tangible_book_value = to_number_opt (json |> member "tangible_book_value") ~default:0.0;
    total_loans = to_number_opt (json |> member "total_loans") ~default:0.0;
    total_deposits = to_number_opt (json |> member "total_deposits") ~default:0.0;
    tier1_capital_ratio = to_number_opt (json |> member "tier1_capital_ratio") ~default:0.0;
    npl_ratio = to_number_opt (json |> member "npl_ratio") ~default:0.0;
    (* Insurance-specific fields - default to 0.0 for non-insurers *)
    premiums_earned = to_number_opt (json |> member "premiums_earned") ~default:0.0;
    losses_incurred = to_number_opt (json |> member "losses_incurred") ~default:0.0;
    underwriting_expenses = to_number_opt (json |> member "underwriting_expenses") ~default:0.0;
    investment_income = to_number_opt (json |> member "investment_income") ~default:0.0;
    float_amount = to_number_opt (json |> member "float_amount") ~default:0.0;
    loss_ratio = to_number_opt (json |> member "loss_ratio") ~default:0.0;
    expense_ratio = to_number_opt (json |> member "expense_ratio") ~default:0.0;
    combined_ratio = to_number_opt (json |> member "combined_ratio") ~default:0.0;
    (* Oil & Gas E&P specific fields - default to 0.0 for non-O&G *)
    is_oil_gas =
      (try json |> member "is_oil_gas" |> to_bool with _ -> false);
    proven_reserves = to_number_opt (json |> member "proven_reserves") ~default:0.0;
    production_boe_day = to_number_opt (json |> member "production_boe_day") ~default:0.0;
    ebitdax = to_number_opt (json |> member "ebitdax") ~default:0.0;
    exploration_expense = to_number_opt (json |> member "exploration_expense") ~default:0.0;
    dd_and_a = to_number_opt (json |> member "dd_and_a") ~default:0.0;
    finding_cost = to_number_opt (json |> member "finding_cost") ~default:0.0;
    lifting_cost = to_number_opt (json |> member "lifting_cost") ~default:0.0;
    oil_pct = to_number_opt (json |> member "oil_pct") ~default:0.5;
  }

(** Format oil & gas valuation result *)
let format_oil_gas_result (result : Types.oil_gas_valuation_result) =
  let open Types in
  let open Printf in

  let buffer = Buffer.create 1024 in
  let bprintf = Buffer.add_string buffer in

  bprintf (sprintf "\n========================================\n");
  bprintf (sprintf "Oil & Gas E&P Valuation: %s\n" result.ticker);
  bprintf (sprintf "========================================\n\n");

  bprintf (sprintf "Market Data:\n");
  bprintf (sprintf "  Current Price: $%.2f\n" result.price);
  bprintf (sprintf "\n");

  bprintf (sprintf "O&G Metrics:\n");
  bprintf (sprintf "  Reserve Life: %.1f years\n" result.oil_gas_metrics.reserve_life);
  bprintf (sprintf "  EBITDAX Margin: %.1f%%\n" (result.oil_gas_metrics.ebitdax_margin *. 100.0));
  bprintf (sprintf "  EBITDAX/BOE: $%.2f\n" result.oil_gas_metrics.ebitdax_per_boe);
  bprintf (sprintf "  Netback: $%.2f/BOE\n" result.oil_gas_metrics.netback);
  bprintf (sprintf "  Recycle Ratio: %.2fx\n" result.oil_gas_metrics.recycle_ratio);
  bprintf (sprintf "  EV/EBITDAX: %.2fx\n" result.oil_gas_metrics.ev_to_ebitdax);
  bprintf (sprintf "  EV/BOE: $%.2f\n" result.oil_gas_metrics.ev_per_boe);
  bprintf (sprintf "  Debt/EBITDAX: %.2fx\n" result.oil_gas_metrics.debt_to_ebitdax);
  bprintf (sprintf "  ROE: %.2f%%\n" (result.oil_gas_metrics.roe *. 100.0));
  bprintf (sprintf "\n");

  bprintf (sprintf "Cost of Capital:\n");
  bprintf (sprintf "  Discount Rate: %.2f%%\n" (result.cost_of_capital *. 100.0));
  bprintf (sprintf "\n");

  bprintf (sprintf "Valuation Results (NAV Model):\n");
  bprintf (sprintf "  Reserve Value (PV): $%.2f/share\n" result.reserve_value);
  bprintf (sprintf "  PV-10 Value: $%.2f/share\n" result.pv10_value);
  bprintf (sprintf "  NAV per Share: $%.2f\n" result.nav_per_share);
  bprintf (sprintf "  Fair Value per Share: $%.2f\n" result.fair_value_per_share);
  bprintf (sprintf "  Margin of Safety: %.2f%%\n" (result.margin_of_safety *. 100.0));
  (match result.implied_oil_price with
   | Some price -> bprintf (sprintf "  Market-Implied Oil Price: $%.2f/bbl\n" price)
   | None -> bprintf "  Market-Implied Oil Price: N/A\n");
  bprintf (sprintf "\n");

  bprintf (sprintf "Investment Signal: %s\n" (Signal.signal_to_colored_string result.signal));
  bprintf (sprintf "  %s\n" (Signal.signal_explanation result.signal));
  bprintf (sprintf "\n");

  Buffer.contents buffer

(** Format insurance valuation result *)
let format_insurance_result (result : Types.insurance_valuation_result) =
  let open Types in
  let open Printf in

  let buffer = Buffer.create 1024 in
  let bprintf = Buffer.add_string buffer in

  bprintf (sprintf "\n========================================\n");
  bprintf (sprintf "Insurance Valuation: %s\n" result.ticker);
  bprintf (sprintf "========================================\n\n");

  bprintf (sprintf "Market Data:\n");
  bprintf (sprintf "  Current Price: $%.2f\n" result.price);
  bprintf (sprintf "  Book Value per Share: $%.2f\n" result.book_value_per_share);
  bprintf (sprintf "\n");

  bprintf (sprintf "Insurance Metrics:\n");
  bprintf (sprintf "  Combined Ratio: %.1f%%\n" (result.insurance_metrics.combined_ratio *. 100.0));
  bprintf (sprintf "    Loss Ratio: %.1f%%\n" (result.insurance_metrics.loss_ratio *. 100.0));
  bprintf (sprintf "    Expense Ratio: %.1f%%\n" (result.insurance_metrics.expense_ratio *. 100.0));
  bprintf (sprintf "  Underwriting Margin: %.1f%%\n" (result.insurance_metrics.underwriting_margin *. 100.0));
  bprintf (sprintf "  ROE: %.2f%%\n" (result.insurance_metrics.roe *. 100.0));
  bprintf (sprintf "  Investment Yield: %.2f%%\n" (result.insurance_metrics.investment_yield *. 100.0));
  bprintf (sprintf "  Float/Equity: %.2fx\n" result.insurance_metrics.float_to_equity);
  bprintf (sprintf "  Price/Book: %.2fx\n" result.insurance_metrics.price_to_book);
  bprintf (sprintf "  Premium/Equity: %.2fx\n" result.insurance_metrics.premium_to_equity);
  bprintf (sprintf "\n");

  bprintf (sprintf "Cost of Capital:\n");
  bprintf (sprintf "  Cost of Equity: %.2f%%\n" (result.cost_of_equity *. 100.0));
  bprintf (sprintf "\n");

  bprintf (sprintf "Valuation Results (Float-Based Model):\n");
  bprintf (sprintf "  Book Value per Share: $%.2f\n" result.book_value_per_share);
  bprintf (sprintf "  Underwriting Value: $%.2f/share\n" result.underwriting_value);
  bprintf (sprintf "  Float Value: $%.2f/share\n" result.float_value);
  bprintf (sprintf "  Fair Value per Share: $%.2f\n" result.fair_value_per_share);
  bprintf (sprintf "  Margin of Safety: %.2f%%\n" (result.margin_of_safety *. 100.0));
  (match result.implied_combined_ratio with
   | Some cr -> bprintf (sprintf "  Market-Implied Combined Ratio: %.1f%%\n" (cr *. 100.0))
   | None -> bprintf "  Market-Implied Combined Ratio: N/A\n");
  bprintf (sprintf "\n");

  bprintf (sprintf "Investment Signal: %s\n" (Signal.signal_to_colored_string result.signal));
  bprintf (sprintf "  %s\n" (Signal.signal_explanation result.signal));
  bprintf (sprintf "\n");

  Buffer.contents buffer

(** Format bank valuation result *)
let format_bank_result (result : Types.bank_valuation_result) =
  let open Types in
  let open Printf in

  let buffer = Buffer.create 1024 in
  let bprintf = Buffer.add_string buffer in

  bprintf (sprintf "\n========================================\n");
  bprintf (sprintf "Bank Valuation: %s\n" result.ticker);
  bprintf (sprintf "========================================\n\n");

  bprintf (sprintf "Market Data:\n");
  bprintf (sprintf "  Current Price: $%.2f\n" result.price);
  bprintf (sprintf "  Book Value per Share: $%.2f\n" result.book_value_per_share);
  bprintf (sprintf "  Tangible Book per Share: $%.2f\n" result.tangible_book_per_share);
  bprintf (sprintf "\n");

  bprintf (sprintf "Bank Metrics:\n");
  bprintf (sprintf "  ROE: %.2f%%\n" (result.bank_metrics.roe *. 100.0));
  bprintf (sprintf "  ROTCE: %.2f%%\n" (result.bank_metrics.rotce *. 100.0));
  bprintf (sprintf "  ROA: %.2f%%\n" (result.bank_metrics.roa *. 100.0));
  bprintf (sprintf "  Net Interest Margin: %.2f%%\n" (result.bank_metrics.nim *. 100.0));
  bprintf (sprintf "  Efficiency Ratio: %.2f%%\n" (result.bank_metrics.efficiency_ratio *. 100.0));
  bprintf (sprintf "  Price/Book: %.2fx\n" result.bank_metrics.price_to_book);
  bprintf (sprintf "  Price/TBV: %.2fx\n" result.bank_metrics.price_to_tbv);
  bprintf (sprintf "  PPNR per Share: $%.2f\n" result.bank_metrics.ppnr_per_share);
  bprintf (sprintf "\n");

  bprintf (sprintf "Cost of Capital:\n");
  bprintf (sprintf "  Cost of Equity: %.2f%%\n" (result.cost_of_equity *. 100.0));
  bprintf (sprintf "  ROE Spread (ROE - CoE): %.2f%%\n"
    ((result.bank_metrics.roe -. result.cost_of_equity) *. 100.0));
  bprintf (sprintf "\n");

  bprintf (sprintf "Valuation Results (Excess Return Model):\n");
  bprintf (sprintf "  Excess Return Value: $%.2f/share\n" result.excess_return_value);
  bprintf (sprintf "  Fair Value per Share: $%.2f\n" result.fair_value_per_share);
  bprintf (sprintf "  Margin of Safety: %.2f%%\n" (result.margin_of_safety *. 100.0));
  (match result.implied_roe with
   | Some roe -> bprintf (sprintf "  Market-Implied ROE: %.2f%%\n" (roe *. 100.0))
   | None -> bprintf "  Market-Implied ROE: N/A\n");
  bprintf (sprintf "\n");

  bprintf (sprintf "Investment Signal: %s\n" (Signal.signal_to_colored_string result.signal));
  bprintf (sprintf "  %s\n" (Signal.signal_explanation result.signal));
  bprintf (sprintf "\n");

  Buffer.contents buffer

let format_valuation_result result =
  let open Types in
  let open Printf in

  (* If bank result exists, format it instead *)
  match result.bank_result with
  | Some bank_result -> format_bank_result bank_result
  | None ->
  (* If insurance result exists, format it instead *)
  match result.insurance_result with
  | Some insurance_result -> format_insurance_result insurance_result
  | None ->
  (* If oil & gas result exists, format it instead *)
  match result.oil_gas_result with
  | Some oil_gas_result -> format_oil_gas_result oil_gas_result
  | None ->

  let buffer = Buffer.create 1024 in
  let bprintf = Buffer.add_string buffer in

  bprintf (sprintf "\n========================================\n");
  bprintf (sprintf "DCF Valuation: %s\n" result.ticker);
  bprintf (sprintf "========================================\n\n");

  bprintf (sprintf "Market Data:\n");
  bprintf (sprintf "  Current Price: $%.2f\n" result.price);
  bprintf (sprintf "\n");

  bprintf (sprintf "Cost of Capital:\n");
  bprintf (sprintf "  Risk-Free Rate: %.2f%%\n" (result.cost_of_capital.risk_free_rate *. 100.0));

  (* Display ERP with source information *)
  let erp_source_str = match result.cost_of_capital.erp_source_used with
    | Types.Static -> "Static (Damodaran)"
    | Types.Dynamic { vix_mean; sensitivity } ->
        sprintf "Dynamic (VIX adj=%.3f, mean=%.1f, sens=%.2f)"
          result.cost_of_capital.erp_vix_adjustment vix_mean sensitivity
  in
  bprintf (sprintf "  Equity Risk Premium: %.2f%% [%s]\n"
    (result.cost_of_capital.equity_risk_premium *. 100.0) erp_source_str);
  if result.cost_of_capital.erp_vix_adjustment <> 1.0 then
    bprintf (sprintf "    Base ERP: %.2f%%, VIX Adjustment: %.1f%%\n"
      (result.cost_of_capital.erp_base *. 100.0)
      ((result.cost_of_capital.erp_vix_adjustment -. 1.0) *. 100.0));

  bprintf (sprintf "  Leveraged Beta: %.2f\n" result.cost_of_capital.leveraged_beta);
  bprintf (sprintf "  Cost of Equity: %.2f%%\n" (result.cost_of_capital.ce *. 100.0));
  bprintf (sprintf "  Cost of Borrowing: %.2f%%\n" (result.cost_of_capital.cb *. 100.0));
  bprintf (sprintf "  WACC: %.2f%%\n" (result.cost_of_capital.wacc *. 100.0));
  bprintf (sprintf "\n");

  bprintf (sprintf "Growth Rates:\n");
  bprintf (sprintf "  FCFE Growth Rate: %.2f%%%s\n"
    (result.projection.growth_rate_fcfe *. 100.0)
    (if result.projection.growth_clamped_fcfe then " (clamped)" else ""));
  bprintf (sprintf "  FCFF Growth Rate: %.2f%%%s\n"
    (result.projection.growth_rate_fcff *. 100.0)
    (if result.projection.growth_clamped_fcff then " (clamped)" else ""));
  bprintf (sprintf "\n");

  bprintf (sprintf "Valuation Results:\n");
  bprintf (sprintf "  FCFE Method:\n");
  bprintf (sprintf "    Present Value of Equity: $%.2f\n" result.pve);
  bprintf (sprintf "    Intrinsic Value per Share: $%.2f\n" result.ivps_fcfe);
  bprintf (sprintf "    Margin of Safety: %.2f%%\n" (result.margin_of_safety_fcfe *. 100.0));
  (match result.implied_growth_fcfe with
   | Some g -> bprintf (sprintf "    Market-Implied Growth: %.2f%%\n" (g *. 100.0))
   | None -> bprintf "    Market-Implied Growth: N/A\n");
  bprintf (sprintf "\n");

  bprintf (sprintf "  FCFF Method:\n");
  bprintf (sprintf "    Present Value of Firm (minus debt): $%.2f\n" result.pvf_minus_debt);
  bprintf (sprintf "    Intrinsic Value per Share: $%.2f\n" result.ivps_fcff);
  bprintf (sprintf "    Margin of Safety: %.2f%%\n" (result.margin_of_safety_fcff *. 100.0));
  (match result.implied_growth_fcff with
   | Some g -> bprintf (sprintf "    Market-Implied Growth: %.2f%%\n" (g *. 100.0))
   | None -> bprintf "    Market-Implied Growth: N/A\n");
  bprintf (sprintf "\n");

  bprintf (sprintf "Investment Signal: %s\n" (Signal.signal_to_colored_string result.signal));
  bprintf (sprintf "  %s\n" (Signal.signal_explanation result.signal));
  bprintf (sprintf "\n");

  Buffer.contents buffer

let write_log ~filename ~result =
  let oc = open_out filename in
  output_string oc (format_valuation_result result);
  close_out oc

let create_log_filename ~base_dir ~ticker =
  let timestamp = Unix.time () |> Unix.localtime in
  let open Unix in
  Printf.sprintf "%s/dcf_%s_%04d%02d%02d_%02d%02d%02d.log"
    base_dir
    ticker
    (timestamp.tm_year + 1900)
    (timestamp.tm_mon + 1)
    timestamp.tm_mday
    timestamp.tm_hour
    timestamp.tm_min
    timestamp.tm_sec

(* Scenario analysis I/O *)

let format_scenario_comparison comparison =
  let open Scenarios in
  let buffer = Buffer.create 1024 in
  let bprintf s = Buffer.add_string buffer s in

  bprintf (Printf.sprintf "========================================\n");
  bprintf (Printf.sprintf "Scenario Analysis: %s\n" comparison.ticker);
  bprintf (Printf.sprintf "========================================\n\n");
  bprintf (Printf.sprintf "Market Price: $%.2f\n\n" comparison.price);

  let format_scenario (result : scenario_result) =
    let scenario_name = match result.scenario with
      | Bull -> "BULL (Optimistic)"
      | Base -> "BASE (Current)"
      | Bear -> "BEAR (Pessimistic)" in

    bprintf (Printf.sprintf "%s:\n" scenario_name);
    bprintf (Printf.sprintf "  Cost of Equity: %.2f%%\n" (result.cost_of_equity *. 100.0));
    bprintf (Printf.sprintf "  WACC: %.2f%%\n" (result.wacc *. 100.0));
    bprintf (Printf.sprintf "  FCFE Growth: %.2f%%\n" (result.growth_rate_fcfe *. 100.0));
    bprintf (Printf.sprintf "  FCFF Growth: %.2f%%\n" (result.growth_rate_fcff *. 100.0));
    bprintf (Printf.sprintf "  \n");
    bprintf (Printf.sprintf "  FCFE IVPS: $%.2f (%.1f%% MOS)\n"
      result.ivps_fcfe (result.margin_of_safety_fcfe *. 100.0));
    bprintf (Printf.sprintf "  FCFF IVPS: $%.2f (%.1f%% MOS)\n"
      result.ivps_fcff (result.margin_of_safety_fcff *. 100.0));
    bprintf (Printf.sprintf "\n")
  in

  format_scenario comparison.bull;
  format_scenario comparison.base;
  format_scenario comparison.bear;

  bprintf (Printf.sprintf "Summary:\n");
  bprintf (Printf.sprintf "  FCFE Range: $%.2f - $%.2f (spread: $%.2f)\n"
    comparison.bear.ivps_fcfe
    comparison.bull.ivps_fcfe
    (comparison.bull.ivps_fcfe -. comparison.bear.ivps_fcfe));
  bprintf (Printf.sprintf "  FCFF Range: $%.2f - $%.2f (spread: $%.2f)\n"
    comparison.bear.ivps_fcff
    comparison.bull.ivps_fcff
    (comparison.bull.ivps_fcff -. comparison.bear.ivps_fcff));

  Buffer.contents buffer

let write_scenario_csv ~filename ~comparison =
  let open Scenarios in
  let oc = open_out filename in
  
  (* Write header *)
  Printf.fprintf oc "scenario,cost_of_equity,wacc,growth_fcfe,growth_fcff,ivps_fcfe,ivps_fcff,mos_fcfe,mos_fcff\n";
  
  (* Write each scenario *)
  let write_row (result : scenario_result) =
    let scenario_name = match result.scenario with
      | Bull -> "Bull"
      | Base -> "Base"
      | Bear -> "Bear" in
    Printf.fprintf oc "%s,%.4f,%.4f,%.4f,%.4f,%.2f,%.2f,%.4f,%.4f\n"
      scenario_name
      result.cost_of_equity
      result.wacc
      result.growth_rate_fcfe
      result.growth_rate_fcff
      result.ivps_fcfe
      result.ivps_fcff
      result.margin_of_safety_fcfe
      result.margin_of_safety_fcff
  in
  
  write_row comparison.bull;
  write_row comparison.base;
  write_row comparison.bear;
  
  close_out oc
