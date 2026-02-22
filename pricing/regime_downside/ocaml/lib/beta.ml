(** Beta estimation using exponentially weighted covariance *)

open Types

(** Calculate exponentially weighted mean *)
let ewm_mean ~values ~halflife =
  let n = Array.length values in
  if n = 0 then 0.0
  else
    let lambda = 0.5 ** (1.0 /. halflife) in
    let weights_sum = ref 0.0 in
    let weighted_sum = ref 0.0 in

    Array.iteri (fun i v ->
      let age = float_of_int (n - 1 - i) in
      let weight = lambda ** age in
      weights_sum := !weights_sum +. weight;
      weighted_sum := !weighted_sum +. (weight *. v)
    ) values;

    !weighted_sum /. !weights_sum

(** Calculate exponentially weighted covariance *)
let ewm_cov ~x ~y ~halflife =
  let n = Array.length x in
  if n = 0 || n <> Array.length y then
    failwith "Invalid inputs for covariance calculation"
  else
    let lambda = 0.5 ** (1.0 /. halflife) in

    (* Calculate EWM means *)
    let mean_x = ewm_mean ~values:x ~halflife in
    let mean_y = ewm_mean ~values:y ~halflife in

    (* Calculate EWM covariance *)
    let weights_sum = ref 0.0 in
    let cov_sum = ref 0.0 in

    Array.iteri (fun i xi ->
      let yi = y.(i) in
      let age = float_of_int (n - 1 - i) in
      let weight = lambda ** age in
      weights_sum := !weights_sum +. weight;
      cov_sum := !cov_sum +. (weight *. (xi -. mean_x) *. (yi -. mean_y))
    ) x;

    !cov_sum /. !weights_sum

(** Calculate exponentially weighted variance *)
let ewm_var ~values ~halflife =
  ewm_cov ~x:values ~y:values ~halflife

(** Estimate beta for a single asset vs benchmark
    Beta = Cov(asset, benchmark) / Var(benchmark) *)
let estimate_beta ~asset_returns ~benchmark_returns ~halflife =
  let cov = ewm_cov ~x:asset_returns ~y:benchmark_returns ~halflife in
  let var = ewm_var ~values:benchmark_returns ~halflife in
  if var = 0.0 then 0.0
  else cov /. var

(** Downside Beta Calculation

    Downside beta measures an asset's sensitivity to market declines only.
    This is more relevant for downside risk management as it captures
    how much an asset "hurts" when the market falls, ignoring upside.

    Standard Beta treats gains and losses symmetrically:
      β = Cov(R_a, R_m) / Var(R_m)

    Downside Beta only considers negative market returns:
      β_down = Cov(R_a, R_m | R_m < τ) / Var(R_m | R_m < τ)

    Where τ is the threshold (typically 0 or the risk-free rate).

    Empirical finding: Downside beta is often higher than standard beta
    because correlations increase during market stress ("correlations
    go to 1 in a crash" - Longin & Solnik, 2001).
*)

(** Filter arrays to only include observations where benchmark < threshold *)
let filter_downside ~asset_returns ~benchmark_returns ~threshold =
  let n = Array.length asset_returns in
  if n <> Array.length benchmark_returns then
    ([||], [||])
  else begin
    let filtered_asset = ref [] in
    let filtered_benchmark = ref [] in

    for i = 0 to n - 1 do
      if benchmark_returns.(i) < threshold then begin
        filtered_asset := asset_returns.(i) :: !filtered_asset;
        filtered_benchmark := benchmark_returns.(i) :: !filtered_benchmark
      end
    done;

    (Array.of_list (List.rev !filtered_asset),
     Array.of_list (List.rev !filtered_benchmark))
  end

(** Estimate downside beta for a single asset vs benchmark
    Only considers periods when benchmark return < threshold

    Args:
      threshold: Return threshold, typically 0.0 (negative returns only)
                 or risk-free rate per period
*)
let estimate_downside_beta ~asset_returns ~benchmark_returns ~halflife ~threshold =
  let (down_asset, down_benchmark) =
    filter_downside ~asset_returns ~benchmark_returns ~threshold
  in

  let n_down = Array.length down_benchmark in
  if n_down < 10 then
    (* Not enough downside observations; fall back to standard beta *)
    estimate_beta ~asset_returns ~benchmark_returns ~halflife
  else begin
    let cov = ewm_cov ~x:down_asset ~y:down_benchmark ~halflife in
    let var = ewm_var ~values:down_benchmark ~halflife in
    if var = 0.0 then 0.0
    else cov /. var
  end

(** Estimate upside beta (for completeness)
    Only considers periods when benchmark return >= threshold *)
let estimate_upside_beta ~asset_returns ~benchmark_returns ~halflife ~threshold =
  let n = Array.length asset_returns in
  if n <> Array.length benchmark_returns then 0.0
  else begin
    let filtered_asset = ref [] in
    let filtered_benchmark = ref [] in

    for i = 0 to n - 1 do
      if benchmark_returns.(i) >= threshold then begin
        filtered_asset := asset_returns.(i) :: !filtered_asset;
        filtered_benchmark := benchmark_returns.(i) :: !filtered_benchmark
      end
    done;

    let up_asset = Array.of_list (List.rev !filtered_asset) in
    let up_benchmark = Array.of_list (List.rev !filtered_benchmark) in

    let n_up = Array.length up_benchmark in
    if n_up < 10 then
      estimate_beta ~asset_returns ~benchmark_returns ~halflife
    else begin
      let cov = ewm_cov ~x:up_asset ~y:up_benchmark ~halflife in
      let var = ewm_var ~values:up_benchmark ~halflife in
      if var = 0.0 then 0.0
      else cov /. var
    end
  end

(** Calculate beta asymmetry: how much worse downside beta is than upside
    Asymmetry = (β_down - β_up) / β

    Positive asymmetry means asset hurts more in down markets than it
    helps in up markets - important for risk-averse investors.
*)
let calculate_beta_asymmetry ~asset_returns ~benchmark_returns ~halflife ~threshold =
  let beta_down = estimate_downside_beta
    ~asset_returns ~benchmark_returns ~halflife ~threshold in
  let beta_up = estimate_upside_beta
    ~asset_returns ~benchmark_returns ~halflife ~threshold in
  let beta = estimate_beta ~asset_returns ~benchmark_returns ~halflife in

  if abs_float beta < 1e-6 then 0.0
  else (beta_down -. beta_up) /. beta

(** Estimate betas for all assets
    Default halflife: 60 days (approximately 3 months) *)
let estimate_all_betas
    ~(asset_returns_list : return_series list)
    ~(benchmark_returns : float array)
    ?(halflife = 60.0) () : asset_betas =

  List.map (fun (return_series : return_series) ->
    let beta =
      estimate_beta
        ~asset_returns:return_series.returns
        ~benchmark_returns
        ~halflife
    in
    (return_series.ticker, beta)
  ) asset_returns_list
