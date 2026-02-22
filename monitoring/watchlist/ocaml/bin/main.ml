(** Personal Portfolio Tracker CLI *)

open Watchlist
open Types

let usage = {|
Personal Portfolio Tracker

Track your positions with weighted bull/bear thesis arguments.

Usage:
  portfolio --portfolio <portfolio.json> [--prices <prices.json>] [options]

Required:
  --portfolio <file>  Portfolio JSON with positions and thesis arguments

Options:
  --prices <file>     Market data JSON (from fetch_prices.py)
  --output <file>     Output analysis JSON
  --quiet             Only show alerts, not full analysis
  --help              Show this help message

Portfolio JSON format:
  {
    "positions": [
      {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "position": { "type": "long", "shares": 100, "avg_cost": 150.00 },
        "levels": { "buy_target": 140, "sell_target": 200, "stop_loss": 130 },
        "bull": [
          { "arg": "Services growing 20% YoY", "weight": 9 },
          { "arg": "Buybacks 3% annually", "weight": 6 }
        ],
        "bear": [
          { "arg": "iPhone sales peaked", "weight": 8 }
        ],
        "catalysts": ["Earnings Q1", "WWDC June"],
        "notes": "Core holding"
      }
    ]
  }

Example:
  portfolio --portfolio data/portfolio.json --prices data/prices.json
|}

let () =
  let portfolio_file = ref "" in
  let prices_file = ref "" in
  let output_file = ref "" in
  let quiet = ref false in

  let spec = [
    ("--portfolio", Arg.Set_string portfolio_file, "Portfolio JSON file");
    ("--prices", Arg.Set_string prices_file, "Market data JSON file");
    ("--output", Arg.Set_string output_file, "Output analysis JSON");
    ("--quiet", Arg.Set quiet, "Only show alerts");
    ("--help", Arg.Unit (fun () -> print_string usage; exit 0), "Show help");
    ("-h", Arg.Unit (fun () -> print_string usage; exit 0), "Show help");
  ] in

  Arg.parse spec (fun _ -> ()) usage;

  if !portfolio_file = "" then begin
    prerr_string usage;
    exit 1
  end;

  (* Load portfolio *)
  let positions =
    try Io.load_portfolio !portfolio_file
    with e ->
      Printf.eprintf "Error loading portfolio: %s\n" (Printexc.to_string e);
      exit 1
  in

  if List.length positions = 0 then begin
    Printf.printf "No positions found in portfolio\n";
    exit 0
  end;

  (* Load market data if provided *)
  let market_data =
    if !prices_file <> "" then
      try Io.load_market_data !prices_file
      with e ->
        Printf.eprintf "Warning: Could not load market data: %s\n" (Printexc.to_string e);
        []
    else []
  in

  (* Run analysis *)
  let result = Analysis.run_analysis positions market_data in

  (* Output results *)
  if not !quiet then
    Io.print_portfolio_summary result
  else if List.length result.all_alerts > 0 then begin
    Printf.printf "Alerts triggered:\n";
    List.iter (fun (a : triggered_alert) ->
        Printf.printf "  [%s] %s: %s\n"
          (Io.priority_to_string a.priority)
          a.ticker a.message
      ) result.all_alerts
  end else
    Printf.printf "No alerts triggered\n";

  (* Save analysis *)
  if !output_file <> "" then begin
    Io.save_analysis result !output_file;
    Printf.printf "\nAnalysis saved to %s\n" !output_file
  end
