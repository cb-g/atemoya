(* Margin Calculations for Futures and Options *)

open Types

(** Initial and maintenance margin **)

(* Initial margin for futures *)
let initial_margin ~futures ~quantity =
  futures.initial_margin *. float_of_int (abs quantity)

(* Maintenance margin for futures *)
let maintenance_margin ~futures ~quantity =
  futures.maintenance_margin *. float_of_int (abs quantity)

(* Initial margin for futures options

   For LONG options:
   - Pay premium upfront
   - NO additional margin required (max loss = premium paid)
   - This is a key advantage of buying options vs futures

   For SHORT (written) options:
   - RECEIVE premium (credit to account)
   - MUST post margin to cover potential unlimited losses (calls) or large losses (puts)
   - Typical exchange formula: underlying futures margin + premium received
     or a percentage of underlying notional

   This follows standard exchange margin rules (CME, ICE, etc.)
*)
let option_initial_margin ~option ~quantity =
  let qty = abs quantity in

  (* Premium value (notional amount) *)
  let premium_notional = option.premium *.
                         option.underlying_futures.contract_size *.
                         float_of_int qty in

  (* Underlying futures margin requirement *)
  let underlying_margin = option.underlying_futures.initial_margin *. float_of_int qty in

  if quantity > 0 then
    (* LONG option: Only pay the premium. No additional margin needed.
       The premium IS your maximum loss, so no further collateral required. *)
    premium_notional
  else
    (* SHORT option: Must post margin to cover potential losses.

       Exchange-style margin calculation:
       Margin = Underlying futures margin × multiplier - OTM amount (if any)

       Simplified: Use full underlying margin + received premium as buffer
       This is conservative but safe for a short option position *)
    let short_margin = underlying_margin +. premium_notional in

    (* Apply minimum: at least the premium received (can't have negative margin) *)
    max premium_notional short_margin

(** Margin account management **)

(* Create new margin account *)
let create_margin_account ~cash_balance ~initial_margin_required ~maintenance_margin_required =
  let excess = cash_balance -. maintenance_margin_required in
  {
    cash_balance;
    initial_margin_required;
    maintenance_margin_required;
    variation_margin = 0.0;
    excess_margin = max 0.0 excess;
  }

(* Update account after variation margin settlement *)
let update_margin_account ~account ~variation_margin =
  let new_balance = account.cash_balance +. variation_margin in
  let new_excess = new_balance -. account.maintenance_margin_required in
  {
    account with
    cash_balance = new_balance;
    variation_margin;
    excess_margin = max 0.0 new_excess;
  }

(* Check if margin call triggered *)
let is_margin_call ~account =
  account.cash_balance < account.maintenance_margin_required

(* Amount needed to restore margin to initial level *)
let margin_call_amount ~account =
  if is_margin_call ~account then
    account.initial_margin_required -. account.cash_balance
  else
    0.0

(* Calculate excess margin (can be withdrawn) *)
let excess_margin ~account =
  account.excess_margin

(** SPAN margin (simplified) **)

(* Simplified SPAN margin for futures

   Real SPAN calculates worst-case loss across 16 scenarios:
   - Price changes: ±1/3, ±2/3, ±3/3 of expected move
   - Volatility changes: +/-1%, +/-2%, +/-3%

   This is a simplified version using typical ranges
*)
let span_margin_estimate ~(futures : futures_contract) ~quantity =
  let qty = abs quantity in

  (* Assume ±10% price move as worst case *)
  let price_move = 0.10 *. futures.futures_price in
  let max_loss_per_contract = price_move *. futures.contract_size in

  (* SPAN margin is typically 3-5% of contract value *)
  (* let span_pct = 0.04 in *)  (* 4% typical *)

  max_loss_per_contract *. float_of_int qty

(* SPAN margin for options (simplified)

   For options, SPAN considers:
   - Short option risk (unlimited for calls, large for puts)
   - Portfolio offsets (hedges)
   - Volatility risk

   Simplified: Base it on underlying futures margin
*)
let span_option_margin ~option ~quantity =
  let qty = abs quantity in

  if quantity > 0 then
    (* Long options: Limited risk = premium paid *)
    option.premium *. option.underlying_futures.contract_size *. float_of_int qty
  else
    (* Short options: Use SPAN on underlying *)
    let fut_span = span_margin_estimate
      ~futures:option.underlying_futures
      ~quantity:qty
    in
    (* Add some buffer for vega risk *)
    fut_span *. 1.2
