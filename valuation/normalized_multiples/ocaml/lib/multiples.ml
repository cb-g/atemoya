(** Multiple calculations and extraction - Implementation *)

open Types

let make_multiple ~name ~time_window ~value ~underlying_metric =
  let is_valid = value > 0.0 && underlying_metric > 0.0 in
  { name; time_window; value; is_valid; underlying_metric }

let extract_all_multiples company =
  [
    company.pe_ttm;
    company.pe_ntm;
    company.ps_ttm;
    company.pb_ttm;
    company.p_fcf_ttm;
    company.peg_ratio;
    company.ev_ebitda_ttm;
    company.ev_ebit_ttm;
    company.ev_sales_ttm;
    company.ev_fcf_ttm;
  ]

let get_price_multiples company =
  [
    company.pe_ttm;
    company.pe_ntm;
    company.ps_ttm;
    company.pb_ttm;
    company.p_fcf_ttm;
    company.peg_ratio;
  ]

let get_ev_multiples company =
  [
    company.ev_ebitda_ttm;
    company.ev_ebit_ttm;
    company.ev_sales_ttm;
    company.ev_fcf_ttm;
  ]

let all_price_multiple_names =
  ["P/E"; "P/S"; "P/B"; "P/FCF"; "PEG"]

let all_ev_multiple_names =
  ["EV/EBITDA"; "EV/EBIT"; "EV/Sales"; "EV/FCF"]
