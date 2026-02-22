(** I/O operations for systematic risk signals module. *)

open Types

(* JSON parsing helpers *)
let get_string json key =
  match json with
  | `Assoc lst -> (
      match List.assoc_opt key lst with
      | Some (`String s) -> s
      | _ -> "")
  | _ -> ""

let _get_float json key =
  match json with
  | `Assoc lst -> (
      match List.assoc_opt key lst with
      | Some (`Float f) -> f
      | Some (`Int i) -> float_of_int i
      | _ -> 0.0)
  | _ -> 0.0

let get_list json key =
  match json with
  | `Assoc lst -> (
      match List.assoc_opt key lst with
      | Some (`List l) -> l
      | _ -> [])
  | _ -> []

let read_returns_data (filepath : string) : asset_returns array =
  let ic = open_in filepath in
  let content = really_input_string ic (in_channel_length ic) in
  close_in ic;

  let json = Yojson.Basic.from_string content in

  match json with
  | `Assoc _ ->
      let assets = get_list json "assets" in
      Array.of_list (List.map (fun asset ->
        let ticker = get_string asset "ticker" in
        let returns_list = get_list asset "returns" in
        let dates_list = get_list asset "dates" in

        let returns = Array.of_list (List.map (function
          | `Float f -> f
          | `Int i -> float_of_int i
          | _ -> 0.0
        ) returns_list) in

        let dates = Array.of_list (List.map (function
          | `String s -> s
          | _ -> ""
        ) dates_list) in

        { ticker; returns; dates }
      ) assets)
  | _ -> [||]

let write_result_json (filepath : string) (result : analysis_result) : unit =
  let signals_to_json s =
    `Assoc [
      ("var_explained_first", `Float s.var_explained_first);
      ("var_explained_2_to_5", `Float s.var_explained_2_to_5);
      ("mean_eigenvector_centrality", `Float s.mean_eigenvector_centrality);
      ("std_eigenvector_centrality", `Float s.std_eigenvector_centrality);
      ("timestamp", `String s.timestamp);
    ]
  in

  let regime_to_json r =
    `String (regime_to_string r)
  in

  let json = `Assoc [
    ("timestamp", `String result.timestamp);
    ("current_regime", regime_to_json result.current_regime);
    ("transition_probability", `Float result.transition_prob);
    ("latest_signals", signals_to_json result.latest_signals);
    ("signal_history", `List (Array.to_list (Array.map signals_to_json result.signal_history)));
    ("mst_total_weight", `Float result.mst.total_weight);
    ("mst_n_edges", `Int (List.length result.mst.edges));
    ("mean_centrality", `Float result.centralities.mean_centrality);
    ("std_centrality", `Float result.centralities.std_centrality);
    ("centralities", `List (Array.to_list (Array.map (fun c -> `Float c) result.centralities.centralities)));
    ("tickers", `List (List.map (fun t -> `String t) result.config.tickers));
  ] in

  let oc = open_out filepath in
  Yojson.Basic.pretty_to_channel oc json;
  close_out oc

(* ANSI color codes *)
let reset = "\027[0m"
let bold = "\027[1m"
let red = "\027[31m"
let green = "\027[32m"
let yellow = "\027[33m"
let blue = "\027[34m"
let magenta = "\027[35m"
let cyan = "\027[36m"

let signal_bar value max_val width =
  let ratio = min 1.0 (value /. max_val) in
  let filled = int_of_float (ratio *. float_of_int width) in
  let empty = width - filled in
  String.make filled '=' ^ String.make empty ' '

let print_dashboard (signals : risk_signals) (regime : risk_regime) (trans_prob : float) : unit =
  let regime_color = regime_to_color regime in

  Printf.printf "\n%s%s══════════════════════════════════════════════════════════════%s\n" bold blue reset;
  Printf.printf "%s%s          SYSTEMATIC RISK EARLY-WARNING SIGNALS%s\n" bold blue reset;
  Printf.printf "%s%s══════════════════════════════════════════════════════════════%s\n\n" bold blue reset;

  Printf.printf "%sCURRENT REGIME:%s %s%s%s\n\n" bold reset regime_color (regime_to_string regime) reset;

  Printf.printf "%sRISK SIGNALS%s                                          Value\n" bold reset;
  Printf.printf "──────────────────────────────────────────────────────────────\n";

  (* Signal 1: Variance explained by λ₁ *)
  let v1 = signals.var_explained_first in
  let c1 = if v1 > 0.50 then red else if v1 > 0.35 then yellow else green in
  Printf.printf "Var. expl. by λ₁       [%s%s%s]  %s%.1f%%%s\n"
    c1 (signal_bar v1 0.7 20) reset c1 (v1 *. 100.0) reset;

  (* Signal 2: Variance explained by λ₂₋₅ *)
  let v2 = signals.var_explained_2_to_5 in
  let c2 = if v2 > 0.20 then red else if v2 > 0.12 then yellow else green in
  Printf.printf "Var. expl. by λ₂₋₅     [%s%s%s]  %s%.1f%%%s\n"
    c2 (signal_bar v2 0.35 20) reset c2 (v2 *. 100.0) reset;

  (* Signal 3: Mean eigenvector centrality *)
  let v3 = signals.mean_eigenvector_centrality in
  let c3 = if v3 > 0.20 then red else if v3 > 0.12 then yellow else green in
  Printf.printf "Mean EV centrality     [%s%s%s]  %s%.3f%s\n"
    c3 (signal_bar v3 0.3 20) reset c3 v3 reset;

  (* Signal 4: Std dev of eigenvector centrality *)
  let v4 = signals.std_eigenvector_centrality in
  let c4 = if v4 > 0.10 then red else if v4 > 0.06 then yellow else green in
  Printf.printf "Std EV centrality      [%s%s%s]  %s%.3f%s\n"
    c4 (signal_bar v4 0.2 20) reset c4 v4 reset;

  Printf.printf "\n%sTRANSITION PROBABILITY%s\n" bold reset;
  Printf.printf "──────────────────────────────────────────────────────────────\n";

  let prob_color = if trans_prob > 0.7 then red
                   else if trans_prob > 0.5 then yellow
                   else green in
  Printf.printf "P(High Risk | Signals) [%s%s%s]  %s%.1f%%%s\n"
    prob_color (signal_bar trans_prob 1.0 20) reset
    prob_color (trans_prob *. 100.0) reset;

  Printf.printf "\n"

let print_analysis (result : analysis_result) : unit =
  print_dashboard result.latest_signals result.current_regime result.transition_prob;

  Printf.printf "%sMST STATISTICS%s\n" bold reset;
  Printf.printf "──────────────────────────────────────────────────────────────\n";
  Printf.printf "Total MST weight:      %.4f\n" result.mst.total_weight;
  Printf.printf "Number of edges:       %d\n" (List.length result.mst.edges);
  Printf.printf "Number of vertices:    %d\n" result.mst.n_vertices;

  Printf.printf "\n%sTOP CENTRAL ASSETS%s\n" bold reset;
  Printf.printf "──────────────────────────────────────────────────────────────\n";

  (* Sort assets by centrality *)
  let n = Array.length result.centralities.centralities in
  let indexed = Array.mapi (fun i c ->
    let ticker = if i < List.length result.config.tickers
                 then List.nth result.config.tickers i
                 else Printf.sprintf "Asset_%d" i in
    (ticker, c)
  ) result.centralities.centralities in

  Array.sort (fun (_, c1) (_, c2) -> compare c2 c1) indexed;

  let top_n = min 5 n in
  for i = 0 to top_n - 1 do
    let (ticker, centrality) = indexed.(i) in
    Printf.printf "%d. %-10s  %.4f\n" (i + 1) ticker centrality
  done;

  Printf.printf "\n%sINTERPRETATION%s\n" bold reset;
  Printf.printf "──────────────────────────────────────────────────────────────\n";

  (match result.current_regime with
  | LowRisk ->
      Printf.printf "%s• Market showing low systematic risk%s\n" green reset;
      Printf.printf "%s• Correlations are dispersed - idiosyncratic factors dominate%s\n" green reset;
      Printf.printf "%s• MST structure is stretched with peripheral nodes%s\n" green reset
  | NormalRisk ->
      Printf.printf "• Market in normal risk regime\n";
      Printf.printf "• Standard correlation structure observed\n";
      Printf.printf "• No immediate action required\n"
  | ElevatedRisk ->
      Printf.printf "%s• Elevated systematic risk detected%s\n" yellow reset;
      Printf.printf "%s• Correlations beginning to cluster%s\n" yellow reset;
      Printf.printf "%s• Consider reviewing portfolio exposures%s\n" yellow reset
  | HighRisk ->
      Printf.printf "%s• HIGH SYSTEMATIC RISK%s\n" red reset;
      Printf.printf "%s• Strong correlation clustering observed%s\n" red reset;
      Printf.printf "%s• Consider defensive positioning%s\n" red reset
  | CrisisRisk ->
      Printf.printf "%s• CRISIS-LEVEL SYSTEMATIC RISK%s\n" magenta reset;
      Printf.printf "%s• Extreme correlation compression - all assets moving together%s\n" magenta reset;
      Printf.printf "%s• MST highly concentrated - few central nodes explain market%s\n" magenta reset);

  Printf.printf "\n%sTimestamp: %s%s\n\n" cyan result.timestamp reset
