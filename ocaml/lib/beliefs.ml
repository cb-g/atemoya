open Boundary_t

let fields = [ "mean"; "sd"; "floor"; "ceiling"; "why"; "as_of" ]

let check_belief name (json : Yojson.Safe.t) =
  match json with
  | `Assoc kv ->
      let unknown = List.filter (fun (k, _) -> not (List.mem k fields)) kv in
      let missing = List.filter (fun k -> not (List.mem_assoc k kv)) fields in
      if unknown <> [] then
        Error
          (Printf.sprintf "belief %s carries unknown field(s) %s; a belief is exactly %s" name
             (String.concat ", " (List.map fst unknown)) (String.concat ", " fields))
      else if missing <> [] then Error (Printf.sprintf "belief %s lacks %s" name (String.concat ", " missing))
      else
        let number k = match List.assoc k kv with `Float x -> Some x | `Int n -> Some (float_of_int n) | _ -> None in
        let text k = match List.assoc k kv with `String s -> Some s | _ -> None in
        (match (number "mean", number "sd", number "floor", number "ceiling", text "why", text "as_of") with
        | Some _, Some sd, Some floor, Some ceiling, Some why, Some as_of ->
            if sd <= 0. then Error (Printf.sprintf "belief %s: sd %g is not positive" name sd)
            else if floor >= ceiling then Error (Printf.sprintf "belief %s: floor %g is not below ceiling %g" name floor ceiling)
            else if String.trim why = "" then Error (Printf.sprintf "belief %s: why is empty" name)
            else (
              match Date.days_between ~from:as_of ~until:as_of with
              | Ok _ -> Ok ()
              | Error e -> Error (Printf.sprintf "belief %s: as_of: %s" name e))
        | _ -> Error (Printf.sprintf "belief %s: mean, sd, floor and ceiling must be numbers, why and as_of strings" name))
  | _ -> Error (Printf.sprintf "belief %s is not an object" name)

let check_table ~key text =
  match Yojson.Safe.from_string text with
  | exception Yojson.Json_error msg -> Error ("beliefs: " ^ msg)
  | `Assoc top -> (
      match List.assoc_opt key top with
      | Some (`Assoc entries) ->
          List.fold_left
            (fun acc (name, json) -> match acc with Error _ -> acc | Ok () -> check_belief name json)
            (Ok ()) entries
      | _ -> Error (Printf.sprintf "beliefs: no %s object" key))
  | _ -> Error "beliefs: not an object"

let parse reader text =
  match reader text with v -> Ok v | exception Atdgen_runtime.Oj_run.Error msg -> Error ("beliefs: " ^ msg)

let check_optional_table ~key text =
  match Yojson.Safe.from_string text with
  | `Assoc top when List.mem_assoc key top -> check_table ~key text
  | _ -> Ok ()

(* The correlation section (35): exactly common, why, as_of and an optional pairs list of
   exactly a, b, rho, why, as_of; common in [0, 1), rho in (-1, 1). *)
let check_correlation text =
  let exact name (kv : (string * Yojson.Safe.t) list) required optional =
    let unknown = List.filter (fun (k, _) -> not (List.mem k (required @ optional))) kv in
    let missing = List.filter (fun k -> not (List.mem_assoc k kv)) required in
    if unknown <> [] then
      Error (Printf.sprintf "correlation %s carries unknown field(s) %s" name (String.concat ", " (List.map fst unknown)))
    else if missing <> [] then Error (Printf.sprintf "correlation %s lacks %s" name (String.concat ", " missing))
    else Ok ()
  in
  let number kv k = match List.assoc_opt k kv with Some (`Float x) -> Some x | Some (`Int n) -> Some (float_of_int n) | _ -> None in
  match Yojson.Safe.from_string text with
  | `Assoc top -> (
      match List.assoc_opt "correlation" top with
      | None -> Ok ()
      | Some (`Assoc kv) -> (
          match exact "section" kv [ "common"; "why"; "as_of" ] [ "pairs" ] with
          | Error e -> Error e
          | Ok () -> (
              match number kv "common" with
              | Some c when c < 0. || c >= 1. -> Error (Printf.sprintf "correlation common %g is not in [0, 1)" c)
              | None -> Error "correlation common must be a number"
              | Some _ -> (
                  match List.assoc_opt "pairs" kv with
                  | None | Some (`List []) -> Ok ()
                  | Some (`List pairs) ->
                      List.fold_left
                        (fun acc pair ->
                          match (acc, pair) with
                          | Error _, _ -> acc
                          | Ok (), `Assoc pkv -> (
                              match exact "pair" pkv [ "a"; "b"; "rho"; "why"; "as_of" ] [] with
                              | Error e -> Error e
                              | Ok () -> (
                                  match number pkv "rho" with
                                  | Some r when r <= -1. || r >= 1. -> Error (Printf.sprintf "correlation pair rho %g is not in (-1, 1)" r)
                                  | None -> Error "correlation pair rho must be a number"
                                  | Some _ -> Ok ()))
                          | Ok (), _ -> Error "correlation pair is not an object")
                        (Ok ()) pairs
                  | Some _ -> Error "correlation pairs must be a list")))
      | Some _ -> Error "correlation must be an object")
  | _ -> Error "beliefs: not an object"

