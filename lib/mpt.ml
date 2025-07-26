open Lacaml.D
module A1 = Bigarray.Array1

let read_adjusted_closes (csv_file : string) : Lacaml.D.mat =
  let raw = Csv.load csv_file in
  match raw with
  | [] | [_] -> invalid_arg "read_adjusted_closes: CSV must have header and data rows"
  | header :: rows ->
      (* remove the Date column, retain asset tickers *)
      let tickers = match header with
        | _ :: t -> t
        | [] -> invalid_arg "read_adjusted_closes: empty header"
      in
      let n_assets = List.length tickers in
      let n_obs = List.length rows in
      (* create matrix with rows = assets, cols = observations *)
      let mat = Lacaml.D.Mat.create n_assets n_obs in
      (* fill matrix: for each observation j and asset i *)
      List.iteri (fun j row ->
        let values = match row with
          | _ :: v -> v
          | [] -> invalid_arg "read_adjusted_closes: malformed row"
        in
        if List.length values <> n_assets then
          invalid_arg "read_adjusted_closes: inconsistent number of columns";
        List.iteri (fun i s ->
          (* Treat empty strings as NaN *)
          let v = if String.trim s = "" then nan else float_of_string s in
          mat.{i+1, j+1} <- v
        ) values
      ) rows;
      mat

let compute_log_returns (closes : Lacaml.D.mat) : Lacaml.D.mat =
  let n_assets = Lacaml.D.Mat.dim1 closes in
  let n_obs = Lacaml.D.Mat.dim2 closes in
  if n_obs < 2 then invalid_arg "compute_log_returns: need at least two observations";
  (* identify valid time indices j where both j and j+1 have no NaN for all assets *)
  let valid_js =
    let rec collect j acc =
      if j >= n_obs then List.rev acc else
      let rec check i =
        if i > n_assets then true else
        let v0 = closes.{i, j} in
        let v1 = closes.{i, j+1} in
        if Float.is_nan v0 || Float.is_nan v1 then false else check (i+1)
      in
      if check 1 then collect (j+1) (j :: acc) else collect (j+1) acc
    in
    collect 1 []
  in
  let t' = List.length valid_js in
  if t' = 0 then invalid_arg "compute_log_returns: no valid observation pairs after filtering missing data";
  (* Warn if any periods dropped *)
  if t' < (n_obs - 1) then
    Printf.eprintf
      "compute_log_returns: dropped %d observation(s) due to missing data\n"
      ((n_obs - 1) - t');
  (* Build return matrix *)
  let ret = Lacaml.D.Mat.create n_assets t' in
  List.iteri (fun k j ->
    for i = 1 to n_assets do
      let p0 = closes.{i, j} in
      let p1 = closes.{i, j+1} in
      ret.{i, k+1} <- log (p1 /. p0)
    done
  ) valid_js;
  ret

let mean_return_vector (log_r : Lacaml.D.mat) : Lacaml.D.vec =
  (* mean return per asset: average across time for each row *)
  let n_assets = Lacaml.D.Mat.dim1 log_r in
  let n_obs = Lacaml.D.Mat.dim2 log_r in
  let mu = Lacaml.D.Vec.create n_assets in
  for i = 1 to n_assets do
    let sum = ref 0.0 in
    for j = 1 to n_obs do
      sum := !sum +. log_r.{i, j}
    done;
    mu.{i} <- !sum /. float_of_int n_obs
  done;
  mu

let covariance_matrix (log_r : Lacaml.D.mat) : Lacaml.D.mat =
  (* cov matrix of log-returns: cov_{i,k} = (1/(T-1)) * sum_j ((r_{i,j}-mu_i)*(r_{k,j}-mu_k)) *)
  let n_assets = Lacaml.D.Mat.dim1 log_r in
  let n_obs = Lacaml.D.Mat.dim2 log_r in
  if n_obs < 2 then invalid_arg "covariance_matrix: need at least two observations";
  (* mean vector *)
  let mu = mean_return_vector log_r in
  (* allocate cov matrix *)
  let cov = Lacaml.D.Mat.create n_assets n_assets in
  for i = 1 to n_assets do
    for k = 1 to n_assets do
      let sum = ref 0.0 in
      for j = 1 to n_obs do
        let di = log_r.{i, j} -. mu.{i} in
        let dk = log_r.{k, j} -. mu.{k} in
        sum := !sum +. (di *. dk)
      done;
      cov.{i, k} <- !sum /. float_of_int (n_obs - 1)
    done
  done;
  cov

let mat_inv (m : Lacaml.D.mat) : Lacaml.D.mat =
  let n = Mat.dim1 m in
  (* 1) copy A into a fresh matrix so we don’t clobber the input *)
  let a = Mat.create n n in
  Bigarray.Array2.blit m a;
  (* 2) build the identity matrix I *)
  let inv = Mat.create n n in
  for i = 1 to n do inv.{i,i} <- 1.0 done;
  (* 3) solve A · inv = I; result ends up in [inv] *)
  Lacaml.D.gesv a inv;
  inv

