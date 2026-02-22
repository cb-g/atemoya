(** Copula module for modeling dependence between financial metrics *)

open Types

(** Copula type: Gaussian (thin tails) or Student-t (fat tails for tail dependence) *)
type copula_type =
  | Gaussian
  | StudentT of float  (** degrees of freedom, typically 3-10 for financial data *)

(** Configuration for copula-based sampling of financial metrics *)
type copula_config = {
  use_copula : bool;  (** Enable copula-based sampling *)
  copula_type : copula_type;  (** Type of copula to use *)
  correlation_matrix : float array array;  (** Correlation matrix for financial metrics *)
}

(** Sample correlated financial metrics using Gaussian copula

    Returns: (revenue_or_ni, ebit, capex, depreciation, ca, cl)

    The copula approach:
    1. Samples from multivariate normal with correlation matrix
    2. Transforms to uniform [0,1] via standard normal CDF
    3. Transforms to desired marginals via inverse CDF (percentile method)

    Financial metrics correlation structure:
    - Revenue/NI ↔ EBIT: 0.9 (high correlation)
    - EBIT ↔ CapEx: 0.5 (moderate - growth requires investment)
    - Revenue/NI ↔ CapEx: 0.6 (moderate)
    - EBIT ↔ Depreciation: 0.3 (weak - different drivers)
    - Current Assets ↔ Current Liabilities: 0.7 (working capital management)
*)
val sample_correlated_financials :
  time_series:time_series ->
  correlation:float array array ->
  (float * float * float * float * float * float)
(** Sample 6 correlated financial metrics: (revenue_or_ni, ebit, capex, depreciation, ca, cl) *)

(** Get default correlation matrix for financial metrics

    Order: [NI/Revenue, EBIT, CapEx, Depreciation, CA, CL]

    Based on empirical observations:
    - Strong correlations: Revenue-EBIT (0.9)
    - Moderate correlations: EBIT-CapEx (0.5), Revenue-CapEx (0.6)
    - Weak correlations: Most metrics with Depreciation (0.3)
    - Working capital: CA-CL (0.7)
*)
val default_correlation_matrix : unit -> float array array

(** Default copula configuration using Gaussian copula *)
val default_copula_config : float array array -> copula_config

(** Sample from Student-t distribution with df degrees of freedom *)
val student_t_sample : df:float -> float

(** Sample from multivariate Student-t with correlation matrix *)
val sample_multivariate_student_t : correlation:float array array -> df:float -> float array

(** Sample correlated financials with configurable copula type *)
val sample_correlated_financials_with_copula :
  time_series:time_series ->
  correlation:float array array ->
  copula_type:copula_type ->
  (float * float * float * float * float * float)

(** Compute tail dependence coefficient for a copula
    Returns 0.0 for Gaussian (no tail dependence)
    Returns positive value for Student-t (symmetric tail dependence) *)
val tail_dependence_coefficient :
  copula_type:copula_type ->
  correlation_coef:float ->
  float
