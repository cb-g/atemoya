open Yojson.Basic.Util

type input = {
  short_name : string;
  currency : string;
  rfr : float;
  beta_u : float;
  erp : float;
  ebit : float;
  ni : float;
  capx : float;
  d : float;
  ca : float;
  cl : float;
  prev_ca : float;
  prev_cl : float;
  tgr : float;
  h : int;
  ctr : float;
  ic : float;
  dp : float;
  so : float;
  mve : float;
  mvb : float;
  tdr : float;
  time_series : (string * float list) list;
  growth_clamp_upper : float;
  growth_clamp_lower : float;
}

let sample_lognormal ~mu ~sigma =
  let u1 = Random.float 1.0 in
  let u2 = Random.float 1.0 in
  let z = mu +. sigma *. sqrt (-2.0 *. log u1) *. cos (2.0 *. Float.pi *. u2) in
  exp z

let sample_beta_scaled ~alpha ~beta ~a ~b =
  let gamma_sample shape =
    let d = shape -. 1.0 /. 3.0 in
    let c = 1.0 /. sqrt (9.0 *. d) in
    let rec loop () =
      let u1 = Random.float 1.0 in
      let u2 = Random.float 1.0 in
      let x = sqrt (-2.0 *. log u1) *. cos (2.0 *. Float.pi *. u2) in
      let v = (1.0 +. c *. x) ** 3.0 in
      let u = Random.float 1.0 in
      if u < 1.0 -. 0.331 *. x ** 4.0 || log u < 0.5 *. x *. x +. d -. d *. v +. d *. log v
      then d *. v else loop ()
    in loop ()
  in
  let x = gamma_sample alpha in
  let y = gamma_sample beta in
  a +. ((x /. (x +. y)) *. (b -. a))


let parse_time_series json =
  json |> to_assoc |> List.map (fun (k, v) ->
    (k, to_list v |> List.map to_float))

let of_json json : input =
  let ts_json = json |> member "time_series" in
  {
    short_name = json |> member "short_name" |> to_string;
    currency = json |> member "currency" |> to_string;
    rfr = json |> member "rfr" |> to_float;
    beta_u = json |> member "beta_u" |> to_float;
    erp = json |> member "erp" |> to_float;
    ebit = json |> member "ebit" |> to_float;
    ni = json |> member "ni" |> to_float;
    capx = json |> member "capx" |> to_float;
    d = json |> member "d" |> to_float;
    ca = json |> member "ca" |> to_float;
    cl = json |> member "cl" |> to_float;
    prev_ca = json |> member "prev_ca" |> to_float;
    prev_cl = json |> member "prev_cl" |> to_float;
    tgr = json |> member "tgr" |> to_float;
    h = json |> member "h" |> to_int;
    ctr = json |> member "ctr" |> to_float;
    ic = json |> member "ic" |> to_float;
    dp = json |> member "dp" |> to_float;
    so = json |> member "so" |> to_float;
    mve = json |> member "mve" |> to_float;
    mvb = json |> member "mvb" |> to_float;
    tdr = json |> member "tdr" |> to_float;
    time_series = parse_time_series ts_json;
    growth_clamp_upper = json |> member "growth_clamp" |> member "upper" |> to_float;
    growth_clamp_lower = json |> member "growth_clamp" |> member "lower" |> to_float;
  }

let load_inputs path : (string * input) list =
  Yojson.Basic.from_file path
  |> to_assoc
  |> List.map (fun (tkr, j) -> (tkr, of_json j))

(* -- helpers to compute priors from time_series -- *)

let get_mean_std key ts =
  match List.assoc_opt key ts with
  | None -> failwith ("Missing time_series: " ^ key)
  | Some lst ->
    let filtered = List.filter (fun x -> not (Float.is_nan x || x = 0.0)) lst in
    let n = float_of_int (List.length filtered) in
    if n < 2.0 then 0.0, 0.0
    else
      let mu = List.fold_left (+.) 0.0 filtered /. n in
      let var = List.fold_left (fun acc x -> acc +. (x -. mu) ** 2.0) 0.0 filtered /. n in
      mu, sqrt var

let get_mean_std_from_list lst =
  let n = float_of_int (List.length lst) in
  let mu = List.fold_left ( +. ) 0.0 lst /. n in
  let sigma = sqrt (List.fold_left (fun acc x -> acc +. ((x -. mu) ** 2.0)) 0.0 lst /. n) in
  mu, sigma
;;

let rec map3 f l1 l2 l3 =
  match l1, l2, l3 with
  | x1::xs1, x2::xs2, x3::xs3 -> f x1 x2 x3 :: map3 f xs1 xs2 xs3
  | _, _, _ -> []
