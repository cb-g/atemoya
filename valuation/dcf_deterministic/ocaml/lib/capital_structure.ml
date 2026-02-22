(** Capital structure and cost of capital calculations *)

let calculate_leveraged_beta ~unlevered_beta ~tax_rate ~debt ~equity =
  (* Hamada formula: β_L = β_U × [1 + (1 - tax_rate) × (D/E)] *)
  if equity = 0.0 then
    unlevered_beta  (* Avoid division by zero *)
  else
    unlevered_beta *. (1.0 +. (1.0 -. tax_rate) *. (debt /. equity))

let calculate_cost_of_equity ~risk_free_rate ~leveraged_beta ~equity_risk_premium =
  (* CAPM: CE = RFR + β_L × ERP *)
  risk_free_rate +. (leveraged_beta *. equity_risk_premium)

(** Fama-French 3-Factor Model Extensions *)

(** Calculate size factor loading (SMB)
    Based on market cap percentiles:
    - Small cap (< threshold): +1.0
    - Mid cap: 0.0
    - Large cap (> 10× threshold): -0.5

    The loading represents exposure to the size premium.
    Small caps historically outperform large caps by ~2-3% annually.
*)
let calculate_smb_loading ~market_cap ~small_cap_threshold =
  if market_cap < small_cap_threshold then
    1.0  (* Full small-cap exposure *)
  else if market_cap > small_cap_threshold *. 10.0 then
    -0.5  (* Large cap: slight negative exposure *)
  else
    (* Linear interpolation for mid caps *)
    let log_cap = log market_cap in
    let log_small = log small_cap_threshold in
    let log_large = log (small_cap_threshold *. 10.0) in
    let t = (log_cap -. log_small) /. (log_large -. log_small) in
    1.0 -. t *. 1.5  (* Ranges from +1.0 to -0.5 *)

(** Calculate value factor loading (HML)
    Based on book-to-market ratio:
    - Value (high B/M > threshold): +1.0
    - Blend: 0.0
    - Growth (low B/M < threshold/3): -0.5

    The loading represents exposure to the value premium.
    Value stocks historically outperform growth by ~3-5% annually.
*)
let calculate_hml_loading ~book_to_market ~value_btm_threshold =
  if book_to_market > value_btm_threshold then
    1.0  (* Full value exposure *)
  else if book_to_market < value_btm_threshold /. 3.0 then
    -0.5  (* Growth stock: slight negative exposure *)
  else
    (* Linear interpolation *)
    let growth_threshold = value_btm_threshold /. 3.0 in
    let t = (book_to_market -. growth_threshold) /. (value_btm_threshold -. growth_threshold) in
    -0.5 +. t *. 1.5  (* Ranges from -0.5 to +1.0 *)

(** Calculate cost of equity with Fama-French 3-factor model
    CE = RFR + β × ERP + SMB_loading × SMB_premium + HML_loading × HML_premium

    This extends CAPM by adding size and value premiums, which capture
    risk factors not explained by market beta alone.
*)
let calculate_cost_of_equity_fama_french
    ~risk_free_rate
    ~leveraged_beta
    ~equity_risk_premium
    ~smb_loading
    ~hml_loading
    ~smb_premium
    ~hml_premium =
  let capm_ce = calculate_cost_of_equity ~risk_free_rate ~leveraged_beta ~equity_risk_premium in
  let size_contribution = smb_loading *. smb_premium in
  let value_contribution = hml_loading *. hml_premium in
  capm_ce +. size_contribution +. value_contribution

(** Default Fama-French configuration (disabled for backward compatibility) *)
let default_fama_french_config () =
  let open Types in
  {
    enabled = false;
    smb_premium = 0.025;           (* 2.5% size premium *)
    hml_premium = 0.035;           (* 3.5% value premium *)
    small_cap_threshold = 2000.0;  (* $2B market cap *)
    value_btm_threshold = 0.7;     (* Book-to-market > 0.7 = value *)
  }

let calculate_cost_of_borrowing ~interest_expense ~total_debt =
  (* CB = interest_expense / total_debt *)
  if total_debt = 0.0 then
    0.0  (* No debt, no cost of borrowing *)
  else
    interest_expense /. total_debt

let calculate_wacc ~equity ~debt ~cost_of_equity ~cost_of_borrowing ~tax_rate =
  (* WACC = (E/(E+D)) × CE + (D/(E+D)) × CB × (1 - tax_rate) *)
  let total_value = equity +. debt in
  if total_value = 0.0 then
    cost_of_equity  (* Fallback to cost of equity *)
  else
    let equity_weight = equity /. total_value in
    let debt_weight = debt /. total_value in
    (equity_weight *. cost_of_equity) +.
    (debt_weight *. cost_of_borrowing *. (1.0 -. tax_rate))

(** Default ERP configuration (static Damodaran mode for backward compatibility) *)
let default_erp_config ~base_erp =
  let open Types in
  {
    source = Static;
    base_erp;
    current_vix = None;
  }

