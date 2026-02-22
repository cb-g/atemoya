(* Options Hedging - CLI Entry Point *)

open Options_hedging

let () =
  (* Parse command-line arguments *)
  let ticker = ref "" in
  let position_size = ref 100.0 in
  let expiry_days = ref 90 in
  let strategy_types = ref ["protective_put"; "collar"; "covered_call"; "vertical_spread"] in
  let min_protection = ref None in
  let max_cost = ref None in
  let use_svi = ref true in
  let num_pareto_points = ref 20 in

  let speclist = [
    ("-ticker", Arg.Set_string ticker, "Ticker symbol (e.g., AAPL)");
    ("-position", Arg.Set_float position_size, "Number of shares held (default: 100)");
    ("-expiry", Arg.Set_int expiry_days, "Days to expiry (default: 90)");
    ("-strategies", Arg.String (fun s -> strategy_types := String.split_on_char ',' s),
     "Comma-separated strategies: protective_put,collar,vertical_spread,covered_call");
    ("-min-protection", Arg.Float (fun p -> min_protection := Some p),
     "Minimum portfolio protection level ($)");
    ("-max-cost", Arg.Float (fun c -> max_cost := Some c),
     "Maximum hedge cost ($)");
    ("-vol-model", Arg.String (fun m -> use_svi := (m = "svi")),
     "Volatility model: svi or sabr (default: svi)");
    ("-num-points", Arg.Set_int num_pareto_points,
     "Number of Pareto frontier points (default: 20)");
  ] in

  Arg.parse speclist (fun _ -> ()) "Options Hedging Model - Portfolio Protection Optimizer";

  if !ticker = "" then begin
    Printf.eprintf "Error: -ticker argument is required\n";
    Arg.usage speclist "Options Hedging Model - Portfolio Protection Optimizer";
    exit 1
  end;

  Printf.printf "=== Options Hedging Analysis: %s ===\n\n" !ticker;

  (* Paths *)
  let data_dir = "pricing/options_hedging/data" in
  let output_dir = "pricing/options_hedging/output" in
  let log_dir = "pricing/options_hedging/log" in

  (* Create output directories if needed *)
  let _ = Sys.command (Printf.sprintf "mkdir -p %s %s %s/plots" output_dir output_dir log_dir) in

  (* Step 1: Load underlying data *)
  Printf.printf "[1/6] Loading underlying data...\n%!";
  let underlying_file = Printf.sprintf "%s/%s_underlying.csv" data_dir !ticker in

  if not (Sys.file_exists underlying_file) then begin
    Printf.eprintf "Error: Underlying data file not found: %s\n" underlying_file;
    Printf.eprintf "Run: uv run python/fetch/fetch_underlying.py --ticker %s\n" !ticker;
    exit 1
  end;

  let underlying_data = Io.read_underlying_data ~filename:underlying_file in
  Printf.printf "  Spot Price: $%.2f\n" underlying_data.spot_price;
  Printf.printf "  Dividend Yield: %.2f%%\n\n" (underlying_data.dividend_yield *. 100.0);

  (* Step 2: Load or calibrate volatility surface *)
  Printf.printf "[2/6] Loading volatility surface...\n%!";
  let model_name = if !use_svi then "svi" else "sabr" in
  let vol_surface_file = Printf.sprintf "%s/%s_vol_surface_%s.json" data_dir !ticker model_name in
  let legacy_file = Printf.sprintf "%s/%s_vol_surface.json" data_dir !ticker in

  let vol_surface =
    if Sys.file_exists vol_surface_file then begin
      Printf.printf "  Loading calibrated surface from %s\n" vol_surface_file;
      Io.read_vol_surface ~filename:vol_surface_file
    end else if Sys.file_exists legacy_file then begin
      Printf.printf "  Loading calibrated surface from %s (legacy)\n" legacy_file;
      Io.read_vol_surface ~filename:legacy_file
    end else begin
      Printf.printf "  Surface not found. Run calibration first:\n";
      Printf.printf "  uv run python/calibrate_vol_surface.py --ticker %s\n" !ticker;
      exit 1
    end
  in

  Printf.printf "  Surface type: %s\n" (match vol_surface with SVI _ -> "SVI" | SABR _ -> "SABR");
  Printf.printf "  Loaded successfully\n\n";

  (* Step 3: Define optimization problem *)
  Printf.printf "[3/6] Setting up optimization...\n%!";

  let spot = underlying_data.spot_price in
  let rate = 0.05 in  (* 5% risk-free rate - TODO: load from data *)

  (* Generate strike grid: 75% to 125% of spot *)
  let num_strikes = 20 in
  let strike_grid = Array.init num_strikes (fun i ->
    let pct = 0.75 +. (float_of_int i /. float_of_int (num_strikes - 1)) *. 0.50 in
    spot *. pct
  ) in

  (* Expiries: user-specified and nearby ones *)
  let expiry_years = float_of_int !expiry_days /. 365.0 in
  let expiries = [| expiry_years |] in

  let problem = Optimization.create_problem
    ~underlying_position:!position_size
    ~underlying_data
    ~vol_surface
    ~rate
    ~expiries
    ~strike_grid
    ?min_protection:!min_protection
    ?max_cost:!max_cost
    ()
  in

  Printf.printf "  Position: %.0f shares\n" !position_size;
  Printf.printf "  Expiry: %d days (%.2f years)\n" !expiry_days expiry_years;
  Printf.printf "  Strike range: $%.2f - $%.2f\n" strike_grid.(0) strike_grid.(num_strikes - 1);
  Printf.printf "  Rate: %.1f%%\n\n" (rate *. 100.0);

  (* Step 4: Generate Pareto frontier *)
  Printf.printf "[4/6] Generating Pareto frontier...\n%!";
  Printf.printf "  This may take a few minutes for Monte Carlo simulations...\n%!";

  let config = {
    Optimization.num_pareto_points = !num_pareto_points;
    num_mc_paths = 1000;
    risk_measure = `MinValue;
  } in

  let result = Optimization.generate_pareto_frontier problem config in
  let frontier = result.pareto_frontier in

  Printf.printf "  Generated %d Pareto-efficient strategies\n\n" (Array.length frontier);

  (* Step 5: Write results *)
  Printf.printf "[5/6] Writing results...\n%!";

  (* Pareto frontier CSV *)
  let pareto_csv = Printf.sprintf "%s/pareto_frontier.csv" output_dir in
  Io.write_pareto_csv ~filename:pareto_csv ~frontier;
  Printf.printf "  Pareto frontier: %s\n" pareto_csv;

  (* Optimization result JSON *)
  let result_json = Printf.sprintf "%s/optimization_result.json" output_dir in
  Io.write_optimization_result ~filename:result_json ~result;
  Printf.printf "  Full result: %s\n" result_json;

  (* Recommended strategy *)
  begin match result.recommended_strategy with
  | None -> Printf.printf "  No recommended strategy found\n"
  | Some strategy ->
      let strategy_csv = Printf.sprintf "%s/recommended_strategy.csv" output_dir in
      Io.write_strategy_csv ~filename:strategy_csv ~strategy;
      Printf.printf "  Recommended strategy: %s\n" strategy_csv;

      Printf.printf "\n  === Recommended Strategy ===\n";
      Printf.printf "  Type: %s\n" (Types.strategy_name strategy.strategy_type);
      Printf.printf "  Cost: $%.2f\n" strategy.cost;
      Printf.printf "  Protection: $%.2f (%.1f%% of portfolio)\n"
        strategy.protection_level
        (strategy.protection_level /. (!position_size *. spot) *. 100.0);
      Printf.printf "  Contracts: %d\n" strategy.contracts;
      Printf.printf "  Delta: %.4f\n" strategy.greeks.delta;
      Printf.printf "  Gamma: %.4f\n" strategy.greeks.gamma;
      Printf.printf "  Vega: %.4f\n" strategy.greeks.vega;
      Printf.printf "  Theta: %.4f (per day)\n" strategy.greeks.theta;
  end;

  Printf.printf "\n[6/6] Generating visualizations...\n%!";
  Printf.printf "  Run visualization scripts:\n";
  Printf.printf "    uv run python/viz/plot_payoffs.py\n";
  Printf.printf "    uv run python/viz/plot_frontier.py\n";
  Printf.printf "    uv run python/viz/plot_greeks.py\n";
  Printf.printf "    uv run python/viz/plot_vol_surface.py\n";

  Printf.printf "\n✓ Analysis complete for %s\n" !ticker;
  Printf.printf "  Results saved to: %s/\n" output_dir
