(** I/O operations for configuration and data files *)

open Yojson.Basic.Util

(** Helper to convert JSON number (int or float) to float *)
let to_number json =
  try to_float json
  with Yojson.Basic.Util.Type_error _ -> float_of_int (to_int json)

let load_params filename =
  let json = Yojson.Basic.from_file filename in
  let open Types in
  {
    projection_years = json |> member "projection_years" |> to_int;
    terminal_growth_rate =
      json |> member "terminal_growth_rate" |> member "default" |> to_number;
    growth_clamp_upper =
      json |> member "growth_clamp" |> member "upper" |> to_number;
    growth_clamp_lower =
      json |> member "growth_clamp" |> member "lower" |> to_number;
    rfr_duration = json |> member "rfr_duration" |> to_int;
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

let load_financial_data filename =
  let json = Yojson.Basic.from_file filename in
  let open Types in
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
    is_bank = json |> member "is_bank" |> to_bool;
  }

let format_valuation_result result =
  let open Types in
  let open Printf in

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
  bprintf (sprintf "  Equity Risk Premium: %.2f%%\n" (result.cost_of_capital.equity_risk_premium *. 100.0));
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
