(** Forward Volatility Calculator *)

open Types

(** Calculate forward volatility between two expirations *)
let calculate_forward_vol
    ~(ticker : string)
    ~(front_exp : string)
    ~(back_exp : string)
    ~(front_dte : int)
    ~(back_dte : int)
    ~(front_iv : float)
    ~(back_iv : float)
    : forward_vol =

  (* Convert DTE to years *)
  let t1 = float_of_int front_dte /. 365.0 in
  let t2 = float_of_int back_dte /. 365.0 in

  (* Calculate variances (σ²) *)
  let v1 = front_iv *. front_iv in
  let v2 = back_iv *. back_iv in

  (* Calculate forward variance *)
  (* V_fwd = (σ2² × T2 - σ1² × T1) / (T2 - T1) *)
  let forward_variance =
    if t2 > t1 then
      (v2 *. t2 -. v1 *. t1) /. (t2 -. t1)
    else
      0.0  (* Invalid: back must be after front *)
  in

  (* Ensure non-negative variance *)
  let forward_variance = max 0.0 forward_variance in

  (* Calculate forward volatility (σ_fwd = sqrt(V_fwd)) *)
  let forward_volatility = sqrt forward_variance in

  (* Calculate forward factor *)
  (* FF = (σ1 - σ_fwd) / σ_fwd *)
  let forward_factor =
    if forward_volatility > 0.0 then
      (front_iv -. forward_volatility) /. forward_volatility
    else
      0.0
  in

  {
    ticker;
    front_exp;
    back_exp;
    front_dte;
    back_dte;
    front_iv;
    back_iv;
    forward_variance;
    forward_vol = forward_volatility;
    forward_factor;
  }

(** Print forward volatility analysis *)
let print_forward_vol (fv : forward_vol) : unit =
  Printf.printf "\n=== Forward Volatility Analysis: %s ===\n" fv.ticker;
  Printf.printf "Front: %s (%d DTE) | IV: %.2f%%\n"
    fv.front_exp fv.front_dte (fv.front_iv *. 100.0);
  Printf.printf "Back:  %s (%d DTE) | IV: %.2f%%\n"
    fv.back_exp fv.back_dte (fv.back_iv *. 100.0);
  Printf.printf "\nForward Metrics:\n";
  Printf.printf "  Forward Volatility: %.2f%%\n" (fv.forward_vol *. 100.0);
  Printf.printf "  Forward Factor: %.2f (%.1f%%)\n" fv.forward_factor (fv.forward_factor *. 100.0);

  (* Interpretation *)
  if fv.forward_factor >= 1.0 then
    Printf.printf "\n✓ EXTREME BACKWARDATION (FF ≥ 100%%) - Exceptional setup!\n"
  else if fv.forward_factor >= 0.5 then
    Printf.printf "\n✓ STRONG BACKWARDATION (FF ≥ 50%%) - Strong setup\n"
  else if fv.forward_factor >= 0.20 then
    Printf.printf "\n✓ BACKWARDATION (FF ≥ 20%%) - Valid setup\n"
  else if fv.forward_factor > 0.0 then
    Printf.printf "\n⚠ Weak backwardation (FF < 20%%) - Below threshold\n"
  else if fv.forward_factor >= -0.20 then
    Printf.printf "\n⚠ Contango (FF < 0) - Not recommended\n"
  else
    Printf.printf "\n✗ Strong contango (FF < -20%%) - Avoid\n"

(** Check if forward factor passes threshold *)
let passes_threshold ~(fv : forward_vol) ~(threshold : float) : bool =
  fv.forward_factor >= threshold
