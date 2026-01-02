(** Copula module for modeling dependence between financial metrics *)

open Types

(** Configuration for copula-based sampling of financial metrics *)
type copula_config = {
  use_copula : bool;  (** Enable copula-based sampling *)
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
