(** Unit tests for the cross-sectional ranking engine (synthetic panels). *)

open Factor_rank

let row ticker sector fields = { Types.ticker; sector; fields }

(* A "full" tech name whose every value+quality input scales with i, so every value
   factor is monotonically increasing in i (EV is fixed at 10). *)
let tech i =
  let fi = float i in
  row (Printf.sprintf "T%d" i) "Technology"
    [ ("market_cap", 10.); ("total_debt", 0.); ("total_cash", 0.);
      ("ebit", fi); ("ebitda", fi); ("free_cash_flow", fi); ("revenue", fi);
      ("net_income", fi); ("total_equity", fi); ("shareholder_payout", fi);
      ("gross_profit", fi); ("operating_cash_flow", fi); ("total_assets", 100.);
      ("tax_provision", 0.2 *. fi); ("pretax_income", fi) ]

let bank =
  row "BANKX" "Financial Services"
    [ ("market_cap", 10.); ("total_debt", 5.); ("total_cash", 1.);
      ("ebit", 3.); ("ebitda", 4.); ("free_cash_flow", 3.); ("revenue", 8.);
      ("net_income", 2.); ("total_equity", 6.); ("shareholder_payout", 1.);
      ("gross_profit", 5.); ("operating_cash_flow", 2.); ("total_assets", 100.);
      ("tax_provision", 0.4); ("pretax_income", 2.) ]

(* net-cash name: cash >> mktcap+debt -> EV < 0 *)
let evneg =
  row "NETCASH" "Healthcare"
    [ ("market_cap", 10.); ("total_debt", 0.); ("total_cash", 200.);
      ("ebit", 5.); ("ebitda", 6.); ("free_cash_flow", 5.); ("revenue", 9.);
      ("net_income", 4.); ("total_equity", 5.); ("shareholder_payout", 2.);
      ("gross_profit", 7.); ("operating_cash_flow", 4.); ("total_assets", 100.);
      ("tax_provision", 0.8); ("pretax_income", 4.) ]

(* sparse name: only one value input, no quality inputs *)
let sparse = row "SPARSE" "Energy" [ ("market_cap", 10.); ("net_income", 1.) ]

let panel = List.init 8 (fun i -> tech (i + 1)) @ [ bank; evneg; sparse ]

let find t = List.find (fun r -> r.Types.ticker = t) (Rank_engine.rank panel)

let test_orientation () =
  let v8 = (find "T8").Types.value_pct and v1 = (find "T1").Types.value_pct in
  Alcotest.(check bool) "T8 value present" true (v8 <> None);
  Alcotest.(check bool) "T1 value present" true (v1 <> None);
  Alcotest.(check bool) "higher inputs -> higher value_pct (cheaper)" true
    (Option.get v8 > Option.get v1);
  Alcotest.(check string) "T8 is DeepValue" "DeepValue" (find "T8").Types.signal

let test_quality_orientation () =
  (* gp_assets increases with i; T8 should out-rank T1 on quality *)
  let q8 = (find "T8").Types.quality_pct and q1 = (find "T1").Types.quality_pct in
  Alcotest.(check bool) "quality present" true (q8 <> None && q1 <> None);
  Alcotest.(check bool) "T8 quality >= T1 quality" true (Option.get q8 >= Option.get q1)

let test_half_rule_na () =
  let r = find "SPARSE" in
  Alcotest.(check (option (float 0.01))) "sparse value_pct N/A" None r.Types.value_pct;
  Alcotest.(check (option (float 0.01))) "sparse quality_pct N/A" None r.Types.quality_pct

let test_bank_excludes_ev () =
  let r = find "BANKX" in
  Alcotest.(check int) "bank value factors = 3 (no EV)" 3 r.Types.n_value_allowed;
  Alcotest.(check int) "bank quality factors = 2" 2 r.Types.n_quality_allowed

let test_ev_negative () =
  let r = find "NETCASH" in
  (* the 4 EV-based value factors are excluded; only the 3 equity-based remain *)
  Alcotest.(check int) "EV<0 -> 3 value factors used" 3 r.Types.n_value_used;
  Alcotest.(check (option (float 0.01))) "EV<0 -> value_pct N/A (<half)" None r.Types.value_pct;
  Alcotest.(check bool) "EV<0 -> quality still ranks" true (r.Types.quality_pct <> None)

let () =
  Alcotest.run "factor_rank"
    [ ( "rank_engine",
        [ Alcotest.test_case "value orientation" `Quick test_orientation;
          Alcotest.test_case "quality orientation" `Quick test_quality_orientation;
          Alcotest.test_case "half-present rule -> N/A" `Quick test_half_rule_na;
          Alcotest.test_case "bank excludes EV factors" `Quick test_bank_excludes_ev;
          Alcotest.test_case "EV<=0 handling" `Quick test_ev_negative ] ) ]
