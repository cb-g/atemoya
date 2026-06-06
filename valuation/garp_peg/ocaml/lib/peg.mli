(** PEG ratio calculations for GARP analysis *)

(** Select the best available growth rate from the data.
    Returns (growth_rate_pct, source_description) *)
val select_growth_rate : Types.garp_data -> float * string

(** Calculate PEG ratio: P/E / Growth Rate (%)
    Returns None if growth rate is zero or negative *)
val calculate_peg : float -> float -> float option

(** Calculate PEGY ratio: P/E / (Growth Rate + Dividend Yield)
    Useful for dividend-paying growth stocks *)
val calculate_pegy : float -> float -> float -> float option

(** Assess PEG ratio and return interpretation string *)
val assess_peg : float option -> string

(** Calculate all PEG metrics from raw data *)
val calculate_peg_metrics : Types.garp_data -> Types.peg_metrics

(** Explicit high-growth horizon (years) for the justified-P/E fade. *)
val high_growth_years : int

(** Calculate implied fair P/E based on growth rate (PEG = 1.0). Legacy/naive;
    retained for reference. Prefer [justified_fair_pe]. *)
val implied_fair_pe : float -> float option

(** Justified (fair) trailing P/E from a two-stage earnings model: near-term
    [growth] fades to [terminal_growth] over [years], payout follows the
    sustainable-growth identity (retention = g / ROE), and the stream is
    discounted at [cost_of_equity]. All rates are decimals. Returns None if the
    discount rate does not exceed terminal growth. *)
val justified_fair_pe :
  growth:float -> terminal_growth:float -> cost_of_equity:float ->
  roe:float -> years:int -> float option

(** Calculate implied fair price based on fair P/E *)
val implied_fair_price : float -> float option -> float option

(** Calculate upside/downside to fair price as percentage *)
val calculate_upside_downside : float -> float option -> float option

(** Peter Lynch's rules of thumb assessment *)
val lynch_assessment : float option -> float -> string
