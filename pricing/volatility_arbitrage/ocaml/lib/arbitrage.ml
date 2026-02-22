(* Arbitrage detection implementation *)

open Types

(* ============================================================================ *)
(* Black-Scholes pricing (simplified, reused from options_hedging concept) *)
(* ============================================================================ *)

(* Error function approximation (Abramowitz and Stegun) *)
let erf x =
  let a1 =  0.254829592 in
  let a2 = -0.284496736 in
  let a3 =  1.421413741 in
  let a4 = -1.453152027 in
  let a5 =  1.061405429 in
  let p  =  0.3275911 in
  let sign = if x < 0.0 then -1.0 else 1.0 in
  let x = abs_float x in
  let t = 1.0 /. (1.0 +. p *. x) in
  let y = 1.0 -. (((((a5 *. t +. a4) *. t) +. a3) *. t +. a2) *. t +. a1) *. t *. exp (-. x *. x) in
  sign *. y

let normal_cdf x =
  0.5 *. (1.0 +. erf (x /. sqrt 2.0))

let bs_price ~option_type ~spot ~strike ~expiry ~rate ~dividend ~volatility =
  if expiry <= 0.0 || volatility <= 0.0 then 0.0
  else begin
    let d1 = (log (spot /. strike) +. (rate -. dividend +. 0.5 *. volatility *. volatility) *. expiry)
             /. (volatility *. sqrt expiry) in
    let d2 = d1 -. volatility *. sqrt expiry in

    match option_type with
    | Call ->
        spot *. exp (-.dividend *. expiry) *. normal_cdf d1 -.
        strike *. exp (-.rate *. expiry) *. normal_cdf d2
    | Put ->
        strike *. exp (-.rate *. expiry) *. normal_cdf (-.d2) -.
        spot *. exp (-.dividend *. expiry) *. normal_cdf (-.d1)
  end

(* Get implied vol from vol surface *)
let get_iv_from_surface vol_surface ~strike ~expiry ~spot =
  match vol_surface with
  | SVI params ->
      (* Find closest expiry *)
      if Array.length params = 0 then 0.20
      else begin
        let closest_idx = ref 0 in
        let min_diff = ref (abs_float (params.(0).expiry -. expiry)) in
        for i = 1 to Array.length params - 1 do
          let diff = abs_float (params.(i).expiry -. expiry) in
          if diff < !min_diff then begin
            min_diff := diff;
            closest_idx := i
          end
        done;

        let p = params.(!closest_idx) in
        let log_moneyness = log (strike /. spot) in
        let delta_k = log_moneyness -. p.m in
        let sqrt_term = sqrt (delta_k *. delta_k +. p.sigma *. p.sigma) in
        let total_var = p.a +. p.b *. (p.rho *. delta_k +. sqrt_term) in
        sqrt (total_var /. expiry)
      end

  | SABR params ->
      (* Simplified: use ATM vol *)
      if Array.length params = 0 then 0.20
      else params.(0).alpha

(*============================================================================ *)
(* Arbitrage Detection Functions *)
(* ============================================================================ *)

(* Butterfly arbitrage detection *)
let detect_butterfly_arbitrage vol_surface ~spot ~expiry ~rate ~dividend =
  (* Check butterflies at various strike levels *)
  let strikes = [|
    0.85 *. spot; 0.90 *. spot; 0.95 *. spot; spot; 1.05 *. spot; 1.10 *. spot; 1.15 *. spot;
  |] in

  let signals = ref [] in

  (* Check all possible butterfly combinations with equal spacing *)
  for i = 0 to Array.length strikes - 3 do
    let k1 = strikes.(i) in
    let k3 = strikes.(i + 2) in
    let k2 = (k1 +. k3) /. 2.0 in

    (* Get IVs *)
    let iv1 = get_iv_from_surface vol_surface ~strike:k1 ~expiry ~spot in
    let iv2 = get_iv_from_surface vol_surface ~strike:k2 ~expiry ~spot in
    let iv3 = get_iv_from_surface vol_surface ~strike:k3 ~expiry ~spot in

    (* Price options *)
    let c1 = bs_price ~option_type:Call ~spot ~strike:k1 ~expiry ~rate ~dividend ~volatility:iv1 in
    let c2 = bs_price ~option_type:Call ~spot ~strike:k2 ~expiry ~rate ~dividend ~volatility:iv2 in
    let c3 = bs_price ~option_type:Call ~spot ~strike:k3 ~expiry ~rate ~dividend ~volatility:iv3 in

    (* Butterfly condition: C(K1) + C(K3) >= 2·C(K2) *)
    let lhs = c1 +. c3 in
    let rhs = 2.0 *. c2 in

    if lhs < rhs -. 0.10 then begin
      (* Arbitrage: buy butterfly (buy wings, sell body) *)
      let violation = rhs -. lhs in
      let expected_profit = violation -. 0.05 in  (* Transaction costs *)

      if expected_profit > 0.0 then begin
        let signal = {
          timestamp = Unix.time ();
          ticker = "";
          arb_type = ButterflyViolation {
            lower_strike = k1;
            middle_strike = k2;
            upper_strike = k3;
            violation_amount = violation;
          };
          confidence = 0.9;
          expected_profit;
        } in
        signals := signal :: !signals
      end
    end
  done;

  Array.of_list !signals

