(** Weekly scenario generation from daily returns *)

open Types

(** Convert daily returns to weekly returns
    Compounds daily returns within each week *)
let daily_to_weekly returns =
  let n = Array.length returns in
  let n_weeks = n / 5 in  (* 5 trading days per week *)

  if n_weeks = 0 then [||]
  else
    let weekly = Array.make n_weeks 0.0 in

    for week = 0 to n_weeks - 1 do
      let start_idx = week * 5 in
      let end_idx = min (start_idx + 5) n in

      (* Compound returns: (1+r1)(1+r2)...(1+r5) - 1 *)
      let compound = ref 1.0 in
      for i = start_idx to end_idx - 1 do
        compound := !compound *. (1.0 +. returns.(i))
      done;

      weekly.(week) <- !compound -. 1.0
    done;

    weekly

(** Create weekly scenario matrix from asset return series list *)
let create_weekly_scenarios asset_returns_list =
  (* Convert each asset's daily returns to weekly *)
  let weekly_by_asset = List.map (fun (rs : return_series) ->
    (rs.ticker, daily_to_weekly rs.returns)
  ) asset_returns_list in

  (* Get number of weeks (should be same for all assets) *)
  let n_weeks = match weekly_by_asset with
    | [] -> 0
    | (_, weeks) :: _ -> Array.length weeks
  in

  (* Get number of assets *)
  let n_assets = List.length weekly_by_asset in

  (* Create scenario matrix R[t,i] *)
  let scenarios = Array.make_matrix n_weeks n_assets 0.0 in

  List.iteri (fun asset_idx (_, weekly_returns) ->
    for week = 0 to n_weeks - 1 do
      scenarios.(week).(asset_idx) <- weekly_returns.(week)
    done
  ) weekly_by_asset;

  scenarios

(** Get tickers in order from scenario creation *)
let get_tickers_ordered asset_returns_list =
  List.map (fun (rs : return_series) -> rs.ticker) asset_returns_list

(** Create weekly benchmark scenarios *)
let create_weekly_benchmark benchmark_returns =
  daily_to_weekly benchmark_returns

(** Create weekly cash scenarios (typically zeros or risk-free rate) *)
let create_weekly_cash n_weeks =
  Array.make n_weeks 0.0  (* Assume 0% cash return for simplicity *)
