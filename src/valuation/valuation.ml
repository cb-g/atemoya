(* ========================= *)
(* capital structure         *)
(* ========================= *)

(* computes CE (Cost of Equity) via CAPM *)
let calculate_cost_of_equity ~(rfr: float) ~(beta_l: float) ~(erp: float) : float =
  rfr +. (beta_l *. erp)

(* computes Leveraged Beta (β_L) from Unleveraged Beta (β_U) *)
let calculate_leveraged_beta ~(beta_u: float) ~(ctr: float) ~(mvb: float) ~(mve: float) : float =
  if mve = 0.0 then invalid_arg "Market Value of Equity (MVE) cannot be zero."
  else
    let debt_to_equity = mvb /. mve in
    beta_u *. (1.0 +. (1.0 -. ctr) *. debt_to_equity)

(* computes WACC (Weighted Average Cost of Capital) *)
let calculate_wacc ~(mve: float) ~(mvb: float) ~(ce: float) ~(cb: float) ~(ctr: float) : float =
  if mve +. mvb = 0.0 then invalid_arg "Total capital (MVE + MVB) cannot be zero."
  else
    let total_capital = mve +. mvb in
    let equity_weight = mve /. total_capital in
    let debt_weight = mvb /. total_capital in
    (equity_weight *. ce) +. (debt_weight *. cb *. (1.0 -. ctr))

(* ========================= *)
(* cash flow                 *)
(* ========================= *)

(* computes FCFE (Free Cash Flow to Equity) *)
let calculate_delta_wc ~(ca: float) ~(cl: float) ~(prev_ca: float) ~(prev_cl: float) : float =
  (ca -. cl) -. (prev_ca -. prev_cl)

let calculate_fcfe
  ~(ni: float)
  ~(capx: float) ~(d: float)
  ~(ca: float) ~(cl: float)
  ~(prev_ca: float) ~(prev_cl: float)
  ~(net_borrowing: float)
  : float =
  let delta_wc = calculate_delta_wc ~ca ~cl ~prev_ca ~prev_cl in
  ni +. d +. capx -. delta_wc +. net_borrowing

(* let calculate_fcfe
  ~(ni: float) ~(tdr: float)
  ~(capx: float) ~(d: float)
  ~(ca: float) ~(cl: float)
  ~(prev_ca: float) ~(prev_cl: float)
  : float =
  let delta_wc = calculate_delta_wc ~ca ~cl ~prev_ca ~prev_cl in
  let net_investment = capx -. d +. delta_wc in
  ni -. net_investment *)

(* computes FCFF (Free Cash Flow to Firm) *)
let calculate_fcff
  ~(ebit: float) ~(ctr: float)
  ~(b: float)  (* = depreciation *)
  ~(capx: float)
  ~(ca: float) ~(cl: float)
  ~(prev_ca: float) ~(prev_cl: float)
  : float =
  let nopat = ebit *. (1.0 -. ctr) in
  let delta_wc = calculate_delta_wc ~ca ~cl ~prev_ca ~prev_cl in 
  nopat +. b -. capx -. delta_wc

(* ========================= *)
(* growth rate               *)
(* ========================= *)

(* computes FCFEGR (FCFE Growth Rate) *)
let calculate_fcfe_growth_rate ~(ni: float) ~(bve: float) ~(dp: float) : float =
  if bve = 0.0 then invalid_arg "Book Value of Equity (BVE) cannot be zero."
  else if ni = 0.0 then invalid_arg "Net Income (NI) cannot be zero."
  else
    let roe = ni /. bve in
    let retention_ratio = 1.0 -. (dp /. ni) in
    roe *. retention_ratio

