(** Which factors apply per sector, and the thin-sector threshold.

    Ports the spirit of [relative_valuation/.../multiples.ml:multiples_for_sector]:
    some factors are meaningless for certain sectors and must be excluded from the
    composite rather than ranked as if comparable. EV is meaningless for
    banks/insurers (debt is operating raw material); EV/EBIT and earnings yield are
    distorted for REITs by heavy depreciation. *)

let all_value =
  [ "ebit_ev"; "ebitda_ev"; "fcf_ev"; "sales_ev"; "earnings_yield";
    "book_price"; "shareholder_yield" ]

let all_quality =
  [ "roic"; "gp_assets"; "gross_margin"; "roe"; "accruals_neg"; "leverage_neg" ]

(* sectors with fewer than this many names (with a given factor present) in the
   panel are ranked against the global pool instead of their tiny sector. *)
let thin_sector_threshold = 8

let contains ~sub s =
  let s = String.lowercase_ascii s and sub = String.lowercase_ascii sub in
  let ls = String.length s and lsub = String.length sub in
  let rec go i =
    if i + lsub > ls then false
    else if String.sub s i lsub = sub then true
    else go (i + 1)
  in
  if lsub = 0 then true else go 0

let is_financial sector = contains ~sub:"financial" sector
let is_reit sector = contains ~sub:"real estate" sector

(** Value factors allowed for a sector. Banks/insurers drop all EV-based factors;
    REITs drop EV/EBIT and earnings yield (depreciation distortion). *)
let value_factors_for sector =
  if is_financial sector then [ "book_price"; "earnings_yield"; "shareholder_yield" ]
  else if is_reit sector then [ "book_price"; "fcf_ev"; "sales_ev"; "shareholder_yield" ]
  else all_value

(** Quality factors allowed for a sector. ROIC / leverage / gross-profitability are
    meaningless for banks/insurers and distorted for REITs, so both fall back to a
    thin {roe, accruals} pillar (flagged via low n_quality_used). *)
let quality_factors_for sector =
  if is_financial sector || is_reit sector then [ "roe"; "accruals_neg" ]
  else all_quality
