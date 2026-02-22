(** Equity Risk Premium (ERP) Calculation Module

    Supports two modes:
    1. Static: Uses Damodaran's annually-updated country ERP estimates
    2. Dynamic: Adjusts base ERP using current VIX levels

    The dynamic approach is based on the observation that implied volatility
    (VIX) is a real-time measure of market risk aversion. When VIX rises,
    investors demand higher compensation for equity risk.

    Academic basis:
    - Bollerslev, Tauchen, Zhou (2009): "Expected Stock Returns and Variance
      Risk Premia" - shows VIX contains information about expected returns
    - Graham & Harvey surveys: CFO discount rate expectations correlate with
      market volatility
    - Damodaran's ERP is based on implied ERP from S&P 500 forward earnings
*)

open Types

(** Default VIX parameters based on historical data (1990-2024) *)
let default_vix_mean = 19.5      (* Long-term VIX average *)
let default_vix_sensitivity = 0.4 (* Moderate sensitivity *)

(** Default ERP configuration using static mode *)
let default_erp_config ~base_erp =
  {
    source = Static;
    base_erp;
    current_vix = None;
  }

(** Create a dynamic ERP configuration

    Args:
      base_erp: Country-specific base ERP (from Damodaran)
      current_vix: Current VIX level
      vix_mean: Historical VIX mean (default 19.5)
      sensitivity: ERP sensitivity to VIX ratio (default 0.4)
*)
let dynamic_erp_config
    ~base_erp
    ~current_vix
    ?(vix_mean = default_vix_mean)
    ?(sensitivity = default_vix_sensitivity)
    () =
  {
    source = Dynamic { vix_mean; sensitivity };
    base_erp;
    current_vix = Some current_vix;
  }

(** Calculate the VIX adjustment factor

    adjustment = (VIX / VIX_mean) ^ sensitivity

    This gives:
    - VIX = VIX_mean: adjustment = 1.0 (no change)
    - VIX > VIX_mean: adjustment > 1.0 (higher ERP in fearful markets)
    - VIX < VIX_mean: adjustment < 1.0 (lower ERP in calm markets)

    The power function (rather than linear) captures the non-linear
    relationship between volatility and risk aversion.

    Example:
    - VIX = 30, mean = 20, sensitivity = 0.4
    - adjustment = (30/20)^0.4 = 1.5^0.4 ≈ 1.176
    - If base ERP = 4.33%, dynamic ERP = 5.09%
*)
let calculate_vix_adjustment ~current_vix ~vix_mean ~sensitivity =
  if vix_mean <= 0.0 then 1.0
  else
    let ratio = current_vix /. vix_mean in
    (* Clamp ratio to avoid extreme adjustments *)
    let clamped_ratio = max 0.5 (min 3.0 ratio) in
    clamped_ratio ** sensitivity

(** Calculate the effective ERP given the configuration

    Returns (erp, adjustment_factor):
    - erp: The equity risk premium to use
    - adjustment_factor: 1.0 for static, VIX adjustment for dynamic
*)
let calculate_erp config =
  match config.source with
  | Static ->
      (* Static mode: just return the base Damodaran ERP *)
      (config.base_erp, 1.0)

  | Dynamic { vix_mean; sensitivity } ->
      (* Dynamic mode: adjust base ERP using current VIX *)
      begin match config.current_vix with
      | None ->
          (* No VIX data available, fall back to static *)
          (config.base_erp, 1.0)
      | Some current_vix ->
          let adjustment = calculate_vix_adjustment
            ~current_vix ~vix_mean ~sensitivity
          in
          let adjusted_erp = config.base_erp *. adjustment in
          (adjusted_erp, adjustment)
      end

(** Create ERP config from country lookup with optional VIX override

    This is the main entry point for getting ERP:
    - Looks up base ERP from country list (Damodaran data)
    - If vix_config is provided, uses dynamic mode
    - Otherwise uses static mode
*)
let get_erp_for_country
    ~erp_list
    ~country
    ?vix_config
    () =
  (* Look up base ERP for country *)
  let base_erp =
    match List.assoc_opt country erp_list with
    | Some erp -> erp
    | None ->
        (* Fall back to US ERP as global default *)
        match List.assoc_opt "USA" erp_list with
        | Some erp -> erp
        | None -> 0.05  (* Ultimate fallback: 5% *)
  in

  (* Create appropriate config *)
  let config = match vix_config with
    | None ->
        default_erp_config ~base_erp
    | Some (current_vix, vix_mean, sensitivity) ->
        dynamic_erp_config ~base_erp ~current_vix ~vix_mean ~sensitivity ()
  in

  calculate_erp config

(** Convenience function to get ERP info for display/logging *)
let describe_erp_source config (erp, adjustment) =
  let open Printf in
  match config.source with
  | Static ->
      sprintf "Static (Damodaran): %.2f%%" (erp *. 100.0)
  | Dynamic { vix_mean; sensitivity = sens } ->
      begin match config.current_vix with
      | None ->
          sprintf "Dynamic (VIX unavailable, using static): %.2f%%" (erp *. 100.0)
      | Some vix ->
          sprintf "Dynamic: %.2f%% (base %.2f%% × %.3f VIX adj, VIX=%.1f, mean=%.1f, sens=%.2f)"
            (erp *. 100.0)
            (config.base_erp *. 100.0)
            adjustment
            vix
            vix_mean
            sens
      end