(* computes FCFFGR (FCFF Growth Rate) *)
let calculate_fcff_growth_rate
  ~(ebit: float) ~(ite: float) ~(ic: float) ~(capx: float) ~(d: float) ~(ca: float) ~(cl: float)
  : float =
  if ic = 0.0 then invalid_arg "Invested Capital (IC) cannot be zero."
  else if ebit = 0.0 then invalid_arg "EBIT cannot be zero."
  else
    let nopat = ebit *. (1.0 -. (ite /. ebit)) in
    (* let reinvestment = (capx -. d +. (ca -. cl)) in *)
    let reinvestment = capx -. d +. (cl -. ca) in
    let return_on_invested_capital = nopat /. ic in
    let reinvestment_rate = reinvestment /. nopat in
    return_on_invested_capital *. reinvestment_rate

    let project_fcfe
    ~(ni : float)
    ~(capx : float)
    ~(d : float)
    ~(ca : float)
    ~(cl : float)
    ~(tdr : float)
    ~(years : int)
    ~(fcfegr : float)
  : float list =
  let wc = ca -. cl in
  let rec loop t acc ni capx d wc =
    if t > years then List.rev acc
    else
      let ni_t = ni *. (1.0 +. fcfegr) in
      let capx_t = capx *. (1.0 +. fcfegr) in
      let d_t = d *. (1.0 +. fcfegr) in
      let wc_t = wc *. (1.0 +. fcfegr) in
      let delta_wc = wc_t -. wc in
      let reinvestment = capx_t -. d_t +. delta_wc in
      let net_borrowing = tdr *. reinvestment in
      let fcfe_t = ni_t +. d_t -. capx_t -. delta_wc +. net_borrowing in
      loop (t + 1) (fcfe_t :: acc) ni_t capx_t d_t wc_t
  in
  loop 1 [] ni capx d wc
;;

let calculate_pve_from_projection
    ~(fcfe_list : float list)
    ~(ce : float)
    ~(tgr : float)
  : float =
  let h = List.length fcfe_list in
  let tgr =
    if tgr >= ce then (
      let adjusted = ce -. 0.001 in
      Printf.printf "[WARN] TGR (%.4f) >= Cost of Equity (%.4f). Capping TGR to %.4f.\n%!" tgr ce adjusted;
      adjusted
    ) else tgr
  in
  let sum_pv =
    List.mapi (fun i fcfe ->
      let t = i + 1 in
      fcfe /. ((1.0 +. ce) ** float_of_int t)
    ) fcfe_list |> List.fold_left ( +. ) 0.0
  in
  let fcfe_h = List.nth fcfe_list (h - 1) in
  let terminal = (fcfe_h *. (1.0 +. tgr)) /. (ce -. tgr) in
  let pv_terminal = terminal /. ((1.0 +. ce) ** float_of_int h) in
  sum_pv +. pv_terminal
;;

let project_fcff
    ~(ebit : float)
    ~(ctr : float)
    ~(capx : float)
    ~(d : float)
    ~(ca : float)
    ~(cl : float)
    ~(years : int)
    ~(fcffgr : float)
  : float list =
  let wc = ca -. cl in
  let rec loop t acc ebit capx d wc =
    if t > years then List.rev acc
    else
      let ebit_t = ebit *. (1.0 +. fcffgr) in
      let capx_t = capx *. (1.0 +. fcffgr) in
      let d_t = d *. (1.0 +. fcffgr) in
      let wc_t = wc *. (1.0 +. fcffgr) in
      let delta_wc = wc_t -. wc in
      let nopat_t = ebit_t *. (1.0 -. ctr) in
      let fcff_t = nopat_t +. d_t -. capx_t -. delta_wc in
      loop (t + 1) (fcff_t :: acc) ebit_t capx_t d_t wc_t
  in
  loop 1 [] ebit capx d wc
;;

let calculate_pvf_from_projection
    ~(fcff_list : float list)
    ~(wacc : float)
    ~(tgr : float)
  : float =
  let h = List.length fcff_list in
  let tgr =
    if tgr >= wacc then (
      let adjusted = wacc -. 0.001 in
      Printf.printf "[WARN] TGR (%.4f) >= WACC (%.4f). Capping TGR to %.4f.\n%!" tgr wacc adjusted;
      adjusted
    ) else tgr
  in
  let sum_pv =
    List.mapi (fun i fcff ->
      let t = i + 1 in
      fcff /. ((1.0 +. wacc) ** float_of_int t)
    ) fcff_list |> List.fold_left ( +. ) 0.0
  in
  let fcff_h = List.nth fcff_list (h - 1) in
  let terminal = (fcff_h *. (1.0 +. tgr)) /. (wacc -. tgr) in
  let pv_terminal = terminal /. ((1.0 +. wacc) ** float_of_int h) in
  sum_pv +. pv_terminal
;;

(* ========================= *)
(* discounted cash flow      *)
(* ========================= *)

