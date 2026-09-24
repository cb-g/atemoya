open Boundary_t

let bracket_convention =
  "the latest listed expiry strictly before the release and the earliest on or after it; an \
   expiry on the release date is the later leg, since a release is dated by its filing day \
   and an option expiring that day is still exposed to one made before the open"

let listed (chain : option_chain) =
  List.sort_uniq compare (List.map (fun (q : option_quote) -> q.expiration) chain.quotes)
  |> List.filter (fun expiry ->
         match Date.days_between ~from:chain.snapshot_date ~until:expiry with
         | Ok days -> days > 0
         | Error _ -> false)

let bracket (chain : option_chain) ~next =
  let expiries = listed chain in
  (* ISO dates order lexicographically, which is the whole reason the store writes them so. *)
  let before = List.filter (fun e -> e < next) expiries in
  let after = List.filter (fun e -> e >= next) expiries in
  match (before, after) with
  | [], _ -> Error (Printf.sprintf "no listed expiry precedes %s" next)
  | _, [] -> Error (Printf.sprintf "no listed expiry falls on or after %s" next)
  | before, after -> Ok (List.nth before (List.length before - 1), List.hd after)

let total_variance_at (chain : option_chain) ~rf ~expiry =
  match Date.days_between ~from:chain.snapshot_date ~until:expiry with
  | Error r -> Error r
  | Ok days -> (
      match Market_implied.fit_expiry chain ~rf ~expiry ~days with
      | Error r -> Error (Printf.sprintf "the smile at %s would not fit: %s" expiry r)
      (* w(0) is the total variance AT THE FORWARD, which is what the subtraction wants:
         both legs are then on the same forward, the one put-call parity gives. *)
      | Ok (f : Market_implied.expiry_fit) -> Ok (Market_implied.total_variance f.params 0.))

let implied_of (chain : option_chain) ~rf ~next =
  match bracket chain ~next with
  | Error r -> Error r
  | Ok (earlier, later) -> (
      match (total_variance_at chain ~rf ~expiry:earlier, total_variance_at chain ~rf ~expiry:later) with
      | Error r, _ | _, Error r -> Error r
      | Ok w_earlier, Ok w_later ->
          let event = w_later -. w_earlier in
          if event <= 0. then
            Error
              (Printf.sprintf
                 "the term structure carries no event premium: the total variance at %s is %.6f \
                  against %.6f at %s, so the subtraction is negative"
                 later w_later w_earlier earlier)
          else
            Ok
              {
                snapshot_date = chain.snapshot_date;
                earlier_expiry = earlier;
                later_expiry = later;
                earlier_total_variance = w_earlier;
                later_total_variance = w_later;
                event_variance = event;
                implied_move = sqrt event;
                forward_convention =
                  "put-call parity at the straddle nearest spot on each expiry, the same \
                   convention on both legs; " ^ bracket_convention;
              })

let spans ~expiry ~next = expiry >= next

let block_of ~(calendar : earnings_calendar) ~valued_on ~implied =
  let days_to_next =
    match Date.days_between ~from:valued_on ~until:calendar.next_date with Ok d -> d | Error _ -> 0
  in
  let implied_block = match implied with Ok i -> Some i | Error _ -> None in
  let implied_reason = match implied with Error r -> Some r | Ok _ -> None in
  let implied_over_realised =
    match (implied_block, calendar.realised_median_abs_excess) with
    | Some i, Some realised when realised > 0. -> Some (i.implied_move /. realised)
    | _ -> None
  in
  { calendar; days_to_next; implied = implied_block; implied_reason; implied_over_realised }
