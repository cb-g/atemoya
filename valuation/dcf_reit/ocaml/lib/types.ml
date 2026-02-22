(** Core types for REIT valuation model

    REITs (Real Estate Investment Trusts) require specialized valuation
    because:
    1. Depreciation is largely non-economic (real estate appreciates)
    2. 90%+ of taxable income must be distributed as dividends
    3. Growth comes from external funding, not retained earnings
    4. NAV (Net Asset Value) is often more relevant than DCF

    Mortgage REITs (mREITs) are different:
    1. Invest in mortgages/MBS, not physical properties
    2. Earn Net Interest Income (NII), not NOI
    3. Valued by Price/Book, not NAV
    4. Higher leverage, interest rate sensitivity
*)

type ticker = string [@@deriving show]
type currency = string [@@deriving show]

(** REIT property sector classification *)
type property_sector =
  | Retail           (* Shopping centers, malls *)
  | Office           (* Office buildings *)
  | Industrial       (* Warehouses, logistics *)
  | Residential      (* Apartments, multifamily *)
  | Healthcare       (* Hospitals, senior housing *)
  | DataCenter       (* Data centers *)
  | SelfStorage      (* Self-storage facilities *)
  | Hotel            (* Hotels, resorts *)
  | Specialty        (* Cell towers, timber, etc. *)
  | Diversified      (* Multiple property types *)
  | Mortgage         (* Mortgage REIT - invests in mortgages/MBS *)
[@@deriving show]

(** REIT type classification *)
type reit_type =
  | EquityREIT       (* Owns physical properties *)
  | MortgageREIT     (* Owns mortgages and MBS *)
  | HybridREIT       (* Mix of both *)
[@@deriving show]

(** Market data for REIT *)
type market_data = {
  ticker : ticker;
  price : float;              (* Current share price *)
  shares_outstanding : float; (* Shares outstanding *)
  market_cap : float;         (* Market capitalization *)
  dividend_yield : float;     (* Current dividend yield *)
  dividend_per_share : float; (* Annual dividend per share *)
  currency : currency;
  sector : property_sector;
  reit_type : reit_type;      (* Equity, Mortgage, or Hybrid *)
}
[@@deriving show]

