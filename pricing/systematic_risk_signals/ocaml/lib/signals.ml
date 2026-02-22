(** Early-warning risk signals computation. *)

open Types

let compute_signals (returns : asset_returns array) (timestamp : string) : risk_signals =
  (* Step 1: Compute covariance matrix *)
  let cov_mat = Covariance.compute_covariance returns in

  (* Step 2: Eigenvalue decomposition for signals 1 & 2 *)
  let eigen = Covariance.eigen_decompose cov_mat in
  let var_explained_first = Covariance.var_explained_first eigen in
  let var_explained_2_to_5 = Covariance.var_explained_2_to_5 eigen in

  (* Step 3: Convert to correlation, then distance *)
  let corr = Covariance.to_correlation cov_mat in
  let dist = Covariance.correlation_to_distance corr in

  (* Step 4: Build MST and compute eigenvector centrality *)
  let (_mst, centrality) = Graph.compute_graph_metrics dist in

  {
    var_explained_first;
    var_explained_2_to_5;
    mean_eigenvector_centrality = centrality.mean_centrality;
    std_eigenvector_centrality = centrality.std_centrality;
    timestamp;
  }

(** Classify regime based on signal thresholds.
    Thresholds derived from paper's empirical analysis. *)
let classify_regime (signals : risk_signals) : risk_regime =
  (* The paper shows:
     - During crises, variance explained by λ₁ increases significantly
     - Mean centrality increases during high systematic risk
     - Combined scoring approach *)

  let var1_score =
    if signals.var_explained_first > 0.60 then 4
    else if signals.var_explained_first > 0.50 then 3
    else if signals.var_explained_first > 0.40 then 2
    else if signals.var_explained_first > 0.30 then 1
    else 0
  in

  let var25_score =
    if signals.var_explained_2_to_5 > 0.25 then 4
    else if signals.var_explained_2_to_5 > 0.20 then 3
    else if signals.var_explained_2_to_5 > 0.15 then 2
    else if signals.var_explained_2_to_5 > 0.10 then 1
    else 0
  in

  let centrality_score =
    if signals.mean_eigenvector_centrality > 0.25 then 4
    else if signals.mean_eigenvector_centrality > 0.20 then 3
    else if signals.mean_eigenvector_centrality > 0.15 then 2
    else if signals.mean_eigenvector_centrality > 0.10 then 1
    else 0
  in

  let std_score =
    if signals.std_eigenvector_centrality > 0.15 then 4
    else if signals.std_eigenvector_centrality > 0.10 then 3
    else if signals.std_eigenvector_centrality > 0.07 then 2
    else if signals.std_eigenvector_centrality > 0.04 then 1
    else 0
  in

  let total_score = var1_score + var25_score + centrality_score + std_score in

  if total_score >= 12 then CrisisRisk
  else if total_score >= 9 then HighRisk
  else if total_score >= 6 then ElevatedRisk
  else if total_score >= 3 then NormalRisk
  else LowRisk

(** Estimate transition probability using logistic-like function.
    Higher signals -> higher probability of transitioning to high risk. *)
let transition_probability (signal_history : risk_signals array) : float =
  if Array.length signal_history = 0 then 0.5
  else
    let n = Array.length signal_history in
    let recent = signal_history.(n - 1) in

    (* Normalize signals to [0, 1] range approximately *)
    let x1 = min 1.0 (recent.var_explained_first /. 0.7) in
    let x2 = min 1.0 (recent.var_explained_2_to_5 /. 0.35) in
    let x3 = min 1.0 (recent.mean_eigenvector_centrality /. 0.3) in
    let x4 = min 1.0 (recent.std_eigenvector_centrality /. 0.2) in

    (* Simple logistic combination *)
    let z = -2.0 +. 2.0 *. x1 +. 1.5 *. x2 +. 2.5 *. x3 +. 1.5 *. x4 in
    1.0 /. (1.0 +. exp (-.z))

(** Extract returns for a rolling window *)
let extract_window_returns (returns : asset_returns array) (start_idx : int) (window_size : int) : asset_returns array =
  Array.map (fun r ->
    let n = Array.length r.returns in
    let end_idx = min n (start_idx + window_size) in
    let actual_start = max 0 start_idx in
    let len = end_idx - actual_start in
    {
      ticker = r.ticker;
      returns = Array.sub r.returns actual_start len;
      dates = Array.sub r.dates actual_start len;
    }
  ) returns

let compute_signal_series (returns : asset_returns array) (window_size : int) (dates : string array) : signal_series =
  let n_returns = Array.length returns.(0).returns in
  let n_signals = max 1 (n_returns - window_size + 1) in

  let signals = Array.init n_signals (fun i ->
    let window_returns = extract_window_returns returns i window_size in
    let timestamp = if i + window_size - 1 < Array.length dates
                    then dates.(i + window_size - 1)
                    else string_of_int i in
    compute_signals window_returns timestamp
  ) in

  let regime_history = Array.map classify_regime signals in
  let current_regime = if n_signals > 0 then regime_history.(n_signals - 1) else NormalRisk in
  let transition_probability = transition_probability signals in

  { signals; regime_history; current_regime; transition_probability }

let full_analysis (config : config) (returns : asset_returns array) : analysis_result =
  let dates = returns.(0).dates in
  let signal_series = compute_signal_series returns config.rolling_window dates in

  let n = Array.length signal_series.signals in
  let latest_signals = if n > 0 then signal_series.signals.(n - 1)
                       else {
                         var_explained_first = 0.0;
                         var_explained_2_to_5 = 0.0;
                         mean_eigenvector_centrality = 0.0;
                         std_eigenvector_centrality = 0.0;
                         timestamp = "";
                       } in

  (* Compute MST for visualization *)
  let cov_mat = Covariance.compute_covariance returns in
  let corr = Covariance.to_correlation cov_mat in
  let dist = Covariance.correlation_to_distance corr in
  let (mst, centralities) = Graph.compute_graph_metrics dist in

  let timestamp =
    let t = Unix.localtime (Unix.time ()) in
    Printf.sprintf "%04d-%02d-%02d"
      (t.Unix.tm_year + 1900) (t.Unix.tm_mon + 1) t.Unix.tm_mday
  in

  {
    config;
    latest_signals;
    signal_history = signal_series.signals;
    current_regime = signal_series.current_regime;
    transition_prob = signal_series.transition_probability;
    mst;
    centralities;
    timestamp;
  }
