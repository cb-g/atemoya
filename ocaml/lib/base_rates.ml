open Boundary_t

let horizon = 5

let rec take n = function [] -> [] | x :: rest -> if n <= 0 then [] else x :: take (n - 1) rest

let compound path ~years =
  if years <= 0 || List.length path < years then None
  else
    let product = List.fold_left (fun acc g -> acc *. (1. +. g)) 1. (take years path) in
    if product <= 0. then None else Some ((product ** (1. /. float_of_int years)) -. 1.)

(* The share of the class at or above [x]: the percentile rank of [x] by linear
   interpolation between the percentile points, one minus it, held to the table's range. *)
let share_at_or_above percentiles x =
  let points = List.mapi (fun i v -> (float_of_int (i + 1) /. 100., v)) percentiles in
  let rec rank = function
    | (p0, v0) :: ((p1, v1) :: _ as rest) ->
        if x <= v0 then p0
        else if x <= v1 then if v1 = v0 then p1 else p0 +. ((p1 -. p0) *. (x -. v0) /. (v1 -. v0))
        else rank rest
    | [ (p, _) ] -> p
    | [] -> 0.5
  in
  Float.max 0.01 (Float.min 0.99 (1. -. rank points))

let scope_limits =
  [ "the record's growth is of free cash flow and the reference class's is of revenue: the comparison holds margins and capital intensity constant";
    "the growth the price needs is solved on the record's own base cash flow; where that base is held down, by a build-out, a trough or a lens that does not fit, the needed growth is overstated and its share understated";
    "survivors only: companies that filed no revenue at the end of a window are left out, so the class grew faster than everything that started in it";
    "the windows overlap and share the years since 2009, so the share is a frequency from one stretch of history and carries no error bar";
    "the size classes are nominal dollars, the same bounds in every year";
    "the outside view beside the declared belief: no fair value, margin of safety or signal reads it" ]

let of_inputs (table : Reference_t.base_rates option) ~currency ~revenue ~(inputs : inputs) ~implied =
  let reason r = (None, Some r) in
  match (table, currency, revenue) with
  | None, _, _ -> reason "base rates not fetched: run python/base_rates.py"
  | Some _, c, _ when c <> Some "USD" ->
      reason
        (Printf.sprintf "the reference class is in dollars and the record is in %s" (Option.value c ~default:"no currency"))
  | Some _, _, None -> reason "the latest fiscal period carries no revenue to place the company in a size class"
  | Some t, _, Some revenue -> (
      let fits (b : Reference_t.base_rate_table) =
        b.horizon_years = horizon && revenue >= b.lower && match b.upper with None -> true | Some u -> revenue < u
      in
      match (List.find_opt fits t.tables, compound inputs.growth_path ~years:horizon) with
      | None, _ -> reason (Printf.sprintf "no %d-year table for a starting revenue of %.4g dollars" horizon revenue)
      | _, None -> reason (Printf.sprintf "the record's growth path is shorter than %d years" horizon)
      | Some b, Some headline ->
          let needed =
            match implied with
            | Error r -> Error r
            | Ok (i : implied) -> (
                if i.level_name <> "implied_g0" then Error "the record's implied readout is not a starting growth"
                else
                  match i.level.value with
                  | None -> Error (Option.value i.level.reason ~default:"no implied starting growth")
                  | Some g0 -> (
                      let path =
                        Growth.path ~g0 ~terminal_growth_rate:inputs.terminal_growth_rate.value
                          ~lambda:inputs.mean_reversion_lambda.value ~projection_years:inputs.projection_years.value
                      in
                      match compound path ~years:horizon with
                      | Some g -> Ok g
                      | None -> Error "the implied path is shorter than the horizon"))
          in
          ( Some
              {
                horizon_years = horizon;
                starting_revenue = revenue;
                bucket = b.bucket;
                n = b.n;
                not_reported_at_end = b.not_reported_at_end;
                years = Printf.sprintf "%d to %d" t.first_year t.last_year;
                median_growth = List.nth b.percentiles 49;
                headline_growth = headline;
                headline_share = share_at_or_above b.percentiles headline;
                implied_growth = Result.to_option needed;
                implied_share = Option.map (share_at_or_above b.percentiles) (Result.to_option needed);
                implied_reason = (match needed with Error r -> Some r | Ok _ -> None);
                scope_limits;
              },
            None ))
