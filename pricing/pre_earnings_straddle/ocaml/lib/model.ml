(** Linear Regression Model *)

open Types

(** Predict expected return using linear regression model *)
let predict_return
    ~(signals : signals)
    ~(coefficients : model_coefficients)
    : float =

  coefficients.intercept +.
  (coefficients.coef_implied_vs_last_implied *. signals.implied_vs_last_implied_ratio) +.
  (coefficients.coef_implied_vs_last_realized *. signals.implied_vs_last_realized_gap) +.
  (coefficients.coef_implied_vs_avg_implied *. signals.implied_vs_avg_implied_ratio) +.
  (coefficients.coef_implied_vs_avg_realized *. signals.implied_vs_avg_realized_gap)

(** Calculate Kelly fraction for this trade *)
let calculate_kelly
    ~(predicted_return : float)
    ~(max_loss : float)
    : float =
  let _ = max_loss in  (* Max loss is the debit paid for straddle *)

  (* For long straddles:
     - Max loss = debit paid
     - Win rate ~ 42% from backtest
     - Avg win ~ ???
     - This is complex, so use simplified formula *)

  (* Conservative Kelly for long vol strategies *)
  (* Kelly = (p * b - q) / b *)
  (* Where p = win prob, q = loss prob, b = win/loss ratio *)

  (* From video: win rate ~42%, mean return ~3.3% on filtered *)
  (* Assume avg winner ~ +15%, avg loser ~ -50% of debit *)

  let p = 0.42 in  (* Win probability *)
  let q = 1.0 -. p in  (* Loss probability *)
  let b = 0.15 /. 0.50 in  (* Win/loss ratio (very conservative estimate) *)

  let kelly_full = (p *. b -. q) /. b in

  (* Scale by predicted return vs average *)
  let avg_return = 0.033 in  (* 3.3% from backtest *)
  let scale = if avg_return > 0.0 then predicted_return /. avg_return else 1.0 in
  let scaled_kelly = kelly_full *. (max 0.0 (min 2.0 scale)) in

  (* Cap at reasonable maximum *)
  max 0.0 (min 0.10 scaled_kelly)  (* Max 10% Kelly *)

(** Load model coefficients from CSV file *)
let load_coefficients ~(file_path : string) : model_coefficients =
  try
    let ic = open_in file_path in
    let _ = input_line ic in  (* Skip header *)
    let line = input_line ic in
    close_in ic;

    let parts = String.split_on_char ',' line in
    match parts with
    | [intercept; coef1; coef2; coef3; coef4] ->
        {
          intercept = float_of_string intercept;
          coef_implied_vs_last_implied = float_of_string coef1;
          coef_implied_vs_last_realized = float_of_string coef2;
          coef_implied_vs_avg_implied = float_of_string coef3;
          coef_implied_vs_avg_realized = float_of_string coef4;
        }
    | _ ->
        Printf.printf "Warning: Invalid coefficients file, using defaults\n";
        default_coefficients
  with Sys_error _ | End_of_file | Failure _ ->
    Printf.printf "Warning: Could not load coefficients file, using defaults\n";
    default_coefficients

(** Save model coefficients to CSV file *)
let save_coefficients ~(file_path : string) ~(coefficients : model_coefficients) : unit =
  let oc = open_out file_path in
  Printf.fprintf oc "intercept,coef_implied_vs_last_implied,coef_implied_vs_last_realized,coef_implied_vs_avg_implied,coef_implied_vs_avg_realized\n";
  Printf.fprintf oc "%.6f,%.6f,%.6f,%.6f,%.6f\n"
    coefficients.intercept
    coefficients.coef_implied_vs_last_implied
    coefficients.coef_implied_vs_last_realized
    coefficients.coef_implied_vs_avg_implied
    coefficients.coef_implied_vs_avg_realized;
  close_out oc
