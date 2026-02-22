(* Correlation analytics for dispersion trading *)

open Types

(** Statistics helpers **)

(* Calculate mean of array *)
let mean arr =
  if Array.length arr = 0 then 0.0
  else
    let sum = Array.fold_left (+.) 0.0 arr in
    sum /. float_of_int (Array.length arr)

(* Calculate standard deviation *)
let std arr =
  if Array.length arr < 2 then 0.0
  else
    let mu = mean arr in
    let variance = Array.fold_left (fun acc x -> acc +. (x -. mu) ** 2.0) 0.0 arr
                   /. float_of_int (Array.length arr - 1) in
    sqrt variance

(* Calculate returns from prices *)
let returns prices =
  let n = Array.length prices in
  if n < 2 then [||]
  else
    Array.init (n - 1) (fun i ->
      let r = (prices.(i + 1) -. prices.(i)) /. prices.(i) in
      r
    )

(** Correlation calculations **)

(* Calculate covariance between two return series *)
let covariance returns1 returns2 =
  let n = min (Array.length returns1) (Array.length returns2) in
  if n < 2 then 0.0
  else
    let mu1 = mean returns1 in
    let mu2 = mean returns2 in
    let cov = ref 0.0 in
    for i = 0 to n - 1 do
      cov := !cov +. (returns1.(i) -. mu1) *. (returns2.(i) -. mu2)
    done;
    !cov /. float_of_int (n - 1)

(* Calculate correlation between two return series *)
let correlation returns1 returns2 =
  let cov = covariance returns1 returns2 in
  let std1 = std returns1 in
  let std2 = std returns2 in
  if std1 = 0.0 || std2 = 0.0 then 0.0
  else cov /. (std1 *. std2)

(* Calculate correlation matrix from returns *)
let correlation_matrix returns_array =
  let n = Array.length returns_array in
  let corr_matrix = Array.make_matrix n n 1.0 in

  for i = 0 to n - 1 do
    for j = i + 1 to n - 1 do
      let corr = correlation returns_array.(i) returns_array.(j) in
      corr_matrix.(i).(j) <- corr;
      corr_matrix.(j).(i) <- corr
    done
  done;

  corr_matrix

(* Calculate average pairwise correlation *)
let avg_pairwise_correlation corr_matrix =
  let n = Array.length corr_matrix in
  if n < 2 then 0.0
  else
    let sum = ref 0.0 in
    let count = ref 0 in
    for i = 0 to n - 1 do
      for j = i + 1 to n - 1 do
        sum := !sum +. corr_matrix.(i).(j);
        count := !count + 1
      done
    done;
    !sum /. float_of_int !count

(* Calculate realized correlation from price history *)
let realized_correlation ~index_prices ~constituent_prices ~weights =
  (* Calculate returns *)
  let _index_returns = returns index_prices in
  let constituent_returns = Array.map returns constituent_prices in

  (* Build correlation matrix *)
  let corr_matrix = correlation_matrix constituent_returns in

  (* Calculate weighted average correlation *)
  let n = Array.length weights in
  let weighted_corr = ref 0.0 in
  let weight_sum = ref 0.0 in

  for i = 0 to n - 1 do
    for j = i + 1 to n - 1 do
      let w = weights.(i) *. weights.(j) in
      weighted_corr := !weighted_corr +. w *. corr_matrix.(i).(j);
      weight_sum := !weight_sum +. w
    done
  done;

  if !weight_sum > 0.0 then !weighted_corr /. !weight_sum
  else avg_pairwise_correlation corr_matrix

(* Calculate implied correlation from volatilities

   Formula: ρ_impl = (σ_index² - Σ w_i² σ_i²) / (2 Σ_i Σ_j>i w_i w_j σ_i σ_j)

   Derivation: σ_index² = Σ w_i² σ_i² + 2 Σ_i Σ_j>i w_i w_j ρ_ij σ_i σ_j
   Assuming uniform correlation ρ: ρ_impl = (σ_index² - Σ w_i² σ_i²) / (2 Σ_i Σ_j>i w_i w_j σ_i σ_j)
*)
let implied_correlation ~index_vol ~constituent_vols ~weights =
  let n = Array.length constituent_vols in

  (* Calculate variance contribution from single names *)
  let var_single = ref 0.0 in
  for i = 0 to n - 1 do
    var_single := !var_single +. weights.(i) *. weights.(i) *. constituent_vols.(i) *. constituent_vols.(i)
  done;

  (* Calculate covariance term denominator *)
  let cov_denom = ref 0.0 in
  for i = 0 to n - 1 do
    for j = i + 1 to n - 1 do
      cov_denom := !cov_denom +. weights.(i) *. weights.(j) *. constituent_vols.(i) *. constituent_vols.(j)
    done
  done;

  let index_var = index_vol *. index_vol in

  if !cov_denom > 0.0 then
    let implied_corr = (index_var -. !var_single) /. (2.0 *. !cov_denom) in
    (* Clamp to [-1, 1] *)
    max (-1.0) (min 1.0 implied_corr)
  else
    0.0

(* Build full correlation metrics *)
let calculate_correlation_metrics ~index_prices ~index_vol ~constituent_prices ~constituent_vols ~weights =
  let realized_corr = realized_correlation
    ~index_prices
    ~constituent_prices
    ~weights in

  let implied_corr = implied_correlation
    ~index_vol
    ~constituent_vols
    ~weights in

  let constituent_returns = Array.map returns constituent_prices in
  let corr_matrix = correlation_matrix constituent_returns in
  let avg_corr = avg_pairwise_correlation corr_matrix in

  {
    implied_correlation = implied_corr;
    realized_correlation = realized_corr;
    avg_pairwise_correlation = avg_corr;
    correlation_matrix = corr_matrix;
  }
