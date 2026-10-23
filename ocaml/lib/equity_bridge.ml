open Boundary_t

let definition = "claims_between_enterprise_and_equity_value"

type cash_flow = Consolidated_operating_income | Parent_net_income

let united_states = "United States"

let leases_outside_debt (fin : financials) =
  fin.taxonomy = "ifrs-full" || (fin.taxonomy = "" && fin.country <> Some united_states)

(* [sign] is +1 for a claim deducted, -1 for an asset added; [after_tax] the share of the
   value that is deducted, below 1 where a tax saving goes with settling it. *)
let item_after_tax ~after_tax ~name ~value ~row ~applied ~sign ~why =
  let deduction = match (applied, value) with true, Some v -> sign *. v *. after_tax | _ -> 0. in
  { name; value; row; applied = applied && Option.is_some value; deduction; why }

let item ~name ~value ~row ~applied ~sign ~why = item_after_tax ~after_tax:1. ~name ~value ~row ~applied ~sign ~why

let not_filed = "not filed at the period end"

let minority (p : fiscal_period) ~cash_flow ~share_count_includes_minority =
  let applied, why =
    match (p.minority_interest, share_count_includes_minority, cash_flow) with
    | None, _, _ -> (false, not_filed)
    | Some _, Some declared, _ ->
        (false, "not deducted: the share count already holds the units the minority interest stands for (declared: " ^ declared ^ ")")
    | Some _, None, Parent_net_income ->
        (false, "not deducted: the cash flow is built from net income attributable to the parent, which leaves the minority holders' share out already")
    | Some _, None, Consolidated_operating_income ->
        (true, "deducted: the cash flow starts from consolidated operating income, which carries the minority holders' share of consolidated subsidiaries")
  in
  item ~name:"minority_interest" ~value:p.minority_interest ~row:p.minority_interest_row ~applied ~sign:1. ~why

let investees (fin : financials) (p : fiscal_period) ~cash_flow =
  let applied, why =
    match (p.equity_method_investments, cash_flow, p.investees_in_operating_income) with
    | None, _, _ -> (false, not_filed)
    | Some _, Parent_net_income, _ -> (false, "not added: net income holds the investees' earnings already")
    | Some _, Consolidated_operating_income, Some true ->
        ( false,
          "not added: the filer's operating income holds the investees' earnings, operating income less revenue less costs and expenses equalling the equity-method line, so the cash flow values them already" )
    (* (2026-10-23) IFRS leaves the share's place to the filer, and BP's profit before interest
       and taxation holds it: added only where the subtotals place it below *)
    | Some _, Consolidated_operating_income, None when fin.taxonomy = "ifrs-full" ->
        ( false,
          "not added: the filing's subtotals do not place the investees' share below operating profit, which IFRS leaves to the filer, so the cash flow may value them already" )
    | Some _, Consolidated_operating_income, (Some false | None) ->
        (true, "added at book value, not market: operating income leaves the investees' earnings out")
  in
  item ~name:"equity_method_investments" ~value:p.equity_method_investments ~row:p.equity_method_investments_row ~applied
    ~sign:(-1.) ~why

