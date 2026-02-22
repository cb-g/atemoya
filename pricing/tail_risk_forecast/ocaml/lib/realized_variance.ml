(** Realized Variance computation from intraday returns *)

open Types

let compute_daily_rv ~date ~close_price (returns : intraday_return array) : daily_rv =
  let n = Array.length returns in
  if n = 0 then
    { date; rv = 0.0; n_obs = 0; close_price }
  else
    (* RV = sum of squared returns *)
    let rv = Array.fold_left (fun acc r -> acc +. (r.ret *. r.ret)) 0.0 returns in
    { date; rv; n_obs = n; close_price }

let compute_rv_series (data : intraday_data) : daily_rv array =
  let n_days = Array.length data.bars in
  if n_days = 0 then [||]
  else
    Array.mapi (fun i day_returns ->
      let date, close_price =
        if i < Array.length data.daily_closes then
          data.daily_closes.(i)
        else
          ("unknown", 0.0)
      in
      compute_daily_rv ~date ~close_price day_returns
    ) data.bars

let annualize_rv rv = rv *. 252.0

let rv_to_vol rv = sqrt rv

let log_returns prices =
  let n = Array.length prices in
  if n < 2 then [||]
  else
    Array.init (n - 1) (fun i ->
      log (prices.(i + 1) /. prices.(i))
    )
