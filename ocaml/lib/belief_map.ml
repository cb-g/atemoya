open Boundary_t

let map_model = "undecayed growth for N years, then terminal"
let growth_domain = (0., 0.5)
let growth_step = 0.02
let horizon_max = 40
let growth_grid = List.init 26 (fun i -> float_of_int i /. 50.)
let horizon_grid = List.init horizon_max (fun i -> i + 1)

let fair_value ~base ~rate ~terminal ~net_debt ~shares ~growth ~years =
  let rec explicit t cash acc =
    if t > years then (acc, cash)
    else
      let cash = cash *. (1. +. growth) in
      explicit (t + 1) cash (acc +. (cash /. ((1. +. rate) ** float_of_int t)))
  in
  let pv, last = explicit 1 base 0. in
  let terminal_value = last *. (1. +. terminal) /. (rate -. terminal) in
  ((pv +. (terminal_value /. ((1. +. rate) ** float_of_int years))) -. net_debt) /. shares

(* What the map reads from each model: the base, its rate, terminal growth, net debt and
   shares (0 and 1 on a per-share base), and the observed start. *)
let parameters (m : model_inputs) =
  match m with
  | `Dcf i -> Ok ("fcff", i.fcff, "wacc", i.wacc, i.terminal_growth_rate.value, i.net_debt, i.shares, i.g0)
  | `Dcf_midcycle mc ->
      let i = mc.dcf in
      Ok ("fcff_mid", i.fcff, "wacc", i.wacc, i.terminal_growth_rate.value, i.net_debt, i.shares, i.g0)
  | `Reit_ffo_dividend i ->
      Ok ("dividend_per_share", i.dividend_per_share, "cost_of_equity", i.cost_of_equity, i.terminal_growth_rate.value, 0., 1., i.g0)
  | `Residual_income _ | `Residual_income_insurer _ ->
      Error "no belief map: the residual-income path has no growth-then-terminal structure to hold a growth on"

let contour ~base ~rate ~terminal ~net_debt ~shares ~price =
  let lo, hi = growth_domain in
  List.map
    (fun years ->
      let f growth = fair_value ~base ~rate ~terminal ~net_debt ~shares ~growth ~years in
      let growth =
        match Implied.bisect ~f ~target:price ~lo ~hi ~tolerance:Implied.tolerance with
        | Implied.Root g -> { value = Some g; reason = None }
        | Implied.Beyond_high ->
            { value = None;
              reason = Some (Printf.sprintf "no growth in [0%%, 50%%] held for %d years reaches the price: fair value at 50%% is %.2f" years (f hi)) }
        | Implied.Beyond_low ->
            { value = None; reason = Some (Printf.sprintf "the price is below fair value at zero growth for %d years (%.2f)" years (f lo)) }
        | Implied.Flat -> { value = None; reason = Some "fair value does not vary with growth" }
      in
      { years; growth })
    horizon_grid

let of_inputs (m : model_inputs) ~price =
  match parameters m with
  | Error reason -> Error reason
  | Ok (base_name, base, rate_name, rate, terminal, net_debt, shares, observed_growth) ->
      let lo, hi = growth_domain in
      Ok
        {
          map_model;
          base_name;
          base;
          rate_name;
          rate;
          terminal_growth_rate = terminal;
          net_debt;
          shares;
          observed_growth;
          growth_domain = [ lo; hi ];
          growth_step;
          horizon_max;
          price_contour = contour ~base ~rate ~terminal ~net_debt ~shares ~price;
          solver = "bisection";
          tolerance = Implied.tolerance;
        }

let grid (b : belief_map) ~ticker ~price =
  {
    ticker;
    map_model = b.map_model;
    price;
    observed_growth = b.observed_growth;
    growth_grid;
    horizon_grid;
    fair_values =
      List.map
        (fun growth ->
          List.map
            (fun years ->
              fair_value ~base:b.base ~rate:b.rate ~terminal:b.terminal_growth_rate ~net_debt:b.net_debt ~shares:b.shares
                ~growth ~years)
            horizon_grid)
        growth_grid;
    price_contour = b.price_contour;
  }