(* computes PVF (Firm Present Value) *)
let calculate_pvf ~(fcff0: float) ~(fcffgr: float) ~(wacc: float) ~(tgr: float) ~(h: int) : float =
  let tgr = if wacc <= tgr then (
    let adjusted = wacc -. 0.001 in
    Printf.printf "[WARN] TGR (%.4f) >= WACC (%.4f). Capping TGR to %.4f.\n%!" tgr wacc adjusted;
    adjusted
  ) else tgr in

  let rec sum_fcff t acc =
    if t > h then acc
    else
      let fcff_t = fcff0 *. ((1.0 +. fcffgr) ** float_of_int t) in
      let discounted_fcff_t = fcff_t /. ((1.0 +. wacc) ** float_of_int t) in
      sum_fcff (t + 1) (acc +. discounted_fcff_t)
  in
  let sum_of_fcffs = sum_fcff 1 0.0 in
  let fcff_h = fcff0 *. ((1.0 +. fcffgr) ** float_of_int h) in
  let terminal_value = (fcff_h *. (1.0 +. tgr)) /. (wacc -. tgr) in
  let discounted_terminal_value = terminal_value /. ((1.0 +. wacc) ** float_of_int h) in
  sum_of_fcffs +. discounted_terminal_value


(* computes PVE (Equity Present Value) *)
let calculate_pve ~(fcfe0: float) ~(fcfegr: float) ~(ce: float) ~(tgr: float) ~(h: int) : float =
  let tgr = if ce <= tgr then (
    let adjusted = ce -. 0.001 in
    Printf.printf "[WARN] TGR (%.4f) >= Cost of Equity (%.4f). Capping TGR to %.4f.\n%!" tgr ce adjusted;
    adjusted
  ) else tgr in

  let rec sum_fcfe t acc =
    if t > h then acc
    else
      let fcfe_t = fcfe0 *. ((1.0 +. fcfegr) ** float_of_int t) in
      let discounted_fcfe_t = fcfe_t /. ((1.0 +. ce) ** float_of_int t) in
      sum_fcfe (t + 1) (acc +. discounted_fcfe_t)
  in
  let sum_of_fcfes = sum_fcfe 1 0.0 in
  let fcfe_h = fcfe0 *. ((1.0 +. fcfegr) ** float_of_int h) in
  let terminal_value = (fcfe_h *. (1.0 +. tgr)) /. (ce -. tgr) in
  let discounted_terminal_value = terminal_value /. ((1.0 +. ce) ** float_of_int h) in
  sum_of_fcfes +. discounted_terminal_value

let average_growth_rate (lst : float list) : float =
  let rec compute acc = function
    | [] | [_] -> acc
    | x1 :: (x2 :: _ as rest) ->
        let g = (x2 -. x1) /. abs_float x1 in
        compute (g :: acc) rest
  in
  match lst with
  | [] | [_] -> 0.0
  | _ ->
    let growth_rates = compute [] lst in
    let sum = List.fold_left ( +. ) 0.0 growth_rates in
    sum /. float_of_int (List.length growth_rates)
;;

let implied_fcfe_growth_rate_over_h
  ~(fcfe0 : float)
  ~(ce : float)
  ~(tgr : float)
  ~(h : int)
  ~(so : float)
  ~(price : float)
  : float =
  let market_equity_value = so *. price in
  let tolerance = 1e-5 in
  let max_iter = 50 in

  let npv_of_fcfe_projection g =
    let sum_pv =
      List.init h (fun i ->
        let t = float_of_int (i + 1) in
        let fcfe_t = fcfe0 *. ((1.0 +. g) ** t) in
        fcfe_t /. ((1.0 +. ce) ** t)
      ) |> List.fold_left ( +. ) 0.0
    in
    let fcfe_h = fcfe0 *. ((1.0 +. g) ** float_of_int h) in
    let terminal_value = (fcfe_h *. (1.0 +. tgr)) /. (ce -. tgr) in
    let pv_terminal = terminal_value /. ((1.0 +. ce) ** float_of_int h) in
    sum_pv +. pv_terminal
  in

  let rec newton g iter =
    if iter >= max_iter then raise Exit else
    let f = npv_of_fcfe_projection g -. market_equity_value in
    let g_next = g -. f /. 0.01 in  (* crude step, or use numerical derivative *)
    if abs_float f < tolerance && g_next > -.0.99 && g_next < 0.99 then g_next
    else newton g_next (iter + 1)
  in

  let rec bisection low high iter =
    if iter >= 100 then (low +. high) /. 2.0 else
    let mid = (low +. high) /. 2.0 in
    let f_mid = npv_of_fcfe_projection mid -. market_equity_value in
    if abs_float f_mid < tolerance then mid
    else if f_mid > 0.0 then bisection low mid (iter + 1)
    else bisection mid high (iter + 1)
  in

  try newton 0.05 0 with Exit -> bisection (-0.99) 0.99 0

