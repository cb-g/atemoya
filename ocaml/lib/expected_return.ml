open Boundary_t

let min_names = 10
let benchmark = "SPY"
let steps = 1200

let svix2 ?(lower = -3.) ?(upper = 3.) (p : Market_implied.svi) ~forward =
  let price k =
    let strike = forward *. exp k in
    let call = Market_implied.black_call ~forward ~strike ~w:(Market_implied.total_variance p k) in
    let otm = if k < 0. then call -. (forward -. strike) else call in
    (* dK = F e^k dk *)
    Float.max 0. otm *. strike
  in
  let h = (upper -. lower) /. float_of_int steps in
  let sum = ref (price lower +. price upper) in
  for i = 1 to steps - 1 do
    let k = lower +. (float_of_int i *. h) in
    sum := !sum +. ((if i mod 2 = 1 then 4. else 2.) *. price k)
  done;
  2. /. (forward *. forward) *. (!sum *. h /. 3.)

let scope_limits =
  [ "under Martin and Wagner's assumptions the formula is an equality; without them it is a lower bound, and it is the market's risk pricing, not a forecast";
    "the average runs over the names the options store holds with a usable chain, weighted by market capitalisation, not over every index member as in the paper";
    "each name's variance is read at its own longest expiry and annualised, so the horizons differ by a few months across names";
    "the integral runs only between the lowest and the highest quoted strike the fit read, so the variance beyond them is left out and each figure understates; a name quoted over a narrower range is understated more";
    "single-stock options are American and the inversion is European, which raises a long-dated put's implied volatility and the variance with it";
    "a lens beside CAPM and the declared required return: no fair value, margin of safety or signal reads it" ]

type leg = { snapshot_date : string; expiry : string; years : float; annual : float; lower : float; upper : float }

let leg_of (chain : option_chain) ~rf =
  let spot = chain.underlying_close in
  match Market_implied.select_expiry chain.quotes ~spot ~snapshot_date:chain.snapshot_date with
  | Error r -> Error r
  | Ok (expiry, days, _, _) -> (
      match Market_implied.fit_expiry chain ~rf ~expiry ~days with
      | Error r -> Error r
      | Ok f ->
          let years = float_of_int days /. 365. in
          (* Only between the lowest and the highest strike the fit read: the smile beyond
             them is an extrapolation, and the integrand weights high strikes by the strike
             itself, so an unquoted upper wing would carry much of the answer. *)
          let ks = List.map fst f.points in
          let lower = List.fold_left Float.min 0. ks and upper = List.fold_left Float.max 0. ks in
          Ok { snapshot_date = chain.snapshot_date; expiry; years; annual = svix2 ~lower ~upper f.params ~forward:f.forward /. years; lower; upper })

let annotate ~lookup ~rf ~caps (records : valuation list) =
  let with_reason r (v : valuation) = { v with options_expected_return = None; options_expected_return_reason = Some r } in
  let is_fund (v : valuation) = v.entity_class = Some `Wrapper in
  let stocks f = List.map (fun (v : valuation) -> if is_fund v then v else f v) records in
  match rf with
  | Error why -> stocks (with_reason ("no risk-free rate for the benchmark's currency: " ^ why))
  | Ok rf -> (
      match Result.bind (lookup benchmark) (leg_of ~rf) with
      | Error why -> stocks (with_reason (Printf.sprintf "no benchmark variance from %s: %s" benchmark why))
      | Ok market ->
          let legs =
            List.filter_map
              (fun (v : valuation) ->
                if is_fund v then None
                else
                  Some
                    ( v.ticker,
                      match Result.bind (lookup v.ticker) (leg_of ~rf) with
                      | Error r -> Error r
                      | Ok l when l.snapshot_date <> market.snapshot_date ->
                          Error
                            (Printf.sprintf "the name's chain is from %s and the benchmark's from %s" l.snapshot_date
                               market.snapshot_date)
                      | Ok l -> Ok l ))
              records
          in
          let weighted =
            List.filter_map
              (fun (ticker, leg) ->
                match (leg, List.assoc_opt ticker caps) with
                | Ok l, Some cap when cap > 0. -> Some (cap, l.annual)
                | _ -> None)
              legs
          in
          let n = List.length weighted in
          if n < min_names then
            stocks
              (with_reason
                 (Printf.sprintf "%d names in the run carry a usable chain and a market capitalisation on %s; the average needs %d" n
                    market.snapshot_date min_names))
          else
            let total = List.fold_left (fun acc (cap, _) -> acc +. cap) 0. weighted in
            let average = List.fold_left (fun acc (cap, x) -> acc +. (cap *. x)) 0. weighted /. total in
            stocks (fun v ->
                match List.assoc_opt v.ticker legs with
                | None -> v
                | Some (Error r) -> with_reason r v
                | Some (Ok l) ->
                    let excess = (1. +. rf) *. (market.annual +. ((l.annual -. average) /. 2.)) in
                    {
                      v with
                      options_expected_return_reason = None;
                      options_expected_return =
                        Some
                          {
                            snapshot_date = l.snapshot_date;
                            expiry = l.expiry;
                            horizon_years = l.years;
                            risk_free_rate = rf;
                            svix2 = l.annual;
                            strike_range = [ exp l.lower; exp l.upper ];
                            benchmark;
                            benchmark_expiry = market.expiry;
                            market_svix2 = market.annual;
                            average_svix2 = average;
                            names_in_average = n;
                            in_average = (match List.assoc_opt v.ticker caps with Some c -> c > 0. | None -> false);
                            expected_excess_return = excess;
                            expected_return = rf +. excess;
                            scope_limits;
                          };
                    }))
