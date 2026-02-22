(** Systematic Risk Early-Warning Signals CLI

    Based on: "An early-warning risk signals framework to capture
    systematic risk in financial markets" (Ciciretti et al. 2025)

    Computes four early-warning signals:
    1. Variance explained by largest eigenvalue (λ₁)
    2. Variance explained by eigenvalues 2-5 (λ₂₋₅)
    3. Mean eigenvector centrality from MST
    4. Std dev of eigenvector centrality from MST
*)

open Systematic_risk_signals
open Types

let print_help () =
  print_endline "Systematic Risk Early-Warning Signals";
  print_endline "";
  print_endline "Computes early-warning signals for systematic risk based on";
  print_endline "graph theory (MST) and covariance matrix eigenvalue analysis.";
  print_endline "";
  print_endline "Usage:";
  print_endline "  risk_signals --tickers AAPL,MSFT,GOOGL   Analyze these tickers";
  print_endline "  risk_signals --data <file>              Use pre-fetched data file";
  print_endline "";
  print_endline "Options:";
  print_endline "  --tickers <list>    Comma-separated ticker symbols";
  print_endline "  --data <dir>        Data directory (default: pricing/systematic_risk_signals/data)";
  print_endline "  --output <dir>      Output directory (default: pricing/systematic_risk_signals/output)";
  print_endline "  --window <days>     Rolling window size (default: 20)";
  print_endline "  --lookback <days>   Historical lookback period (default: 252)";
  print_endline "  --python <cmd>      Python command to run fetcher";
  print_endline "  --json              Output JSON instead of formatted text";
  print_endline "  --help              Show this help";
  print_endline "";
  print_endline "Examples:";
  print_endline "  risk_signals --tickers SPY,QQQ,IWM,EFA,AGG --python '.venv/bin/python3'";
  print_endline "  risk_signals --data pricing/systematic_risk_signals/data/returns.json"

let parse_tickers s =
  String.split_on_char ',' s |> List.map String.trim

let run_python_fetcher python_cmd tickers data_dir =
  let ticker_str = String.concat "," tickers in
  let cmd = Printf.sprintf "%s pricing/systematic_risk_signals/python/fetch/fetch_returns.py --tickers %s --output %s/returns.json"
    python_cmd ticker_str data_dir in
  let exit_code = Sys.command cmd in
  if exit_code <> 0 then
    failwith (Printf.sprintf "Python fetcher failed with exit code %d" exit_code)

let () =
  let tickers = ref [] in
  let data_dir = ref "pricing/systematic_risk_signals/data" in
  let output_dir = ref "pricing/systematic_risk_signals/output" in
  let window = ref 20 in
  let lookback = ref 252 in
  let python_cmd = ref "" in
  let json_output = ref false in
  let data_file = ref "" in

  let args = Array.to_list Sys.argv |> List.tl in

  let rec parse = function
    | [] -> ()
    | "--help" :: _ -> print_help (); exit 0
    | "--tickers" :: t :: rest ->
        tickers := parse_tickers t;
        parse rest
    | "--data" :: d :: rest ->
        if Sys.file_exists d && not (Sys.is_directory d) then
          data_file := d
        else
          data_dir := d;
        parse rest
    | "--output" :: o :: rest ->
        output_dir := o;
        parse rest
    | "--window" :: w :: rest ->
        window := int_of_string w;
        parse rest
    | "--lookback" :: l :: rest ->
        lookback := int_of_string l;
        parse rest
    | "--python" :: p :: rest ->
        python_cmd := p;
        parse rest
    | "--json" :: rest ->
        json_output := true;
        parse rest
    | _ :: rest -> parse rest
  in
  parse args;

  (* Validate inputs *)
  if !tickers = [] && !data_file = "" then begin
    print_help ();
    exit 1
  end;

  (* Fetch data if needed *)
  if !data_file = "" then begin
    if !python_cmd = "" then begin
      Printf.eprintf "Error: --python required when using --tickers\n";
      exit 1
    end;
    run_python_fetcher !python_cmd !tickers !data_dir;
    data_file := !data_dir ^ "/returns.json"
  end;

  (* Read data *)
  let returns = Io.read_returns_data !data_file in

  if Array.length returns = 0 then begin
    Printf.eprintf "Error: No return data found in %s\n" !data_file;
    exit 1
  end;

  (* Create config *)
  let config = {
    tickers = if !tickers <> [] then !tickers
              else Array.to_list (Array.map (fun r -> r.ticker) returns);
    lookback_days = !lookback;
    rolling_window = !window;
    data_dir = !data_dir;
    output_dir = !output_dir;
  } in

  (* Run analysis *)
  let result = Signals.full_analysis config returns in

  (* Output results *)
  if !json_output then begin
    let json_file = !output_dir ^ "/risk_signals.json" in
    Io.write_result_json json_file result;
    Printf.printf "Results written to %s\n" json_file
  end else
    Io.print_analysis result
