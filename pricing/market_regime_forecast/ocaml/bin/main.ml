(** Market Regime Forecast - CLI Entry Point *)

open Market_regime_forecast

type model_type = Basic | MsGarch | Bocpd | GaussianProcess

let usage = {|
Market Regime Forecast

Usage:
  market_regime_forecast <price_data.json> [options]

Options:
  --output <file>     Save forecast to JSON file
  --model <type>      Model type: 'basic', 'ms-garch', 'bocpd', or 'gp' (default: basic)
  --save-params       Save fitted GARCH/HMM params for quick inference
  --quiet             Suppress detailed output

Models:
  basic     Separate GARCH(1,1) for volatility + HMM for trend (default)
  ms-garch  Markov-Switching GARCH with regime-dependent parameters
  bocpd     Bayesian Online Changepoint Detection (Adams & MacKay 2007)
  gp        Gaussian Process regression with uncertainty quantification

Example:
  market_regime_forecast data/spy_prices.json --output output/forecast.json
  market_regime_forecast data/spy_prices.json --model ms-garch --output output/forecast.json
  market_regime_forecast data/spy_prices.json --model gp --output output/forecast.json
|}

(** Print MS-GARCH specific results *)
let print_ms_garch_result (result : Classifier.ms_garch_classification) =
  let state = result.current_state in
  let ms = result.ms_result in

  Printf.printf "\n";
  Printf.printf "MS-GARCH REGIME CLASSIFICATION\n";
  Printf.printf "==============================\n";
  Printf.printf "\n";

  Printf.printf "Current Regime:\n";
  Printf.printf "  Trend:       %s\n" (Types.string_of_trend_regime state.trend);
  Printf.printf "  Volatility:  %s\n" (Types.string_of_vol_regime state.volatility);
  Printf.printf "  Confidence:  %.1f%%\n" (state.confidence *. 100.0);
  Printf.printf "  Regime Age:  %d days\n" state.regime_age;
  Printf.printf "\n";

  Printf.printf "Actual Returns (sanity check):\n";
  Printf.printf "  1 Month:  %+.1f%%\n" (state.return_1m *. 100.0);
  Printf.printf "  3 Month:  %+.1f%%\n" (state.return_3m *. 100.0);
  Printf.printf "  6 Month:  %+.1f%%\n" (state.return_6m *. 100.0);
  Printf.printf "\n";

  Printf.printf "Vol Regime Probabilities:\n";
  let vol_probs = Ms_garch.current_regime_probs ms in
  Printf.printf "  Low Vol:    %.1f%%\n" (vol_probs.(0) *. 100.0);
  Printf.printf "  Normal Vol: %.1f%%\n" (vol_probs.(1) *. 100.0);
  Printf.printf "  High Vol:   %.1f%%\n" (vol_probs.(2) *. 100.0);
  Printf.printf "\n";

  Printf.printf "Next Period Vol Forecast:\n";
  let next_probs = result.next_vol_probs in
  Printf.printf "  Low Vol:    %.1f%%\n" (next_probs.(0) *. 100.0);
  Printf.printf "  Normal Vol: %.1f%%\n" (next_probs.(1) *. 100.0);
  Printf.printf "  High Vol:   %.1f%%\n" (next_probs.(2) *. 100.0);
  Printf.printf "\n";

  Printf.printf "MS-GARCH Parameters by Regime:\n";
  Printf.printf "  %-12s %10s %10s %10s %10s %10s\n"
    "Regime" "mu (ann)" "omega" "alpha" "beta" "uncond vol";
  Printf.printf "  %s\n" (String.make 62 '-');
  let params = ms.params in
  let regime_vols = Ms_garch.regime_volatilities ms in
  for k = 0 to params.n_regimes - 1 do
    let regime_name = match k with
      | 0 -> "Low Vol"
      | 1 -> "Normal Vol"
      | _ -> "High Vol"
    in
    Printf.printf "  %-12s %+9.1f%% %10.2e %10.4f %10.4f %9.1f%%\n"
      regime_name
      (params.mus.(k) *. 252.0 *. 100.0)
      params.omegas.(k)
      params.alphas.(k)
      params.betas.(k)
      (regime_vols.(k) *. 100.0)
  done;
  Printf.printf "\n";

  Printf.printf "Transition Matrix:\n";
  Printf.printf "  From\\To     Low Vol  Normal   High Vol\n";
  Printf.printf "  %s\n" (String.make 45 '-');
  let regime_names = [| "Low Vol"; "Normal"; "High Vol" |] in
  for i = 0 to params.n_regimes - 1 do
    Printf.printf "  %-10s" regime_names.(i);
    for j = 0 to params.n_regimes - 1 do
      Printf.printf " %8.1f%%" (params.transition_matrix.(i).(j) *. 100.0)
    done;
    Printf.printf "\n"
  done;
  Printf.printf "\n";

  Printf.printf "Model Fit:\n";
  Printf.printf "  Log-Likelihood: %.2f\n" ms.log_likelihood;
  Printf.printf "  AIC:            %.2f\n" ms.aic;
  Printf.printf "  BIC:            %.2f\n" ms.bic;
  Printf.printf "  Converged:      %s (%d iterations)\n"
    (if ms.converged then "Yes" else "No") ms.n_iterations;
  Printf.printf "\n";

  let suitability = Classifier.covered_call_suitability state in
  let strategy = Classifier.recommend_strategy state in
  Printf.printf "Income ETF Suitability: %d/5\n" suitability;
  Printf.printf "Recommendation: %s\n" strategy;
  Printf.printf "\n"

