(** Vertical Spread Optimizer *)

open Types

(** Calculate spread economics *)
let calculate_spread_economics
    ~(long_price : float)
    ~(short_price : float)
    ~(long_strike : float)
    ~(short_strike : float)
    ~(spread_type : string)
    : (float * float * float * float * float) =

  match spread_type with
  | "bull_call" ->
      (* Debit spread: buy lower strike call, sell higher strike call *)
      let debit = long_price -. short_price in
      let max_profit = (short_strike -. long_strike) -. debit in
      let max_loss = debit in
      let breakeven = long_strike +. debit in
      let reward_risk = if max_loss > 0.0 then max_profit /. max_loss else 0.0 in
      (debit, max_profit, max_loss, reward_risk, breakeven)

  | "bear_put" ->
      (* Debit spread: buy higher strike put, sell lower strike put *)
      let debit = long_price -. short_price in
      let max_profit = (long_strike -. short_strike) -. debit in
      let max_loss = debit in
      let breakeven = long_strike -. debit in
      let reward_risk = if max_loss > 0.0 then max_profit /. max_loss else 0.0 in
      (debit, max_profit, max_loss, reward_risk, breakeven)

  | "bull_put" ->
      (* Credit spread: sell higher strike put, buy lower strike put *)
      let credit = short_price -. long_price in
      let strike_width = short_strike -. long_strike in
      let max_profit = credit in
      let max_loss = strike_width -. credit in
      let breakeven = short_strike -. credit in
      let reward_risk = if max_loss > 0.0 then max_profit /. max_loss else 0.0 in
      (-.credit, max_profit, max_loss, reward_risk, breakeven)

  | "bear_call" ->
      (* Credit spread: sell lower strike call, buy higher strike call *)
      let credit = short_price -. long_price in
      let strike_width = long_strike -. short_strike in
      let max_profit = credit in
      let max_loss = strike_width -. credit in
      let breakeven = short_strike +. credit in
      let reward_risk = if max_loss > 0.0 then max_profit /. max_loss else 0.0 in
      (-.credit, max_profit, max_loss, reward_risk, breakeven)

  | _ -> (0.0, 0.0, 0.0, 0.0, 0.0)

(** Estimate probability of profit using simplified Black-Scholes *)
let estimate_prob_profit
    ~(spot : float)
    ~(breakeven : float)
    ~(iv : float)
    ~(days_to_expiry : int)
    ~(spread_type : string)
    : float =

  if days_to_expiry <= 0 then 0.0
  else
    let t = float_of_int days_to_expiry /. 365.0 in
    let sigma = iv *. sqrt t in

    (* Standard deviation of price move *)
    let std_dev = spot *. sigma in

    if std_dev <= 0.0 then 0.0
    else
      (* Distance to breakeven in standard deviations *)
      let z = (breakeven -. spot) /. std_dev in

      (* Approximate normal CDF using error function approximation *)
      let cdf z =
        let sign = if z < 0.0 then -1.0 else 1.0 in
        let x = abs_float z in
        let t = 1.0 /. (1.0 +. 0.2316419 *. x) in
        let d = 0.3989423 *. exp (-. x *. x /. 2.0) in
        let poly = t *. (0.319381530 +. t *. (-0.356563782 +.
                   t *. (1.781477937 +. t *. (-1.821255978 +.
                   t *. 1.330274429)))) in
        0.5 +. sign *. (0.5 -. d *. poly)
      in

      match spread_type with
      | "bull_call" -> 1.0 -. cdf z  (* Prob spot > breakeven *)
      | "bear_put" -> cdf z          (* Prob spot < breakeven *)
      | "bull_put" -> 1.0 -. cdf z   (* Prob spot > breakeven (stays above short put) *)
      | "bear_call" -> cdf z         (* Prob spot < breakeven (stays below short call) *)
      | _ -> 0.0