(* [efficient_frontier mu cov n_pts]
   generate [n_pts] points (μ,σ) on the mean–variance frontier *)
(* return: (μ, σ, weights) list *)
let efficient_frontier (mu : Vec.t) (cov : Mat.t) (n_pts : int) :
  (float * float * Vec.t) list =

  let cov_inv = mat_inv cov in
  let ones    = Vec.make (Vec.dim mu) 1. in

  let a = dot (gemv cov_inv mu)    ones in
  let b = dot (gemv cov_inv mu)    mu   in
  let c = dot (gemv cov_inv ones)  ones in
  let d = (b *. c) -. (a *. a) in

  let min_r = Vec.min mu and max_r = Vec.max mu in
  let step  = (max_r -. min_r) /. float (n_pts - 1) in

  let rec loop i acc =
    if i >= n_pts then List.rev acc else
    let target = min_r +. float i *. step in

    let v1 = gemv cov_inv ones in
    scal ((b -. a *. target) /. d) v1;
    let w1 = v1 in

    let v2 = gemv cov_inv mu in
    scal (((c *. target) -. a) /. d) v2;
    let w2 = v2 in

    let w = Lacaml.D.Vec.create (A1.dim w1) in
    for i = 1 to A1.dim w1 do
      w.{i} <- w1.{i}
    done;
    axpy ~alpha:1.0 w2 w;

    let var   = dot w (gemv cov w) in
    let sigma = sqrt var in

    loop (i+1) ((target, sigma, w) :: acc)
  in
  loop 0 []

let write_frontier_to_csv (filename : string) (frontier : (float * float * Vec.t) list) : unit =
  let out = open_out filename in
  output_string out "Return,Risk\n";
  List.iter (fun (mu, sigma, _) ->
    let annual_mu = mu *. 252.0 in
    let annual_sigma = sigma *. sqrt 252.0 in
    Printf.fprintf out "%.12f,%.12f\n" annual_mu annual_sigma
  ) frontier;
  close_out out

let write_example_portfolios_to_csv
    (filename : string)
    (tickers : string list)
    (examples : (string * float * float * Vec.t) list) : unit =
  let out = open_out filename in
  (* Write header *)
  Printf.fprintf out "Portfolio,Return,Risk,%s\n" (String.concat "," tickers);
  (* Write rows *)
  List.iter (fun (label, mu, sigma, w) ->
    let annual_mu = mu *. 252.0 in
    let annual_sigma = sigma *. sqrt 252.0 in
    let weights = List.init (Vec.dim w) (fun i -> w.{i+1}) in
    let row = Printf.sprintf "%s,%.12f,%.12f,%s"
                 label annual_mu annual_sigma
                 (String.concat "," (List.map string_of_float weights))
    in
    output_string out (row ^ "\n")
  ) examples;
  close_out out
