(* Unit Tests for Systematic Risk Signals *)

open Systematic_risk_signals

(* Helper: create mock return data *)
let make_returns ticker returns =
  { Types.ticker; returns = Array.of_list returns; dates = [||] }

(* Test covariance matrix computation *)
let test_covariance_identity () =
  (* Two perfectly uncorrelated assets should have ~0 covariance *)
  let returns1 = [| 0.01; -0.02; 0.03; -0.01; 0.02 |] in
  let returns2 = [| 0.02; 0.01; -0.01; 0.03; -0.02 |] in
  let assets = [|
    { Types.ticker = "A"; returns = returns1; dates = [||] };
    { Types.ticker = "B"; returns = returns2; dates = [||] };
  |] in
  let cov = Covariance.compute_covariance assets in
  (* Covariance matrix should be 2x2 *)
  Alcotest.(check int) "cov matrix rows" 2 (Array.length cov.matrix);
  Alcotest.(check int) "cov matrix cols" 2 (Array.length cov.matrix.(0));
  (* Diagonal elements should be positive (variances) *)
  Alcotest.(check bool) "var A > 0" true (cov.matrix.(0).(0) > 0.0);
  Alcotest.(check bool) "var B > 0" true (cov.matrix.(1).(1) > 0.0)

let test_covariance_symmetric () =
  (* Covariance matrix should be symmetric *)
  let assets = [|
    make_returns "A" [0.01; 0.02; -0.01; 0.03; -0.02];
    make_returns "B" [0.02; -0.01; 0.01; -0.02; 0.03];
    make_returns "C" [-0.01; 0.03; 0.02; -0.01; 0.01];
  |] in
  let cov = Covariance.compute_covariance assets in
  for i = 0 to 2 do
    for j = 0 to 2 do
      Alcotest.(check (float 0.000001))
        (Printf.sprintf "cov[%d][%d] = cov[%d][%d]" i j j i)
        cov.matrix.(i).(j) cov.matrix.(j).(i)
    done
  done

let test_correlation_bounds () =
  (* Correlation should be in [-1, 1] *)
  let assets = [|
    make_returns "A" [0.01; 0.02; -0.01; 0.03; -0.02; 0.01; -0.01];
    make_returns "B" [0.02; -0.01; 0.01; -0.02; 0.03; -0.01; 0.02];
    make_returns "C" [-0.01; 0.03; 0.02; -0.01; 0.01; 0.02; -0.02];
  |] in
  let cov = Covariance.compute_covariance assets in
  let corr = Covariance.to_correlation cov in
  for i = 0 to 2 do
    for j = 0 to 2 do
      if i = j then
        Alcotest.(check (float 0.0001)) "diagonal = 1" 1.0 corr.(i).(j)
      else begin
        Alcotest.(check bool) "corr >= -1" true (corr.(i).(j) >= -1.0);
        Alcotest.(check bool) "corr <= 1" true (corr.(i).(j) <= 1.0)
      end
    done
  done

(* Test eigenvalue decomposition *)
let test_eigenvalues_positive () =
  (* Eigenvalues of covariance matrix should be non-negative *)
  let assets = [|
    make_returns "A" [0.01; 0.02; -0.01; 0.03; -0.02; 0.01; -0.01; 0.02];
    make_returns "B" [0.02; -0.01; 0.01; -0.02; 0.03; -0.01; 0.02; -0.01];
    make_returns "C" [-0.01; 0.03; 0.02; -0.01; 0.01; 0.02; -0.02; 0.01];
  |] in
  let cov = Covariance.compute_covariance assets in
  let eigen = Covariance.eigen_decompose cov in
  Array.iter (fun ev ->
    Alcotest.(check bool) "eigenvalue >= 0" true (ev >= -0.0001)  (* allow small numerical error *)
  ) eigen.eigenvalues

