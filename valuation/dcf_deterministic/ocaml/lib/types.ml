(** Core types for deterministic DCF valuation model *)

type ticker = string [@@deriving show]
type currency = string [@@deriving show]
type country = string [@@deriving show]
type industry = string [@@deriving show]

type market_data = {
  ticker : ticker;
  price : float;
  mve : float;
  mvb : float;
  shares_outstanding : float;
  currency : currency;
  country : country;
  industry : industry;
}
[@@deriving show]

type financial_data = {
  ebit : float;
  net_income : float;
  interest_expense : float;
  taxes : float;
  capex : float;
  depreciation : float;
  delta_wc : float;
  book_value_equity : float;
  invested_capital : float;
  is_bank : bool;
  is_insurance : bool;
  (* Bank-specific fields - only populated when is_bank = true *)
  net_interest_income : float;      (* NII = Interest Income - Interest Expense *)
  non_interest_income : float;      (* Fee income, trading, etc. *)
  non_interest_expense : float;     (* Operating expenses *)
  provision_for_loan_losses : float; (* Credit cost *)
  tangible_book_value : float;      (* Book Value - Goodwill - Intangibles *)
  total_loans : float;              (* Gross loan portfolio *)
  total_deposits : float;           (* Total deposits *)
  tier1_capital_ratio : float;      (* Regulatory capital ratio, 0 if unknown *)
  npl_ratio : float;                (* Non-performing loans / Total loans, 0 if unknown *)
  (* Insurance-specific fields - only populated when is_insurance = true *)
  premiums_earned : float;          (* Net premiums earned *)
  losses_incurred : float;          (* Claims and loss adjustment expenses *)
  underwriting_expenses : float;    (* Policy acquisition and admin costs *)
  investment_income : float;        (* Income from invested float *)
  float_amount : float;             (* Unearned premiums + loss reserves *)
  loss_ratio : float;               (* Losses / Premiums, 0 if unknown *)
  expense_ratio : float;            (* Expenses / Premiums, 0 if unknown *)
  combined_ratio : float;           (* Loss + Expense ratio, 0 if unknown *)
  (* Oil & Gas E&P specific fields - only populated when is_oil_gas = true *)
  is_oil_gas : bool;                (* Flag for O&G E&P handling *)
  proven_reserves : float;          (* Proven reserves in MMBOE (million barrels oil equivalent) *)
  production_boe_day : float;       (* Daily production in BOE/day *)
  ebitdax : float;                  (* EBITDA + Exploration expense *)
  exploration_expense : float;      (* Exploration and dry hole costs *)
  dd_and_a : float;                 (* Depletion, depreciation, amortization *)
  finding_cost : float;             (* F&D cost per BOE, 0 if unknown *)
  lifting_cost : float;             (* Operating cost per BOE, 0 if unknown *)
  oil_pct : float;                  (* Percentage of production that is oil vs gas *)
}
[@@deriving show]

(** Bank-specific metrics calculated from financial_data *)
type bank_metrics = {
  roe : float;                      (* Return on Equity = NI / Book Value *)
  rotce : float;                    (* Return on Tangible Common Equity *)
  roa : float;                      (* Return on Assets *)
  nim : float;                      (* Net Interest Margin = NII / Earning Assets *)
  efficiency_ratio : float;         (* Non-Int Expense / (NII + Non-Int Income) *)
  price_to_book : float;            (* P / BV *)
  price_to_tbv : float;             (* P / TBV *)
  ppnr : float;                     (* Pre-Provision Net Revenue *)
  ppnr_per_share : float;
}
[@@deriving show]

(** Insurance-specific metrics calculated from financial_data *)
type insurance_metrics = {
  roe : float;                      (* Return on Equity *)
  combined_ratio : float;           (* Loss ratio + Expense ratio; <100% = profit *)
  loss_ratio : float;               (* Losses / Premiums *)
  expense_ratio : float;            (* Expenses / Premiums *)
  underwriting_margin : float;      (* 1 - Combined ratio *)
  investment_yield : float;         (* Investment income / Float *)
  float_to_equity : float;          (* Float / Book Value - leverage measure *)
  price_to_book : float;            (* P / BV *)
  premium_to_equity : float;        (* Premiums / Equity - capacity measure *)
}
[@@deriving show]

