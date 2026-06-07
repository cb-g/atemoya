(** Lean strike selector: given a ticker + direction + a fresh option-chain CSV,
    run the existing Spreads.find_best_* strike selection and print ONE JSON line
    (the placeable spread) to stdout.

    Deliberately bypasses main.ml's prices/momentum/skew machinery (and its
    Random.float dummy skew history) — the signal/z-scores are owned by the Python
    layer; this entrypoint only picks strikes from a chain. The Python orchestrator
    (build_trades.py) writes the chain CSVs and captures this stdout JSON. *)

open Skew_verticals_lib
open Types

let spread_json ~direction (s : vertical_spread) : string =
  Printf.sprintf
    {|{"ticker":"%s","direction":"%s","found":true,"spread_type":"%s","expiration":"%s","days_to_expiry":%d,"long_strike":%.2f,"long_delta":%.4f,"long_iv":%.4f,"long_price":%.2f,"short_strike":%.2f,"short_delta":%.4f,"short_iv":%.4f,"short_price":%.2f,"width":%.2f,"debit":%.4f,"max_profit":%.4f,"max_loss":%.4f,"reward_risk_ratio":%.4f,"breakeven":%.2f,"prob_profit":%.4f,"expected_value":%.4f,"expected_return_pct":%.2f}|}
    s.ticker direction s.spread_type s.expiration s.days_to_expiry
    s.long_strike s.long_delta s.long_iv s.long_price
    s.short_strike s.short_delta s.short_iv s.short_price
    (abs_float (s.short_strike -. s.long_strike))
    s.debit s.max_profit s.max_loss s.reward_risk_ratio s.breakeven
    s.prob_profit s.expected_value s.expected_return_pct

let () =
  let ticker = ref "" and direction = ref "" in
  let data_dir = ref "pricing/skew_verticals/data" and expiration = ref "" in
  let spec =
    [ ("--direction", Arg.Set_string direction, "bullish|bearish");
      ("--data", Arg.Set_string data_dir, "data directory holding the chain CSVs");
      ("--expiration", Arg.Set_string expiration, "expiry tag YYYY-MM-DD") ]
  in
  Arg.parse spec
    (fun s -> if !ticker = "" then ticker := s)
    "strike_select <ticker> --direction <bullish|bearish> --expiration <YYYY-MM-DD> [--data <dir>]";
  if !ticker = "" || !direction = "" || !expiration = "" then begin
    prerr_endline "Usage: strike_select <ticker> --direction <bullish|bearish> --expiration <YYYY-MM-DD> [--data <dir>]";
    exit 1
  end;
  let fail msg =
    Printf.printf
      {|{"ticker":"%s","direction":"%s","found":false,"error":"%s"}|}
      !ticker !direction msg;
    print_newline ();
    exit 0
  in
  try
    let f suffix = Printf.sprintf "%s/%s_%s_%s.csv" !data_dir !ticker !expiration suffix in
    let calls = Io.load_options_csv ~file_path:(f "calls") in
    let puts = Io.load_options_csv ~file_path:(f "puts") in
    let (_, spot, exp_date, days, atm_strike) =
      Io.load_metadata_csv ~file_path:(f "metadata")
    in
    let chain : options_chain =
      { ticker = !ticker; spot_price = spot; expiration = exp_date;
        days_to_expiry = days; calls; puts; atm_strike }
    in
    (* atm_iv = IV of the call whose strike is closest to the ATM strike (only field
       Spreads.find_best_* reads from skew) *)
    let atm_iv =
      let closest =
        Array.fold_left
          (fun acc (c : option_data) ->
            match acc with
            | None -> Some c
            | Some b ->
              if abs_float (c.strike -. atm_strike) < abs_float (b.strike -. atm_strike)
              then Some c else Some b)
          None calls
      in
      match closest with Some c -> c.implied_vol | None -> 0.20
    in
    let skew : skew_metrics =
      { ticker = !ticker; date = exp_date; call_skew = 0.0; call_skew_zscore = 0.0;
        put_skew = 0.0; put_skew_zscore = 0.0; atm_iv; atm_call_25delta_iv = 0.0;
        atm_put_25delta_iv = 0.0; realized_vol_30d = 0.0; vrp = 0.0 }
    in
    (* "Sell the rich skew" is a CREDIT spread on that side: bullish sells the rich
       put skew (bull_put), bearish sells the rich call skew (bear_call). The debit
       spreads are off-thesis directional bets, so they're not emitted here. *)
    let min_rr_credit = 0.10 in
    let candidates =
      match !direction with
      | "bullish" -> [ Spreads.find_best_bull_put ~chain ~skew ~min_reward_risk:min_rr_credit ]
      | "bearish" -> [ Spreads.find_best_bear_call ~chain ~skew ~min_reward_risk:min_rr_credit ]
      | d -> fail (Printf.sprintf "direction must be bullish|bearish, got %s" d)
    in
    let valid = List.filter_map (fun x -> x) candidates in
    let best =
      List.fold_left
        (fun acc s ->
          match acc with
          | None -> Some s
          | Some b -> if s.expected_value > b.expected_value then Some s else Some b)
        None valid
    in
    match best with
    | Some s -> print_endline (spread_json ~direction:!direction s)
    | None -> fail "no spread passed the reward/risk and liquidity filters"
  with e -> fail (String.map (fun c -> if c = '"' then '\'' else c) (Printexc.to_string e))