(** REIT-specific financial data *)
type financial_data = {
  (* Income statement items *)
  revenue : float;                  (* Total revenue *)
  net_income : float;               (* GAAP net income *)
  depreciation : float;             (* Real estate depreciation *)
  amortization : float;             (* Amortization of intangibles *)
  gains_on_sales : float;           (* Gains on property sales (subtracted from FFO) *)
  impairments : float;              (* Impairment charges (added back to FFO) *)

  (* FFO adjustments - equity REITs *)
  straight_line_rent_adj : float;   (* Straight-line rent adjustment *)
  stock_compensation : float;       (* Stock-based compensation *)

  (* CapEx breakdown - equity REITs *)
  maintenance_capex : float;        (* Required to maintain properties *)
  development_capex : float;        (* New development/acquisitions *)

  (* Balance sheet items *)
  total_debt : float;               (* Total debt outstanding *)
  cash : float;                     (* Cash and equivalents *)
  total_assets : float;             (* Total assets (book value) *)
  total_equity : float;             (* Shareholders' equity *)
  book_value_per_share : float;     (* Book value per share *)

  (* Property-level data - equity REITs *)
  noi : float;                      (* Net Operating Income *)
  occupancy_rate : float;           (* Portfolio occupancy rate 0-1 *)
  same_store_noi_growth : float;    (* Same-store NOI growth rate *)

  (* Lease data - equity REITs *)
  weighted_avg_lease_term : float;  (* WALT in years *)
  lease_expiration_1yr : float;     (* % of leases expiring in 1 year *)

  (* mREIT-specific data *)
  interest_income : float;          (* Interest income from mortgages/MBS *)
  interest_expense : float;         (* Interest expense on borrowings *)
  net_interest_income : float;      (* NII = Interest Income - Interest Expense *)
  earning_assets : float;           (* Total earning assets (mortgages, MBS) *)
  distributable_earnings : float;   (* Distributable earnings (mREIT equivalent of AFFO) *)
}
[@@deriving show]

(** Cap rate assumptions by property sector *)
type cap_rate_assumptions = {
  sector : property_sector;
  implied_cap_rate : float;         (* Calculated from NOI/Property Value *)
  market_cap_rate : float;          (* Current market cap rate for sector *)
  cap_rate_spread : float;          (* Spread to 10Y Treasury *)
}
[@@deriving show]

(** FFO and AFFO calculations - for equity REITs *)
type ffo_metrics = {
  ffo : float;                      (* Funds From Operations *)
  affo : float;                     (* Adjusted FFO *)
  ffo_per_share : float;            (* FFO per share *)
  affo_per_share : float;           (* AFFO per share *)
  ffo_payout_ratio : float;         (* Dividend / FFO *)
  affo_payout_ratio : float;        (* Dividend / AFFO *)
}
[@@deriving show]

(** mREIT-specific metrics *)
type mreit_metrics = {
  net_interest_income : float;      (* NII total *)
  nii_per_share : float;            (* NII per share *)
  net_interest_margin : float;      (* NII / Average Earning Assets *)
  book_value_per_share : float;     (* BVPS *)
  price_to_book : float;            (* P/BV ratio *)
  distributable_earnings : float;   (* DE total *)
  de_per_share : float;             (* DE per share *)
  de_payout_ratio : float;          (* Dividend / DE *)
  leverage_ratio : float;           (* Debt / Equity *)
  interest_coverage : float;        (* NII / Interest Expense *)
}
[@@deriving show]

(** NAV calculation components *)
type nav_components = {
  property_value : float;           (* Implied property value = NOI / Cap Rate *)
  other_assets : float;             (* Cash + other assets *)
  total_debt : float;               (* Total debt to subtract *)
  nav : float;                      (* Net Asset Value *)
  nav_per_share : float;            (* NAV per share *)
  premium_discount : float;         (* Price premium/discount to NAV *)
}
[@@deriving show]

(** Dividend discount model inputs *)
type ddm_params = {
  cost_of_equity : float;           (* Required return on equity *)
  dividend_growth_rate : float;     (* Expected dividend growth *)
  terminal_growth_rate : float;     (* Long-term growth rate *)
  projection_years : int;           (* Years to project before terminal *)
}
[@@deriving show]

(** Cost of capital for REITs *)
type cost_of_capital = {
  risk_free_rate : float;
  equity_risk_premium : float;
  reit_beta : float;                (* REIT-specific beta *)
  size_premium : float;             (* Small cap premium if applicable *)
  cost_of_equity : float;           (* ke = Rf + Beta * ERP + Size *)
  cost_of_debt : float;             (* Pre-tax cost of debt *)
  tax_rate : float;                 (* Effective tax rate (often ~0 for REITs) *)
  debt_ratio : float;               (* D / (D + E) *)
  wacc : float;                     (* Weighted average cost of capital *)
}
[@@deriving show]

(** Valuation method results *)
type valuation_method =
  | PriceToFFO of {
      p_ffo : float;                (* Price / FFO *)
      sector_avg : float;           (* Sector average P/FFO *)
      implied_value : float;        (* Value at sector average *)
    }
  | PriceToAFFO of {
      p_affo : float;               (* Price / AFFO *)
      sector_avg : float;           (* Sector average P/AFFO *)
      implied_value : float;        (* Value at sector average *)
    }
  | NAVMethod of {
      nav_per_share : float;        (* NAV per share *)
      premium_discount : float;     (* Current premium/discount *)
      target_premium : float;       (* Target premium for quality *)
      implied_value : float;        (* Fair value estimate *)
    }
  | DividendDiscount of {
      intrinsic_value : float;      (* DDM fair value *)
      dividend_yield : float;       (* Current yield *)
      implied_growth : float;       (* Implied dividend growth *)
    }
  (* mREIT-specific valuation methods *)
  | PriceToBook of {
      p_bv : float;                 (* Price / Book Value *)
      sector_avg : float;           (* Sector average P/BV for mREITs *)
      implied_value : float;        (* Value at sector average *)
    }
  | PriceToDE of {
      p_de : float;                 (* Price / Distributable Earnings *)
      sector_avg : float;           (* Sector average P/DE *)
      implied_value : float;        (* Value at sector average *)
    }
[@@deriving show]

(** Investment signal for REITs *)
type investment_signal =
  | StrongBuy       (* >30% upside, quality metrics strong *)
  | Buy             (* 15-30% upside, solid fundamentals *)
  | Hold            (* -10% to +15% from fair value *)
  | Sell            (* 10-25% overvalued *)
  | StrongSell      (* >25% overvalued or fundamental concerns *)
  | Caution         (* Mixed signals, elevated risk *)
[@@deriving show]

(** Quality metrics for REIT assessment *)
type quality_metrics = {
  occupancy_score : float;          (* 0-1, higher is better *)
  lease_quality_score : float;      (* Based on WALT and expirations *)
  balance_sheet_score : float;      (* Debt ratios, coverage *)
  growth_score : float;             (* Same-store NOI, FFO growth *)
  dividend_safety_score : float;    (* Payout ratio health *)
  overall_quality : float;          (* Weighted average 0-1 *)
}
[@@deriving show]

(** Complete REIT valuation result *)
type valuation_result = {
  ticker : ticker;
  price : float;
  reit_type : reit_type;            (* Equity, Mortgage, or Hybrid *)

  (* FFO-based metrics - equity REITs *)
  ffo_metrics : ffo_metrics;

  (* mREIT metrics - mortgage REITs *)
  mreit_metrics : mreit_metrics option;

  (* NAV analysis - equity REITs *)
  nav : nav_components;

  (* Cost of capital *)
  cost_of_capital : cost_of_capital;

  (* Multiple valuation approaches *)
  p_ffo_valuation : valuation_method;
  p_affo_valuation : valuation_method;
  nav_valuation : valuation_method;
  ddm_valuation : valuation_method;

  (* mREIT valuation methods *)
  p_bv_valuation : valuation_method option;
  p_de_valuation : valuation_method option;

  (* Blended fair value *)
  fair_value : float;               (* Weighted average of methods *)
  upside_potential : float;         (* % upside to fair value *)

  (* Quality assessment *)
  quality : quality_metrics;

  (* Final recommendation *)
  signal : investment_signal;
}
[@@deriving show]

(** Sector-specific cap rate and multiple benchmarks *)
type sector_benchmarks = {
  sector : property_sector;
  avg_cap_rate : float;
  avg_p_ffo : float;
  avg_p_affo : float;
  avg_nav_premium : float;          (* Historical premium/discount to NAV *)
}
[@@deriving show]

(** Valuation configuration *)
type config = {
  risk_free_rate : float;
  equity_risk_premium : float;
  sector_benchmarks : sector_benchmarks list;
  ddm_params : ddm_params;
}
[@@deriving show]
