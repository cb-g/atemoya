open Boundary_t

type svi = { a : float; b : float; rho : float; m : float; sigma : float }

let min_days = 365
let min_strikes_each_side = 8
let quantile_levels = [ 0.05; 0.25; 0.50; 0.75; 0.95 ]

let norm_cdf x = 0.5 *. (1. +. Float.erf (x /. sqrt 2.))
let norm_pdf x = exp (-0.5 *. x *. x) /. sqrt (2. *. Float.pi)

let black_call ~forward ~strike ~w =
  if w <= 0. then Float.max (forward -. strike) 0.
  else
    let s = sqrt w in
    let k = log (strike /. forward) in
    let d1 = (-.k /. s) +. (s /. 2.) and d2 = (-.k /. s) -. (s /. 2.) in
    (forward *. norm_cdf d1) -. (strike *. norm_cdf d2)

let black_put ~forward ~strike ~w = black_call ~forward ~strike ~w -. forward +. strike

(* Black's price is increasing in total variance, so bisection on w. *)
let implied_total_variance ~right ~forward ~strike ~price =
  let f w = match right with `Call -> black_call ~forward ~strike ~w | `Put -> black_put ~forward ~strike ~w in
  let intrinsic = f 0. in
  let upper = match right with `Call -> forward | `Put -> strike in
  if price <= intrinsic || price >= upper then None
  else
    let lo = ref 1e-10 and hi = ref 25. in
    for _ = 1 to 200 do
      let mid = 0.5 *. (!lo +. !hi) in
      if f mid < price then lo := mid else hi := mid
    done;
    Some (0.5 *. (!lo +. !hi))

let total_variance p k =
  let d = k -. p.m in
  p.a +. (p.b *. ((p.rho *. d) +. sqrt ((d *. d) +. (p.sigma *. p.sigma))))

let dw p k =
  let d = k -. p.m in
  p.b *. (p.rho +. (d /. sqrt ((d *. d) +. (p.sigma *. p.sigma))))

let d2w p k =
  let d = k -. p.m in
  let s2 = (d *. d) +. (p.sigma *. p.sigma) in
  p.b *. p.sigma *. p.sigma /. (s2 *. sqrt s2)

let g p k =
  let w = total_variance p k and w1 = dw p k and w2 = d2w p k in
  let t = 1. -. (k *. w1 /. (2. *. w)) in
  (t *. t) -. ((w1 *. w1 /. 4.) *. ((1. /. w) +. 0.25)) +. (w2 /. 2.)

let d_minus p k =
  let w = total_variance p k in
  let s = sqrt w in
  (-.k /. s) -. (s /. 2.)

let cdf p k =
  let w = total_variance p k in
  let dm = d_minus p k in
  1. -. norm_cdf dm +. (norm_pdf dm *. dw p k /. (2. *. sqrt w))

let density p k =
  let w = total_variance p k in
  let dm = d_minus p k in
  g p k /. sqrt (2. *. Float.pi *. w) *. exp (-0.5 *. dm *. dm)

let quantile p prob =
  let lo = ref (-4.) and hi = ref 4. in
  for _ = 1 to 200 do
    let mid = 0.5 *. (!lo +. !hi) in
    if cdf p mid < prob then lo := mid else hi := mid
  done;
  0.5 *. (!lo +. !hi)

(* --- the fit: least squares in total variance over the five parameters by Nelder-Mead
   from several starts, under the SVI constraints (b >= 0, |rho| < 1, sigma > 0, the
   minimum total variance a + b sigma sqrt(1 - rho^2) >= 0), the best start kept;
   deterministic --- *)

let nelder_mead f (x0 : float array) (steps : float array) ~iterations =
  let n = Array.length x0 in
  let simplex = Array.init (n + 1) (fun i -> Array.mapi (fun j x -> if i > 0 && j = i - 1 then x +. steps.(j) else x) x0) in
  let values = Array.map f simplex in
  let order () =
    let idx = Array.init (n + 1) (fun i -> i) in
    Array.stable_sort (fun i j -> compare values.(i) values.(j)) idx;
    let s = Array.map (fun i -> simplex.(i)) idx and v = Array.map (fun i -> values.(i)) idx in
    Array.blit s 0 simplex 0 (n + 1);
    Array.blit v 0 values 0 (n + 1)
  in
  let centroid () =
    Array.init n (fun j ->
        let s = ref 0. in
        for i = 0 to n - 1 do
          s := !s +. simplex.(i).(j)
        done;
        !s /. float_of_int n)
  in
  let combine c x t = Array.init n (fun j -> c.(j) +. (t *. (x.(j) -. c.(j)))) in
  let it = ref 0 in
  let continue = ref true in
  while !continue && !it < iterations do
    incr it;
    order ();
    let size =
      Array.fold_left
        (fun acc x ->
          let d = ref 0. in
          Array.iteri (fun j v -> d := !d +. Float.abs (v -. simplex.(0).(j))) x;
          Float.max acc !d)
        0. simplex
    in
    if size < 1e-11 && Float.abs (values.(n) -. values.(0)) < 1e-18 then continue := false
    else begin
      let c = centroid () in
      let worst = simplex.(n) in
      let xr = combine c worst (-1.) in
      let fr = f xr in
      if fr < values.(0) then begin
        let xe = combine c worst (-2.) in
        let fe = f xe in
        if fe < fr then (simplex.(n) <- xe; values.(n) <- fe) else (simplex.(n) <- xr; values.(n) <- fr)
      end
      else if fr < values.(n - 1) then (simplex.(n) <- xr; values.(n) <- fr)
      else begin
        let xc = if fr < values.(n) then combine c worst (-0.5) else combine c worst 0.5 in
        let fc = f xc in
        if fc < Float.min fr values.(n) then (simplex.(n) <- xc; values.(n) <- fc)
        else
          for i = 1 to n do
            simplex.(i) <- Array.init n (fun j -> simplex.(0).(j) +. (0.5 *. (simplex.(i).(j) -. simplex.(0).(j))));
            values.(i) <- f simplex.(i)
          done
      end
    end
  done;
  order ();
  (simplex.(0), values.(0))

let clamp lo hi x = Float.max lo (Float.min hi x)

let check_lo = -3.
(* The butterfly grid, k from -3 to 3 in steps of 0.02 (K from F/20 to 20 F), shared by the
   fit's constraint and the check so a fit on the boundary passes the check it was held to. *)
let check_grid = List.init 301 (fun i -> check_lo +. (float_of_int i *. 0.02))

let of_array x = { a = x.(0); b = x.(1); rho = x.(2); m = x.(3); sigma = x.(4) }

let fit points =
  let ks = List.map fst points and ws = List.map snd points in
  let k_min = List.fold_left Float.min infinity ks and k_max = List.fold_left Float.max neg_infinity ks in
  let w_min = List.fold_left Float.min infinity ws and w_max = List.fold_left Float.max neg_infinity ws in
  let m_lo = (2. *. k_min) -. 1. and m_hi = (2. *. k_max) +. 1. in
  (* The fit is over arbitrage-free smiles only: Lee's wing bound and g >= 0 on a coarse
     grid over the checked interval are hard constraints, so the extrapolated wings can
     never buy a better fit inside the data; [check] then confirms on the fine grid. *)
  let cost x =
    let p = of_array x in
    if p.b < 0. || Float.abs p.rho >= 1. || p.sigma < 1e-4 || p.sigma > 10. || p.m < m_lo || p.m > m_hi
       || p.a +. (p.b *. p.sigma *. sqrt (1. -. (p.rho *. p.rho))) < 0.
       || p.b *. (1. +. Float.abs p.rho) > 2.
       || List.exists (fun k -> total_variance p k <= 0. || g p k < 0.) check_grid
    then infinity
    else List.fold_left (fun acc (k, w) -> let e = total_variance p k -. w in acc +. (e *. e)) 0. points
  in
  let scale = Float.max (w_max -. w_min) (0.05 *. w_max) in
  let starts =
    List.concat_map
      (fun m0 -> List.map (fun sigma0 -> [| w_min; scale; -0.3; m0; sigma0 |]) [ 0.1; 0.4 ])
      [ k_min /. 2.; 0.; k_max /. 2. ]
  in
  let steps = [| 0.5 *. scale +. 1e-4; 0.5 *. scale +. 1e-3; 0.3; 0.5 *. (k_max -. k_min) +. 0.05; 0.1 |] in
  let best =
    List.fold_left
      (fun (bx, bv) x0 ->
        let x1, _ = nelder_mead cost x0 steps ~iterations:4000 in
        let x2, v2 = nelder_mead cost x1 (Array.map (fun s -> 0.1 *. s) steps) ~iterations:4000 in
        if v2 < bv then (x2, v2) else (bx, bv))
      ([| w_min; 0.; 0.; 0.; 1. |], cost [| w_min; 0.; 0.; 0.; 1. |])
      starts
  in
  of_array (fst best)

let fit_rmse p points =
  let n = float_of_int (List.length points) in
  sqrt (List.fold_left (fun acc (k, w) -> let e = total_variance p k -. w in acc +. (e *. e)) 0. points /. n)

let check p =
  let grid = check_grid in
  let bad_w = List.find_opt (fun k -> total_variance p k <= 0.) grid in
  let bad_g = List.find_opt (fun k -> g p k < 0.) grid in
  match (bad_w, bad_g) with
  | Some k, _ -> Error (Printf.sprintf "smile fit failed: non-positive total variance at k = %.2f" k)
  | _, Some k -> Error (Printf.sprintf "smile fit failed: butterfly arbitrage (g(k) = %.4f at k = %.2f)" (g p k) k)
  | None, None ->
      let slope = p.b *. (1. +. Float.abs p.rho) in
      if slope > 2. then Error (Printf.sprintf "smile fit failed: wing slope b(1+|rho|) = %.3f exceeds 2 (Lee's bound)" slope)
      else Ok ()

(* --- the chain --- *)

let no_expiry_reason =
  Printf.sprintf "no expiry >= %d days with >= %d quoted strikes on each side" min_days min_strikes_each_side

let select_expiry (quotes : option_quote list) ~spot ~snapshot_date =
  let expiries = List.sort_uniq compare (List.map (fun (q : option_quote) -> q.expiration) quotes) in
  let count expiry pred =
    List.filter (fun (q : option_quote) -> q.expiration = expiry && q.bid > 0. && pred q) quotes
    |> List.map (fun (q : option_quote) -> q.strike)
    |> List.sort_uniq compare |> List.length
  in
  let candidates =
    List.filter_map
      (fun expiry ->
        match Date.days_between ~from:snapshot_date ~until:expiry with
        | Ok days when days >= min_days ->
            let below = count expiry (fun q -> q.right = "put" && q.strike < spot) in
            let above = count expiry (fun q -> q.right = "call" && q.strike > spot) in
            if below >= min_strikes_each_side && above >= min_strikes_each_side then Some (expiry, days, below, above) else None
        | _ -> None)
      expiries
  in
  match List.rev candidates with [] -> Error no_expiry_reason | best :: _ -> Ok best

let note =
  "risk-neutral: the distribution embeds the market's risk pricing and is not a forecast; it is read from one \
   expiry's quotes on the snapshot date, whose spot may differ from the record's price"

let growth_note days =
  Printf.sprintf
    "approximate: a %.1f-year horizon stands in for the long run; each quantile price is discounted at the required \
     return used and inverted through the implied-terminal-growth solver, everything else held"
    (float_of_int days /. 365.)

let of_chain (chain : option_chain) ~rf ~ke ~fair_value ~growth =
  let spot = chain.underlying_close in
  match select_expiry chain.quotes ~spot ~snapshot_date:chain.snapshot_date with
  | Error r -> Error r
  | Ok (expiry, days, below, above) ->
      let t = float_of_int days /. 365. in
      let growth_factor = exp (rf *. t) in
      let quotes = List.filter (fun (q : option_quote) -> q.expiration = expiry && q.bid > 0.) chain.quotes in
      let at right strike = List.find_opt (fun (q : option_quote) -> q.right = right && q.strike = strike) quotes in
      (* The forward: put-call parity at the straddle strike nearest spot with both sides quoted. *)
      let straddles =
        List.filter_map
          (fun (q : option_quote) ->
            if q.right = "call" then Option.map (fun (p : option_quote) -> (q.strike, q.mid, p.mid)) (at "put" q.strike) else None)
          quotes
      in
      let forward, forward_source =
        match List.sort (fun (k1, _, _) (k2, _, _) -> compare (Float.abs (k1 -. spot)) (Float.abs (k2 -. spot))) straddles with
        | (k, c, p) :: _ -> (k +. (growth_factor *. (c -. p)), Printf.sprintf "put-call parity at strike %g" k)
        | [] -> (spot *. growth_factor, "spot compounded at the risk-free rate (no strike quoted on both sides)")
      in
      (* Out-of-the-money by the forward: puts below, calls at or above; mids undiscounted;
         a quote whose spread exceeds its mid (ask > 3 bid) says nothing about the price
         and is left out of the fit, counted. *)
      let otm = List.filter (fun (q : option_quote) -> (q.right = "put" && q.strike < forward) || (q.right = "call" && q.strike >= forward)) quotes in
      let tight, wide = List.partition (fun (q : option_quote) -> q.ask <= 3. *. q.bid) otm in
      let invert (q : option_quote) =
        let right = if q.right = "put" then `Put else `Call in
        Option.map (fun w -> (log (q.strike /. forward), w)) (implied_total_variance ~right ~forward ~strike:q.strike ~price:(q.mid *. growth_factor))
      in
      let points = List.filter_map invert tight in
      (* The put-call gap at the forward: the nearest put below against the nearest call at
         or above, in implied vol, a diagnostic of the European inversion of American quotes. *)
      let put_call_iv_gap_at_forward =
        let nearest right cmp =
          List.filter (fun (q : option_quote) -> q.right = right) tight
          |> List.sort (fun (x : option_quote) (y : option_quote) -> cmp x.strike y.strike)
          |> function [] -> None | q :: _ -> invert q
        in
        match (nearest "put" (fun x y -> compare y x), nearest "call" compare) with
        | Some (_, wp), Some (_, wc) -> Some (sqrt (wp /. t) -. sqrt (wc /. t))
        | _ -> None
      in
      let n = List.length points in
      if n < min_strikes_each_side then
        Error (Printf.sprintf "smile fit failed: only %d out-of-the-money quotes invert to an implied volatility" n)
      else
        let p = fit points in
        match check p with
        | Error r -> Error r
        | Ok () ->
            let price_at k = forward *. exp k in
            let price_quantiles = List.map (fun prob -> { p = prob; price = price_at (quantile p prob) }) quantile_levels in
            let anchor_path_price = fair_value *. ((1. +. ke) ** t) in
            let p_below_anchor_path = clamp 0. 1. (cdf p (log (anchor_path_price /. forward))) in
            let implied_growth_quantiles, implied_growth_reason =
              match growth with
              | Error r -> (None, Some r)
              | Ok (rate, f) ->
                  ( Some
                      (List.map
                         (fun (q : price_quantile) ->
                           let today = q.price /. ((1. +. ke) ** t) in
                           let readout, _ = Beliefs.implied_terminal_growth ~f ~price:today ~rate in
                           { p = q.p; growth = readout })
                         price_quantiles),
                    None )
            in
            Ok
              {
                source = chain.source;
                snapshot_date = chain.snapshot_date;
                snapshot_timestamp = chain.snapshot_timestamp;
                spot;
                forward;
                forward_source;
                risk_free_rate = rf;
                expiry;
                horizon_years = t;
                otm_quoted_below = below;
                otm_quoted_above = above;
                smile =
                  { a = p.a; b = p.b; rho = p.rho; m = p.m; sigma = p.sigma; rmse = fit_rmse p points; quotes_fitted = n;
                    quotes_excluded_wide = List.length wide; spread_rule = "ask <= 3 bid"; put_call_iv_gap_at_forward };
                price_quantiles;
                anchor_path_price;
                p_below_anchor_path;
                implied_growth_quantiles;
                implied_growth_reason;
                implied_growth_label = "approximate";
                implied_growth_note = growth_note days;
                risk_neutral = true;
                note;
              }
