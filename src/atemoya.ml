open Yojson.Basic.Util
open Valuation
open Unix
open Printf

(* ========================= *)
(* logging setup             *)
(* ========================= *)

let setup_logging (tickers : string list) : unit =
  let timestamp = Unix.time () |> int_of_float |> string_of_int in
  let joined_tickers = String.concat "_" tickers in
  let filename = Printf.sprintf "src/valuation/logs/valuation_%s_%s.log" timestamp joined_tickers in

  let _ = Sys.command "mkdir -p src/valuation/logs" in
  let log_fd = openfile filename [O_WRONLY; O_CREAT; O_TRUNC] 0o644 in
  let _ = dup2 log_fd stdout in
  let _ = dup2 log_fd stderr in

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
  }

let default_json_path = "src/valuation/data/valuation_data.json"

let () =
  let json = Yojson.Basic.from_file default_json_path in
  let assoc_list = to_assoc json in
  let tickers = List.map fst assoc_list in
  setup_logging tickers;

  List.iter (fun (ticker, data) ->
    let v = parse_inputs data in

    if v.total_debt = 0.0 then invalid_arg "Total debt cannot be zero.";
    let cb = v.interest_expense /. v.total_debt in

    let beta_l = calculate_leveraged_beta ~beta_u:v.beta_u ~ctr:v.ctr ~mvb:v.mvb ~mve:v.mve in
    let ce = calculate_cost_of_equity ~rfr:v.rfr ~beta_l ~erp:v.erp in
    let wacc = calculate_wacc ~mve:v.mve ~mvb:v.mvb ~ce ~cb ~ctr:v.ctr in
    let fcfe0 = calculate_fcfe ~ni:v.ni ~capx:v.capx ~d:v.d ~ca:v.ca ~cl:v.cl ~prev_ca:v.prev_ca ~prev_cl:v.prev_cl ~net_borrowing:0.0 in
    let fcff0 = calculate_fcff ~ebit:v.ebit ~ctr:v.ctr ~b:v.d ~capx:v.capx ~ca:v.ca ~cl:v.cl ~prev_ca:v.prev_ca ~prev_cl:v.prev_cl in
    let raw_fcfegr = calculate_fcfe_growth_rate ~ni:v.ni ~bve:v.bve ~dp:v.dp in
    let fcfegr = min raw_fcfegr 0.25 in
    let capped_fcfegr = raw_fcfegr > 0.25 in
    let raw_fcffgr = calculate_fcff_growth_rate
      ~ebit:v.ebit ~ite:v.ite ~ic:v.ic
      ~capx:v.capx ~d:v.d ~ca:v.ca ~cl:v.cl
    in
    let fcffgr =
      if raw_fcffgr > 0.25 then 0.25
      else if raw_fcffgr < -0.25 then -0.25
      else raw_fcffgr
    in
    let capped_fcffgr = raw_fcffgr > 0.25 in
    let floored_fcffgr = raw_fcffgr < -0.25 in
    

    (* let pvf = calculate_pvf ~fcff0 ~fcffgr ~wacc ~tgr:v.tgr ~h:v.h in *)
    let fcff_projection = project_fcff 
      ~ebit:v.ebit ~ctr:v.ctr
      ~capx:v.capx ~d:v.d ~ca:v.ca ~cl:v.cl
      ~years:v.h 
      ~fcffgr
    in
    let pvf = calculate_pvf_from_projection
      ~fcff_list:fcff_projection ~wacc ~tgr:v.tgr
    in

    (* let pve = calculate_pve ~fcfe0 ~fcfegr ~ce ~tgr:v.tgr ~h:v.h in *)
    let fcfe_projection = project_fcfe
      ~ni:v.ni
      ~capx:v.capx ~d:v.d
      ~ca:v.ca ~cl:v.cl
      ~tdr:v.tdr ~years:v.h
      ~fcfegr
    in

    let pve = calculate_pve_from_projection
      ~fcfe_list:fcfe_projection ~ce ~tgr:v.tgr
    in

    let avg_fcfegr = average_growth_rate fcfe_projection in
    let avg_fcffgr = average_growth_rate fcff_projection in
    let implied_fcfegr = implied_fcfe_growth_rate_over_h
      ~fcfe0 ~ce ~tgr:v.tgr ~h:v.h ~so:v.so ~price:v.price in
    let implied_fcffgr = implied_fcff_growth_rate_over_h
      ~fcff0 ~wacc ~tgr:v.tgr ~h:v.h ~mve:v.mve ~mvb:v.mvb in

    display_valuation_summary
      ~ticker
      ~currency:v.currency
      ~ce ~cb ~wacc
      ~fcfe0 ~fcff0 ~fcfegr ~fcffgr
      ~capped_fcfegr ~capped_fcffgr ~floored_fcffgr
      ~tgr:v.tgr ~so:v.so ~price:v.price
      ~pvf ~pve
      ~avg_fcfegr ~avg_fcffgr
      ~implied_fcfegr ~implied_fcffgr
      ~h:v.h
  ) assoc_list