(** Find best bull call spread *)
let find_best_bull_call
    ~(chain : options_chain)
    ~(skew : skew_metrics)
    ~(min_reward_risk : float)
    : vertical_spread option =

  (* Long: ATM or slightly OTM *)
  (* Short: OTM with high IV from skew *)

  let calls = chain.calls in
  if Array.length calls < 2 then None
  else
    (* Find ATM call by strike closest to spot (95-105% of spot) *)
    let spot = chain.spot_price in
    let atm_candidates = Array.to_list calls |> List.filter (fun c ->
      c.strike >= spot *. 0.95 && c.strike <= spot *. 1.05 &&
      c.mid_price >= 0.10 &&                      (* Has meaningful value *)
      c.implied_vol > 0.05 && c.implied_vol < 2.0 (* Reasonable IV - allow up to 200% for high-vol stocks *)
    ) in

    if List.length atm_candidates = 0 then None
    else
      (* Pick the strike closest to spot *)
      let long_opt = List.fold_left (fun best c ->
        if abs_float (c.strike -. spot) < abs_float (best.strike -. spot) then c else best
      ) (List.hd atm_candidates) atm_candidates in

      (* Strike-based filtering for practical spreads *)
      (* Short strike should be 5-15% above long strike (OTM call) *)
      let min_short_strike = long_opt.strike *. 1.05 in  (* Min 5% width *)
      let max_short_strike = long_opt.strike *. 1.15 in  (* Max 15% width *)

      (* Find OTM calls to sell with sanity filters *)
      let short_candidates = Array.to_list calls |> List.filter (fun c ->
        c.strike >= min_short_strike &&
        c.strike <= max_short_strike &&
        c.mid_price >= 0.05 &&                    (* Not worthless *)
        c.implied_vol < 2.0 &&                    (* IV < 200% sanity check - allow high-vol stocks *)
        c.implied_vol < skew.atm_iv *. 2.5        (* IV < 2.5x ATM IV *)
      ) in

      if List.length short_candidates = 0 then None
      else
        (* Try each candidate and find best reward/risk *)
        let spreads = List.map (fun short_opt ->
          let (debit, max_profit, max_loss, reward_risk, breakeven) =
            calculate_spread_economics
              ~long_price:long_opt.mid_price
              ~short_price:short_opt.mid_price
              ~long_strike:long_opt.strike
              ~short_strike:short_opt.strike
              ~spread_type:"bull_call"
          in

          let prob_profit = estimate_prob_profit
            ~spot:chain.spot_price
            ~breakeven
            ~iv:skew.atm_iv
            ~days_to_expiry:chain.days_to_expiry
            ~spread_type:"bull_call"
          in

          let expected_value = (prob_profit *. max_profit) -. ((1.0 -. prob_profit) *. max_loss) in
          let expected_return_pct = if max_loss > 0.0 then expected_value /. max_loss *. 100.0 else 0.0 in

          {
            ticker = chain.ticker;
            expiration = chain.expiration;
            days_to_expiry = chain.days_to_expiry;
            spread_type = "bull_call";
            long_strike = long_opt.strike;
            long_delta = long_opt.delta;
            long_iv = long_opt.implied_vol;
            long_price = long_opt.mid_price;
            short_strike = short_opt.strike;
            short_delta = short_opt.delta;
            short_iv = short_opt.implied_vol;
            short_price = short_opt.mid_price;
            debit;
            max_profit;
            max_loss;
            reward_risk_ratio = reward_risk;
            breakeven;
            prob_profit;
            expected_value;
            expected_return_pct;
          }
        ) short_candidates in

        (* Filter by min reward/risk and sort by expected value *)
        let valid_spreads = List.filter (fun s -> s.reward_risk_ratio >= min_reward_risk) spreads in
        if List.length valid_spreads = 0 then None
        else
          let sorted = List.sort (fun a b ->
            compare b.expected_value a.expected_value
          ) valid_spreads in
          Some (List.hd sorted)