(* On IFRS statements a filer's Borrowings may carry its leases: the debt less the lease
   liabilities is then the vendor's debt within the threshold, where the debt itself is not. *)
let leases_inside_debt (fin : financials) (p : fiscal_period) lease =
  match (fin.cross_check, p.total_debt) with
  | Some cc, Some debt when fin.taxonomy = "ifrs-full" && cc.period_end = p.period_end -> (
      match List.find_opt (fun (f : field_check) -> f.field = "total_debt") cc.fields with
      | Some { agree = Some false; primary = Some primary; secondary = Some vendor; _ } when primary > 0. ->
          (* the check is in the statements' currency; the period may have been converted *)
          let vendor = vendor *. (debt /. primary) and less = debt -. lease in
          Float.abs (less -. vendor) <= cc.threshold *. Float.max (Float.abs less) (Float.abs vendor)
      | _ -> false)
  | _ -> false

let leases (fin : financials) (p : fiscal_period) =
  let applied, why =
    match (p.lease_liabilities, leases_outside_debt fin) with
    | Some lease, true when leases_inside_debt fin p lease ->
        ( false,
          "not deducted: the debt read already holds them, the debt less the lease liabilities matching the vendor's debt within the threshold where the debt itself does not" )
    | None, true -> (false, not_filed)
    | None, false -> (false, "not read: under US GAAP an operating lease's cost is inside operating income")
    | Some _, false -> (false, "not deducted: under US GAAP an operating lease's cost is inside operating income")
    | Some _, true ->
        ( true,
          "deducted: under IFRS, and on the vendor's statements of a filer outside the United States, the lease cost is depreciation, added back with the rest, and interest, and the principal is paid in financing, so the cash flow never pays it" )
  in
  item ~name:"lease_liabilities" ~value:p.lease_liabilities ~row:p.lease_liabilities_row ~applied ~sign:1. ~why

let contingent (p : fiscal_period) =
  let applied, why =
    match p.contingent_consideration with
    | None -> (false, not_filed)
    | Some _ -> (true, "deducted: an acquisition's deferred price, paid outside the capex and working-capital lines the cash flow reads")
  in
  item ~name:"contingent_consideration" ~value:p.contingent_consideration ~row:p.contingent_consideration_row ~applied ~sign:1.
    ~why

let distributions (fin : financials) (p : fiscal_period) =
  match fin.distributions_since_base with
  | Some d when d.since = p.period_end ->
      let rows = List.filter_map Fun.id [ d.repurchases_row; d.dividends_row; d.issuance_row ] in
      item ~name:"distributions_since_base" ~value:(Some d.net)
        ~row:(if rows = [] then None else Some (String.concat " + " rows))
        ~applied:true ~sign:1.
        ~why:
          (Printf.sprintf
             "deducted: buybacks and common dividends less shares issued from %s to %s, from the quarterly filing's year-to-date cash flow statement (%s): the share count is today's and the base's net debt still holds that cash; buybacks after %s are in the share count and not here"
             d.since d.through d.accession d.through)
  | Some d ->
      item ~name:"distributions_since_base" ~value:None ~row:None ~applied:false ~sign:1.
        ~why:(Printf.sprintf "not deducted: the valued period's balance sheet is not the base the year-to-date figures run from (%s)" d.since)
  | None ->
      item ~name:"distributions_since_base" ~value:None ~row:None ~applied:false ~sign:1.
        ~why:("not read: " ^ Option.value fin.distributions_reason ~default:"no quarterly filing after the base was read")

(* Paid to buy minority interests out since the base, above the book they removed: only where
   the minority interest itself is deducted, at its base-date book, and only from the base. *)
let buyouts (fin : financials) (p : fiscal_period) ~(minority : bridge_item) =
  let name = "minority_buyouts_since_base" in
  match fin.distributions_since_base with
  | Some d when d.since = p.period_end -> (
      match d.minority_net with
      | None -> item ~name ~value:None ~row:None ~applied:false ~sign:1. ~why:"not filed: no payment to minority holders in the year-to-date cash flow statement"
      | Some net when not minority.applied ->
          item ~name ~value:(Some net) ~row:d.minority_buyouts_row ~applied:false ~sign:1.
            ~why:"not deducted: the minority interest itself is not deducted on this record"
      | Some net ->
          let rows = List.filter_map Fun.id [ d.minority_buyouts_row; Option.map (fun r -> "- " ^ r) d.minority_buyouts_book_row ] in
          item ~name ~value:(Some net) ~row:(if rows = [] then None else Some (String.concat " " rows)) ~applied:true ~sign:1.
            ~why:
              (Printf.sprintf
                 "deducted: paid from %s to %s to buy minority interests out, less the book they removed where filed: the minority above is at its base-date book and the purchase settled it at a price, while the base's net debt still holds the cash; dividends to minority holders and contributions from them move the cash and the minority's book alike and are not read"
                 d.since d.through))
  | _ -> item ~name ~value:None ~row:None ~applied:false ~sign:1. ~why:"not read: the year-to-date figures do not run from the valued period"

(* Securities held beyond a year and stakes outside the equity method: their interest,
   dividends and changes in value fall below operating income. *)
let financial (p : fiscal_period) ~cash_flow =
  let applied, why =
    match (p.financial_investments, cash_flow) with
    | None, _ -> (false, not_filed)
    | Some _, Parent_net_income ->
        (false, "not added: net income holds their interest, dividends and changes in value already")
    | Some _, Consolidated_operating_income ->
        ( true,
          "added at carrying value: operating income leaves out their interest, dividends and changes in value; no tax on a gain not yet realised is deducted" )
  in
  item ~name:"financial_investments" ~value:p.financial_investments ~row:p.financial_investments_row ~applied ~sign:(-1.) ~why

(* The defined-benefit plans' deficit, or surplus, after tax: contributions are deductible. *)
let pension (p : fiscal_period) ~cash_flow ~statutory_tax_rate =
  let applied, why =
    match (p.pension_net, cash_flow) with
    | None, _ -> (false, not_filed)
    | Some _, Parent_net_income ->
        (false, "not deducted: net income carries the plans' interest cost and the return on their assets already")
    | Some _, Consolidated_operating_income ->
        ( true,
          Printf.sprintf
            "deducted after tax at the statutory %.4g, a surplus added the same way: operating income carries the plans' service cost and leaves out the interest on the obligation and the return on the assets, and contributions are deductible"
            statutory_tax_rate )
  in
  item_after_tax ~after_tax:(1. -. statutory_tax_rate) ~name:"pension_net" ~value:p.pension_net ~row:p.pension_net_row
    ~applied ~sign:1. ~why

(* Claims charged to earnings and paid outside the cash flow. On US GAAP statements, litigation
   accrued: charged when it arose, on every cash flow alike, and less the deferred tax asset the
   filer records on its legal settlements where filed; an asset retirement obligation is not
   read, its accretion being an operating expense the cash flow already bears. On IFRS
   statements, decommissioning and legal provisions, else the noncurrent provisions, which
   unwind in finance costs: below operating income, inside net income. *)
let provisions (fin : financials) (p : fiscal_period) ~cash_flow ~statutory_tax_rate =
  let name = "provisions" in
  match p.provisions with
  | _ when fin.taxonomy = "" ->
      item ~name ~value:None ~row:None ~applied:false ~sign:1.
        ~why:"not read on the vendor's statements, whose provision rows hold ongoing operating provisions beside the debt-like ones"
  | None -> item ~name ~value:None ~row:None ~applied:false ~sign:1. ~why:not_filed
  | Some v when fin.taxonomy = "ifrs-full" -> (
      match cash_flow with
      | Parent_net_income ->
          item ~name ~value:(Some v) ~row:p.provisions_row ~applied:false ~sign:1.
            ~why:"not deducted: net income carries their unwinding, a finance cost"
      | Consolidated_operating_income ->
          item_after_tax ~after_tax:(1. -. statutory_tax_rate) ~name ~value:(Some v) ~row:p.provisions_row ~applied:true ~sign:1.
            ~why:
              (Printf.sprintf
                 "deducted after tax at the statutory %.4g: decommissioning and legal provisions, else the noncurrent provisions, unwind in finance costs below operating income and are paid outside the capex and working capital the cash flow reads; current provisions, ongoing like payables, are not read"
                 statutory_tax_rate))
  | Some v -> (
      match p.provisions_tax_asset with
      | Some asset when asset > 0. ->
          let row = Option.map (fun r -> r ^ Option.fold ~none:"" ~some:(fun a -> " - " ^ a) p.provisions_tax_asset_row) p.provisions_row in
          { name; value = Some v; row; applied = true; deduction = v -. asset;
            why =
              "deducted less the deferred tax asset the filer records on its legal settlements: litigation charged to earnings when accrued and paid outside every cash flow here" }
      | _ ->
          item_after_tax ~after_tax:(1. -. statutory_tax_rate) ~name ~value:(Some v) ~row:p.provisions_row ~applied:true ~sign:1.
            ~why:
              (Printf.sprintf
                 "deducted after tax at the statutory %.4g, the filer recording no tax asset on it: litigation charged to earnings when accrued and paid outside every cash flow here; a fine is not deductible, and is then understated by the rate"
                 statutory_tax_rate))

let preferred (p : fiscal_period) =
  let applied, why =
    match p.preferred_stock with
    | None -> (false, not_filed)
    | Some _ -> (true, "deducted at carrying value: every cash flow here is before the preferred dividend")
  in
  item ~name:"preferred_stock" ~value:p.preferred_stock ~row:p.preferred_stock_row ~applied ~sign:1. ~why

let of_period ~cash_flow ~statutory_tax_rate ?share_count_includes_minority (fin : financials) (p : fiscal_period) =
  let minority_item = minority p ~cash_flow ~share_count_includes_minority in
  let items =
    [ minority_item; buyouts fin p ~minority:minority_item; investees fin p ~cash_flow; financial p ~cash_flow; leases fin p;
      contingent p; pension p ~cash_flow ~statutory_tax_rate; provisions fin p ~cash_flow ~statutory_tax_rate; preferred p;
      distributions fin p ]
  in
  { definition; items; total = List.fold_left (fun acc (i : bridge_item) -> acc +. i.deduction) 0. items }

let total (i : inputs) = match i.equity_bridge with Some b -> b.total | None -> 0.
