(** Bank valuation using Excess Return Model

    Banks are special because:
    1. Interest expense is operating cost (not financing cost)
    2. Debt (deposits) is the raw material of the business
    3. EBIT/FCFF/FCFE calculations are meaningless
    4. Regulatory capital requirements constrain growth

    The Excess Return Model values banks as:
    Fair Value = Book Value + PV of Future Excess Returns
    where Excess Return = (ROE - Cost of Equity) × Book Value

    This captures the economic value created when banks earn above
    their cost of capital. For banks trading at P/BV > 1.0, the market
    expects positive excess returns (ROE > CoE). Banks with ROE < CoE
    should trade below book value.
*)

open Types

(** Calculate bank-specific metrics from financial data *)
let calculate_bank_metrics ~(financial : financial_data)
    ~(market : market_data) : bank_metrics =
  let shares = market.shares_outstanding in

  (* ROE = Net Income / Book Value of Equity *)
  let roe =
    if financial.book_value_equity > 0.0 then
      financial.net_income /. financial.book_value_equity
    else 0.0
  in

  (* ROTCE = Net Income / Tangible Book Value *)
  let rotce =
    if financial.tangible_book_value > 0.0 then
      financial.net_income /. financial.tangible_book_value
    else 0.0
  in

  (* ROA = Net Income / Total Assets
     We approximate total assets from deposits + equity (rough estimate) *)
  let total_assets_approx =
    financial.total_deposits +. financial.book_value_equity
  in
  let roa =
    if total_assets_approx > 0.0 then
      financial.net_income /. total_assets_approx
    else 0.0
  in

  (* NIM = Net Interest Income / Earning Assets
     Earning assets ≈ Total Loans (simplified) *)
  let nim =
    if financial.total_loans > 0.0 then
      financial.net_interest_income /. financial.total_loans
    else 0.0
  in

  (* Efficiency Ratio = Non-Int Expense / (NII + Non-Int Income)
     Lower is better; typically 50-70% for well-run banks *)
  let total_revenue =
    financial.net_interest_income +. financial.non_interest_income
  in
  let efficiency_ratio =
    if total_revenue > 0.0 then
      financial.non_interest_expense /. total_revenue
    else 0.0
  in

  (* Price-to-Book = Market Cap / Book Value *)
  let price_to_book =
    if financial.book_value_equity > 0.0 then
      market.mve /. financial.book_value_equity
    else 0.0
  in

  (* Price-to-TBV = Market Cap / Tangible Book Value *)
  let price_to_tbv =
    if financial.tangible_book_value > 0.0 then
      market.mve /. financial.tangible_book_value
    else 0.0
  in

  (* PPNR = Pre-Provision Net Revenue
     = NII + Non-Int Income - Non-Int Expense
     This is the bank's core earning power before credit costs *)
  let ppnr = total_revenue -. financial.non_interest_expense in

  let ppnr_per_share =
    if shares > 0.0 then ppnr /. shares else 0.0
  in

  {
    roe;
    rotce;
    roa;
    nim;
    efficiency_ratio;
    price_to_book;
    price_to_tbv;
    ppnr;
    ppnr_per_share;
  }

(** Calculate cost of equity for a bank using CAPM
    Banks typically have lower betas (0.8-1.2) due to regulated nature *)
let calculate_bank_cost_of_equity ~risk_free_rate ~equity_risk_premium
    ~(market : market_data) : float =
  (* Default bank beta based on size:
     - Large diversified banks: ~1.0
     - Regional banks: ~1.1 (more cyclical)
     - Investment banks: ~1.3 (higher risk) *)
  let bank_beta =
    if market.mve > 100_000_000_000.0 then 1.0   (* >$100B: large diversified *)
    else if market.mve > 10_000_000_000.0 then 1.05  (* $10-100B: large regional *)
    else 1.15  (* <$10B: smaller regional/community *)
  in
  risk_free_rate +. (bank_beta *. equity_risk_premium)

(** Calculate present value of excess returns stream

    Value = Σ [(ROE - CoE) × BV_t] / (1 + CoE)^t + Terminal Value

    We use a mean-reverting model where ROE gradually reverts to CoE
    over the projection period, reflecting competition eroding excess returns.
*)
let calculate_excess_return_value ~roe ~cost_of_equity
    ~book_value ~growth_rate ~projection_years ~terminal_growth : float =

  if cost_of_equity <= terminal_growth then 0.0
  else
    (* Mean reversion: ROE reverts toward CoE over time *)
    let lambda = 0.15 in  (* Reversion speed: ~15% per year *)

    (* Project book value and excess returns *)
    let rec project_value acc year bv current_roe =
      if year > projection_years then acc
      else
        let excess_return = (current_roe -. cost_of_equity) *. bv in
        let discount_factor = (1.0 +. cost_of_equity) ** float_of_int year in
        let pv_excess = excess_return /. discount_factor in

        (* Grow book value (retained earnings + some growth) *)
        let retention_rate = 0.6 in  (* Assume 40% dividend payout *)
        let earnings = current_roe *. bv in
        let retained = earnings *. retention_rate in
        let next_bv = bv +. retained +. (bv *. growth_rate *. 0.3) in

        (* ROE mean reverts toward CoE *)
        let next_roe = current_roe +. lambda *. (cost_of_equity -. current_roe) in

        project_value (acc +. pv_excess) (year + 1) next_bv next_roe
    in

    let explicit_pv = project_value 0.0 1 book_value roe in

    (* Terminal value: assume ROE = CoE + small spread in perpetuity *)
    let terminal_roe_spread = 0.02 in  (* 2% sustainable advantage *)
    let terminal_roe = cost_of_equity +. terminal_roe_spread in

    (* Terminal book value after projection period *)
    let rec terminal_bv bv current_roe year =
      if year > projection_years then bv
      else
        let retention_rate = 0.6 in
        let earnings = current_roe *. bv in
        let retained = earnings *. retention_rate in
        let next_bv = bv +. retained +. (bv *. growth_rate *. 0.3) in
        let next_roe = current_roe +. lambda *. (cost_of_equity -. current_roe) in
        terminal_bv next_bv next_roe (year + 1)
    in
    let final_bv = terminal_bv book_value roe 1 in

    let terminal_excess = (terminal_roe -. cost_of_equity) *. final_bv in
    let terminal_value = terminal_excess /. (cost_of_equity -. terminal_growth) in
    let terminal_pv =
      terminal_value /. ((1.0 +. cost_of_equity) ** float_of_int projection_years)
    in

    explicit_pv +. terminal_pv

(** Solve for implied ROE given market price
    Find ROE such that Fair Value = Market Price *)
let solve_implied_roe ~market_price ~book_value ~cost_of_equity
    ~shares_outstanding ~growth_rate ~projection_years ~terminal_growth : float option =
  let target_fv = market_price *. shares_outstanding in

  (* Binary search for implied ROE *)
  let rec search low high iterations =
    if iterations > 50 then None
    else
      let mid = (low +. high) /. 2.0 in
      let excess_pv = calculate_excess_return_value
        ~roe:mid
        ~cost_of_equity
        ~book_value
        ~growth_rate
        ~projection_years
        ~terminal_growth
      in
      let fv = book_value +. excess_pv in
      let diff = fv -. target_fv in

      if abs_float diff < target_fv *. 0.001 then Some mid
      else if diff > 0.0 then search low mid (iterations + 1)
      else search mid high (iterations + 1)
  in

  (* ROE typically ranges from -20% to +40% *)
  search (-0.20) 0.40 0

(** Calculate fair value using Price-to-Book method
    For banks, P/BV should equal 1 + PV(Excess Returns)/BV *)
let value_by_price_to_book ~book_value_per_share ~target_pb : float =
  book_value_per_share *. target_pb

(** Target P/BV based on ROE vs Cost of Equity *)
let calculate_target_pb ~roe ~cost_of_equity ~growth_rate : float =
  (* Gordon-growth-style formula for P/BV:
     P/BV = (ROE - g) / (CoE - g)
     When ROE = CoE, P/BV = 1.0 *)
  if cost_of_equity <= growth_rate then 1.0
  else
    let numerator = roe -. growth_rate in
    let denominator = cost_of_equity -. growth_rate in
    if denominator <= 0.0 then 1.0
    else max 0.5 (min 3.0 (numerator /. denominator))

(** Generate investment signal for bank *)
let classify_bank_signal ~ivps ~market_price ~(metrics : bank_metrics)
    ~cost_of_equity : investment_signal =
  let margin = (ivps -. market_price) /. market_price in
  let roe_spread = metrics.roe -. cost_of_equity in

  (* Strong Buy: >40% undervalued + positive ROE spread + good efficiency *)
  if margin > 0.40 && roe_spread > 0.02 && metrics.efficiency_ratio < 0.65 then
    StrongBuy
  (* Buy: 20-40% undervalued with reasonable metrics *)
  else if margin > 0.20 && roe_spread > 0.0 then
    Buy
  (* Hold: Near fair value *)
  else if margin > -0.10 && margin < 0.10 then
    Hold
  (* Caution: ROE below cost of equity (destroying value) *)
  else if roe_spread < 0.0 then
    CautionLeverage
  (* Avoid: Significantly overvalued *)
  else if margin < -0.25 then
    Avoid
  else
    Hold

(** Full bank valuation *)
let value_bank ~(financial : financial_data) ~(market : market_data)
    ~risk_free_rate ~equity_risk_premium ~terminal_growth_rate
    ~projection_years : bank_valuation_result =

  let shares = market.shares_outstanding in

  (* Calculate bank metrics *)
  let metrics = calculate_bank_metrics ~financial ~market in

  (* Calculate cost of equity *)
  let cost_of_equity = calculate_bank_cost_of_equity
    ~risk_free_rate
    ~equity_risk_premium
    ~market
  in

  (* Calculate fair value using excess return model *)
  let excess_pv = calculate_excess_return_value
    ~roe:metrics.roe
    ~cost_of_equity
    ~book_value:financial.book_value_equity
    ~growth_rate:0.03  (* Assume 3% long-term BV growth *)
    ~projection_years
    ~terminal_growth:terminal_growth_rate
  in

  let fair_value = financial.book_value_equity +. excess_pv in
  let fair_value_per_share =
    if shares > 0.0 then fair_value /. shares else 0.0
  in

  let book_value_per_share =
    if shares > 0.0 then financial.book_value_equity /. shares else 0.0
  in

  let tangible_book_per_share =
    if shares > 0.0 then financial.tangible_book_value /. shares else 0.0
  in

  let margin_of_safety =
    if market.price > 0.0 then
      (fair_value_per_share -. market.price) /. market.price
    else 0.0
  in

  (* Solve for implied ROE *)
  let implied_roe = solve_implied_roe
    ~market_price:market.price
    ~book_value:financial.book_value_equity
    ~cost_of_equity
    ~shares_outstanding:shares
    ~growth_rate:0.03
    ~projection_years
    ~terminal_growth:terminal_growth_rate
  in

  let signal = classify_bank_signal
    ~ivps:fair_value_per_share
    ~market_price:market.price
    ~metrics
    ~cost_of_equity
  in

  {
    ticker = market.ticker;
    price = market.price;
    book_value_per_share;
    tangible_book_per_share;
    excess_return_value = excess_pv /. shares;
    fair_value_per_share;
    margin_of_safety;
    implied_roe;
    signal;
    cost_of_equity;
    bank_metrics = metrics;
  }
