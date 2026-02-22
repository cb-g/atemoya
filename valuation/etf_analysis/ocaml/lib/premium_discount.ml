(** Premium/Discount and NAV Analysis *)

open Types

(** Classify premium/discount status *)
let classify_nav_status (premium_discount_pct : float) : nav_status =
  if abs_float premium_discount_pct < 0.1 then AtNav
  else if premium_discount_pct > 0.0 then Premium premium_discount_pct
  else Discount premium_discount_pct

(** Get string representation of NAV status *)
let nav_status_to_string (status : nav_status) : string =
  match status with
  | AtNav -> "At NAV"
  | Premium pct -> Printf.sprintf "Premium (+%.2f%%)" pct
  | Discount pct -> Printf.sprintf "Discount (%.2f%%)" pct

(** Check if premium/discount is unusual (beyond typical range) *)
let is_unusual_nav_gap (premium_discount_pct : float) (derivatives_type : derivatives_type) : bool =
  let threshold =
    match derivatives_type with
    | Standard -> 0.5      (* Standard ETFs should track NAV closely *)
    | CoveredCall -> 1.0   (* Options can cause slight deviation *)
    | Buffer -> 1.5        (* Options-based, more deviation expected *)
    | Volatility -> 2.0    (* VIX products can gap significantly *)
    | PutWrite -> 1.0
    | Leveraged -> 1.0
  in
  abs_float premium_discount_pct > threshold

(** Score premium/discount for ETF quality *)
let score_nav_gap (premium_discount_pct : float) : float =
  let abs_gap = abs_float premium_discount_pct in
  if abs_gap < 0.05 then 10.0
  else if abs_gap < 0.10 then 8.0
  else if abs_gap < 0.25 then 6.0
  else if abs_gap < 0.50 then 4.0
  else if abs_gap < 1.00 then 2.0
  else 0.0

(** Assess tracking quality from tracking error *)
let classify_tracking_quality (tracking_error_pct : float) : tracking_quality =
  if tracking_error_pct < 0.10 then Excellent
  else if tracking_error_pct < 0.25 then Good
  else if tracking_error_pct < 0.50 then Acceptable
  else if tracking_error_pct < 1.00 then Poor
  else VeryPoor

(** Get string representation of tracking quality *)
let tracking_quality_to_string (quality : tracking_quality) : string =
  match quality with
  | Excellent -> "Excellent"
  | Good -> "Good"
  | Acceptable -> "Acceptable"
  | Poor -> "Poor"
  | VeryPoor -> "Very Poor"

(** Score tracking quality *)
let score_tracking (tracking : tracking_metrics option) : float =
  match tracking with
  | None -> 12.5  (* Default to middle score if no tracking data *)
  | Some t ->
    let te = t.tracking_error_pct in
    if te < 0.10 then 25.0
    else if te < 0.25 then 20.0
    else if te < 0.50 then 15.0
    else if te < 1.00 then 10.0
    else 5.0

(** Check if tracking is degraded (significantly negative tracking difference) *)
let is_tracking_degraded (tracking : tracking_metrics option) : bool =
  match tracking with
  | None -> false
  | Some t ->
    (* Tracking diff more negative than -1% is concerning *)
    t.tracking_difference_pct < -1.0

(** Generate recommendations based on NAV and tracking analysis *)
let generate_nav_recommendations (data : etf_data) : string list =
  let recs = ref [] in

  (* Premium/discount recommendations *)
  if is_unusual_nav_gap data.premium_discount_pct data.derivatives_type then begin
    if data.premium_discount_pct > 0.0 then
      recs := "Trading at unusual premium to NAV - verify arbitrage mechanism" :: !recs
    else
      recs := "Trading at unusual discount to NAV - check liquidity and market conditions" :: !recs
  end;

  (* Tracking recommendations *)
  (match data.tracking with
   | Some t ->
     if t.tracking_error_pct > 1.0 then
       recs := "High tracking error - may not closely follow benchmark" :: !recs;
     if t.tracking_difference_pct < -1.0 then
       recs := Printf.sprintf "Significant tracking drag (%.2f%%) vs benchmark" t.tracking_difference_pct :: !recs;
     if t.correlation < 0.95 then
       recs := "Lower correlation to benchmark - check holdings alignment" :: !recs
   | None -> ());

  List.rev !recs