(** Find best bear put spread *)
let find_best_bear_put
    ~(chain : options_chain)
    ~(skew : skew_metrics)
    ~(min_reward_risk : float)
    : vertical_spread option =

  (* Long: ATM or slightly OTM put *)
  (* Short: OTM put with high IV from skew *)

  let puts = chain.puts in
  if Array.length puts < 2 then None
  else
    (* Find ATM put by strike closest to spot (95-105% of spot) *)
    let spot = chain.spot_price in
    let atm_candidates = Array.to_list puts |> List.filter (fun p ->
      p.strike >= spot *. 0.95 && p.strike <= spot *. 1.05 &&
      p.mid_price >= 0.10 &&                      (* Has meaningful value *)
      p.implied_vol > 0.05 && p.implied_vol < 2.0 (* Reasonable IV - allow up to 200% for high-vol stocks *)
    ) in

    if List.length atm_candidates = 0 then None
    else
      (* Pick the strike closest to spot *)
      let long_opt = List.fold_left (fun best p ->
        if abs_float (p.strike -. spot) < abs_float (best.strike -. spot) then p else best
      ) (List.hd atm_candidates) atm_candidates in

      (* Strike-based filtering for practical spreads *)
      (* Short strike should be 5-15% below long strike (OTM put) *)
      let min_short_strike = long_opt.strike *. 0.85 in  (* Max 15% width *)
      let max_short_strike = long_opt.strike *. 0.95 in  (* Min 5% width *)

      (* Find OTM puts to sell with sanity filters *)
      let short_candidates = Array.to_list puts |> List.filter (fun p ->
        p.strike >= min_short_strike &&
        p.strike <= max_short_strike &&
        p.mid_price >= 0.05 &&                    (* Not worthless *)
        p.implied_vol < 2.0 &&                    (* IV < 200% sanity check - allow high-vol stocks *)
        p.implied_vol < skew.atm_iv *. 2.5        (* IV < 2.5x ATM IV *)
      ) in

      if List.length short_candidates = 0 then None
      else
        (* Try each candidate and find best reward/risk *)
        let spreads = List.map (fun short_opt ->
          let (debit, max_profit, max_loss, reward_risk, breakeven) =
            calculate_spread_economics
              ~long_price:long_opt.mid_price
              ~short_price:short_opt.mid_price
              ~long_strike:long_opt.strike
              ~short_strike:short_opt.strike
              ~spread_type:"bear_put"
          in

          let prob_profit = estimate_prob_profit
            ~spot:chain.spot_price
            ~breakeven
            ~iv:skew.atm_iv
            ~days_to_expiry:chain.days_to_expiry
            ~spread_type:"bear_put"
          in

          let expected_value = (prob_profit *. max_profit) -. ((1.0 -. prob_profit) *. max_loss) in
          let expected_return_pct = if max_loss > 0.0 then expected_value /. max_loss *. 100.0 else 0.0 in

          {
            ticker = chain.ticker;
            expiration = chain.expiration;
            days_to_expiry = chain.days_to_expiry;
            spread_type = "bear_put";
            long_strike = long_opt.strike;
            long_delta = long_opt.delta;
            long_iv = long_opt.implied_vol;
            long_price = long_opt.mid_price;
            short_strike = short_opt.strike;
            short_delta = short_opt.delta;
            short_iv = short_opt.implied_vol;
            short_price = short_opt.mid_price;
            debit;
            max_profit;
            max_loss;
            reward_risk_ratio = reward_risk;
            breakeven;
            prob_profit;
            expected_value;
            expected_return_pct;
          }
        ) short_candidates in

        (* Filter by min reward/risk and sort by expected value *)
        let valid_spreads = List.filter (fun s -> s.reward_risk_ratio >= min_reward_risk) spreads in
        if List.length valid_spreads = 0 then None
        else
          let sorted = List.sort (fun a b ->
            compare b.expected_value a.expected_value
          ) valid_spreads in
          Some (List.hd sorted)

