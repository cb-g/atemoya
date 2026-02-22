(* FX Forward Pricing - Covered Interest Rate Parity *)

open Types

(* Calculate forward rate using covered interest rate parity

   Formula: F = S × e^((r_d - r_f) × T)

   Intuition:
   - If domestic rate > foreign rate: forward > spot (base currency depreciates)
   - If domestic rate < foreign rate: forward < spot (base currency appreciates)
*)
let forward_rate ~spot ~domestic_rate ~foreign_rate ~maturity =
  if maturity < 0.0 then
    failwith "Forwards.forward_rate: maturity must be non-negative"
  else if maturity = 0.0 then
    spot  (* At maturity, forward = spot *)
  else
    spot *. exp ((domestic_rate -. foreign_rate) *. maturity)

(* Forward points (forward premium/discount) *)
let forward_points ~spot ~domestic_rate ~foreign_rate ~maturity =
  let fwd = forward_rate ~spot ~domestic_rate ~foreign_rate ~maturity in
  fwd -. spot

(* Build a complete forward contract *)
let build_forward ~(pair : fx_pair) ~domestic_rate ~foreign_rate ~maturity ~notional =
  let fwd_rate = forward_rate
    ~spot:pair.spot_rate
    ~domestic_rate
    ~foreign_rate
    ~maturity
  in
  ({
    pair;
    forward_rate = fwd_rate;
    domestic_rate;
    foreign_rate;
    maturity;
    notional;
  } : forward_contract)

(* Extract implied foreign rate from observed forward

   Rearranging CIP: r_f = r_d - ln(F/S) / T
*)
let implied_foreign_rate ~spot ~forward ~domestic_rate ~maturity =
  if maturity <= 0.0 then
    failwith "Forwards.implied_foreign_rate: maturity must be positive"
  else
    domestic_rate -. (log (forward /. spot)) /. maturity

(* Extract implied domestic rate from observed forward

   Rearranging CIP: r_d = r_f + ln(F/S) / T
*)
let implied_domestic_rate ~spot ~forward ~foreign_rate ~maturity =
  if maturity <= 0.0 then
    failwith "Forwards.implied_domestic_rate: maturity must be positive"
  else
    foreign_rate +. (log (forward /. spot)) /. maturity

(* Check if covered interest parity holds within tolerance

   CIP condition: F = S × e^((r_d - r_f) × T)

   Arbitrage-free if: |F_observed - F_theoretical| < tolerance
*)
let check_covered_interest_parity ~spot ~forward ~domestic_rate ~foreign_rate ~maturity ~tolerance =
  let theoretical_forward = forward_rate ~spot ~domestic_rate ~foreign_rate ~maturity in
  let deviation = abs_float (forward -. theoretical_forward) in
  deviation <= tolerance

(* Mark-to-market value of existing forward contract

   Value = (F_current - F_entry) × Notional × e^(-r_d × T)

   where:
     F_current = current forward rate for remaining maturity
     F_entry = forward rate at entry
     T = time remaining to maturity
*)
let forward_value ~contract ~current_spot ~current_domestic_rate ~current_foreign_rate ~time_remaining =
  if time_remaining <= 0.0 then
    (* At maturity, value = (Spot - Forward) × Notional *)
    (current_spot -. contract.forward_rate) *. contract.notional
  else
    (* Before maturity, calculate current forward and discount *)
    let current_forward = forward_rate
      ~spot:current_spot
      ~domestic_rate:current_domestic_rate
      ~foreign_rate:current_foreign_rate
      ~maturity:time_remaining
    in
    let pv_factor = exp (-. current_domestic_rate *. time_remaining) in
    (current_forward -. contract.forward_rate) *. contract.notional *. pv_factor

(* P&L from closing forward position

   P&L = (Exit_Forward - Entry_Forward) × Notional

   Note: Sign convention
   - Long forward (agree to buy base currency): profit if forward rate rises
   - Short forward (agree to sell base currency): profit if forward rate falls
*)
let forward_pnl ~entry_forward ~exit_forward ~notional =
  (exit_forward -. entry_forward) *. notional
