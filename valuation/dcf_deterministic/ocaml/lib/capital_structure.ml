(** Capital structure and cost of capital calculations *)

let calculate_leveraged_beta ~unlevered_beta ~tax_rate ~debt ~equity =
  (* Hamada formula: β_L = β_U × [1 + (1 - tax_rate) × (D/E)] *)
  if equity = 0.0 then
    unlevered_beta  (* Avoid division by zero *)
  else
    unlevered_beta *. (1.0 +. (1.0 -. tax_rate) *. (debt /. equity))

let calculate_cost_of_equity ~risk_free_rate ~leveraged_beta ~equity_risk_premium =
  (* CAPM: CE = RFR + β_L × ERP *)
  risk_free_rate +. (leveraged_beta *. equity_risk_premium)

let calculate_cost_of_borrowing ~interest_expense ~total_debt =
  (* CB = interest_expense / total_debt *)
  if total_debt = 0.0 then
    0.0  (* No debt, no cost of borrowing *)
  else
    interest_expense /. total_debt

let calculate_wacc ~equity ~debt ~cost_of_equity ~cost_of_borrowing ~tax_rate =
  (* WACC = (E/(E+D)) × CE + (D/(E+D)) × CB × (1 - tax_rate) *)
  let total_value = equity +. debt in
  if total_value = 0.0 then
    cost_of_equity  (* Fallback to cost of equity *)
  else
    let equity_weight = equity /. total_value in
    let debt_weight = debt /. total_value in
    (equity_weight *. cost_of_equity) +.
    (debt_weight *. cost_of_borrowing *. (1.0 -. tax_rate))

let calculate_cost_of_capital
    ~market_data
    ~financial_data
    ~unlevered_beta
    ~risk_free_rate
    ~equity_risk_premium
    ~tax_rate =
  let open Types in

  (* Calculate leveraged beta *)
  let leveraged_beta = calculate_leveraged_beta
    ~unlevered_beta
    ~tax_rate
    ~debt:market_data.mvb
    ~equity:market_data.mve
  in

  (* Calculate cost of equity using CAPM *)
  let ce = calculate_cost_of_equity
    ~risk_free_rate
    ~leveraged_beta
    ~equity_risk_premium
  in

  (* Calculate cost of borrowing *)
  let cb = calculate_cost_of_borrowing
    ~interest_expense:financial_data.interest_expense
    ~total_debt:market_data.mvb
  in

  (* Calculate WACC *)
  let wacc = calculate_wacc
    ~equity:market_data.mve
    ~debt:market_data.mvb
    ~cost_of_equity:ce
    ~cost_of_borrowing:cb
    ~tax_rate
  in

  {
    ce;
    cb;
    wacc;
    leveraged_beta;
    risk_free_rate;
    equity_risk_premium;
  }