let test_eigenvalues_sorted () =
  (* Eigenvalues should be sorted descending *)
  let assets = [|
    make_returns "A" [0.01; 0.02; -0.01; 0.03; -0.02; 0.01; -0.01; 0.02];
    make_returns "B" [0.02; -0.01; 0.01; -0.02; 0.03; -0.01; 0.02; -0.01];
    make_returns "C" [-0.01; 0.03; 0.02; -0.01; 0.01; 0.02; -0.02; 0.01];
  |] in
  let cov = Covariance.compute_covariance assets in
  let eigen = Covariance.eigen_decompose cov in
  for i = 0 to Array.length eigen.eigenvalues - 2 do
    Alcotest.(check bool)
      (Printf.sprintf "eigenvalue[%d] >= eigenvalue[%d]" i (i+1))
      true (eigen.eigenvalues.(i) >= eigen.eigenvalues.(i+1))
  done

let test_var_explained_sum () =
  (* Sum of variance explained should be ~1 *)
  let assets = [|
    make_returns "A" [0.01; 0.02; -0.01; 0.03; -0.02; 0.01; -0.01; 0.02];
    make_returns "B" [0.02; -0.01; 0.01; -0.02; 0.03; -0.01; 0.02; -0.01];
    make_returns "C" [-0.01; 0.03; 0.02; -0.01; 0.01; 0.02; -0.02; 0.01];
    make_returns "D" [0.03; -0.02; 0.01; 0.01; -0.01; 0.02; 0.01; -0.03];
    make_returns "E" [-0.02; 0.01; 0.02; -0.03; 0.02; -0.01; 0.03; 0.01];
  |] in
  let cov = Covariance.compute_covariance assets in
  let eigen = Covariance.eigen_decompose cov in
  let var1 = Covariance.var_explained_first eigen in
  let var2_5 = Covariance.var_explained_2_to_5 eigen in
  (* var1 + var2_5 should be <= 1 (could be less if more than 5 assets) *)
  Alcotest.(check bool) "var explained <= 1" true (var1 +. var2_5 <= 1.0 +. 0.0001);
  Alcotest.(check bool) "var1 > 0" true (var1 > 0.0);
  Alcotest.(check bool) "var1 <= 1" true (var1 <= 1.0)

(* Test distance metric *)
let test_correlation_to_distance () =
  (* d = sqrt(1 - rho^2), so rho=0 -> d=1, rho=1 -> d=0 *)
  let corr = [|
    [| 1.0; 0.0; 0.5 |];
    [| 0.0; 1.0; -0.5 |];
    [| 0.5; -0.5; 1.0 |];
  |] in
  let dist = Covariance.correlation_to_distance corr in
  (* Diagonal should be 0 *)
  Alcotest.(check (float 0.0001)) "dist[0][0] = 0" 0.0 dist.(0).(0);
  (* Uncorrelated: d = sqrt(1 - 0) = 1 *)
  Alcotest.(check (float 0.0001)) "dist[0][1] = 1" 1.0 dist.(0).(1);
  (* rho = 0.5: d = sqrt(1 - 0.25) = sqrt(0.75) *)
  let expected = sqrt 0.75 in
  Alcotest.(check (float 0.0001)) "dist[0][2]" expected dist.(0).(2)

(* Test MST construction *)
let test_mst_edges () =
  (* MST should have n-1 edges for n vertices *)
  let n = 5 in
  let edges = [
    { Types.from_idx = 0; to_idx = 1; weight = 1.0 };
    { Types.from_idx = 0; to_idx = 2; weight = 2.0 };
    { Types.from_idx = 1; to_idx = 2; weight = 1.5 };
    { Types.from_idx = 1; to_idx = 3; weight = 2.5 };
    { Types.from_idx = 2; to_idx = 3; weight = 1.0 };
    { Types.from_idx = 2; to_idx = 4; weight = 3.0 };
    { Types.from_idx = 3; to_idx = 4; weight = 1.5 };
  ] in
  let mst = Graph.kruskal_mst edges n in
  Alcotest.(check int) "MST has n-1 edges" (n - 1) (List.length mst.edges);
  Alcotest.(check int) "MST has n vertices" n mst.n_vertices