(** Oil & Gas E&P specific metrics calculated from financial_data *)
type oil_gas_metrics = {
  reserve_life : float;             (* Proven reserves / Annual production (years) *)
  production_growth : float;        (* YoY production growth rate *)
  ebitdax_margin : float;           (* EBITDAX / Revenue *)
  ebitdax_per_boe : float;          (* EBITDAX / Annual production *)
  ev_per_boe : float;               (* Enterprise value / Proven reserves *)
  ev_to_ebitdax : float;            (* EV / EBITDAX multiple *)
  netback : float;                  (* Revenue per BOE - Lifting cost *)
  recycle_ratio : float;            (* Netback / Finding cost *)
  debt_to_ebitdax : float;          (* Total debt / EBITDAX *)
  roe : float;                      (* Return on Equity *)
}
[@@deriving show]

(** Fama-French factor configuration *)
type fama_french_config = {
  enabled : bool;                (* false = pure CAPM, true = 3-factor model *)
  smb_premium : float;           (* Small Minus Big premium, typically 2-3% *)
  hml_premium : float;           (* High Minus Low (value) premium, typically 3-5% *)
  small_cap_threshold : float;   (* Market cap below this = small cap, in millions *)
  value_btm_threshold : float;   (* Book-to-market above this = value stock *)
}
[@@deriving show]

(** Equity Risk Premium source type

    Static: Uses pre-computed country-specific ERPs from Damodaran's annual survey.
            Pros: Academically validated, stable, no live data dependency
            Cons: Updated only annually, may lag during stress periods

    Dynamic: Adjusts base ERP using current VIX relative to historical levels.
             ERP_dynamic = ERP_base × (VIX / VIX_historical_mean)^sensitivity

             Rationale: VIX captures implied volatility and risk aversion.
             When VIX spikes (fear), investors demand higher ERP.
             Historical VIX mean ≈ 19-20; sensitivity typically 0.3-0.5.

             Example: VIX=30, mean=20, sensitivity=0.4, base ERP=4.33%
             ERP_dynamic = 4.33% × (30/20)^0.4 = 4.33% × 1.176 = 5.09%
*)
type erp_source =
  | Static                       (* Damodaran-style pre-computed ERPs *)
  | Dynamic of {                 (* VIX-adjusted dynamic ERP *)
      vix_mean : float;          (* Long-term VIX average, typically 19-20 *)
      sensitivity : float;       (* Elasticity of ERP to VIX ratio, typically 0.3-0.5 *)
    }
[@@deriving show]

(** ERP configuration *)
type erp_config = {
  source : erp_source;
  base_erp : float;              (* Country-specific base ERP (used for both modes) *)
  current_vix : float option;    (* Current VIX level (only needed for Dynamic) *)
}
[@@deriving show]

type cost_of_capital = {
  ce : float;
  cb : float;
  wacc : float;
  leveraged_beta : float;
  risk_free_rate : float;
  equity_risk_premium : float;
  (* ERP components *)
  erp_source_used : erp_source;  (* Static or Dynamic mode that was used *)
  erp_base : float;              (* Base Damodaran ERP before adjustment *)
  erp_vix_adjustment : float;    (* VIX adjustment factor (1.0 if Static) *)
  (* Fama-French components (optional, zero if disabled) *)
  smb_loading : float;           (* Size factor loading: +1 small, 0 mid, -1 large *)
  hml_loading : float;           (* Value factor loading: +1 value, 0 blend, -1 growth *)
  size_premium : float;          (* SMB contribution to cost of equity *)
  value_premium : float;         (* HML contribution to cost of equity *)
}
[@@deriving show]

(** ERP mode for valuation params *)
type erp_mode =
  | ERPStatic   (* Use Damodaran country ERPs as-is *)
  | ERPDynamic  (* Adjust base ERP using current VIX *)
[@@deriving show]

