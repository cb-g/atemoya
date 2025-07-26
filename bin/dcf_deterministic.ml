open Yojson.Basic.Util
open Unix
open Printf

(* ========================= *)
(* logging setup             *)
(* ========================= *)

let setup_logging (tickers : string list) : unit =
  let now = Unix.localtime (Unix.time ()) in
  let timestamp =
    Printf.sprintf "%04d-%02d-%02d_%02d-%02d-%02d"
      (1900 + now.Unix.tm_year)
      (now.Unix.tm_mon + 1)
      now.Unix.tm_mday
      now.Unix.tm_hour
      now.Unix.tm_min
      now.Unix.tm_sec
  in

  let joined_tickers = String.concat "_" tickers in
  let filename = Printf.sprintf "log/val/dcf_deterministic/IVPS_%s_%s.log" timestamp joined_tickers in

  (* ensure log directory exists *)
  let _ = Sys.command "mkdir -p log/val/dcf_deterministic" in

  (* redirect stdout and stderr to log file *)
  let log_fd = Unix.openfile filename [O_WRONLY; O_CREAT; O_TRUNC] 0o644 in
  let _ = Unix.dup2 log_fd Unix.stdout in
  let _ = Unix.dup2 log_fd Unix.stderr in

  printf "[INFO] Logging to: %s\n%!" filename

(* ========================= *)
(* valuation module          *)
(* ========================= *)

(* type for structured valuation input *)
type valuation_inputs = {
  mve: float; mvb: float;
  rfr: float; beta_u: float; erp: float;
  interest_expense: float; total_debt: float;
  ctr: float; 
  tdr: float;
  ni: float; bve: float; dp: float;
  ebit: float; ite: float; ic: float;
  capx: float; d: float;
  ca: float; cl: float;
  prev_ca: float; prev_cl: float;
  tgr: float; h: int; so: float;
  price: float;
  currency: string;
  long_name: string;
  growth_clamp_fcfe_upper : float;
  growth_clamp_fcfe_lower : float;
  growth_clamp_fcff_upper : float;
  growth_clamp_fcff_lower : float;
}

(* extracts a float from JSON regardless of int/float representation *)
let get_number key json =
  match json |> member key with
  | `Float f -> f
  | `Int i -> float_of_int i
  | other -> raise (Type_error ("Expected number", other))

(* parses a JSON object into a valuation_inputs record *)
let parse_inputs (json : Yojson.Basic.t) : valuation_inputs =
  {
    mve = get_number "mve" json;
    mvb = get_number "mvb" json;
    rfr = get_number "rfr" json;
    beta_u = get_number "beta_u" json;
    erp = get_number "erp" json;
    interest_expense = get_number "interest_expense" json;
    total_debt = get_number "total_debt" json;
    ctr = get_number "ctr" json;
    tdr = get_number "tdr" json;
    ni = get_number "ni" json;
    bve = get_number "bve" json;
    dp = get_number "dp" json;
    ebit = get_number "ebit" json;
    ite = get_number "ite" json;
    ic = get_number "ic" json;
    capx = get_number "capx" json;
    d = get_number "d" json;
    ca = get_number "ca" json;
    cl = get_number "cl" json;
    prev_ca = get_number "prev_ca" json;
    prev_cl = get_number "prev_cl" json;
    tgr = get_number "tgr" json;
    h = int_of_float (get_number "h" json);
    so = get_number "so" json;
    price = get_number "price" json;
    currency = json |> member "currency" |> to_string;
    long_name = json |> member "long_name" |> to_string;
    growth_clamp_fcfe_upper = get_number "upper" (json |> member "growth_clamp");
    growth_clamp_fcfe_lower = get_number "lower" (json |> member "growth_clamp");
    growth_clamp_fcff_upper = get_number "upper" (json |> member "growth_clamp");
    growth_clamp_fcff_lower = get_number "lower" (json |> member "growth_clamp");
  }

let default_json_path = "data/val/dcf/input_for_deterministic.json"