let test_mst_weight_minimality () =
  (* MST should select minimum weight edges *)
  let n = 3 in
  let edges = [
    { Types.from_idx = 0; to_idx = 1; weight = 1.0 };
    { Types.from_idx = 0; to_idx = 2; weight = 3.0 };
    { Types.from_idx = 1; to_idx = 2; weight = 2.0 };
  ] in
  let mst = Graph.kruskal_mst edges n in
  (* Minimum spanning tree should have edges (0,1) and (1,2) with total weight 3.0 *)
  Alcotest.(check (float 0.0001)) "MST total weight" 3.0 mst.total_weight

(* Test eigenvector centrality *)
let test_centrality_bounds () =
  (* Centrality should be non-negative and normalized *)
  let adj = [|
    [| 0.0; 1.0; 0.0 |];
    [| 1.0; 0.0; 1.0 |];
    [| 0.0; 1.0; 0.0 |];
  |] in
  let result = Graph.eigenvector_centrality adj in
  Array.iter (fun c ->
    Alcotest.(check bool) "centrality >= 0" true (c >= 0.0)
  ) result.centralities;
  (* Central node (index 1) should have highest centrality *)
  Alcotest.(check bool) "central node has highest centrality"
    true (result.centralities.(1) >= result.centralities.(0))

(* Test regime classification *)
let test_regime_low_risk () =
  let signals = {
    Types.var_explained_first = 0.25;  (* Low = few assets dominating *)
    var_explained_2_to_5 = 0.15;
    mean_eigenvector_centrality = 0.15;  (* Low = dispersed market *)
    std_eigenvector_centrality = 0.05;
    timestamp = "2024-01-01";
  } in
  let regime = Signals.classify_regime signals in
  (* This should be classified as low risk *)
  Alcotest.(check bool) "low risk regime" true
    (regime = Types.LowRisk || regime = Types.NormalRisk)

let test_regime_high_risk () =
  let signals = {
    Types.var_explained_first = 0.75;  (* High = market moving together *)
    var_explained_2_to_5 = 0.20;
    mean_eigenvector_centrality = 0.50;  (* High = concentrated *)
    std_eigenvector_centrality = 0.25;
    timestamp = "2024-01-01";
  } in
  let regime = Signals.classify_regime signals in
  (* This should be classified as elevated, high, or crisis risk *)
  Alcotest.(check bool) "elevated+ risk regime" true
    (regime = Types.ElevatedRisk || regime = Types.HighRisk || regime = Types.CrisisRisk)

(* Test regime to string conversion *)
let test_regime_to_string () =
  Alcotest.(check string) "low risk string" "Low Risk"
    (Types.regime_to_string Types.LowRisk);
  Alcotest.(check string) "crisis string" "Crisis"
    (Types.regime_to_string Types.CrisisRisk)

(* Test suite *)
let () =
  let open Alcotest in
  run "Systematic Risk Signals" [
    "Covariance", [
      test_case "Identity test" `Quick test_covariance_identity;
      test_case "Symmetric" `Quick test_covariance_symmetric;
      test_case "Correlation bounds" `Quick test_correlation_bounds;
      test_case "Distance metric" `Quick test_correlation_to_distance;
    ];
    "Eigenvalues", [
      test_case "Positive" `Quick test_eigenvalues_positive;
      test_case "Sorted" `Quick test_eigenvalues_sorted;
      test_case "Variance explained sum" `Quick test_var_explained_sum;
    ];
    "Graph", [
      test_case "MST edges" `Quick test_mst_edges;
      test_case "MST weight minimality" `Quick test_mst_weight_minimality;
      test_case "Centrality bounds" `Quick test_centrality_bounds;
    ];
    "Regime", [
      test_case "Low risk" `Quick test_regime_low_risk;
      test_case "High risk" `Quick test_regime_high_risk;
      test_case "To string" `Quick test_regime_to_string;
    ];
  ]