let load_classes_string text =
  Result.bind (check_table ~key:"classes" text) (fun () ->
      Result.bind (check_optional_table ~key:"names" text) (fun () ->
          Result.bind (check_correlation text) (fun () -> parse Reference_j.class_beliefs_of_string text)))

let load_names_string text =
  Result.bind (check_table ~key:"tickers" text) (fun () -> parse Reference_j.name_beliefs_of_string text)

let read path loader =
  match In_channel.with_open_bin path In_channel.input_all with
  | text -> Result.map_error (fun m -> path ^ ": " ^ m) (loader text)
  | exception Sys_error msg -> Error msg

let load_classes path = read path load_classes_string
let load_names path = read path load_names_string

(* Percentage points to a decimal fraction, rounded at the tenth decimal so 3% - 2 pp is
   exactly 1% on the record and in the version hash. *)
let tidy x = Float.round (x *. 1e10) /. 1e10
let pp x = tidy (x /. 100.)

(* (58) The belief's parameter. On the DCF-shaped paths it is long-run growth and the class
   offsets are measured around the country's terminal growth; on the residual-income path it
   is the long-run return on equity and they are measured around the cost of equity. The
   anchor and its name are given by the caller so one resolver serves both. *)
let resolve ~(classes : Reference_t.class_beliefs) ?(names : Reference_t.name_beliefs option) ~ticker ~entity_class
    ~anchor ~anchor_name () =
  let of_name (b : Reference_t.belief) : belief =
    { mean = pp b.mean; sd = pp b.sd; floor = pp b.floor; ceiling = pp b.ceiling; why = b.why; as_of = b.as_of }
  in
  let extra = Option.bind names (fun (n : Reference_t.name_beliefs) -> List.assoc_opt ticker n.tickers) in
  match (extra, List.assoc_opt ticker classes.names) with
  | Some b, _ -> Some (of_name b, Printf.sprintf "per-name entry for %s from the --beliefs file, absolute" ticker)
  | None, Some b -> Some (of_name b, Printf.sprintf "per-name entry for %s, absolute" ticker)
  | None, None -> (
      match List.assoc_opt entity_class classes.classes with
      | Some b ->
          (* offsets applied in percentage points, so 3% - 2 pp is exactly 1% *)
          let around offset = tidy (((anchor *. 100.) +. offset) /. 100.) in
          Some
            ( { mean = around b.mean; sd = pp b.sd; floor = around b.floor; ceiling = around b.ceiling; why = b.why;
                as_of = b.as_of },
              Printf.sprintf "class default for %s: offsets around %s %.4f" entity_class anchor_name anchor )
      | None -> None)

let version (b : belief) ~source_kind =
  let key = Printf.sprintf "%.17g|%.17g|%.17g|%.17g|%s|%s" b.mean b.sd b.floor b.ceiling b.why b.as_of in
  Printf.sprintf "%s-%s-%s" b.as_of (String.sub (Digest.to_hex (Digest.string key)) 0 7) source_kind

let phi z = 0.5 *. (1. +. Float.erf (z /. sqrt 2.))

