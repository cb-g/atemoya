(** IO module for Market Regime Forecast *)

open Types

(** Load price data from JSON file *)
let load_price_data filepath =
  let json = Yojson.Basic.from_file filepath in
  let open Yojson.Basic.Util in

  let ticker = json |> member "ticker" |> to_string in
  let dates = json |> member "dates" |> to_list |> List.map to_string |> Array.of_list in
  let prices = json |> member "prices" |> to_list |> List.map (fun p ->
    match p with
    | `Int i -> float_of_int i
    | `Float f -> f
    | _ -> to_float p
  ) |> Array.of_list in

  (* Calculate log returns *)
  let n = Array.length prices in
  let returns = Array.make (n - 1) 0.0 in
  for i = 1 to n - 1 do
    returns.(i - 1) <- log (prices.(i) /. prices.(i - 1))
  done;

  (* Shift dates to align with returns *)
  let return_dates = Array.sub dates 1 (n - 1) in

  { ticker; dates = return_dates; prices; returns }

(** Print regime state *)
let print_regime_state state =
  Printf.printf "\n";
  Printf.printf "CURRENT REGIME\n";
  Printf.printf "──────────────────────────────────────────────────────────────\n";
  Printf.printf "  Trend:           %s\n" (string_of_trend_regime state.trend);
  Printf.printf "  Volatility:      %s\n" (string_of_vol_regime state.volatility);
  Printf.printf "\n";
  Printf.printf "  Trend Probabilities:\n";
  Printf.printf "    Bull:      %5.1f%%\n" (state.trend_probs.(0) *. 100.0);
  Printf.printf "    Bear:      %5.1f%%\n" (state.trend_probs.(1) *. 100.0);
  Printf.printf "    Sideways:  %5.1f%%\n" (state.trend_probs.(2) *. 100.0);
  Printf.printf "\n";
  Printf.printf "  Vol Forecast:    %.1f%% (annualized)\n" (state.vol_forecast *. 100.0);
  Printf.printf "  Vol Percentile:  %.0f%% vs 5Y history\n" (state.vol_percentile *. 100.0);
  Printf.printf "  Confidence:      %.0f%%\n" (state.confidence *. 100.0);
  Printf.printf "  Regime Age:      %d days\n" state.regime_age;
  Printf.printf "\n";
  Printf.printf "  Actual Returns (period):\n";
  Printf.printf "    1-Month:  %+.1f%%\n" (state.return_1m *. 100.0);
  Printf.printf "    3-Month:  %+.1f%%\n" (state.return_3m *. 100.0);
  Printf.printf "    6-Month:  %+.1f%%\n" (state.return_6m *. 100.0)

(** Print GARCH fit results *)
let print_garch_fit (result : Types.garch_result) =
  Printf.printf "\n";
  Printf.printf "GARCH(1,1) FIT\n";
  Printf.printf "──────────────────────────────────────────────────────────────\n";
  Printf.printf "  Parameters:\n";
  Printf.printf "    ω (omega):  %.2e\n" result.params.omega;
  Printf.printf "    α (alpha):  %.4f  (shock reaction)\n" result.params.alpha;
  Printf.printf "    β (beta):   %.4f  (persistence)\n" result.params.beta;
  Printf.printf "\n";
  Printf.printf "  Persistence (α+β):    %.4f\n" result.persistence;
  Printf.printf "  Unconditional Vol:    %.1f%%\n" (result.unconditional_vol *. 100.0);
  Printf.printf "  Log-Likelihood:       %.2f\n" result.log_likelihood;
  Printf.printf "  AIC:                  %.2f\n" result.aic;
  Printf.printf "  BIC:                  %.2f\n" result.bic