(** Save MS-GARCH result to JSON *)
let save_ms_garch_result filename (result : Classifier.ms_garch_classification) as_of_date =
  let state = result.current_state in
  let ms = result.ms_result in
  let params = ms.params in

  let trend_probs_assoc = [
    ("bull", `Float state.trend_probs.(0));
    ("bear", `Float state.trend_probs.(1));
    ("sideways", `Float state.trend_probs.(2));
  ] in

  let vol_probs = Ms_garch.current_regime_probs ms in
  let vol_probs_assoc = [
    ("low", `Float vol_probs.(0));
    ("normal", `Float vol_probs.(1));
    ("high", `Float vol_probs.(2));
  ] in

  let next_probs = result.next_vol_probs in
  let next_vol_assoc = [
    ("low", `Float next_probs.(0));
    ("normal", `Float next_probs.(1));
    ("high", `Float next_probs.(2));
  ] in

  let regime_vols = Ms_garch.regime_volatilities ms in
  let regime_params = `List (
    List.init params.n_regimes (fun k ->
      `Assoc [
        ("regime", `Int k);
        ("mu", `Float params.mus.(k));
        ("omega", `Float params.omegas.(k));
        ("alpha", `Float params.alphas.(k));
        ("beta", `Float params.betas.(k));
        ("unconditional_vol", `Float regime_vols.(k));
      ]
    )
  ) in

  let trans_matrix = `List (
    Array.to_list (Array.map (fun row ->
      `List (Array.to_list (Array.map (fun x -> `Float x) row))
    ) params.transition_matrix)
  ) in

  let suitability = Classifier.covered_call_suitability state in
  let strategy = Classifier.recommend_strategy state in

  let json = `Assoc [
    ("model", `String "ms-garch");
    ("as_of_date", `String as_of_date);
    ("current_regime", `Assoc [
      ("trend", `String (Types.string_of_trend_regime state.trend));
      ("volatility", `String (Types.string_of_vol_regime state.volatility));
      ("trend_probabilities", `Assoc trend_probs_assoc);
      ("vol_regime_probabilities", `Assoc vol_probs_assoc);
      ("vol_forecast", `Float state.vol_forecast);
      ("vol_percentile", `Float state.vol_percentile);
      ("confidence", `Float state.confidence);
      ("regime_age_days", `Int state.regime_age);
      ("actual_returns", `Assoc [
        ("return_1m", `Float state.return_1m);
        ("return_3m", `Float state.return_3m);
        ("return_6m", `Float state.return_6m);
      ]);
    ]);
    ("next_period", `Assoc [
      ("vol_regime_probabilities", `Assoc next_vol_assoc);
    ]);
    ("ms_garch_fit", `Assoc [
      ("n_regimes", `Int params.n_regimes);
      ("regime_params", regime_params);
      ("transition_matrix", trans_matrix);
      ("log_likelihood", `Float ms.log_likelihood);
      ("aic", `Float ms.aic);
      ("bic", `Float ms.bic);
      ("converged", `Bool ms.converged);
      ("n_iterations", `Int ms.n_iterations);
    ]);
    ("income_etf", `Assoc [
      ("covered_call_suitability", `Int suitability);
      ("recommendation", `String strategy);
    ]);
  ] in

  let oc = open_out filename in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc;
  Printf.printf "Saved MS-GARCH forecast to %s\n" filename

