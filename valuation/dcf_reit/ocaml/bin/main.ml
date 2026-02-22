(** REIT Valuation Model - Main Entry Point

    Usage:
      ./main -d <data_dir> [-t <ticker>] [-o <output_dir>]

    Performs REIT-specific valuation using:
    - FFO/AFFO analysis
    - NAV (Net Asset Value) calculation
    - Dividend Discount Model
    - P/FFO and P/AFFO relative valuation
*)

open Dcf_reit

let data_dir = ref "valuation/dcf_reit/data"
let output_dir = ref "valuation/dcf_reit/output/data"
let ticker = ref ""
let risk_free_rate = ref 0.045   (* 4.5% default *)
let equity_risk_premium = ref 0.05  (* 5% default *)

let usage = "Usage: main -d <data_dir> [-t <ticker>] [-o <output_dir>] [-r <rfr>] [-e <erp>]"

let specs = [
  ("-d", Arg.Set_string data_dir, "Data directory containing REIT JSON files");
  ("-t", Arg.Set_string ticker, "Single ticker to process (optional, processes all if not set)");
  ("-o", Arg.Set_string output_dir, "Output directory for results");
  ("-r", Arg.Set_float risk_free_rate, "Risk-free rate (default: 0.045)");
  ("-e", Arg.Set_float equity_risk_premium, "Equity risk premium (default: 0.05)");
]

let get_json_files dir =
  let handle = Unix.opendir dir in
  let rec collect acc =
    match Unix.readdir handle with
    | exception End_of_file -> Unix.closedir handle; acc
    | "." | ".." -> collect acc
    | filename ->
        if Filename.check_suffix filename ".json" &&
           not (String.equal filename "config.json") then
          collect ((Filename.concat dir filename) :: acc)
        else
          collect acc
  in
  collect []

let process_reit filepath =
  Printf.printf "Processing: %s\n" filepath;

  try
    let (market, financial) = Io.load_reit_data filepath in

    Printf.printf "  Ticker: %s\n" market.ticker;
    Printf.printf "  Sector: %s\n" (Io.string_of_property_sector market.sector);
    Printf.printf "  Price:  $%.2f\n" market.price;

    let result = Valuation.value_reit
      ~financial
      ~market
      ~risk_free_rate:!risk_free_rate
      ~equity_risk_premium:!equity_risk_premium
    in

    (* Calculate income investor metrics *)
    let income_metrics = match result.reit_type with
      | Types.MortgageREIT ->
          (match result.mreit_metrics with
           | Some mreit_m ->
               Some (Income.calculate_mreit
                 ~market
                 ~mreit_metrics:mreit_m
                 ~risk_free_rate:!risk_free_rate)
           | None -> None)
      | Types.EquityREIT | Types.HybridREIT ->
          Some (Income.calculate_equity_reit
            ~market
            ~ffo_metrics:result.ffo_metrics
            ~quality:result.quality
            ~risk_free_rate:!risk_free_rate)
    in

    (* Print value investor view *)
    Io.print_summary result;

    (* Print income investor view *)
    (match income_metrics with
     | Some im -> Io.print_income_metrics im
     | None -> ());

    (* Save result with income metrics *)
    let output_file = Filename.concat !output_dir
      (Printf.sprintf "%s_valuation.json" market.ticker) in
    Io.save_result_with_income output_file result income_metrics;
    Printf.printf "  Saved: %s\n\n" output_file;

    Some (result, income_metrics)

  with e ->
    Printf.printf "  Error: %s\n\n" (Printexc.to_string e);
    None

let () =
  Arg.parse specs (fun _ -> ()) usage;

  (* Ensure output directory exists *)
  (try Unix.mkdir !output_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());

  Printf.printf "REIT Valuation Model\n";
  Printf.printf "══════════════════════════════════════════════\n";
  Printf.printf "Risk-Free Rate:      %.2f%%\n" (!risk_free_rate *. 100.0);
  Printf.printf "Equity Risk Premium: %.2f%%\n" (!equity_risk_premium *. 100.0);
  Printf.printf "══════════════════════════════════════════════\n\n";

  let files =
    if !ticker <> "" then
      [Filename.concat !data_dir (!ticker ^ ".json")]
    else
      get_json_files !data_dir
  in

  let results = List.filter_map process_reit files in

  Printf.printf "\n══════════════════════════════════════════════\n";
  Printf.printf "Processed %d REITs\n" (List.length results);

  (* Print summary table - value and income views *)
  if List.length results > 0 then begin
    Printf.printf "\nVALUE INVESTOR SUMMARY\n";
    Printf.printf "%-8s %8s %8s %8s %12s\n" "Ticker" "Price" "Fair Val" "Upside" "Signal";
    Printf.printf "──────── ──────── ──────── ──────── ────────────\n";
    List.iter (fun ((r : Types.valuation_result), _) ->
      Printf.printf "%-8s %8.2f %8.2f %7.1f%% %12s\n"
        r.ticker r.price r.fair_value (r.upside_potential *. 100.0)
        (Io.string_of_signal r.signal)
    ) results;

    Printf.printf "\nINCOME INVESTOR SUMMARY\n";
    Printf.printf "%-8s %7s %8s %10s %7s %18s\n" "Ticker" "Yield" "Coverage" "Payout" "Score" "Recommendation";
    Printf.printf "──────── ─────── ──────── ────────── ─────── ──────────────────\n";
    List.iter (fun ((r : Types.valuation_result), income_opt) ->
      match income_opt with
      | Some (im : Income.income_metrics) ->
          Printf.printf "%-8s %6.2f%% %7.2fx %9.0f%% %6.0f %18s\n"
            r.ticker (im.dividend_yield *. 100.0) im.coverage_ratio
            (im.payout_ratio *. 100.0) im.income_score im.income_recommendation
      | None ->
          Printf.printf "%-8s %7s %8s %10s %7s %18s\n"
            r.ticker "-" "-" "-" "-" "-"
    ) results
  end