;;

let rec map6 f l1 l2 l3 l4 l5 l6 =
  match l1, l2, l3, l4, l5, l6 with
  | a::as_, b::bs, c::cs, d::ds, e::es, f_::fs ->
      f a b c d e f_ :: map6 f as_ bs cs ds es fs
  | _ -> []
;;

let sample_gaussian ~mu ~sigma =
  let u1 = Random.float 1.0 in
  let u2 = Random.float 1.0 in
  mu +. sigma *. sqrt (-2.0 *. log u1) *. cos (2.0 *. Float.pi *. u2)

let safe_div x y =
  if abs_float y < 1e-6 then 0.0 else x /. y
;;

let sample_fcfegr ~ts ~clamp_upper ~clamp_lower =
  try
    let ni = List.assoc "ni" ts in
    let bve = List.assoc "bve" ts in
    let dp = List.assoc "dp" ts in
    let growths = map3 (fun ni bve dp ->
      if abs_float bve < 1e-6 || abs_float ni < 1e-6 then 0.0
      else
        let roe_raw = safe_div ni bve in
        let retention_raw = 1.0 -. safe_div dp ni in

        (* Apply prior-informed smoothing *)
        let roe = 
          min 0.4 (max 0.0 (
            0.5 *. roe_raw +. 0.5 *. sample_beta_scaled ~alpha:2.0 ~beta:5.0 ~a:0.0 ~b:0.4
          ))
        in
        let retention = 
          min 1.0 (max 0.0 (
            0.5 *. retention_raw +. 0.5 *. sample_beta_scaled ~alpha:2.0 ~beta:2.0 ~a:0.0 ~b:1.0
          ))
        in
        roe *. retention
    ) ni bve dp
    in
    let mu, sigma = get_mean_std_from_list growths in
    let g = sample_gaussian ~mu ~sigma in
    max clamp_lower (min clamp_upper g)
  with Not_found | Invalid_argument _ -> 0.05
;;

let sample_fcffgr ~ts ~clamp_upper ~clamp_lower =
  try
    let ebit = List.assoc "ebit" ts in
    let ic = List.assoc "ic" ts in
    let capx = List.assoc "capx" ts in
    let d = List.assoc "d" ts in
    let ca = List.assoc "ca" ts in
    let cl = List.assoc "cl" ts in
    let growths = map6 (fun ebit ic capx d ca cl ->
      if abs_float ic < 1e-6 || abs_float ebit < 1e-6 then 0.0
      else
        let nopat = ebit *. 0.75 in
        let reinvest = capx -. d +. (cl -. ca) in

        let roic_empirical = safe_div nopat ic in
        let reinvestment_empirical = safe_div reinvest nopat in

        let roic_prior = sample_beta_scaled ~alpha:2.0 ~beta:5.0 ~a:0.0 ~b:0.4 in
        let reinvestment_prior = sample_beta_scaled ~alpha:2.0 ~beta:2.0 ~a:0.0 ~b:1.0 in

        let roic = min 0.4 (max 0.0 (0.5 *. roic_empirical +. 0.5 *. roic_prior)) in
        let reinvestment_rate = min 1.0 (max 0.0 (0.5 *. reinvestment_empirical +. 0.5 *. reinvestment_prior)) in

        roic *. reinvestment_rate
    ) ebit ic capx d ca cl in
    let mu, sigma = get_mean_std_from_list growths in
    let g = sample_gaussian ~mu ~sigma in
    max clamp_lower (min clamp_upper g)
  with Not_found | Invalid_argument _ -> 0.05
;;

let calculate_delta_wc ~ca ~cl ~prev_ca ~prev_cl =
  (ca -. cl) -. (prev_ca -. prev_cl)

let project_fcfe ~ni ~capx ~d ~ca ~cl ~tdr ~delta_wc ~years ~fcfegr =
  let wc = ca -. cl in
  let rec loop t acc ni capx d wc =
    if t > years then List.rev acc
    else
      let ni_t = ni *. (1.0 +. fcfegr) in
      let capx_t = capx *. (1.0 +. fcfegr) in
      let d_t = d *. (1.0 +. fcfegr) in
      let wc_t = wc *. (1.0 +. fcfegr) in
      let delta_wc_t = delta_wc *. (1.0 +. fcfegr) ** float_of_int t in
      let reinvestment = capx_t -. d_t +. delta_wc_t in
      let net_borrowing = tdr *. reinvestment in
      let fcfe_t = ni_t +. d_t -. capx_t -. delta_wc_t +. net_borrowing in
      loop (t + 1) (fcfe_t :: acc) ni_t capx_t d_t wc_t
  in
  loop 1 [] ni capx d wc