let run (_args : string list) : unit =
  let json = Yojson.Basic.from_file default_json_path in
  let assoc_list = to_assoc json in
  let tickers = List.map fst assoc_list in
  setup_logging tickers;

  List.iter (fun (ticker, data) ->
    let v = parse_inputs data in

    if v.total_debt = 0.0 then invalid_arg "Total debt cannot be zero.";
    let cb = v.interest_expense /. v.total_debt in

    let beta_l = Atemoya.Dcf_deterministic.calculate_leveraged_beta ~beta_u:v.beta_u ~ctr:v.ctr ~mvb:v.mvb ~mve:v.mve in
    let ce = Atemoya.Dcf_deterministic.calculate_cost_of_equity ~rfr:v.rfr ~beta_l ~erp:v.erp in
    let wacc = Atemoya.Dcf_deterministic.calculate_wacc ~mve:v.mve ~mvb:v.mvb ~ce ~cb ~ctr:v.ctr in
    let fcfe0 = Atemoya.Dcf_deterministic.calculate_fcfe ~ni:v.ni ~capx:v.capx ~d:v.d ~ca:v.ca ~cl:v.cl ~prev_ca:v.prev_ca ~prev_cl:v.prev_cl ~net_borrowing:0.0 in
    let fcff0 = Atemoya.Dcf_deterministic.calculate_fcff ~ebit:v.ebit ~ctr:v.ctr ~b:v.d ~capx:v.capx ~ca:v.ca ~cl:v.cl ~prev_ca:v.prev_ca ~prev_cl:v.prev_cl in
    
    let raw_fcfegr = Atemoya.Dcf_deterministic.calculate_fcfe_growth_rate ~ni:v.ni ~bve:v.bve ~dp:v.dp in
    let fcfegr =
      Float.min v.growth_clamp_fcfe_upper raw_fcfegr
      |> Float.max v.growth_clamp_fcfe_lower
    in
    let capped_fcfegr = raw_fcfegr > v.growth_clamp_fcfe_upper in
    let floored_fcfegr = raw_fcfegr < v.growth_clamp_fcfe_lower in
    
    let raw_fcffgr = Atemoya.Dcf_deterministic.calculate_fcff_growth_rate
      ~ebit:v.ebit ~ite:v.ite ~ic:v.ic
      ~capx:v.capx ~d:v.d ~ca:v.ca ~cl:v.cl
    in
    let fcffgr =
      Float.min v.growth_clamp_fcff_upper raw_fcffgr
      |> Float.max v.growth_clamp_fcff_lower
    in
    let capped_fcffgr = raw_fcffgr > v.growth_clamp_fcff_upper in
    let floored_fcffgr = raw_fcffgr < v.growth_clamp_fcff_lower in

    (* let pvf = calculate_pvf ~fcff0 ~fcffgr ~wacc ~tgr:v.tgr ~h:v.h in *)
    let fcff_projection = Atemoya.Dcf_deterministic.project_fcff 
      ~ebit:v.ebit ~ctr:v.ctr
      ~capx:v.capx ~d:v.d ~ca:v.ca ~cl:v.cl
      ~years:v.h 
      ~fcffgr
    in
    let pvf = Atemoya.Dcf_deterministic.calculate_pvf_from_projection
      ~fcff_list:fcff_projection ~wacc ~tgr:v.tgr
    in

    (* let pve = calculate_pve ~fcfe0 ~fcfegr ~ce ~tgr:v.tgr ~h:v.h in *)
    let fcfe_projection = Atemoya.Dcf_deterministic.project_fcfe
      ~ni:v.ni
      ~capx:v.capx ~d:v.d
      ~ca:v.ca ~cl:v.cl
      ~tdr:v.tdr ~years:v.h
      ~fcfegr
    in

    let pve = Atemoya.Dcf_deterministic.calculate_pve_from_projection
      ~fcfe_list:fcfe_projection ~ce ~tgr:v.tgr
    in

    let avg_fcfegr = Atemoya.Dcf_deterministic.average_growth_rate fcfe_projection in
    let avg_fcffgr = Atemoya.Dcf_deterministic.average_growth_rate fcff_projection in
    let implied_fcfegr = Atemoya.Dcf_deterministic.implied_fcfe_growth_rate_over_h
      ~fcfe0 ~ce ~tgr:v.tgr ~h:v.h ~so:v.so ~price:v.price in
    let implied_fcffgr = Atemoya.Dcf_deterministic.implied_fcff_growth_rate_over_h
      ~fcff0 ~wacc ~tgr:v.tgr ~h:v.h ~mve:v.mve ~mvb:v.mvb in

    Atemoya.Dcf_deterministic.display_valuation_summary
      ~ticker
      ~currency:v.currency
      ~ce ~cb ~wacc
      ~fcfe0 ~fcff0 ~fcfegr ~fcffgr
      ~capped_fcfegr ~capped_fcffgr ~floored_fcfegr ~floored_fcffgr
      ~fcfegr_clamp_upper:v.growth_clamp_fcfe_upper
      ~fcfegr_clamp_lower:v.growth_clamp_fcfe_lower
      ~fcffgr_clamp_upper:v.growth_clamp_fcff_upper
      ~fcffgr_clamp_lower:v.growth_clamp_fcff_lower
      ~tgr:v.tgr ~so:v.so ~price:v.price
      ~pvf ~pve
      ~avg_fcfegr ~avg_fcffgr
      ~implied_fcfegr ~implied_fcffgr
      ~h:v.h
      ~long_name:v.long_name
  ) assoc_list

let () =
  let args = Array.to_list Sys.argv |> List.tl in
  run args
