(** Data I/O and logging utilities *)

open Types

(** Read CSV file with returns data *)
let read_returns_csv ~filename ~ticker =
  try
    let ic = open_in filename in
    let csv = Csv.of_channel ic in
    let rows = Csv.input_all csv in
    close_in ic;

    match rows with
    | [] -> failwith "Empty CSV file"
    | _header :: data_rows ->
        let dates = Array.of_list (List.map (fun row -> List.nth row 0) data_rows) in
        let returns = Array.of_list (List.map (fun row ->
          float_of_string (List.nth row 1)
        ) data_rows) in
        { ticker; dates; returns }
  with
  | Sys_error msg -> failwith (Printf.sprintf "Failed to read %s: %s" filename msg)
  | _ -> failwith (Printf.sprintf "Failed to parse CSV file %s" filename)

(** Read benchmark CSV *)
let read_benchmark_csv ~filename =
  try
    let ic = open_in filename in
    let csv = Csv.of_channel ic in
    let rows = Csv.input_all csv in
    close_in ic;

    match rows with
    | [] -> failwith "Empty CSV file"
    | _header :: data_rows ->
        let dates = Array.of_list (List.map (fun row -> List.nth row 0) data_rows) in
        let returns = Array.of_list (List.map (fun row ->
          float_of_string (List.nth row 1)
        ) data_rows) in
        { dates; returns }
  with
  | Sys_error msg -> failwith (Printf.sprintf "Failed to read %s: %s" filename msg)
  | _ -> failwith (Printf.sprintf "Failed to parse CSV file %s" filename)

(** Write log entry to file *)
let write_log_entry ~log_file ~entry =
  let oc = open_out_gen [Open_creat; Open_append; Open_text] 0o644 log_file in
  let fmt = Format.formatter_of_out_channel oc in

  Format.fprintf fmt "\n=== Evaluation: %s ===\n" entry.date;
  Format.fprintf fmt "Regime:\n";
  Format.fprintf fmt "  Volatility: %.4f\n" entry.regime.volatility;
  Format.fprintf fmt "  Stress weight: %.4f\n" entry.regime.stress_weight;
  Format.fprintf fmt "  Is stress: %b\n" entry.regime.is_stress;

  Format.fprintf fmt "\nAsset Betas:\n";
  List.iter (fun (ticker, beta) ->
    Format.fprintf fmt "  %s: %.4f\n" ticker beta
  ) entry.asset_betas;

  Format.fprintf fmt "\nCurrent Risk:\n";
  Format.fprintf fmt "  LPM1: %.6f\n" entry.risk_current.lpm1;
  Format.fprintf fmt "  CVaR 95%%: %.6f\n" entry.risk_current.cvar_95;
  Format.fprintf fmt "  Portfolio Beta: %.4f\n" entry.risk_current.portfolio_beta;

  Format.fprintf fmt "\nProposed Risk:\n";
  Format.fprintf fmt "  LPM1: %.6f\n" entry.risk_proposed.lpm1;
  Format.fprintf fmt "  CVaR 95%%: %.6f\n" entry.risk_proposed.cvar_95;
  Format.fprintf fmt "  Portfolio Beta: %.4f\n" entry.risk_proposed.portfolio_beta;

  Format.fprintf fmt "\nRebalancing Decision:\n";
  Format.fprintf fmt "  Should rebalance: %b\n" entry.decision.should_rebalance;
  Format.fprintf fmt "  Reason: %s\n" entry.decision.reason;
  Format.fprintf fmt "  Improvement: %.6f\n" entry.decision.objective_improvement;
  Format.fprintf fmt "  Turnover: %.4f\n" entry.turnover;
  Format.fprintf fmt "  Costs: %.6f\n" entry.costs;

  Format.fprintf fmt "\n@.";
  close_out oc

(** Read parameters from JSON file *)
let read_params_json ~filename =
  let json = Yojson.Basic.from_file filename in
  let open Yojson.Basic.Util in
  {
    lambda_lpm1 = json |> member "lambda_lpm1" |> to_float;
    lambda_cvar = json |> member "lambda_cvar" |> to_float;
    transaction_cost_bps = json |> member "transaction_cost_bps" |> to_float;
    turnover_penalty = json |> member "turnover_penalty" |> to_float;
    beta_penalty = json |> member "beta_penalty" |> to_float;
    target_beta = json |> member "target_beta" |> to_float;
    lpm1_threshold = json |> member "lpm1_threshold" |> to_float;
    rebalance_threshold = json |> member "rebalance_threshold" |> to_float;
  }