let project_fcff ~ebit ~d ~capx ~ca ~cl ~ctr ~delta_wc ~years ~fcffgr =
  let wc = ca -. cl in
  let rec loop t acc ebit d capx wc =
    if t > years then List.rev acc
    else
      let ebit_t = ebit *. (1.0 +. fcffgr) in
      let d_t = d *. (1.0 +. fcffgr) in
      let capx_t = capx *. (1.0 +. fcffgr) in
      let wc_t = wc *. (1.0 +. fcffgr) in
      let delta_wc_t = delta_wc *. (1.0 +. fcffgr) ** float_of_int t in
      let fcff_t = (ebit_t *. (1.0 -. ctr)) +. d_t -. capx_t -. delta_wc_t in
      loop (t + 1) (fcff_t :: acc) ebit_t d_t capx_t wc_t
  in
  loop 1 [] ebit d capx wc

let calculate_leveraged_beta ~beta_u ~ctr ~mvb ~mve =
  let debt_to_equity = mvb /. mve in
  beta_u *. (1.0 +. (1.0 -. ctr) *. debt_to_equity)

let calculate_cost_of_equity ~rfr ~beta_l ~erp =
  rfr +. (beta_l *. erp)

let calculate_pve_from_projection ~fcfe_list ~ce ~tgr =
  let h = List.length fcfe_list in
  let sum_pv =
    List.mapi (fun i fcfe ->
      let t = i + 1 in
      fcfe /. ((1.0 +. ce) ** float_of_int t)
    ) fcfe_list |> List.fold_left ( +. ) 0.0
  in
  let fcfe_h = List.nth fcfe_list (h - 1) in
  let safe_tgr = max 0.0 (min (ce -. 0.001) tgr) in
  let denom = max 0.01 (ce -. safe_tgr) in
  let terminal = (fcfe_h *. (1.0 +. safe_tgr)) /. denom in
  let pv_terminal = terminal /. ((1.0 +. ce) ** float_of_int h) in
  sum_pv +. pv_terminal

let simulate_fcfe (input : input) : float list =
  let ts = input.time_series in
  let sample key =
  let mu, sigma = get_mean_std key ts in
  match key with
  | "ni" | "capx" | "d" | "ca" | "cl" ->
      let mu_log = if mu <= 0.0 then log 1e-3 else log mu in
      let sigma_log = if mu <= 0.0 then 0.1 else sigma /. mu in
      sample_lognormal ~mu:mu_log ~sigma:sigma_log
  | _ ->
      sample_gaussian ~mu ~sigma
 in

  (* sample inputs *)
  let squash x threshold =
    if x < threshold then x
    else threshold +. log (1.0 +. (x -. threshold))
  in
  let ni_raw = sample "ni" in
  let ni_series =
    match List.assoc_opt "ni" ts with
    | Some lst when lst <> [] -> lst
    | _ -> [input.ni]
  in
  let ni_empirical_cap = List.fold_left max neg_infinity ni_series *. 3.0 in
  let ni_market_cap = input.mve *. 0.3 in
  let ni_cap = min ni_empirical_cap ni_market_cap in
  let ni = squash ni_raw ni_cap in
  let capx = sample "capx" in
  let d = sample "d" in
  let ca = sample "ca" in
  let cl = sample "cl" in

  (* deterministic params *)
  let prev_ca = input.prev_ca in
  let prev_cl = input.prev_cl in
  let tdr = input.tdr in
  let h = input.h in
  let tgr = input.tgr in
  let beta_u = input.beta_u in
  let ctr = input.ctr in
  let mvb = input.mvb in
  let mve = input.mve in
  let rfr = input.rfr in
  let erp = input.erp in

  let fcfegr = sample_fcfegr ~ts ~clamp_upper:input.growth_clamp_upper ~clamp_lower:input.growth_clamp_lower in
  (* let fcfegr = min 0.25 (max (-0.1) fcfegr) in *)
  (* Printf.printf "[DEBUG] Sampled FCFEGR: %.4f\n%!" fcfegr; *)

  let fcfe_proj =
    let delta_wc = calculate_delta_wc ~ca ~cl ~prev_ca ~prev_cl in
    project_fcfe ~ni ~capx ~d ~ca ~cl ~tdr ~delta_wc ~years:h ~fcfegr
  in

  (* Printf.printf "[DEBUG] FCFE projection (first simulation):\n%!";
  List.iteri (fun i v -> Printf.printf "  Year %d → %.2f\n%!" (i + 1) v) fcfe_proj; *)

  let beta_l = calculate_leveraged_beta ~beta_u ~ctr ~mvb ~mve in
  let ce = calculate_cost_of_equity ~rfr ~beta_l ~erp in

  let pv = calculate_pve_from_projection ~fcfe_list:fcfe_proj ~ce ~tgr in

  (* Printf.printf "[DEBUG] Present Value (FCFE): %.2f\n%!" pv; *)
  (* Printf.printf "[DEBUG] Sampled: ni=%.2f capx=%.2f d=%.2f ca=%.2f cl=%.2f\n%!" ni capx d ca cl; *)
  (* Printf.printf "[DEBUG] beta_l=%.2f | cost_of_equity=%.2f\n%!" beta_l ce; *)
  (* Printf.printf "[DEBUG] so = %.2f\n%!" input.so; *)

  [pv]