(** Find best bull put spread (credit spread - sell put, buy lower put) *)
let find_best_bull_put
    ~(chain : options_chain)
    ~(skew : skew_metrics)
    ~(min_reward_risk : float)
    : vertical_spread option =

  (* Sell higher strike OTM put (collect premium from high put skew) *)
  (* Buy lower strike put (protection) *)

  let puts = chain.puts in
  if Array.length puts < 2 then None
  else
    (* Find OTM put to sell (5-10% below spot, where put skew is rich) *)
    let spot = chain.spot_price in
    let short_candidates = Array.to_list puts |> List.filter (fun p ->
      p.strike >= spot *. 0.90 && p.strike <= spot *. 0.95 &&
      p.mid_price >= 0.20 &&                      (* Meaningful premium *)
      p.implied_vol > 0.05 && p.implied_vol < 2.0 (* Reasonable IV - allow up to 200% for high-vol stocks *)
    ) in

    if List.length short_candidates = 0 then None
    else
      (* Pick the strike with highest IV (most premium to collect) *)
      let short_opt = List.fold_left (fun best p ->
        if p.implied_vol > best.implied_vol then p else best
      ) (List.hd short_candidates) short_candidates in

      (* Find lower strike put to buy (5-10% below short strike) *)
      let min_long_strike = short_opt.strike *. 0.90 in
      let max_long_strike = short_opt.strike *. 0.95 in

      let long_candidates = Array.to_list puts |> List.filter (fun p ->
        p.strike >= min_long_strike &&
        p.strike <= max_long_strike &&
        p.mid_price >= 0.05 &&
        p.implied_vol < 2.0 &&
        p.implied_vol < skew.atm_iv *. 2.5
      ) in

      if List.length long_candidates = 0 then None
      else
        let spreads = List.map (fun long_opt ->
          let (debit, max_profit, max_loss, reward_risk, breakeven) =
            calculate_spread_economics
              ~long_price:long_opt.mid_price
              ~short_price:short_opt.mid_price
              ~long_strike:long_opt.strike
              ~short_strike:short_opt.strike
              ~spread_type:"bull_put"
          in

          let prob_profit = estimate_prob_profit
            ~spot:chain.spot_price
            ~breakeven
            ~iv:skew.atm_iv
            ~days_to_expiry:chain.days_to_expiry
            ~spread_type:"bull_put"
          in

          let expected_value = (prob_profit *. max_profit) -. ((1.0 -. prob_profit) *. max_loss) in
          let expected_return_pct = if max_loss > 0.0 then expected_value /. max_loss *. 100.0 else 0.0 in

          {
            ticker = chain.ticker;
            expiration = chain.expiration;
            days_to_expiry = chain.days_to_expiry;
            spread_type = "bull_put";
            long_strike = long_opt.strike;
            long_delta = long_opt.delta;
            long_iv = long_opt.implied_vol;
            long_price = long_opt.mid_price;
            short_strike = short_opt.strike;
            short_delta = short_opt.delta;
            short_iv = short_opt.implied_vol;
            short_price = short_opt.mid_price;
            debit;
            max_profit;
            max_loss;
            reward_risk_ratio = reward_risk;
            breakeven;
            prob_profit;
            expected_value;
            expected_return_pct;
          }
        ) long_candidates in

        let valid_spreads = List.filter (fun s -> s.reward_risk_ratio >= min_reward_risk) spreads in
        if List.length valid_spreads = 0 then None
        else
          let sorted = List.sort (fun a b ->
            compare b.expected_value a.expected_value
          ) valid_spreads in
          Some (List.hd sorted)

