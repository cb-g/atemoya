open Boundary_t

let fields = [ "g0"; "fcff"; "currency"; "fiscal_year_ending"; "steady_fcff"; "why"; "as_of" ]

let check_entry name (json : Yojson.Safe.t) =
  match json with
  | `Assoc kv -> (
      let has k = List.mem_assoc k kv in
      let number k = match List.assoc_opt k kv with Some (`Float x) -> Some x | Some (`Int n) -> Some (float_of_int n) | _ -> None in
      let text k = match List.assoc_opt k kv with Some (`String s) -> Some s | _ -> None in
      let fail reason = Error (Printf.sprintf "growth %s: %s" name reason) in
      let unknown = List.filter (fun (k, _) -> not (List.mem k fields)) kv in
      let missing = List.filter (fun k -> not (has k)) [ "why"; "as_of" ] in
      let dated () =
        match (text "why", text "as_of") with
        | Some why, Some as_of -> (
            if String.trim why = "" then fail "why is empty"
            else match Date.days_between ~from:as_of ~until:as_of with Ok _ -> Ok () | Error e -> fail ("as_of: " ^ e))
        | _ -> fail "why and as_of must be strings"
      in
      if unknown <> [] then
        Error
          (Printf.sprintf
             "growth %s carries unknown field(s) %s; an entry is exactly one of g0, or fcff with currency and fiscal_year_ending and an optional steady_fcff, and why and as_of"
             name (String.concat ", " (List.map fst unknown)))
      else if missing <> [] then Error (Printf.sprintf "growth %s lacks %s" name (String.concat ", " missing))
      else
        match (has "g0", has "fcff") with
        | true, true -> fail "declares both g0 and fcff; an entry declares exactly one"
        | false, false -> fail "declares neither g0 nor fcff"
        | true, false -> (
            if has "currency" || has "fiscal_year_ending" || has "steady_fcff" then
              fail "a g0 entry carries no currency, fiscal_year_ending or steady_fcff"
            else
              match number "g0" with
              | None -> fail "g0 must be a number, in percentage points"
              | Some g when g <= -100. -> fail (Printf.sprintf "g0 %g is not above -100" g)
              | Some _ -> dated ())
        | false, true -> (
            let year = match List.assoc_opt "fiscal_year_ending" kv with Some (`Int n) -> Some n | _ -> None in
            match (number "fcff", text "currency", year) with
            | None, _, _ -> fail "fcff must be a number"
            | Some f, _, _ when f <= 0. ->
                fail (Printf.sprintf "fcff %g is not positive: a path to a non-positive free cash flow values nothing" f)
            | _, None, _ -> fail "an fcff entry needs currency, a string"
            | _, _, None -> fail "an fcff entry needs fiscal_year_ending, an integer year"
            | Some _, Some _, Some _ -> (
                match (has "steady_fcff", number "steady_fcff") with
                | true, None -> fail "steady_fcff must be a number"
                | true, Some s when s <= 0. -> fail (Printf.sprintf "steady_fcff %g is not positive" s)
                | _ -> dated ())))
  | _ -> Error (Printf.sprintf "growth %s is not an object" name)

let load_names_string text =
  match Yojson.Safe.from_string text with
  | exception Yojson.Json_error msg -> Error ("growth: " ^ msg)
  | `Assoc top -> (
      match List.assoc_opt "tickers" top with
      | Some (`Assoc entries) -> (
          let checked =
            List.fold_left (fun acc (name, json) -> match acc with Error _ -> acc | Ok () -> check_entry name json) (Ok ()) entries
          in
          match checked with
          | Error e -> Error e
          | Ok () -> (
              match Reference_j.name_growth_of_string text with
              | v -> Ok v
              | exception Atdgen_runtime.Oj_run.Error msg -> Error ("growth: " ^ msg)))
      | _ -> Error "growth: no tickers object")
  | _ -> Error "growth: not an object"

let load_names path =
  match In_channel.with_open_bin path In_channel.input_all with
  | text -> Result.map_error (fun m -> path ^ ": " ^ m) (load_names_string text)
  | exception Sys_error msg -> Error msg

let version (d : Reference_t.growth_declaration) =
  let number = function Some x -> Printf.sprintf "%.17g" x | None -> "" in
  let key =
    Printf.sprintf "%s|%s|%s|%s|%s|%s|%s" (number d.g0) (number d.fcff) (Option.value d.currency ~default:"")
      (match d.fiscal_year_ending with Some y -> string_of_int y | None -> "")
      (number d.steady_fcff) d.why d.as_of
  in
  Printf.sprintf "%s-%s-name" d.as_of (String.sub (Digest.to_hex (Digest.string key)) 0 7)

let path_of (i : inputs) ~g0 =
  Growth.path ~g0 ~terminal_growth_rate:i.terminal_growth_rate.value ~lambda:i.mean_reversion_lambda.value
    ~projection_years:i.projection_years.value

(* The flow in each projection year from the base along [growth_path], every year after
   [step_after] scaled by [ratio]. *)
let flows ~fcff ~growth_path ~step_after ~ratio =
  let _, _, acc =
    List.fold_left
      (fun (t, cash_flow, acc) g ->
        let cash_flow = cash_flow *. (1. +. g) in
        (t + 1, cash_flow, (if t > step_after then cash_flow *. ratio else cash_flow) :: acc))
      (1, fcff, []) growth_path
  in
  List.rev acc

(* The headline's arithmetic (Dcf.enterprise_value) on the stepped flows: the terminal value
   is on the last year's flow, which lies after the declared year or, where the declared year
   is the last, is scaled for the years beyond it. *)
let stepped_fair_value (i : inputs) ~g0 ~step_after ~ratio =
  let growth_path = path_of i ~g0 in
  let terminal_growth_rate = i.terminal_growth_rate.value in
  let discount t = (1. +. i.wacc) ** float_of_int t in
  let stepped = flows ~fcff:i.fcff ~growth_path ~step_after ~ratio in
  let pv_explicit = List.fold_left ( +. ) 0. (List.mapi (fun k cf -> cf /. discount (k + 1)) stepped) in
  let years = List.length stepped in
  let last = match List.rev stepped with cf :: _ -> cf | [] -> i.fcff *. ratio in
  let terminal = last *. (if years = step_after then ratio else 1.) *. (1. +. terminal_growth_rate) /. (i.wacc -. terminal_growth_rate) in
  let enterprise_value = pv_explicit +. (terminal /. discount years) in
  (enterprise_value -. i.net_debt) /. i.shares

let year_of date = int_of_string_opt (String.sub date 0 (min 4 (String.length date)))

let path_limits ~midcycle ~basis =
  let path_limit =
    if basis = "g0" then
      "the starting growth is the reader's declaration, decaying to terminal growth along the headline's own path; nothing here checks it against the statements"
    else
      "the starting growth is solved so the headline's own fading path, from the base free cash flow, reaches the declared free cash flow in the declared year: the years before it are that path and not a forecast of their own, and the years after it keep the path's growth, above terminal where the declared year comes early"
  in
  let midcycle_limit =
    if not midcycle then []
    else if basis = "g0" then
      [ "on the mid-cycle path the declared starting growth grows the through-cycle free cash flow on today's capital, not the latest year's" ]
    else
      [ "on the mid-cycle path the base is the through-cycle free cash flow on today's capital, so the declared free cash flow is read as the through-cycle level in its year: one for a peak or a trough year is carried as the normal level into the years after it and the terminal value" ]
  in
  path_limit :: midcycle_limit

let of_inputs (d : Reference_t.growth_declaration) ~midcycle ~currency (i : inputs) ~fair_value =
  let ( let* ) = Result.bind in
  let n = i.projection_years.value in
  let lambda = i.mean_reversion_lambda.value in
  let record_currency = Option.value currency ~default:"" in
  let* base_year =
    match year_of i.fiscal_period_end with
    | Some y -> Ok y
    | None -> Error (Printf.sprintf "the base period end %s carries no year" i.fiscal_period_end)
  in
  let* basis, g0, years_from_base, ratio =
    match (d.g0, d.fcff, d.fiscal_year_ending, d.currency) with
    | Some g, _, _, _ -> Ok ("g0", Float.round (g /. 100. *. 1e10) /. 1e10, None, 1.)
    | None, Some fcff, Some year, Some declared_currency -> (
        let t = year - base_year in
        if declared_currency <> record_currency then
          Error
            (Printf.sprintf
               "the declared free cash flow is in %s and the record's in %s: declare it in %s, the currency the record values in"
               declared_currency record_currency record_currency)
        else if t < 1 then
          Error
            (Printf.sprintf
               "the declared year %d is not after the base, the fiscal year ending %s: a declared free cash flow is for a year inside the projection, %d to %d"
               year i.fiscal_period_end (base_year + 1) (base_year + n))
        else if t > n then
          Error
            (Printf.sprintf
               "the declared year %d is beyond the projection's last year, the fiscal year ending in %d, %d years from the base ending %s"
               year (base_year + n) n i.fiscal_period_end)
        else
          let flow_at g0 =
            List.fold_left (fun cf g -> cf *. (1. +. g)) i.fcff
              (Growth.path ~g0 ~terminal_growth_rate:i.terminal_growth_rate.value ~lambda ~projection_years:t)
          in
          let lo, hi = Implied.level_domain in
          let ratio = match d.steady_fcff with Some s -> s /. fcff | None -> 1. in
          match Implied.bisect ~f:flow_at ~target:fcff ~lo ~hi ~tolerance:Implied.tolerance with
          | Implied.Root g0 -> Ok ("fcff", g0, Some t, ratio)
          | Implied.Beyond_high ->
              Error (Printf.sprintf "the declared free cash flow needs a starting growth above %.2f, the top of the domain" hi)
          | Implied.Beyond_low ->
              Error (Printf.sprintf "the declared free cash flow needs a starting growth below %.2f, the bottom of the domain" lo)
          | Implied.Flat -> Error "the path's free cash flow does not vary with the starting growth")
    | _ -> Error "the declaration names neither a starting growth nor a free cash flow with its currency and year"
  in
  let growth_path = path_of i ~g0 in
  let step_after = Option.value years_from_base ~default:n in
  let shadow_value =
    if d.steady_fcff = None then Implied.dcf_fair_value i ~g0 ~lambda else stepped_fair_value i ~g0 ~step_after ~ratio
  in
  let lower = i.growth_clamp_lower.value and upper = i.growth_clamp_upper.value in
  let outside_clamp = g0 < lower || g0 > upper in
  let above_roic = match i.roic with Some r -> g0 > r | None -> false in
  let steady_limit =
    match (basis, d.steady_fcff) with
    | "fcff", Some _ ->
        [ Printf.sprintf
            "after the declared year the flows and the terminal value run on the declared steady free cash flow, %.2f times the declared year's: the reader's assertion that capex returns to a steady level then, which nothing here checks"
            ratio ]
    | "fcff", None ->
        [ "with no steady free cash flow declared, the declared year's capex is carried into every year after it and into the terminal value: a year still building out is valued as if it built out forever" ]
    | _ -> []
  in
  let clamp_limit =
    if outside_clamp then
      [ Printf.sprintf "the starting growth %.4f is outside the clamp [%g, %g] the headline's estimate is held to; a declaration is not held to it" g0 lower upper ]
    else []
  in
  let roic_limit =
    match i.roic with
    | Some r when above_roic ->
        [ Printf.sprintf
            "the starting growth %.4f is above the return on capital %.4f, the cap the headline holds revenue history to: free cash flow can outgrow the return on capital for a few years as spending falls or margins widen, and reinvestment at that return cannot fund it for longer"
            g0 r ]
    | _ -> []
  in
  Ok
    {
      version = version d;
      why = d.why;
      as_of = d.as_of;
      basis;
      declared_g0 = (if basis = "g0" then Some g0 else None);
      declared_fcff = d.fcff;
      fiscal_year_ending = d.fiscal_year_ending;
      years_from_base;
      steady_fcff = d.steady_fcff;
      currency = record_currency;
      base_period_end = i.fiscal_period_end;
      base_fcff = i.fcff;
      projection_years = n;
      g0;
      headline_g0 = i.g0;
      outside_clamp;
      roic = i.roic;
      above_roic;
      growth_path;
      fcff_path = flows ~fcff:i.fcff ~growth_path ~step_after ~ratio;
      headline_fair_value = fair_value;
      fair_value = shadow_value;
      margin_of_safety = (shadow_value -. i.price) /. i.price;
      scope_limits =
        path_limits ~midcycle ~basis @ steady_limit @ clamp_limit @ roic_limit
        @ [ "a shadow on a reader's declaration: the record's fair value, margin of safety and signal are the headline's and are not moved by this block";
            Measured.declared_growth ];
    }

let model_name m = match Boundary_j.string_of_model m with s when String.length s >= 2 -> String.sub s 1 (String.length s - 2) | s -> s

let not_run ~model =
  match model with
  | Some ((`Dcf | `Dcf_midcycle) as m) ->
      Printf.sprintf "the %s did not complete on this record, so the declaration has nothing to run on; failed_reason says why" (model_name m)
  | Some m ->
      Printf.sprintf
        "the declared growth runs on the generic and mid-cycle DCF paths only, and this record is valued by %s, which has no free cash flow path"
        (model_name m)
  | None -> "no model ran on this record, so the declaration has nothing to run on; failed_reason says why"