let simulate_fcff (input : input) : float list =
  let ts = input.time_series in
  let sample key =
  let mu, sigma = get_mean_std key ts in
  match key with
  | "ebit" | "capx" | "d" | "ca" | "cl" ->
      let mu_log = if mu <= 0.0 then log 1e-3 else log mu in
      let sigma_log = if mu <= 0.0 then 0.1 else sigma /. mu in
      sample_lognormal ~mu:mu_log ~sigma:sigma_log
  | _ ->
      sample_gaussian ~mu ~sigma
  in

  (* sampled inputs *)
  let squash x threshold =
    if x < threshold then x
    else threshold +. log (1.0 +. (x -. threshold))
  in
  let ebit_raw = sample "ebit" in
  let ebit_series =
    match List.assoc_opt "ebit" ts with
    | Some lst when lst <> [] -> lst
    | _ -> [input.ebit]
  in
  let ebit_empirical_cap = List.fold_left max neg_infinity ebit_series *. 3.0 in
  let ebit_market_cap = input.mve *. 0.3 in
  let ebit_cap = min ebit_empirical_cap ebit_market_cap in
  let ebit = squash ebit_raw ebit_cap in
  let capx = sample "capx" in
  let d = sample "d" in
  let ca = sample "ca" in
  let cl = sample "cl" in

  (* Printf.printf "[DEBUG] Sampled: ebit=%.2f capx=%.2f d=%.2f ca=%.2f cl=%.2f\n%!" ebit capx d ca cl; *)

  (* deterministic inputs *)
  let prev_ca = input.prev_ca in
  let prev_cl = input.prev_cl in
  let h = input.h in
  let tgr = input.tgr in
  let ctr = input.ctr in
  let beta_u = input.beta_u in
  let mvb = input.mvb in
  let mve = input.mve in
  let rfr = input.rfr in
  let erp = input.erp in

  let fcffgr = sample_fcffgr ~ts ~clamp_upper:input.growth_clamp_upper ~clamp_lower:input.growth_clamp_lower in
  (* let fcffgr = min 0.25 (max (-0.1) fcffgr) in *)
  (* Printf.printf "[DEBUG] Sampled FCFFGR: %.4f\n%!" fcffgr; *)
  let delta_wc = calculate_delta_wc ~ca ~cl ~prev_ca ~prev_cl in

  let fcff_proj =
    project_fcff ~ebit ~d ~capx ~ca ~cl ~ctr ~delta_wc ~years:h ~fcffgr
  in

  (* Printf.printf "[DEBUG] FCFF projection (first simulation):\n%!";
  List.iteri (fun i v -> Printf.printf "  Year %d → %.2f\n%!" (i + 1) v) fcff_proj; *)

  let beta_l = calculate_leveraged_beta ~beta_u ~ctr ~mvb ~mve in
  let ce = calculate_cost_of_equity ~rfr ~beta_l ~erp in

  (* Printf.printf "[DEBUG] beta_l=%.2f | cost_of_equity=%.2f\n%!" beta_l ce; *)
  (* Printf.printf "[DEBUG] so = %.2f\n%!" input.so; *)

  let pv = calculate_pve_from_projection ~fcfe_list:fcff_proj ~ce ~tgr in

  (* Printf.printf "[DEBUG] Present Value (FCFF): %.2f\n%!" pv; *)
  [pv]

let run_monte_carlo (input : input) ~n ~fcfe =
  let run_once () =
    if fcfe then simulate_fcfe input
    else simulate_fcff input
  in
  List.init n (fun _ ->
    let pv = List.hd (run_once ()) in
    let so = max input.so 1.0 in
    pv /. so
  )