(** Print HMM fit results *)
let print_hmm_fit (result : Types.hmm_result) =
  let params = result.params in
  Printf.printf "\n";
  Printf.printf "HMM FIT (3-state)\n";
  Printf.printf "──────────────────────────────────────────────────────────────\n";
  Printf.printf "  Converged:      %s (%d iterations)\n"
    (if result.converged then "Yes" else "No") result.n_iterations;
  Printf.printf "  Log-Likelihood: %.2f\n" result.log_likelihood;
  Printf.printf "\n";
  Printf.printf "  State Characteristics (annualized):\n";
  Printf.printf "    Bull:     μ = %+.1f%%, σ = %.1f%%\n"
    (params.emission_means.(0) *. 252.0 *. 100.0)
    (sqrt params.emission_vars.(0) *. sqrt 252.0 *. 100.0);
  Printf.printf "    Bear:     μ = %+.1f%%, σ = %.1f%%\n"
    (params.emission_means.(1) *. 252.0 *. 100.0)
    (sqrt params.emission_vars.(1) *. sqrt 252.0 *. 100.0);
  Printf.printf "    Sideways: μ = %+.1f%%, σ = %.1f%%\n"
    (params.emission_means.(2) *. 252.0 *. 100.0)
    (sqrt params.emission_vars.(2) *. sqrt 252.0 *. 100.0);
  Printf.printf "\n";
  Printf.printf "  Transition Matrix (daily):\n";
  Printf.printf "              To Bull   To Bear   To Sideways\n";
  Printf.printf "    Bull:     %6.1f%%   %6.1f%%   %6.1f%%\n"
    (params.transition_matrix.(0).(0) *. 100.0)
    (params.transition_matrix.(0).(1) *. 100.0)
    (params.transition_matrix.(0).(2) *. 100.0);
  Printf.printf "    Bear:     %6.1f%%   %6.1f%%   %6.1f%%\n"
    (params.transition_matrix.(1).(0) *. 100.0)
    (params.transition_matrix.(1).(1) *. 100.0)
    (params.transition_matrix.(1).(2) *. 100.0);
  Printf.printf "    Sideways: %6.1f%%   %6.1f%%   %6.1f%%\n"
    (params.transition_matrix.(2).(0) *. 100.0)
    (params.transition_matrix.(2).(1) *. 100.0)
    (params.transition_matrix.(2).(2) *. 100.0)

(** Print full forecast *)
let print_forecast (forecast : Types.regime_forecast) =
  Printf.printf "\n";
  Printf.printf "════════════════════════════════════════════════════════════════\n";
  Printf.printf "MARKET REGIME FORECAST\n";
  Printf.printf "════════════════════════════════════════════════════════════════\n";
  Printf.printf "  As of: %s\n" forecast.as_of_date;

  print_regime_state forecast.current_state;
  print_garch_fit forecast.garch_fit;
  print_hmm_fit forecast.hmm_fit;

  Printf.printf "\n";
  Printf.printf "NEXT PERIOD FORECAST\n";
  Printf.printf "──────────────────────────────────────────────────────────────\n";
  Printf.printf "  Trend Probabilities:\n";
  Printf.printf "    Bull:      %5.1f%%\n" (forecast.next_trend_probs.(0) *. 100.0);
  Printf.printf "    Bear:      %5.1f%%\n" (forecast.next_trend_probs.(1) *. 100.0);
  Printf.printf "    Sideways:  %5.1f%%\n" (forecast.next_trend_probs.(2) *. 100.0);

  Printf.printf "\n";
  Printf.printf "INCOME ETF RECOMMENDATION\n";
  Printf.printf "──────────────────────────────────────────────────────────────\n";
  let suitability = Classifier.covered_call_suitability forecast.current_state in
  Printf.printf "  Covered Call Suitability: %d/5\n" suitability;
  Printf.printf "  %s\n" (Classifier.recommend_strategy forecast.current_state);

  Printf.printf "\n";
  Printf.printf "════════════════════════════════════════════════════════════════\n"

