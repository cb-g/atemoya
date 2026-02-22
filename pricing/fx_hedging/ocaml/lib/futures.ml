(* FX Futures Pricing and Analysis *)

open Types

(** Futures pricing **)

(* Calculate theoretical futures price

   For currency futures, the futures price equals the forward price
   (under no-arbitrage and continuous compounding):

   F = S × e^((r_d - r_f) × T)
*)
let futures_price ~spot ~domestic_rate ~foreign_rate ~maturity =
  Forwards.forward_rate ~spot ~domestic_rate ~foreign_rate ~maturity

(* Build a complete futures contract *)
let build_futures ~spec ~spot ~domestic_rate ~foreign_rate ~expiry ~contract_month =
  let fut_price = futures_price ~spot ~domestic_rate ~foreign_rate ~maturity:expiry in
  {
    underlying = { spec.currency_pair with spot_rate = spot };
    contract_code = spec.code;
    contract_month;
    futures_price = fut_price;
    contract_size = spec.contract_size;
    tick_size = spec.tick_size;
    tick_value = spec.tick_value;
    initial_margin = spec.typical_initial_margin;
    maintenance_margin = spec.typical_maintenance_margin;
    expiry;
  }

(** Basis analysis **)

(* Basis = Futures - Spot *)
let basis ~futures_price ~spot_price =
  futures_price -. spot_price

(* Basis as percentage *)
let basis_pct ~futures_price ~spot_price =
  (futures_price -. spot_price) /. spot_price *. 100.0

(* Check if in contango (futures > spot) *)
let is_contango ~futures_price ~spot_price =
  futures_price > spot_price

(* Check if in backwardation (futures < spot) *)
let is_backwardation ~futures_price ~spot_price =
  futures_price < spot_price

(** Roll yield **)

(* Calculate annualized roll yield

   Roll Yield = (F_near - F_far) / F_near × (365 / days_between)

   Interpretation:
   - Positive roll yield: Backwardation, profit from rolling forward
   - Negative roll yield: Contango, cost of rolling forward

   Example:
   - F_near = 1.105, F_far = 1.110, days = 90
   - Roll Yield = (1.105 - 1.110) / 1.105 × (365/90) = -1.84% annualized
   - Cost to roll from near to far contract
*)
let roll_yield ~futures_near ~futures_far ~days_between =
  if days_between <= 0 then
    failwith "Futures.roll_yield: days_between must be positive"
  else
    let raw_return = (futures_near -. futures_far) /. futures_near in
    let annualization_factor = 365.0 /. float_of_int days_between in
    raw_return *. annualization_factor

(* Calculate dollar cost of rolling *)
let roll_cost ~futures_near ~futures_far ~contract_size ~quantity =
  let price_diff = futures_far -. futures_near in
  let cost_per_contract = price_diff *. contract_size in
  cost_per_contract *. float_of_int quantity

(** Contract valuation **)

(* Notional value of futures position *)
let contract_value ~futures_price ~contract_size ~quantity =
  futures_price *. contract_size *. float_of_int quantity

(* P&L from futures position

   Long futures: profit if price rises
   Short futures: profit if price falls
*)
let futures_pnl ~entry_price ~current_price ~contract_size ~quantity =
  let price_change = current_price -. entry_price in
  price_change *. contract_size *. float_of_int quantity

(* Daily variation margin (mark-to-market settlement)

   Paid/received each day based on settlement price changes
*)
let variation_margin ~settlement_yesterday ~settlement_today ~contract_size ~quantity =
  futures_pnl
    ~entry_price:settlement_yesterday
    ~current_price:settlement_today
    ~contract_size
    ~quantity

(** Hedging calculations **)

(* Calculate number of contracts needed

   Contracts = Exposure / (Futures_Price × Contract_Size)

   Example:
   - Exposure: $500,000 EUR
   - Futures: EUR/USD = 1.10
   - Contract Size: 125,000 EUR
   - Contracts = 500,000 / (1.10 × 125,000) = 3.64 ≈ 4 contracts
*)
let hedge_contracts ~exposure_usd ~futures_price ~contract_size =
  let notional_per_contract = futures_price *. contract_size in
  let contracts_exact = exposure_usd /. notional_per_contract in
  (* Round to nearest integer *)
  int_of_float (contracts_exact +. 0.5)

(* Calculate actual hedge ratio achieved *)
let hedge_ratio ~futures_notional ~exposure =
  if exposure = 0.0 then 0.0
  else futures_notional /. exposure

(** Convergence **)

(* Expected basis at time t (linear convergence approximation)

   As expiry approaches, basis converges to zero:
   Basis(t) ≈ Basis(0) × (T - t) / T

   where:
   - Basis(0) = current basis
   - T = original time to expiry
   - t = time elapsed
*)
let convergence_value ~futures_price ~spot_price ~time_to_expiry =
  if time_to_expiry <= 0.0 then
    0.0  (* At expiry, basis = 0 *)
  else
    (* Current basis will decay linearly to zero *)
    basis ~futures_price ~spot_price
