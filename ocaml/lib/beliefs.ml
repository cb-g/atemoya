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

let load_classes_string text =
  Result.bind (check_table ~key:"classes" text) (fun () -> parse Reference_j.class_beliefs_of_string text)

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

let resolve ~(classes : Reference_t.class_beliefs) ?(names : Reference_t.name_beliefs option) ~ticker ~entity_class
    ~terminal_growth_rate () =
  let of_name (b : Reference_t.belief) : belief =
    { mean = pp b.mean; sd = pp b.sd; floor = pp b.floor; ceiling = pp b.ceiling; why = b.why; as_of = b.as_of }
  in
  match Option.bind names (fun (n : Reference_t.name_beliefs) -> List.assoc_opt ticker n.tickers) with
  | Some b -> Some (of_name b, Printf.sprintf "per-name entry for %s, absolute" ticker)
  | None -> (
      match List.assoc_opt entity_class classes.classes with
      | Some b ->
          (* offsets applied in percentage points, so 3% - 2 pp is exactly 1% *)
          let around offset = tidy (((terminal_growth_rate *. 100.) +. offset) /. 100.) in
          Some
            ( { mean = around b.mean; sd = pp b.sd; floor = around b.floor; ceiling = around b.ceiling; why = b.why;
                as_of = b.as_of },
              Printf.sprintf "class default for %s: offsets around the country's terminal growth %.4f" entity_class
                terminal_growth_rate )
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

let implied_terminal_growth ~f ~price ~rate =
  let lo = -0.10 and hi = rate -. 0.0005 in
  let r =
    match Implied.bisect ~f ~target:price ~lo ~hi ~tolerance:Implied.tolerance with
    | Implied.Root g -> { value = Some g; reason = None }
    | Implied.Beyond_high -> { value = None; reason = Some "the price needs long-run growth at or above the discount rate" }
    | Implied.Beyond_low -> { value = None; reason = Some "the price is below the value at -10% long-run growth" }
    | Implied.Flat -> { value = None; reason = Some "fair value does not vary with long-run growth" }
  in
  (r, [ lo; hi ])

let note =
  "probability_overpaid is a statement of the declared belief, not a frequency: P(long-run growth below what the \
   price needs) under the truncated normal beside it; revise the belief by a dated declaration when evidence \
   warrants, never because of what this number looks like"

let readout (b : belief) ~source ~source_kind ~f ~price ~rate ~fair_value =
  let implied, domain = implied_terminal_growth ~f ~price ~rate in
  let probability, reason =
    match (implied.value, implied.reason) with
    | Some g, _ -> (cdf b g, None)
    | None, Some r when r = "the price is below the value at -10% long-run growth" -> (0., Some r)
    | None, Some r when r = "fair value does not vary with long-run growth" -> ((if fair_value < price then 1. else 0.), Some r)
    | None, r -> (1., r)
  in
  {
    declared = b;
    source;
    belief_version = version b ~source_kind;
    implied_terminal_growth = implied;
    implied_domain = domain;
    probability_overpaid = probability;
    probability_reason = reason;
    value_surplus = (fair_value -. price) /. price;
    note;
  }