(** Write optimization result to CSV *)
let write_result_csv ~filename ~results =
  let oc = open_out filename in
  let csv_out = Csv.to_channel oc in

  (* Write header *)
  Csv.output_record csv_out
    ["date"; "ticker"; "weight"; "objective"; "lpm1"; "cvar_95"; "beta"; "turnover"; "costs"];

  (* Write data rows *)
  List.iter (fun (date, result) ->
    List.iter (fun (ticker, weight) ->
      Csv.output_record csv_out [
        date;
        ticker;
        Printf.sprintf "%.6f" weight;
        Printf.sprintf "%.6f" result.objective_value;
        Printf.sprintf "%.6f" result.risk_metrics.lpm1;
        Printf.sprintf "%.6f" result.risk_metrics.cvar_95;
        Printf.sprintf "%.4f" result.risk_metrics.portfolio_beta;
        Printf.sprintf "%.4f" result.turnover;
        Printf.sprintf "%.6f" result.transaction_costs;
      ]
    ) result.weights.assets;

    (* Add cash row *)
    Csv.output_record csv_out [
      date;
      "CASH";
      Printf.sprintf "%.6f" result.weights.cash;
      Printf.sprintf "%.6f" result.objective_value;
      Printf.sprintf "%.6f" result.risk_metrics.lpm1;
      Printf.sprintf "%.6f" result.risk_metrics.cvar_95;
      Printf.sprintf "%.4f" result.risk_metrics.portfolio_beta;
      Printf.sprintf "%.4f" result.turnover;
      Printf.sprintf "%.6f" result.transaction_costs;
    ]
  ) results;

  Csv.close_out csv_out;
  close_out oc

(** Write dual optimization results to CSV *)
let write_dual_result_csv ~filename ~results =
  let oc = open_out filename in
  let csv_out = Csv.to_channel oc in

  (* Write header *)
  Csv.output_record csv_out
    ["date"; "ticker"; "weight_constrained"; "weight_frictionless";
     "objective_constrained"; "objective_frictionless";
     "lpm1_constrained"; "lpm1_frictionless";
     "cvar_constrained"; "cvar_frictionless";
     "beta_constrained"; "beta_frictionless";
     "turnover_constrained";
     "gap_distance"; "gap_lpm1"; "gap_cvar"; "gap_beta"];

  (* Write data rows *)
  List.iter (fun (date, dual_result) ->
    (* Get frictionless weights as a map for easy lookup *)
    let frictionless_map =
      List.fold_left (fun acc (ticker, weight) ->
        (ticker, weight) :: acc
      ) [] dual_result.frictionless.weights.assets
    in

    (* Write asset rows *)
    List.iter (fun (ticker, weight_constrained) ->
      let weight_frictionless =
        try List.assoc ticker frictionless_map
        with Not_found -> 0.0
      in
      Csv.output_record csv_out [
        date;
        ticker;
        Printf.sprintf "%.6f" weight_constrained;
        Printf.sprintf "%.6f" weight_frictionless;
        Printf.sprintf "%.6f" dual_result.constrained.objective_value;
        Printf.sprintf "%.6f" dual_result.frictionless.objective_value;
        Printf.sprintf "%.6f" dual_result.constrained.risk_metrics.lpm1;
        Printf.sprintf "%.6f" dual_result.frictionless.risk_metrics.lpm1;
        Printf.sprintf "%.6f" dual_result.constrained.risk_metrics.cvar_95;
        Printf.sprintf "%.6f" dual_result.frictionless.risk_metrics.cvar_95;
        Printf.sprintf "%.4f" dual_result.constrained.risk_metrics.portfolio_beta;
        Printf.sprintf "%.4f" dual_result.frictionless.risk_metrics.portfolio_beta;
        Printf.sprintf "%.4f" dual_result.constrained.turnover;
        Printf.sprintf "%.4f" dual_result.gap_distance;
        Printf.sprintf "%.6f" dual_result.gap_lpm1;
        Printf.sprintf "%.6f" dual_result.gap_cvar;
        Printf.sprintf "%.4f" dual_result.gap_beta;
      ]
    ) dual_result.constrained.weights.assets;

    (* Add cash row *)
    Csv.output_record csv_out [
      date;
      "CASH";
      Printf.sprintf "%.6f" dual_result.constrained.weights.cash;
      Printf.sprintf "%.6f" dual_result.frictionless.weights.cash;
      Printf.sprintf "%.6f" dual_result.constrained.objective_value;
      Printf.sprintf "%.6f" dual_result.frictionless.objective_value;
      Printf.sprintf "%.6f" dual_result.constrained.risk_metrics.lpm1;
      Printf.sprintf "%.6f" dual_result.frictionless.risk_metrics.lpm1;
      Printf.sprintf "%.6f" dual_result.constrained.risk_metrics.cvar_95;
      Printf.sprintf "%.6f" dual_result.frictionless.risk_metrics.cvar_95;
      Printf.sprintf "%.4f" dual_result.constrained.risk_metrics.portfolio_beta;
      Printf.sprintf "%.4f" dual_result.frictionless.risk_metrics.portfolio_beta;
      Printf.sprintf "%.4f" dual_result.constrained.turnover;
      Printf.sprintf "%.4f" dual_result.gap_distance;
      Printf.sprintf "%.6f" dual_result.gap_lpm1;
      Printf.sprintf "%.6f" dual_result.gap_cvar;
      Printf.sprintf "%.4f" dual_result.gap_beta;
    ]
  ) results;

  Csv.close_out csv_out;
  close_out oc