(** Calculate cost of capital with optional Fama-French 3-factor model and ERP mode

    Args:
      erp_config: Optional ERP configuration. If not provided, uses static mode
                  with equity_risk_premium as the base ERP.
      fama_french_config: Optional Fama-French 3-factor configuration
      market_data: Market data for the company
      financial_data: Financial statement data
      unlevered_beta: Industry unlevered beta
      risk_free_rate: Risk-free rate
      equity_risk_premium: Base ERP (used if erp_config not provided)
      tax_rate: Corporate tax rate
*)
let calculate_cost_of_capital
    ?erp_config
    ?(fama_french_config = default_fama_french_config ())
    ~market_data
    ~financial_data
    ~unlevered_beta
    ~risk_free_rate
    ~equity_risk_premium
    ~tax_rate
    () =
  let open Types in

  (* Determine ERP using provided config or default to static mode *)
  let (erp_config_used, effective_erp, erp_adjustment) =
    match erp_config with
    | Some config ->
        let (erp, adj) = Erp.calculate_erp config in
        (config.source, erp, adj)
    | None ->
        (* Legacy mode: use provided equity_risk_premium directly (static) *)
        (Static, equity_risk_premium, 1.0)
  in

  let erp_base = match erp_config with
    | Some config -> config.base_erp
    | None -> equity_risk_premium
  in

  (* Calculate leveraged beta *)
  let leveraged_beta = calculate_leveraged_beta
    ~unlevered_beta
    ~tax_rate
    ~debt:market_data.mvb
    ~equity:market_data.mve
  in

  (* Calculate Fama-French factor loadings if enabled *)
  let (smb_loading, hml_loading, size_premium, value_premium) =
    if fama_french_config.enabled then begin
      (* Market cap in millions *)
      let market_cap_mm = market_data.mve /. 1_000_000.0 in

      (* Book-to-market ratio *)
      let book_to_market =
        if market_data.mve > 0.0 then
          financial_data.book_value_equity /. market_data.mve
        else 0.0
      in

      let smb_l = calculate_smb_loading
        ~market_cap:market_cap_mm
        ~small_cap_threshold:fama_french_config.small_cap_threshold
      in

      let hml_l = calculate_hml_loading
        ~book_to_market
        ~value_btm_threshold:fama_french_config.value_btm_threshold
      in

      let size_p = smb_l *. fama_french_config.smb_premium in
      let value_p = hml_l *. fama_french_config.hml_premium in

      (smb_l, hml_l, size_p, value_p)
    end else
      (0.0, 0.0, 0.0, 0.0)
  in

  (* Calculate cost of equity using effective ERP *)
  let ce =
    if fama_french_config.enabled then
      calculate_cost_of_equity_fama_french
        ~risk_free_rate
        ~leveraged_beta
        ~equity_risk_premium:effective_erp
        ~smb_loading
        ~hml_loading
        ~smb_premium:fama_french_config.smb_premium
        ~hml_premium:fama_french_config.hml_premium
    else
      calculate_cost_of_equity
        ~risk_free_rate
        ~leveraged_beta
        ~equity_risk_premium:effective_erp
  in

  (* Calculate cost of borrowing *)
  let cb = calculate_cost_of_borrowing
    ~interest_expense:financial_data.interest_expense
    ~total_debt:market_data.mvb
  in

  (* Calculate WACC *)
  let wacc = calculate_wacc
    ~equity:market_data.mve
    ~debt:market_data.mvb
    ~cost_of_equity:ce
    ~cost_of_borrowing:cb
    ~tax_rate
  in

  {
    ce;
    cb;
    wacc;
    leveraged_beta;
    risk_free_rate;
    equity_risk_premium = effective_erp;
    erp_source_used = erp_config_used;
    erp_base;
    erp_vix_adjustment = erp_adjustment;
    smb_loading;
    hml_loading;
    size_premium;
    value_premium;
  }

(** Legacy wrapper for backward compatibility (pure CAPM, static ERP) *)
let calculate_cost_of_capital_capm
    ~market_data
    ~financial_data
    ~unlevered_beta
    ~risk_free_rate
    ~equity_risk_premium
    ~tax_rate =
  calculate_cost_of_capital
    ~fama_french_config:(default_fama_french_config ())
    ~market_data
    ~financial_data
    ~unlevered_beta
    ~risk_free_rate
    ~equity_risk_premium
    ~tax_rate
    ()

(** Calculate cost of capital with dynamic VIX-adjusted ERP

    This is the recommended entry point when you want to use real-time
    VIX data to adjust the equity risk premium.

    Args:
      current_vix: Current VIX level (e.g., from CBOE)
      vix_mean: Historical VIX mean (default: 19.5)
      vix_sensitivity: ERP sensitivity to VIX (default: 0.4)
*)
let calculate_cost_of_capital_dynamic
    ~current_vix
    ?(vix_mean = Erp.default_vix_mean)
    ?(vix_sensitivity = Erp.default_vix_sensitivity)
    ?(fama_french_config = default_fama_french_config ())
    ~market_data
    ~financial_data
    ~unlevered_beta
    ~risk_free_rate
    ~base_equity_risk_premium
    ~tax_rate
    () =
  let open Types in
  let erp_config = {
    source = Dynamic { vix_mean; sensitivity = vix_sensitivity };
    base_erp = base_equity_risk_premium;
    current_vix = Some current_vix;
  } in
  calculate_cost_of_capital
    ~erp_config
    ~fama_french_config
    ~market_data
    ~financial_data
    ~unlevered_beta
    ~risk_free_rate
    ~equity_risk_premium:base_equity_risk_premium
    ~tax_rate
    ()