(** Find best bear call spread (credit spread - sell call, buy higher call) *)
let find_best_bear_call
    ~(chain : options_chain)
    ~(skew : skew_metrics)
    ~(min_reward_risk : float)
    : vertical_spread option =

  (* Sell lower strike OTM call (collect premium from call skew) *)
  (* Buy higher strike call (protection) *)

  let calls = chain.calls in
  if Array.length calls < 2 then None
  else
    (* Find OTM call to sell (5-10% above spot) *)
    let spot = chain.spot_price in
    let short_candidates = Array.to_list calls |> List.filter (fun c ->
      c.strike >= spot *. 1.05 && c.strike <= spot *. 1.10 &&
      c.mid_price >= 0.20 &&                      (* Meaningful premium *)
      c.implied_vol > 0.05 && c.implied_vol < 2.0 (* Reasonable IV - allow up to 200% for high-vol stocks *)
    ) in

    if List.length short_candidates = 0 then None
    else
      (* Pick the strike with highest IV (most premium to collect) *)
      let short_opt = List.fold_left (fun best c ->
        if c.implied_vol > best.implied_vol then c else best
      ) (List.hd short_candidates) short_candidates in

      (* Find higher strike call to buy (5-10% above short strike) *)
      let min_long_strike = short_opt.strike *. 1.05 in
      let max_long_strike = short_opt.strike *. 1.10 in

      let long_candidates = Array.to_list calls |> List.filter (fun c ->
        c.strike >= min_long_strike &&
        c.strike <= max_long_strike &&
        c.mid_price >= 0.05 &&
        c.implied_vol < 2.0 &&
        c.implied_vol < skew.atm_iv *. 2.5
      ) in

      if List.length long_candidates = 0 then None
      else
        let spreads = List.map (fun long_opt ->
          let (debit, max_profit, max_loss, reward_risk, breakeven) =
            calculate_spread_economics
              ~long_price:long_opt.mid_price
              ~short_price:short_opt.mid_price
              ~long_strike:long_opt.strike
              ~short_strike:short_opt.strike
              ~spread_type:"bear_call"
          in

          let prob_profit = estimate_prob_profit
            ~spot:chain.spot_price
            ~breakeven
            ~iv:skew.atm_iv
            ~days_to_expiry:chain.days_to_expiry
            ~spread_type:"bear_call"
          in

          let expected_value = (prob_profit *. max_profit) -. ((1.0 -. prob_profit) *. max_loss) in
          let expected_return_pct = if max_loss > 0.0 then expected_value /. max_loss *. 100.0 else 0.0 in

          {
            ticker = chain.ticker;
            expiration = chain.expiration;
            days_to_expiry = chain.days_to_expiry;
            spread_type = "bear_call";
            long_strike = long_opt.strike;
            long_delta = long_opt.delta;
            long_iv = long_opt.implied_vol;
            long_price = long_opt.mid_price;
            short_strike = short_opt.strike;
            short_delta = short_opt.delta;
            short_iv = short_opt.implied_vol;
            short_price = short_opt.mid_price;
            debit;
            max_profit;
            max_loss;
            reward_risk_ratio = reward_risk;
            breakeven;
            prob_profit;
            expected_value;
            expected_return_pct;
          }
        ) long_candidates in

        let valid_spreads = List.filter (fun s -> s.reward_risk_ratio >= min_reward_risk) spreads in
        if List.length valid_spreads = 0 then None
        else
          let sorted = List.sort (fun a b ->
            compare b.expected_value a.expected_value
          ) valid_spreads in
          Some (List.hd sorted)

(** Print vertical spread *)
let print_vertical_spread (spread : vertical_spread) : unit =
  Printf.printf "\n=== Vertical Spread: %s ===\n" spread.ticker;
  Printf.printf "Type: %s\n" spread.spread_type;
  Printf.printf "Expiration: %s (%d days)\n" spread.expiration spread.days_to_expiry;

  Printf.printf "\nLong leg (BUY):\n";
  Printf.printf "  Strike: $%.2f | Delta: %.2f | IV: %.2f%% | Price: $%.2f\n"
    spread.long_strike spread.long_delta (spread.long_iv *. 100.0) spread.long_price;

  Printf.printf "\nShort leg (SELL):\n";
  Printf.printf "  Strike: $%.2f | Delta: %.2f | IV: %.2f%% | Price: $%.2f\n"
    spread.short_strike spread.short_delta (spread.short_iv *. 100.0) spread.short_price;

  Printf.printf "\nSpread Economics:\n";
  if spread.debit >= 0.0 then
    Printf.printf "  Debit (cost): $%.2f\n" spread.debit
  else
    Printf.printf "  Credit (receive): $%.2f\n" (-.spread.debit);
  Printf.printf "  Max profit: $%.2f\n" spread.max_profit;
  Printf.printf "  Max loss: $%.2f\n" spread.max_loss;
  Printf.printf "  Reward/Risk: %.2f:1\n" spread.reward_risk_ratio;
  Printf.printf "  Breakeven: $%.2f\n" spread.breakeven;

  Printf.printf "\nExpected Value:\n";
  Printf.printf "  Prob profit: %.1f%%\n" (spread.prob_profit *. 100.0);
  Printf.printf "  Expected value: $%.2f\n" spread.expected_value;
  Printf.printf "  Expected return: %.1f%%\n" spread.expected_return_pct;

  if spread.reward_risk_ratio >= 5.0 then
    Printf.printf "\n✓ EXCELLENT reward/risk (≥5:1)\n";

  if spread.expected_value > 0.0 then
    Printf.printf "✓ POSITIVE expected value\n"