(** Save forecast to JSON *)
let save_forecast filepath (forecast : Types.regime_forecast) =
  let state = forecast.current_state in
  let garch = forecast.garch_fit in
  let hmm = forecast.hmm_fit in

  let json = `Assoc [
    ("as_of_date", `String forecast.as_of_date);

    ("current_regime", `Assoc [
      ("trend", `String (string_of_trend_regime state.trend));
      ("volatility", `String (string_of_vol_regime state.volatility));
      ("trend_probabilities", `Assoc [
        ("bull", `Float state.trend_probs.(0));
        ("bear", `Float state.trend_probs.(1));
        ("sideways", `Float state.trend_probs.(2));
      ]);
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
      ("trend_probabilities", `Assoc [
        ("bull", `Float forecast.next_trend_probs.(0));
        ("bear", `Float forecast.next_trend_probs.(1));
        ("sideways", `Float forecast.next_trend_probs.(2));
      ]);
    ]);

    ("garch_fit", `Assoc [
      ("omega", `Float garch.params.omega);
      ("alpha", `Float garch.params.alpha);
      ("beta", `Float garch.params.beta);
      ("persistence", `Float garch.persistence);
      ("unconditional_vol", `Float garch.unconditional_vol);
      ("log_likelihood", `Float garch.log_likelihood);
      ("aic", `Float garch.aic);
      ("bic", `Float garch.bic);
    ]);

    ("hmm_fit", `Assoc [
      ("converged", `Bool hmm.converged);
      ("n_iterations", `Int hmm.n_iterations);
      ("log_likelihood", `Float hmm.log_likelihood);
      ("emission_means", `List (Array.to_list (Array.map (fun x -> `Float x) hmm.params.emission_means)));
      ("emission_vars", `List (Array.to_list (Array.map (fun x -> `Float x) hmm.params.emission_vars)));
      ("transition_matrix", `List (Array.to_list (Array.map (fun row ->
        `List (Array.to_list (Array.map (fun x -> `Float x) row))
      ) hmm.params.transition_matrix)));
    ]);

    ("income_etf", `Assoc [
      ("covered_call_suitability", `Int (Classifier.covered_call_suitability state));
      ("recommendation", `String (Classifier.recommend_strategy state));
    ]);
  ] in

  let oc = open_out filepath in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc;
  Printf.printf "Saved forecast to %s\n" filepath

(** Save GARCH parameters for quick inference *)
let save_garch_params filepath params =
  let json = `Assoc [
    ("omega", `Float params.omega);
    ("alpha", `Float params.alpha);
    ("beta", `Float params.beta);
  ] in
  let oc = open_out filepath in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc

(** Load GARCH parameters *)
let load_garch_params filepath =
  let json = Yojson.Basic.from_file filepath in
  let open Yojson.Basic.Util in
  {
    omega = json |> member "omega" |> to_float;
    alpha = json |> member "alpha" |> to_float;
    beta = json |> member "beta" |> to_float;
  }

(** Save HMM parameters for quick inference *)
let save_hmm_params filepath params =
  let json = `Assoc [
    ("n_states", `Int params.n_states);
    ("emission_means", `List (Array.to_list (Array.map (fun x -> `Float x) params.emission_means)));
    ("emission_vars", `List (Array.to_list (Array.map (fun x -> `Float x) params.emission_vars)));
    ("initial_probs", `List (Array.to_list (Array.map (fun x -> `Float x) params.initial_probs)));
    ("transition_matrix", `List (Array.to_list (Array.map (fun row ->
      `List (Array.to_list (Array.map (fun x -> `Float x) row))
    ) params.transition_matrix)));
  ] in
  let oc = open_out filepath in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc

(** Load HMM parameters *)
let load_hmm_params filepath =
  let json = Yojson.Basic.from_file filepath in
  let open Yojson.Basic.Util in

  let n_states = json |> member "n_states" |> to_int in
  let emission_means = json |> member "emission_means" |> to_list
    |> List.map to_float |> Array.of_list in
  let emission_vars = json |> member "emission_vars" |> to_list
    |> List.map to_float |> Array.of_list in
  let initial_probs = json |> member "initial_probs" |> to_list
    |> List.map to_float |> Array.of_list in
  let transition_matrix = json |> member "transition_matrix" |> to_list
    |> List.map (fun row -> row |> to_list |> List.map to_float |> Array.of_list)
    |> Array.of_list in

  { n_states; transition_matrix; emission_means; emission_vars; initial_probs }
