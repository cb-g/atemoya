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