(** Print BOCPD results *)
let print_bocpd_result (result : Bocpd.bocpd_result) =
  Printf.printf "\n";
  Printf.printf "BOCPD REGIME CLASSIFICATION\n";
  Printf.printf "===========================\n";
  Printf.printf "(Bayesian Online Changepoint Detection)\n";
  Printf.printf "\n";

  Printf.printf "Current Regime:\n";
  Printf.printf "  Trend:       %s\n" (Types.string_of_trend_regime result.trend);
  Printf.printf "  Volatility:  %s\n" (Types.string_of_vol_regime result.volatility);
  Printf.printf "\n";

  Printf.printf "Run Length Analysis:\n";
  Printf.printf "  Current Run Length:   %d days\n" result.run_length;
  Printf.printf "  Expected Run Length:  %.1f days\n" result.expected_run_length;
  Printf.printf "  Regime Stability:     %.1f%%\n" (result.regime_stability *. 100.0);
  Printf.printf "  Changepoint Prob:     %.1f%% (probability regime just changed)\n"
    (result.changepoint_prob *. 100.0);
  Printf.printf "\n";

  Printf.printf "Current Regime Statistics:\n";
  Printf.printf "  Mean Return:    %+.2f%% (daily) / %+.1f%% (annualized)\n"
    (result.regime_mean *. 100.0) (result.regime_mean *. 252.0 *. 100.0);
  Printf.printf "  Volatility:     %.2f%% (daily) / %.1f%% (annualized)\n"
    (result.regime_vol *. 100.0) (result.regime_vol *. sqrt 252.0 *. 100.0);
  Printf.printf "\n";

  let n_changepoints = List.length result.detected_changepoints in
  Printf.printf "Detected Changepoints: %d\n" n_changepoints;
  if n_changepoints > 0 && n_changepoints <= 10 then begin
    Printf.printf "  At days: %s\n"
      (String.concat ", " (List.map string_of_int result.detected_changepoints))
  end;
  Printf.printf "\n";

  (* Compute suitability based on trend and vol *)
  let state = {
    Types.trend = result.trend;
    volatility = result.volatility;
    trend_probs = [| 0.0; 0.0; 0.0 |];
    vol_forecast = result.regime_vol *. sqrt 252.0;
    vol_percentile = 0.5;
    confidence = result.regime_stability;
    regime_age = result.run_length;
    return_1m = 0.0;
    return_3m = 0.0;
    return_6m = 0.0;
  } in
  let suitability = Classifier.covered_call_suitability state in
  let strategy = Classifier.recommend_strategy state in

  Printf.printf "Income ETF Suitability: %d/5\n" suitability;
  Printf.printf "Recommendation: %s\n" strategy;
  Printf.printf "\n"