(* Calendar arbitrage detection *)
let detect_calendar_arbitrage vol_surface ~spot ~strike ~rate ~dividend =
  (* Get available expiries from vol surface *)
  let expiries = match vol_surface with
    | SVI params -> Array.map (fun (p : svi_params) -> p.expiry) params
    | SABR params -> Array.map (fun (p : sabr_params) -> p.expiry) params
  in

  if Array.length expiries < 2 then [||]
  else begin
    let signals = ref [] in

    (* Check all pairs of expiries *)
    for i = 0 to Array.length expiries - 2 do
      for j = i + 1 to Array.length expiries - 1 do
        let t1 = expiries.(i) in
        let t2 = expiries.(j) in

        (* Get IVs *)
        let iv1 = get_iv_from_surface vol_surface ~strike ~expiry:t1 ~spot in
        let iv2 = get_iv_from_surface vol_surface ~strike ~expiry:t2 ~spot in

        (* Price options *)
        let c1 = bs_price ~option_type:Call ~spot ~strike ~expiry:t1 ~rate ~dividend ~volatility:iv1 in
        let c2 = bs_price ~option_type:Call ~spot ~strike ~expiry:t2 ~rate ~dividend ~volatility:iv2 in

        (* Calendar condition: C(K, T2) >= C(K, T1) *)
        if c2 < c1 -. 0.10 then begin
          let violation = c1 -. c2 in
          let expected_profit = violation -. 0.05 in

          if expected_profit > 0.0 then begin
            let signal = {
              timestamp = Unix.time ();
              ticker = "";
              arb_type = CalendarViolation {
                strike;
                near_expiry = t1;
                far_expiry = t2;
                violation_amount = violation;
              };
              confidence = 0.85;
              expected_profit;
            } in
            signals := signal :: !signals
          end
        end
      done
    done;

    Array.of_list !signals
  end

(* Put-call parity violation *)
let detect_put_call_parity_violation ~call_price ~put_price ~spot ~strike ~expiry ~rate ~dividend ~ticker =
  (* Put-call parity: C - P = S·e^(-qT) - K·e^(-rT) *)
  let lhs = call_price -. put_price in
  let rhs = spot *. exp (-.dividend *. expiry) -. strike *. exp (-.rate *. expiry) in

  let violation = abs_float (lhs -. rhs) in

  if violation > 0.25 then begin  (* Threshold: $0.25 *)
    let expected_profit = violation -. 0.10 in  (* Transaction costs higher for multi-leg *)

    if expected_profit > 0.0 then
      Some {
        timestamp = Unix.time ();
        ticker;
        arb_type = PutCallParity { strike; expiry; violation_amount = violation };
        confidence = 0.95;
        expected_profit;
      }
    else None
  end else None

(* Vertical spread arbitrage *)
let detect_vertical_arbitrage vol_surface ~spot ~expiry ~rate ~dividend =
  let strikes = [|
    0.85 *. spot; 0.90 *. spot; 0.95 *. spot; spot; 1.05 *. spot; 1.10 *. spot; 1.15 *. spot;
  |] in

  let signals = ref [] in

  for i = 0 to Array.length strikes - 2 do
    let k1 = strikes.(i) in
    let k2 = strikes.(i + 1) in

    let iv1 = get_iv_from_surface vol_surface ~strike:k1 ~expiry ~spot in
    let iv2 = get_iv_from_surface vol_surface ~strike:k2 ~expiry ~spot in

    (* Calls: C(K1) should be >= C(K2) *)
    let c1 = bs_price ~option_type:Call ~spot ~strike:k1 ~expiry ~rate ~dividend ~volatility:iv1 in
    let c2 = bs_price ~option_type:Call ~spot ~strike:k2 ~expiry ~rate ~dividend ~volatility:iv2 in

    if c1 < c2 -. 0.10 then begin
      let violation = c2 -. c1 in
      let expected_profit = violation -. 0.05 in

      if expected_profit > 0.0 then begin
        let signal = {
          timestamp = Unix.time ();
          ticker = "";
          arb_type = VerticalSpread {
            lower_strike = k1;
            upper_strike = k2;
            expiry;
            violation_amount = violation;
          };
          confidence = 0.90;
          expected_profit;
        } in
        signals := signal :: !signals
      end
    end
  done;

  Array.of_list !signals

