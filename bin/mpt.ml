let () =
  (* hardcoded file paths *)
  let input_csv = "data/pri/mpt/adjusted_closes.csv" in
  let mean_out = "data/pri/mpt/mean.csv" in
  let cov_out = "data/pri/mpt/cov.csv" in
  (* load header for tickers *)
  let raw = Csv.load input_csv in
  let tickers = match raw with
    | header :: _ -> (
        match header with
        | _ :: ts -> ts
        | [] -> failwith "Empty header in input CSV"
      )
    | _ -> failwith "Input CSV is empty"
  in
  (* compute matrix outputs *)
  let closes = Atemoya.Mpt.read_adjusted_closes input_csv in
  let log_r = Atemoya.Mpt.compute_log_returns closes in
  let mu = Atemoya.Mpt.mean_return_vector log_r in
  let cov = Atemoya.Mpt.covariance_matrix log_r in
  (* prepare mean csv *)
  let mean_table =
    let header = ["Ticker"; "Mean"] in
    let rows =
      List.mapi (fun i ticker -> [ ticker; string_of_float mu.{i+1} ]) tickers
    in
    header :: rows
  in
  Csv.save mean_out mean_table;
  (* prepare covariance csv *)
  let cov_table =
    let header = "" :: tickers in
    let rows =
      List.mapi (fun i ticker_i ->
        let row_vals = List.mapi (fun j _ -> string_of_float cov.{i+1, j+1}) tickers in
        ticker_i :: row_vals
      ) tickers
    in
    header :: rows
  in
  Csv.save cov_out cov_table;

  (* calculate and save efficient frontier *)
  let frontier_points = Atemoya.Mpt.efficient_frontier mu cov 100 in
  (* save annualized efficient frontier points (mu, sigma only) *)
  let frontier_out = "data/pri/mpt/efficient_frontier.csv" in
  let frontier_table =
    let header = ["Return"; "Risk"] in
    let rows =
      List.map (fun (ret, risk, _) ->
        let annual_mu = ret *. 252.0 in
        let annual_sigma = risk *. sqrt 252.0 in
        [string_of_float annual_mu; string_of_float annual_sigma]
      ) frontier_points
    in
    header :: rows
  in
  Csv.save frontier_out frontier_table;

  (* extract 3 representative portfolios: min-risk, mid-point, max-return *)
  let fst3 (x, _, _) = x
  and snd3 (_, x, _) = x
  and trd3 (_, _, x) = x in

  (* extract min-risk portfolio *)
  let min_risk_point =
    List.fold_left (fun acc x -> if snd3 x < snd3 acc then x else acc)
                  (List.hd frontier_points) frontier_points
  in

  (* extract max-return portfolio (last point, since μ is increasing) *)
  let max_return_point = List.hd (List.rev frontier_points) in

  (* midpoint in return space *)
  let mid_mu_target = (fst3 min_risk_point +. fst3 max_return_point) /. 2.0 in

  (* portfolio with return closest to that midpoint *)
  let mid_point =
    List.fold_left (fun best x ->
      let diff = abs_float (fst3 x -. mid_mu_target) in
      let best_diff = abs_float (fst3 best -. mid_mu_target) in
      if diff < best_diff then x else best
    ) (List.hd frontier_points) frontier_points
  in

  (* construct labeled example portfolios *)
  let example_portfolios = [
    ("min-risk", fst3 min_risk_point, snd3 min_risk_point, trd3 min_risk_point);
    ("mid-return", fst3 mid_point, snd3 mid_point, trd3 mid_point);
    ("max-return", fst3 max_return_point, snd3 max_return_point, trd3 max_return_point);
  ]
  in

  (* save 3 example portfolios: label, return, risk, per-asset weights *)
  let example_out = "data/pri/mpt/example_portfolios.csv" in
  Atemoya.Mpt.write_example_portfolios_to_csv example_out tickers example_portfolios;

  print_endline "MPT data exported to mean.csv, cov.csv, and annualized efficient_frontier.csv.";


  