(** ERP parameters for valuation *)
type erp_params = {
  mode : erp_mode;
  vix_mean : float;       (* Historical VIX mean for dynamic mode *)
  vix_sensitivity : float; (* ERP elasticity to VIX ratio *)
}
[@@deriving show]

type valuation_params = {
  projection_years : int;
  terminal_growth_rate : float;
  growth_clamp_upper : float;
  growth_clamp_lower : float;
  rfr_duration : int;
  (* Mean reversion parameters for growth rate decay toward terminal growth *)
  mean_reversion_enabled : bool;  (* false = constant growth (legacy), true = mean-reverting *)
  mean_reversion_lambda : float;  (* Speed of reversion: 0.1 = slow, 0.5 = fast. Typical: 0.2-0.3 *)
  (* ERP parameters *)
  erp_params : erp_params;
}
[@@deriving show]

type config = {
  risk_free_rates : (country * (int * float) list) list;
  equity_risk_premiums : (country * float) list;
  industry_betas : (industry * float) list;
  tax_rates : (country * float) list;
  params : valuation_params;
}
[@@deriving show]

type cash_flow_projection = {
  fcfe : float array;
  fcff : float array;
  growth_rate_fcfe : float;
  growth_rate_fcff : float;
  growth_clamped_fcfe : bool;
  growth_clamped_fcff : bool;
}
[@@deriving show]

type investment_signal =
  | StrongBuy
  | Buy
  | BuyEquityUpside
  | CautionLong
  | Hold
  | CautionLeverage
  | SpeculativeHighLeverage
  | SpeculativeExecutionRisk
  | Avoid
[@@deriving show]

(** Bank valuation result using excess return model *)
type bank_valuation_result = {
  ticker : ticker;
  price : float;
  book_value_per_share : float;
  tangible_book_per_share : float;
  excess_return_value : float;       (** PV of (ROE - CoE) × Book Value stream *)
  fair_value_per_share : float;      (** Book Value + Excess Return Value *)
  margin_of_safety : float;
  implied_roe : float option;        (** ROE implied by current price *)
  signal : investment_signal;
  cost_of_equity : float;
  bank_metrics : bank_metrics;
}
[@@deriving show]

(** Insurance valuation result using float-based model *)
type insurance_valuation_result = {
  ticker : ticker;
  price : float;
  book_value_per_share : float;
  underwriting_value : float;        (** PV of underwriting profits *)
  float_value : float;               (** Value of investable float *)
  fair_value_per_share : float;      (** Book Value + Underwriting + Float Value *)
  margin_of_safety : float;
  implied_combined_ratio : float option;  (** Combined ratio implied by price *)
  signal : investment_signal;
  cost_of_equity : float;
  insurance_metrics : insurance_metrics;
}
[@@deriving show]

(** Oil & Gas E&P valuation result using NAV model *)
type oil_gas_valuation_result = {
  ticker : ticker;
  price : float;
  nav_per_share : float;             (** Net Asset Value per share *)
  reserve_value : float;             (** PV of proven reserves per share *)
  pv10_value : float;                (** SEC PV-10 value per share (10% discount) *)
  fair_value_per_share : float;      (** Blended NAV estimate *)
  margin_of_safety : float;
  implied_oil_price : float option;  (** Oil price implied by current valuation *)
  signal : investment_signal;
  cost_of_capital : float;
  oil_gas_metrics : oil_gas_metrics;
}
[@@deriving show]

type valuation_result = {
  ticker : ticker;
  price : float;
  pve : float;
  pvf_minus_debt : float;
  ivps_fcfe : float;
  ivps_fcff : float;
  margin_of_safety_fcfe : float;
  margin_of_safety_fcff : float;
  implied_growth_fcfe : float option;
  implied_growth_fcff : float option;
  signal : investment_signal;
  cost_of_capital : cost_of_capital;
  projection : cash_flow_projection;
  (* Bank-specific results - only populated when is_bank = true *)
  bank_result : bank_valuation_result option;
  (* Insurance-specific results - only populated when is_insurance = true *)
  insurance_result : insurance_valuation_result option;
  (* Oil & Gas E&P results - only populated when is_oil_gas = true *)
  oil_gas_result : oil_gas_valuation_result option;
}
[@@deriving show]