let implied_fcff_growth_rate_over_h
  ~(fcff0 : float)
  ~(wacc : float)
  ~(tgr : float)
  ~(h : int)
  ~(mve : float)
  ~(mvb : float)
  : float =
  let firm_value = mve +. mvb in
  let tolerance = 1e-5 in
  let max_iter = 50 in

  let npv_of_fcff_projection g =
    let sum_pv =
      List.init h (fun i ->
        let t = float_of_int (i + 1) in
        let fcff_t = fcff0 *. ((1.0 +. g) ** t) in
        fcff_t /. ((1.0 +. wacc) ** t)
      ) |> List.fold_left ( +. ) 0.0
    in
    let fcff_h = fcff0 *. ((1.0 +. g) ** float_of_int h) in
    let terminal = (fcff_h *. (1.0 +. tgr)) /. (wacc -. tgr) in
    let pv_terminal = terminal /. ((1.0 +. wacc) ** float_of_int h) in
    sum_pv +. pv_terminal
  in

  let rec newton g iter =
    if iter >= max_iter then raise Exit else
    let f = npv_of_fcff_projection g -. firm_value in
    let g_next = g -. f /. 0.01 in
    if abs_float f < tolerance && g_next > -.0.99 && g_next < wacc -. 1e-4 then g_next
    else newton g_next (iter + 1)
  in

  let rec bisection low high iter =
    if iter >= 100 then (low +. high) /. 2.0 else
    let mid = (low +. high) /. 2.0 in
    let f_mid = npv_of_fcff_projection mid -. firm_value in
    if abs_float f_mid < tolerance then mid
    else if f_mid > 0.0 then bisection low mid (iter + 1)
    else bisection mid high (iter + 1)
  in

  try newton 0.05 0 with Exit -> bisection (-0.99) (wacc -. 1e-4) 0
;;


(* ========================= *)
(* verdict                   *)
(* ========================= *)

type relation = Above | Approx | Below

let pad_left total_width s =
  let len = String.length s in
  if len >= total_width then s
  else String.make (total_width - len) ' ' ^ s
;;

let format_large_number value =
  if value >= 1.0e9 then Printf.sprintf "%.2fB" (value /. 1.0e9)
  else if value >= 1.0e6 then Printf.sprintf "%.2fM" (value /. 1.0e6)
  else Printf.sprintf "%.2f" value
;;

let format_currency ~currency value =
  let suffix = " " ^ currency in
  if value >= 1.0e9 then Printf.sprintf "%.2fB%s" (value /. 1.0e9) suffix
  else if value >= 1.0e6 then Printf.sprintf "%.2fM%s" (value /. 1.0e6) suffix
  else Printf.sprintf "%.2f%s" value suffix
;;

let classify_relation value price =
  let tolerance = 0.05 *. price in
  if value > price +. tolerance then Above
  else if value < price -. tolerance then Below
  else Approx
;;

let signal_recommendation ~ivps_fcfe ~ivps_fcff ~price =
  let r_fcfe = classify_relation ivps_fcfe price in
  let r_fcff = classify_relation ivps_fcff price in
  match (r_fcfe, r_fcff) with
  | (Above, Above) ->
      "Strong Buy – The firm's assets and operations generate\n\
       more value than what is priced in by the market,\n\
       and equity holders retain it — low leverage or\n\
       efficient debt structure."
  | (Approx, Above) ->
      "Buy – The firm's assets and operations are underpriced,\n\
       but excess value is absorbed by debt or reinvestment,\n\
       leaving equity fairly valued."
  | (Below, Above) ->
      "Caution – The firm's assets and operations are underpriced,\n\
       but debt or reinvestment absorbs most cash flows —\n\
       equity claims more than it economically receives."
  | (Above, Approx) ->
      "Buy – The firm's assets and operations are fairly priced,\n\
       but equity captures a disproportionately large share —\n\
       market underprices the equity upside."
  | (Approx, Approx) ->
      "Hold – The present value of free cash flows — to the firm\n\
       (before payments to debt holders) and to equity (after them)\n\
       — is consistent with market prices; no mispricing is evident."
  | (Below, Approx) ->
      "Speculative – The business generates enough pre-financing\n\
       cash flow to justify its market price, but equity holders\n\
       retain too little after payments to debt holders."
  | (Above, Below) ->
      "Caution – The business is overvalued, but equity appears\n\
       cheap due to temporarily favorable debt terms — value may\n\
       be unstable under a leveraged structure."
  | (Approx, Below) ->
      "Speculative – Equity is fairly priced, but depends on cash\n\
       flows from a business generating less than what its market\n\
       price would suggest — any decline in operations could\n\
       undermine equity value."
  | (Below, Below) ->
      "Avoid – There isn't sufficient cash flow to the business or\n\
       the equity for the fundamentals to justify the high market price."