(** Save BOCPD result to JSON *)
let save_bocpd_result filename (result : Bocpd.bocpd_result) as_of_date =
  let state = {
    Types.trend = result.trend;
    volatility = result.volatility;
    trend_probs = [| 0.0; 0.0; 0.0 |];
    vol_forecast = result.regime_vol *. sqrt 252.0;
    vol_percentile = 0.5;
    confidence = result.regime_stability;
    regime_age = result.run_length;
    return_1m = 0.0;
    return_3m = 0.0;
    return_6m = 0.0;
  } in
  let suitability = Classifier.covered_call_suitability state in
  let strategy = Classifier.recommend_strategy state in

  let json = `Assoc [
    ("model", `String "bocpd");
    ("as_of_date", `String as_of_date);
    ("current_regime", `Assoc [
      ("trend", `String (Types.string_of_trend_regime result.trend));
      ("volatility", `String (Types.string_of_vol_regime result.volatility));
      ("run_length", `Int result.run_length);
      ("expected_run_length", `Float result.expected_run_length);
      ("regime_stability", `Float result.regime_stability);
      ("changepoint_prob", `Float result.changepoint_prob);
      ("regime_mean_daily", `Float result.regime_mean);
      ("regime_vol_daily", `Float result.regime_vol);
      ("regime_mean_annual", `Float (result.regime_mean *. 252.0));
      ("regime_vol_annual", `Float (result.regime_vol *. sqrt 252.0));
    ]);
    ("changepoints", `List (List.map (fun x -> `Int x) result.detected_changepoints));
    ("income_etf", `Assoc [
      ("covered_call_suitability", `Int suitability);
      ("recommendation", `String strategy);
    ]);
  ] in

  let oc = open_out filename in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc;
  Printf.printf "Saved BOCPD forecast to %s\n" filename

(** Print GP results *)
let print_gp_result (result : Gp.gp_classification) =
  let gp = result.result in

  Printf.printf "\n";
  Printf.printf "GAUSSIAN PROCESS REGIME CLASSIFICATION\n";
  Printf.printf "======================================\n";
  Printf.printf "\n";

  Printf.printf "Current Regime:\n";
  Printf.printf "  Trend:       %s\n" (Types.string_of_trend_regime result.trend);
  Printf.printf "  Volatility:  %s\n" (Types.string_of_vol_regime result.volatility);
  Printf.printf "  Confidence:  %.1f%%\n" (result.regime_confidence *. 100.0);
  Printf.printf "\n";

  Printf.printf "GP Model:\n";
  Printf.printf "  Kernel:        %s\n" (Gp.string_of_kernel gp.params.kernel);
  Printf.printf "  Length Scale:  %.1f days\n" gp.params.length_scale;
  Printf.printf "  Signal Var:    %.2e\n" gp.params.signal_var;
  Printf.printf "  Noise Var:     %.2e\n" gp.params.noise_var;
  Printf.printf "  Log ML:        %.2f\n" gp.posterior.log_marginal_likelihood;
  Printf.printf "\n";

  Printf.printf "Current Estimate:\n";
  Printf.printf "  Trend (daily):     %+.4f%%\n" (gp.current_trend *. 100.0);
  Printf.printf "  Trend (annual):    %+.1f%%\n" (gp.current_trend *. 252.0 *. 100.0);
  Printf.printf "  Uncertainty (σ):   %.4f%% daily / %.1f%% annual\n"
    (gp.current_uncertainty *. 100.0) (gp.current_uncertainty *. sqrt 252.0 *. 100.0);
  Printf.printf "  Anomaly Score:     %.2f σ\n" gp.anomaly_score;
  Printf.printf "\n";

  Printf.printf "Forecast (%d days):\n" (Array.length gp.trend_forecast);
  Printf.printf "  Mean Return:   %+.1f%% (annualized)\n" (result.forecast_mean *. 100.0);
  Printf.printf "  Uncertainty:   %.1f%% (annualized)\n" (result.forecast_std *. 100.0);
  Printf.printf "\n";

  (* Compute suitability *)
  let state = {
    Types.trend = result.trend;
    volatility = result.volatility;
    trend_probs = [| 0.0; 0.0; 0.0 |];
    vol_forecast = gp.current_uncertainty *. sqrt 252.0;
    vol_percentile = 0.5;
    confidence = result.regime_confidence;
    regime_age = 0;
    return_1m = 0.0;
    return_3m = 0.0;
    return_6m = 0.0;
  } in
  let suitability = Classifier.covered_call_suitability state in
  let strategy = Classifier.recommend_strategy state in

  Printf.printf "Income ETF Suitability: %d/5\n" suitability;
  Printf.printf "Recommendation: %s\n" strategy;
  Printf.printf "\n"

(** Save GP result to JSON *)
let save_gp_result filename (result : Gp.gp_classification) as_of_date =
  let gp = result.result in

  let state = {
    Types.trend = result.trend;
    volatility = result.volatility;
    trend_probs = [| 0.0; 0.0; 0.0 |];
    vol_forecast = gp.current_uncertainty *. sqrt 252.0;
    vol_percentile = 0.5;
    confidence = result.regime_confidence;
    regime_age = 0;
    return_1m = 0.0;
    return_3m = 0.0;
    return_6m = 0.0;
  } in
  let suitability = Classifier.covered_call_suitability state in
  let strategy = Classifier.recommend_strategy state in

  let json = `Assoc [
    ("model", `String "gp");
    ("as_of_date", `String as_of_date);
    ("current_regime", `Assoc [
      ("trend", `String (Types.string_of_trend_regime result.trend));
      ("volatility", `String (Types.string_of_vol_regime result.volatility));
      ("confidence", `Float result.regime_confidence);
      ("current_trend_daily", `Float gp.current_trend);
      ("current_trend_annual", `Float (gp.current_trend *. 252.0));
      ("uncertainty_daily", `Float gp.current_uncertainty);
      ("uncertainty_annual", `Float (gp.current_uncertainty *. sqrt 252.0));
      ("anomaly_score", `Float gp.anomaly_score);
    ]);
    ("gp_params", `Assoc [
      ("kernel", `String (Gp.string_of_kernel gp.params.kernel));
      ("length_scale", `Float gp.params.length_scale);
      ("signal_var", `Float gp.params.signal_var);
      ("noise_var", `Float gp.params.noise_var);
      ("log_marginal_likelihood", `Float gp.posterior.log_marginal_likelihood);
    ]);
    ("forecast", `Assoc [
      ("horizon_days", `Int (Array.length gp.trend_forecast));
      ("mean_annual", `Float result.forecast_mean);
      ("std_annual", `Float result.forecast_std);
    ]);
    ("income_etf", `Assoc [
      ("covered_call_suitability", `Int suitability);
      ("recommendation", `String strategy);
    ]);
  ] in

  let oc = open_out filename in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc;
  Printf.printf "Saved GP forecast to %s\n" filename

let () =
  let args = Array.to_list Sys.argv |> List.tl in

  if List.length args = 0 || List.mem "--help" args || List.mem "-h" args then begin
    print_string usage;
    exit 0
  end;

  (* Parse arguments *)
  let input_file = ref "" in
  let output_file = ref "" in
  let model_type = ref Basic in
  let save_params = ref false in
  let quiet = ref false in

  let rec parse = function
    | [] -> ()
    | "--output" :: file :: rest ->
        output_file := file;
        parse rest
    | "--model" :: "basic" :: rest ->
        model_type := Basic;
        parse rest
    | "--model" :: "ms-garch" :: rest ->
        model_type := MsGarch;
        parse rest
    | "--model" :: "bocpd" :: rest ->
        model_type := Bocpd;
        parse rest
    | "--model" :: "gp" :: rest ->
        model_type := GaussianProcess;
        parse rest
    | "--model" :: m :: _ ->
        Printf.eprintf "Unknown model type: %s (use 'basic', 'ms-garch', 'bocpd', or 'gp')\n" m;
        exit 1
    | "--save-params" :: rest ->
        save_params := true;
        parse rest
    | "--quiet" :: rest ->
        quiet := true;
        parse rest
    | file :: rest when !input_file = "" ->
        input_file := file;
        parse rest
    | unknown :: _ ->
        Printf.eprintf "Unknown argument: %s\n" unknown;
        exit 1
  in
  parse args;

  if !input_file = "" then begin
    Printf.eprintf "Error: No input file specified\n";
    print_string usage;
    exit 1
  end;

  (* Load price data *)
  let price_data =
    try Io.load_price_data !input_file
    with e ->
      Printf.eprintf "Error loading price data: %s\n" (Printexc.to_string e);
      exit 1
  in

  let n = Array.length price_data.returns in
  let as_of_date = price_data.dates.(Array.length price_data.dates - 1) in

  Printf.printf "Loaded %d returns for %s\n" n price_data.ticker;
  Printf.printf "Model: %s\n" (match !model_type with
    | Basic -> "Basic (GARCH+HMM)"
    | MsGarch -> "MS-GARCH"
    | Bocpd -> "BOCPD (Bayesian Online Changepoint Detection)"
    | GaussianProcess -> "Gaussian Process");

  let config = Types.default_config in

  match !model_type with
  | Basic ->
      (* Run basic GARCH + HMM classification *)
      let forecast =
        try
          let result = Classifier.classify ~returns:price_data.returns ~config in
          { result with Types.as_of_date }
        with e ->
          Printf.eprintf "Error during classification: %s\n" (Printexc.to_string e);
          exit 1
      in

      if not !quiet then
        Io.print_forecast forecast;

      if !output_file <> "" then
        Io.save_forecast !output_file forecast;

      if !save_params then begin
        let base_dir = Filename.dirname !input_file in
        let garch_file = Filename.concat base_dir "garch_params.json" in
        let hmm_file = Filename.concat base_dir "hmm_params.json" in
        Io.save_garch_params garch_file forecast.garch_fit.params;
        Io.save_hmm_params hmm_file forecast.hmm_fit.params;
        Printf.printf "Saved parameters to %s and %s\n" garch_file hmm_file
      end

  | MsGarch ->
      (* Run MS-GARCH classification *)
      let result =
        try Classifier.classify_ms_garch ~returns:price_data.returns ~config
        with e ->
          Printf.eprintf "Error during MS-GARCH classification: %s\n" (Printexc.to_string e);
          exit 1
      in

      if not !quiet then
        print_ms_garch_result result;

      if !output_file <> "" then
        save_ms_garch_result !output_file result as_of_date

  | Bocpd ->
      (* Run BOCPD classification *)
      let bocpd_config = Bocpd.default_bocpd_config in
      let result =
        try Bocpd.analyze ~returns:price_data.returns ~config:bocpd_config
        with e ->
          Printf.eprintf "Error during BOCPD classification: %s\n" (Printexc.to_string e);
          exit 1
      in

      if not !quiet then
        print_bocpd_result result;

      if !output_file <> "" then
        save_bocpd_result !output_file result as_of_date

  | GaussianProcess ->
      (* Run GP classification *)
      let gp_config = Gp.default_gp_config in
      let result =
        try Gp.analyze ~returns:price_data.returns ~config:gp_config
        with e ->
          Printf.eprintf "Error during GP classification: %s\n" (Printexc.to_string e);
          exit 1
      in

      if not !quiet then
        print_gp_result result;

      if !output_file <> "" then
        save_gp_result !output_file result as_of_date
