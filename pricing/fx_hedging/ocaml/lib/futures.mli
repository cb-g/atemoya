(* Interface for FX futures pricing and analysis *)

open Types

(** Futures pricing **)

(* Calculate theoretical futures price

   For FX futures: F = S × e^((r_d - r_f) × T)

   Same as forward pricing under perfect markets
*)
val futures_price :
  spot:float ->
  domestic_rate:float ->
  foreign_rate:float ->
  maturity:float ->
  float

(* Build futures contract from specification *)
val build_futures :
  spec:cme_contract_spec ->
  spot:float ->
  domestic_rate:float ->
  foreign_rate:float ->
  expiry:float ->
  contract_month:string ->
  futures_contract

(** Basis analysis **)

(* Calculate basis (futures - spot)

   Positive basis (contango): futures > spot
   Negative basis (backwardation): futures < spot
*)
val basis :
  futures_price:float ->
  spot_price:float ->
  float

(* Calculate basis as percentage of spot *)
val basis_pct :
  futures_price:float ->
  spot_price:float ->
  float

(* Check if basis is in contango (futures > spot) *)
val is_contango :
  futures_price:float ->
  spot_price:float ->
  bool

(* Check if basis is in backwardation (futures < spot) *)
val is_backwardation :
  futures_price:float ->
  spot_price:float ->
  bool

(** Roll yield **)

(* Calculate roll yield when rolling from near to far contract

   Roll Yield = (F_near - F_far) / F_near × (365 / days_between)

   Positive: profit from rolling (backwardation)
   Negative: cost from rolling (contango)
*)
val roll_yield :
  futures_near:float ->
  futures_far:float ->
  days_between:int ->
  float  (* annualized yield *)

(* Calculate roll cost (dollar amount) *)
val roll_cost :
  futures_near:float ->
  futures_far:float ->
  contract_size:float ->
  quantity:int ->
  float

(** Contract valuation **)

(* Calculate notional value of futures position

   Notional = Futures_Price × Contract_Size × Quantity
*)
val contract_value :
  futures_price:float ->
  contract_size:float ->
  quantity:int ->
  float

(* Calculate P&L from futures position

   P&L = (Exit_Price - Entry_Price) × Contract_Size × Quantity
*)
val futures_pnl :
  entry_price:float ->
  current_price:float ->
  contract_size:float ->
  quantity:int ->
  float

(* Calculate daily variation margin (mark-to-market P&L)

   Variation = (Settlement_Today - Settlement_Yesterday) × Contract_Size × Quantity
*)
val variation_margin :
  settlement_yesterday:float ->
  settlement_today:float ->
  contract_size:float ->
  quantity:int ->
  float

(** Hedging calculations **)

(* Calculate number of futures contracts needed to hedge exposure

   Contracts = Exposure / (Futures_Price × Contract_Size)
*)
val hedge_contracts :
  exposure_usd:float ->
  futures_price:float ->
  contract_size:float ->
  int

(* Calculate hedge ratio (futures notional / exposure) *)
val hedge_ratio :
  futures_notional:float ->
  exposure:float ->
  float

(** Convergence **)

(* Calculate convergence to spot as expiry approaches

   At expiry: Futures → Spot (basis → 0)
*)
val convergence_value :
  futures_price:float ->
  spot_price:float ->
  time_to_expiry:float ->
  float  (* Expected basis at time t *)