;;

(* computes margin of safety as a percentage *)
let calculate_margin_of_safety ~ivps ~price : float =
  (ivps -. price) /. price *. 100.0
;;

let display_valuation_summary
    ~(ticker: string)
    ~(currency: string)
    ~(ce: float) ~(cb: float) ~(wacc: float)
    ~(fcfe0: float) ~(fcff0: float) ~(fcfegr: float) ~(fcffgr: float)
    ~(capped_fcfegr: bool) ~(capped_fcffgr: bool) ~(floored_fcffgr: bool)
    ~(tgr: float) ~(so: float) ~(price: float)
    ~(pvf: float) ~(pve: float)
    ~(avg_fcfegr: float) ~(avg_fcffgr: float)
    ~(implied_fcfegr: float) ~(implied_fcffgr: float)
    ~(h: int)
    : unit =
  let ivps_fcff = pvf /. so in
  let ivps_fcfe = pve /. so in
  let signal = signal_recommendation ~ivps_fcfe ~ivps_fcff ~price in
  let margin_fcfe = calculate_margin_of_safety ~ivps:ivps_fcfe ~price in
  let margin_fcff = calculate_margin_of_safety ~ivps:ivps_fcff ~price in

  Printf.printf "\n\n===============================================================\n%!";
  Printf.printf "==== Valuation for %s ====\n" ticker;

  if capped_fcfegr then
    Printf.printf "[WARN] Capping FCFEGR to 0.25\n%!";
  if capped_fcffgr then
    Printf.printf "[WARN] Capping FCFFGR to 0.25\n%!";
  if floored_fcffgr then
    Printf.printf "[WARN] Flooring FCFFGR to -0.25\n%!";

  (* if fcfegr > 0.5 then
    Printf.printf "[WARN] FCFE growth rate unusually high: %.4f\n" fcfegr; *)
  (* if ivps_fcfe > (price *. 3.0) then
    Printf.printf "[WARN] FCFE valuation is over 3x market price — consider reviewing inputs or growth rate.\n%!"; *)

  Printf.printf "\n==== Valuation Debug Info ====\n";
  Printf.printf "CE (Cost of Equity): %f\n" ce;
  Printf.printf "CB (Cost of Debt): %f\n" cb;
  Printf.printf "WACC: %f\n" wacc;
  Printf.printf "FCFE₀: %s\n" (format_currency ~currency fcfe0);
  Printf.printf "FCFF₀: %s\n" (format_currency ~currency fcff0);
  Printf.printf "FCFEGR: %f\n" fcfegr;
  Printf.printf "FCFFGR: %f\n" fcffgr;
  Printf.printf "TGR: %f\n" tgr;
  Printf.printf "Shares Outstanding: %s shares\n" (format_large_number so);

  Printf.printf "\n==== Valuation Results ====\n";
  Printf.printf "Intrinsic Value (FCFE): %s\n" (format_currency ~currency pve);
  Printf.printf "Intrinsic Value (FCFF): %s\n" (format_currency ~currency pvf);
  Printf.printf "Current Market Price: %.2f %s\n" price currency;
  Printf.printf "IVPS (from FCFE): %.2f %s; %s; margin of safety: %.2f%%\n"
    ivps_fcfe currency
    (if ivps_fcfe > price then "undervalued" else "overvalued")
    margin_fcfe;
  Printf.printf "IVPS (from FCFF): %.2f %s; %s; margin of safety: %.2f%%\n"
    ivps_fcff currency
    (if ivps_fcff > price then "undervalued" else "overvalued")
    margin_fcff;

  Printf.printf "\n==== Implied vs Forecast Growth Rates ====\n";
  Printf.printf "Avg Projected FCFE Growth (Years 1-%d): %.2f%% | Implied FCFE g* (1-%d yrs): %.2f%%\n"
    h (avg_fcfegr *. 100.0) h (implied_fcfegr *. 100.0);
  Printf.printf "Avg Projected FCFF Growth (Years 1-%d): %.2f%% | Implied FCFF g* (1-%d yrs): %.2f%%\n"
    h (avg_fcffgr *. 100.0) h (implied_fcffgr *. 100.0);

  Printf.printf "\n==== Signal Recommendation ====\n";
  Printf.printf "Signal: %s\n" signal;
  Printf.printf "===============================================================\n\n%!"
;;