let cdf (b : belief) x =
  if x <= b.floor then 0.
  else if x >= b.ceiling then 1.
  else
    let z v = (v -. b.mean) /. b.sd in
    let lo = phi (z b.floor) and hi = phi (z b.ceiling) in
    if hi -. lo <= 0. then if x < Float.min b.ceiling (Float.max b.floor b.mean) then 0. else 1.
    else Float.min 1. (Float.max 0. ((phi (z x) -. lo) /. (hi -. lo)))

(* (58) Which end the solver came out of, so the probability mapping below reads a tag
   rather than comparing reason strings, and serves both parameters. *)
type outcome = Solved | Above | Below | Flat

let implied_terminal_growth ~f ~price ~rate =
  let lo = -0.10 and hi = rate -. 0.0005 in
  let r, outcome =
    match Implied.bisect ~f ~target:price ~lo ~hi ~tolerance:Implied.tolerance with
    | Implied.Root g -> ({ value = Some g; reason = None }, Solved)
    | Implied.Beyond_high -> ({ value = None; reason = Some "the price needs long-run growth at or above the discount rate" }, Above)
    | Implied.Beyond_low -> ({ value = None; reason = Some "the price is below the value at -10% long-run growth" }, Below)
    | Implied.Flat -> ({ value = None; reason = Some "fair value does not vary with long-run growth" }, Flat)
  in
  (r, [ lo; hi ], outcome)

(* (58) The same, in the long-run return on equity, over ten points under the cost of equity
   to thirty over it. *)
let implied_roe_target ~f ~price ~cost_of_equity =
  let lo, hi = Implied.roe_target_domain ~cost_of_equity in
  let r, outcome =
    match Implied.bisect ~f ~target:price ~lo ~hi ~tolerance:Implied.tolerance with
    | Implied.Root x -> ({ value = Some x; reason = None }, Solved)
    | Implied.Beyond_high ->
        ({ value = None; reason = Some (Printf.sprintf "the price needs a long-run return above the domain, %.0f points over the cost of equity" ((hi -. cost_of_equity) *. 100.)) }, Above)
    | Implied.Beyond_low ->
        ({ value = None; reason = Some (Printf.sprintf "the price is below the value at a long-run return %.0f points under the cost of equity" ((cost_of_equity -. lo) *. 100.)) }, Below)
    | Implied.Flat -> ({ value = None; reason = Some "fair value does not vary with the long-run return on equity" }, Flat)
  in
  (r, [ lo; hi ], outcome)

let surplus_points = 41

let surplus_curve (b : belief) ~f ~price =
  List.init surplus_points (fun k ->
      let growth = b.floor +. ((b.ceiling -. b.floor) *. float_of_int k /. float_of_int (surplus_points - 1)) in
      { growth; surplus = (f growth -. price) /. price })

let note =
  "probability_overpaid is a statement of the declared belief, not a frequency: P(long-run growth below what the \
   price needs) under the truncated normal beside it; revise the belief by a dated declaration when evidence \
   warrants, never because of what this number looks like"

let roe_note =
  "probability_overpaid is a statement of the declared belief, not a frequency: P(the long-run return on equity \
   below what the price needs) under the truncated normal beside it; the belief is centred on the cost of equity, \
   where the long run grants no franchise value; revise it by a dated declaration when evidence warrants, never \
   because of what this number looks like"

let growth_axis = "long_run_growth"
let roe_axis = "long_run_return_on_equity"

let readout (b : belief) ~source ~source_kind ~axis ~(implied : readout) ~implied_domain ~outcome ~price ~fair_value =
  let probability, reason =
    match (outcome, implied.value) with
    | Solved, Some x -> (cdf b x, None)
    | Solved, None -> (1., implied.reason)
    | Below, _ -> (0., implied.reason)
    | Flat, _ -> ((if fair_value < price then 1. else 0.), implied.reason)
    | Above, _ -> (1., implied.reason)
  in
  let on_roe = axis = roe_axis in
  {
    declared = b;
    source;
    belief_version = version b ~source_kind;
    belief_parameter = axis;
    implied_terminal_growth = (if on_roe then None else Some implied);
    implied_roe_target = (if on_roe then Some implied else None);
    implied_domain;
    probability_overpaid = probability;
    probability_reason = reason;
    value_surplus = (fair_value -. price) /. price;
    note = (if on_roe then roe_note else note);
  }