(* Strike arbitrage (bid-ask crossover) *)
let detect_strike_arbitrage iv_observations =
  (* Group by expiry and option type *)
  let n = Array.length iv_observations in
  let signals = ref [] in

  (* Check if any lower strike has higher price than higher strike *)
  for i = 0 to n - 2 do
    for j = i + 1 to n - 1 do
      let (obs1 : iv_observation) = iv_observations.(i) in
      let (obs2 : iv_observation) = iv_observations.(j) in

      (* Same expiry and type *)
      if abs_float (obs1.expiry -. obs2.expiry) < 0.01 &&
         obs1.option_type = obs2.option_type then begin

        (* For calls: lower strike should have higher price *)
        if obs1.option_type = Call && obs1.strike < obs2.strike then begin
          if obs1.bid < obs2.ask then begin
            let violation = obs2.ask -. obs1.bid in
            let expected_profit = violation -. 0.10 in

            if expected_profit > 0.0 then begin
              let signal = {
                timestamp = Unix.time ();
                ticker = obs1.ticker;
                arb_type = VerticalSpread {
                  lower_strike = obs1.strike;
                  upper_strike = obs2.strike;
                  expiry = obs1.expiry;
                  violation_amount = violation;
                };
                confidence = 0.70;  (* Lower confidence for bid-ask based *)
                expected_profit;
              } in
              signals := signal :: !signals
            end
          end
        end
      end
    done
  done;

  Array.of_list !signals

(* Scan for all arbitrage *)
let scan_for_arbitrage vol_surface ~iv_observations ~underlying ~rate ~config:_ =
  let all_signals = ref [] in

  (* Standard expiries to check *)
  let expiries = [| 30.0 /. 365.0; 60.0 /. 365.0; 90.0 /. 365.0 |] in

  (* Butterfly arbitrage *)
  Array.iter (fun expiry ->
    let signals = detect_butterfly_arbitrage vol_surface
      ~spot:underlying.spot_price ~expiry ~rate ~dividend:underlying.dividend_yield in
    all_signals := Array.to_list signals @ !all_signals
  ) expiries;

  (* Calendar arbitrage *)
  let strikes = [| 0.90 *. underlying.spot_price; underlying.spot_price; 1.10 *. underlying.spot_price |] in
  Array.iter (fun strike ->
    let signals = detect_calendar_arbitrage vol_surface
      ~spot:underlying.spot_price ~strike ~rate ~dividend:underlying.dividend_yield in
    all_signals := Array.to_list signals @ !all_signals
  ) strikes;

  (* Vertical arbitrage *)
  Array.iter (fun expiry ->
    let signals = detect_vertical_arbitrage vol_surface
      ~spot:underlying.spot_price ~expiry ~rate ~dividend:underlying.dividend_yield in
    all_signals := Array.to_list signals @ !all_signals
  ) expiries;

  (* Strike arbitrage from market quotes *)
  if Array.length iv_observations > 0 then begin
    let signals = detect_strike_arbitrage iv_observations in
    all_signals := Array.to_list signals @ !all_signals
  end;

  (* Set ticker for all signals *)
  let signals_with_ticker = List.map (fun (signal : arbitrage_signal) ->
    { signal with ticker = underlying.ticker }
  ) !all_signals in

  Array.of_list signals_with_ticker

(* Filter by minimum profit *)
let filter_by_profit signals ~min_profit =
  Array.of_list (List.filter (fun signal ->
    signal.expected_profit >= min_profit
  ) (Array.to_list signals))

(* Sort by profit (descending) *)
let sort_by_profit signals =
  let signals_list = Array.to_list signals in
  let sorted = List.sort (fun s1 s2 ->
    compare s2.expected_profit s1.expected_profit
  ) signals_list in
  Array.of_list sorted
