(** Perpetual futures pricing formulas. *)

open Types

(** {1 Linear Perpetual Futures} *)

val price_linear_discrete :
  kappa:float -> iota:float -> r_a:float -> r_b:float -> spot:float -> float

val price_linear_continuous :
  kappa:float -> iota:float -> r_a:float -> r_b:float -> spot:float -> float

(** {1 Inverse Perpetual Futures} *)

val price_inverse_discrete :
  kappa:float -> iota:float -> r_a:float -> r_b:float -> spot:float -> float

val price_inverse_continuous :
  kappa:float -> iota:float -> r_a:float -> r_b:float -> spot:float -> float

(** {1 Quanto Perpetual Futures} *)

val price_quanto :
  kappa:float -> iota:float -> r_a:float -> r_c:float ->
  sigma_x:float -> sigma_z:float -> rho:float -> spot_z:float -> float

(** {1 Perfect Anchoring} *)

val perfect_iota_linear_discrete : r_a:float -> r_b:float -> float
val perfect_iota_inverse_discrete : r_a:float -> r_b:float -> float
val perfect_iota_linear_continuous : r_a:float -> r_b:float -> float
val perfect_iota_inverse_continuous : r_a:float -> r_b:float -> float

(** {1 Utility Functions} *)

val futures_spot_ratio_linear : kappa:float -> r_a:float -> r_b:float -> float
val implied_iota :
  kappa:float -> r_a:float -> r_b:float -> futures:float -> spot:float -> float

val annualize_funding_rate : funding_8h:float -> float
val funding_rate_8h : annualized:float -> float

val annual_to_period : annual_rate:float -> periods_per_year:float -> float
val period_to_annual : period_rate:float -> periods_per_year:float -> float

(** {1 Contract Pricing} *)

val price_contract : perpetual_contract -> spot:float -> pricing_result

val mean_random_maturity : kappa:float -> float
