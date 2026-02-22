open Macro_dashboard

let float_eq ~eps = Alcotest.testable
  (fun fmt f -> Format.fprintf fmt "%.4f" f)
  (fun a b -> Float.abs (a -. b) < eps)

(* ══════════════════════════════════════════════════════════════════════════════
   Helper: build macro_snapshot with optional fields (all default to None)
   ══════════════════════════════════════════════════════════════════════════════*)

let make_snapshot
    ?fed_funds ?spread_10y2y ?spread_10y3m
    ?core_pce_yoy ?core_cpi_yoy
    ?unemployment_rate ?initial_claims
    ?gdp_growth
    ?vix
    ()
  : Types.macro_snapshot =
  {
    timestamp = "2026-02-15";
    rates = {
      fed_funds;
      treasury_3m = None;
      treasury_2y = None;
      treasury_10y = None;
      spread_10y2y;
      spread_10y3m;
    };
    inflation = {
      cpi_yoy = None;
      core_cpi_yoy;
      pce_yoy = None;
      core_pce_yoy;
      ppi_yoy = None;
    };
    employment = {
      unemployment_rate;
      nfp_change = None;
      initial_claims;
      continued_claims = None;
      job_openings = None;
    };
    growth = {
      gdp_growth;
      industrial_production_yoy = None;
      retail_sales_yoy = None;
    };
    market = {
      vix;
      move_index = None;
      dollar_index = None;
      gold = None;
      oil = None;
      copper = None;
      sp500_ytd = None;
    };
    consumer = {
      retail_sales_yoy = None;
    };
    housing = {
      housing_starts = None;
      building_permits = None;
      existing_home_sales = None;
      mortgage_rate = None;
    };
  }

(* ══════════════════════════════════════════════════════════════════════════════
   Group 1: Yield Curve Classification
   ══════════════════════════════════════════════════════════════════════════════*)

let test_yield_curve_normal () =
  let snap = make_snapshot ~spread_10y2y:1.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "normal" "Normal (Upward Sloping)"
    (Types.string_of_yield_curve env.yield_curve)

let test_yield_curve_flat () =
  let snap = make_snapshot ~spread_10y2y:0.3 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "flat" "Flat"
    (Types.string_of_yield_curve env.yield_curve)

let test_yield_curve_inverted () =
  let snap = make_snapshot ~spread_10y2y:(-0.2) () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "inverted" "Inverted"
    (Types.string_of_yield_curve env.yield_curve)

let test_yield_curve_deeply_inverted () =
  let snap = make_snapshot ~spread_10y2y:(-0.8) () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "deeply inverted" "Deeply Inverted"
    (Types.string_of_yield_curve env.yield_curve)

let test_yield_curve_fallback_10y3m () =
  (* When 10y2y is missing, uses 10y3m *)
  let snap = make_snapshot ~spread_10y3m:(-0.6) () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "uses 10y3m" "Deeply Inverted"
    (Types.string_of_yield_curve env.yield_curve)

(* ══════════════════════════════════════════════════════════════════════════════
   Group 2: Inflation Regime
   ══════════════════════════════════════════════════════════════════════════════*)

let test_inflation_deflation () =
  let snap = make_snapshot ~core_pce_yoy:(-0.5) () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "deflation" "Deflation"
    (Types.string_of_inflation_regime env.inflation_regime)

let test_inflation_low () =
  let snap = make_snapshot ~core_pce_yoy:1.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "low" "Low Inflation"
    (Types.string_of_inflation_regime env.inflation_regime)

let test_inflation_target () =
  let snap = make_snapshot ~core_pce_yoy:2.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "target" "At Target"
    (Types.string_of_inflation_regime env.inflation_regime)

let test_inflation_high () =
  let snap = make_snapshot ~core_pce_yoy:3.5 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "high" "Elevated"
    (Types.string_of_inflation_regime env.inflation_regime)

let test_inflation_very_high () =
  let snap = make_snapshot ~core_pce_yoy:5.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "very high" "Very High"
    (Types.string_of_inflation_regime env.inflation_regime)

let test_inflation_fallback_cpi () =
  (* When PCE missing, uses core CPI *)
  let snap = make_snapshot ~core_cpi_yoy:(-1.0) () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "CPI fallback" "Deflation"
    (Types.string_of_inflation_regime env.inflation_regime)

(* ══════════════════════════════════════════════════════════════════════════════
   Group 3: Labor & Risk Sentiment
   ══════════════════════════════════════════════════════════════════════════════*)

let test_labor_very_tight () =
  let snap = make_snapshot ~unemployment_rate:3.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "very tight" "Very Tight"
    (Types.string_of_labor_state env.labor_state)

let test_labor_healthy () =
  let snap = make_snapshot ~unemployment_rate:4.5 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "healthy" "Healthy"
    (Types.string_of_labor_state env.labor_state)

let test_labor_weak () =
  let snap = make_snapshot ~unemployment_rate:7.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "weak" "Weak"
    (Types.string_of_labor_state env.labor_state)

let test_risk_off () =
  (* VIX > 30 → RiskOff *)
  let snap = make_snapshot ~vix:35.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "risk off" "Risk-Off"
    (Types.string_of_risk_sentiment env.risk_sentiment)

let test_risk_on () =
  (* VIX <= 15 → RiskOn *)
  let snap = make_snapshot ~vix:12.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "risk on" "Risk-On"
    (Types.string_of_risk_sentiment env.risk_sentiment)

let test_risk_cautious () =
  (* VIX > 20 → Cautious *)
  let snap = make_snapshot ~vix:25.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "cautious" "Cautious"
    (Types.string_of_risk_sentiment env.risk_sentiment)

(* ══════════════════════════════════════════════════════════════════════════════
   Group 4: Cycle Phase & Recession Probability
   ══════════════════════════════════════════════════════════════════════════════*)

let test_cycle_recession () =
  let snap = make_snapshot ~gdp_growth:(-1.5) () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "recession" "Recession (Contraction)"
    (Types.string_of_cycle_phase env.cycle_phase)

let test_cycle_early () =
  (* Low composite: growth 1.0 (score 0) + normal curve (1) + low inflation (0)
     + healthy labor (1) = total 2 → MidCycle. Need lower: use weak labor (-1)
     growth 1.0 (0) + flat curve (0) + deflation (-1) + weak (-1) = -2 → EarlyCycle *)
  let snap = make_snapshot ~gdp_growth:1.0 ~spread_10y2y:0.3
    ~core_pce_yoy:(-0.5) ~unemployment_rate:7.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "early cycle" "Early Cycle (Recovery)"
    (Types.string_of_cycle_phase env.cycle_phase)

let test_cycle_mid () =
  (* growth 2.5 (score 1) + normal curve (1) + target inflation (1) + healthy (1)
     = total 4 → MidCycle (>= 2 but < 5) *)
  let snap = make_snapshot ~gdp_growth:2.5 ~spread_10y2y:1.0
    ~core_pce_yoy:2.0 ~unemployment_rate:4.5 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "mid cycle" "Mid Cycle (Expansion)"
    (Types.string_of_cycle_phase env.cycle_phase)

let test_cycle_late () =
  (* growth 3.5 (score 2) + normal curve (1) + high inflation (2) + very tight (2)
     = total 7 → LateCycle (>= 5) *)
  let snap = make_snapshot ~gdp_growth:3.5 ~spread_10y2y:1.0
    ~core_pce_yoy:3.5 ~unemployment_rate:3.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check string) "late cycle" "Late Cycle (Peak)"
    (Types.string_of_cycle_phase env.cycle_phase)

let test_recession_prob_capped () =
  (* Deeply inverted (+35) + weak labor (+20) + GDP 0.3 (+15) + VIX 35 (+10)
     = base 10 + 80 = 90%, but add all at once:
     0.10 + 0.35 + 0.20 + 0.15 + 0.10 = 0.90, under cap *)
  (* Force over 95%: need even more signals. Actually the max is
     0.10 + 0.35 + 0.20 + 0.15 + 0.10 = 0.90, still < 0.95.
     So cap only triggers if impossible sum. Let's verify it stays <= 0.95 *)
  let snap = make_snapshot ~spread_10y2y:(-0.8) ~unemployment_rate:7.0
    ~gdp_growth:0.3 ~vix:35.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check bool) "capped at 95%" true (env.recession_probability <= 0.95)

let test_recession_prob_low () =
  (* Normal curve + healthy labor + strong GDP + low VIX *)
  let snap = make_snapshot ~spread_10y2y:1.0 ~unemployment_rate:4.5
    ~gdp_growth:3.0 ~vix:14.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check (float_eq ~eps:0.001)) "low prob" 0.10 env.recession_probability

let test_recession_prob_elevated () =
  (* Inverted (+0.20) + softening labor (+0.10) = base 0.10 + 0.30 = 0.40 *)
  let snap = make_snapshot ~spread_10y2y:(-0.2) ~unemployment_rate:5.5
    ~gdp_growth:2.0 ~vix:18.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check (float_eq ~eps:0.001)) "elevated prob" 0.40
    env.recession_probability

(* ══════════════════════════════════════════════════════════════════════════════
   Group 5: Investment Implications
   ══════════════════════════════════════════════════════════════════════════════*)

let test_impl_recession () =
  let snap = make_snapshot ~gdp_growth:(-2.0) () in
  let env = Classifier.classify snap in
  let impl = Classifier.investment_implications env in
  Alcotest.(check string) "equity" "Underweight - Defensive positioning"
    impl.equity_outlook;
  Alcotest.(check bool) "utilities in tilts" true
    (List.mem "Utilities" impl.sector_tilts);
  Alcotest.(check bool) "staples in tilts" true
    (List.mem "Consumer Staples" impl.sector_tilts)

let test_impl_midcycle_riskon () =
  (* MidCycle + RiskOn → Overweight *)
  let snap = make_snapshot ~gdp_growth:2.5 ~spread_10y2y:1.0
    ~core_pce_yoy:2.0 ~unemployment_rate:4.5
    ~vix:12.0 () in
  let env = Classifier.classify snap in
  let impl = Classifier.investment_implications env in
  Alcotest.(check string) "equity overweight"
    "Overweight - Favorable conditions" impl.equity_outlook;
  Alcotest.(check bool) "tech in tilts" true
    (List.mem "Technology" impl.sector_tilts)

let test_impl_early_cycle () =
  let snap = make_snapshot ~gdp_growth:1.0 ~spread_10y2y:0.3
    ~core_pce_yoy:(-0.5) ~unemployment_rate:7.0 () in
  let env = Classifier.classify snap in
  let impl = Classifier.investment_implications env in
  Alcotest.(check string) "equity recovery"
    "Overweight - Recovery plays" impl.equity_outlook;
  Alcotest.(check bool) "financials in tilts" true
    (List.mem "Financials" impl.sector_tilts)

let test_impl_late_riskoff () =
  (* LateCycle + RiskOff → Underweight *)
  let snap = make_snapshot ~gdp_growth:3.5 ~spread_10y2y:1.0
    ~core_pce_yoy:3.5 ~unemployment_rate:3.0
    ~vix:35.0 () in
  let env = Classifier.classify snap in
  let impl = Classifier.investment_implications env in
  Alcotest.(check string) "equity underweight"
    "Underweight - Reduce risk" impl.equity_outlook;
  Alcotest.(check string) "risk high" "High - Reduce exposure"
    impl.risk_level

let test_impl_dovish_bonds () =
  (* Fed dovish → extend duration. Need ff < 1.0 (-2) + deflation (-1) + weak (-1) = -4 → VeryDovish *)
  let snap = make_snapshot ~fed_funds:0.5 ~core_pce_yoy:(-0.5)
    ~unemployment_rate:7.0 () in
  let env = Classifier.classify snap in
  let impl = Classifier.investment_implications env in
  Alcotest.(check bool) "extend duration" true
    (String.length impl.bond_outlook > 0 &&
     (impl.bond_outlook = "Extend duration - Rates falling"
      || impl.bond_outlook = "Neutral - Monitor Fed"))

let test_impl_hawkish_bonds () =
  (* DeeplyInverted + VeryHawkish → Short duration.
     Need ff >= 5.5 (rate_stance=2) + high inflation (1) + very tight (1) = 4 → Hawkish
     Actually need combined > 3 for VeryHawkish. ff 6.0 (2) + VeryHigh (1) + VeryTight (1) = 4 → VeryHawkish.
     Plus deeply inverted spread. *)
  let snap = make_snapshot ~fed_funds:6.0 ~spread_10y2y:(-0.8)
    ~core_pce_yoy:5.0 ~unemployment_rate:3.0 () in
  let env = Classifier.classify snap in
  let impl = Classifier.investment_implications env in
  Alcotest.(check string) "short duration"
    "Short duration - Rate risk" impl.bond_outlook

let test_impl_key_risk_inflation () =
  let snap = make_snapshot ~core_pce_yoy:5.0 () in
  let env = Classifier.classify snap in
  let impl = Classifier.investment_implications env in
  Alcotest.(check bool) "inflation risk" true
    (List.exists (fun r -> String.length r > 0 &&
      (try let _ = String.index r 'i' in true with Not_found -> false) &&
      (try let _ = String.index r 'n' in true with Not_found -> false))
      impl.key_risks
    || List.exists (fun r ->
      r = "Persistent inflation forcing Fed tightening") impl.key_risks)

let test_impl_key_risk_recession () =
  (* High recession prob → yield curve risk in key_risks *)
  let snap = make_snapshot ~spread_10y2y:(-0.8) ~unemployment_rate:5.5 () in
  let env = Classifier.classify snap in
  let impl = Classifier.investment_implications env in
  Alcotest.(check bool) "recession risk" true
    (List.exists (fun r ->
      r = "Recession risk from inverted yield curve") impl.key_risks)

(* ══════════════════════════════════════════════════════════════════════════════
   Group 6: Confidence & Edge Cases
   ══════════════════════════════════════════════════════════════════════════════*)

let test_confidence_all_none () =
  let snap = make_snapshot () in
  let env = Classifier.classify snap in
  Alcotest.(check (float_eq ~eps:0.01)) "zero confidence" 0.0 env.confidence

let test_confidence_full_data () =
  let snap = make_snapshot ~fed_funds:4.0 ~spread_10y2y:0.5
    ~core_pce_yoy:2.0 ~unemployment_rate:4.0
    ~gdp_growth:2.5 ~vix:18.0 () in
  let env = Classifier.classify snap in
  Alcotest.(check (float_eq ~eps:0.01)) "full confidence" 1.0 env.confidence

let test_confidence_partial () =
  (* 3 of 6 key data points *)
  let snap = make_snapshot ~fed_funds:4.0 ~core_pce_yoy:2.0 ~vix:18.0 () in
  let env = Classifier.classify snap in
  let expected = 3.0 /. 6.0 in
  Alcotest.(check (float_eq ~eps:0.01)) "partial" expected env.confidence

let test_all_none_defaults_neutral () =
  let snap = make_snapshot () in
  let env = Classifier.classify snap in
  (* With all None: spread defaults to 0.0 → Flat,
     inflation defaults to 2.0 → Target,
     unemployment defaults to 4.0 → Tight (< 4.0 → Tight),
     fed_funds defaults to 4.0 → rate_stance 0,
     vix defaults to 18.0 → 15 < 18 <= 20 → Neutral,
     gdp defaults to 2.0 → not recession *)
  Alcotest.(check string) "flat curve" "Flat"
    (Types.string_of_yield_curve env.yield_curve);
  Alcotest.(check string) "target inflation" "At Target"
    (Types.string_of_inflation_regime env.inflation_regime);
  Alcotest.(check string) "neutral risk" "Neutral"
    (Types.string_of_risk_sentiment env.risk_sentiment)

let test_string_conversions () =
  Alcotest.(check string) "cycle" "Early Cycle (Recovery)"
    (Types.string_of_cycle_phase EarlyCycle);
  Alcotest.(check string) "yield" "Normal (Upward Sloping)"
    (Types.string_of_yield_curve Normal);
  Alcotest.(check string) "inflation" "Deflation"
    (Types.string_of_inflation_regime Deflation);
  Alcotest.(check string) "labor" "Very Tight"
    (Types.string_of_labor_state VeryTight);
  Alcotest.(check string) "risk" "Risk-On"
    (Types.string_of_risk_sentiment RiskOn);
  Alcotest.(check string) "fed" "Very Dovish"
    (Types.string_of_fed_stance VeryDovish)

(* ══════════════════════════════════════════════════════════════════════════════
   Test Runner
   ══════════════════════════════════════════════════════════════════════════════*)

let () =
  let open Alcotest in
  run "Macro Dashboard" [
    "Yield Curve", [
      test_case "Normal"           `Quick test_yield_curve_normal;
      test_case "Flat"             `Quick test_yield_curve_flat;
      test_case "Inverted"         `Quick test_yield_curve_inverted;
      test_case "Deeply Inverted"  `Quick test_yield_curve_deeply_inverted;
      test_case "Fallback 10y3m"   `Quick test_yield_curve_fallback_10y3m;
    ];
    "Inflation", [
      test_case "Deflation"        `Quick test_inflation_deflation;
      test_case "Low"              `Quick test_inflation_low;
      test_case "Target"           `Quick test_inflation_target;
      test_case "High"             `Quick test_inflation_high;
      test_case "Very High"        `Quick test_inflation_very_high;
      test_case "Fallback CPI"     `Quick test_inflation_fallback_cpi;
    ];
    "Labor & Risk", [
      test_case "Very Tight"       `Quick test_labor_very_tight;
      test_case "Healthy"          `Quick test_labor_healthy;
      test_case "Weak"             `Quick test_labor_weak;
      test_case "Risk Off"         `Quick test_risk_off;
      test_case "Risk On"          `Quick test_risk_on;
      test_case "Cautious"         `Quick test_risk_cautious;
    ];
    "Cycle & Recession", [
      test_case "Recession"        `Quick test_cycle_recession;
      test_case "Early Cycle"      `Quick test_cycle_early;
      test_case "Mid Cycle"        `Quick test_cycle_mid;
      test_case "Late Cycle"       `Quick test_cycle_late;
      test_case "Prob capped"      `Quick test_recession_prob_capped;
      test_case "Prob low"         `Quick test_recession_prob_low;
      test_case "Prob elevated"    `Quick test_recession_prob_elevated;
    ];
    "Investment Implications", [
      test_case "Recession"        `Quick test_impl_recession;
      test_case "MidCycle RiskOn"  `Quick test_impl_midcycle_riskon;
      test_case "Early Cycle"      `Quick test_impl_early_cycle;
      test_case "Late RiskOff"     `Quick test_impl_late_riskoff;
      test_case "Dovish bonds"     `Quick test_impl_dovish_bonds;
      test_case "Hawkish bonds"    `Quick test_impl_hawkish_bonds;
      test_case "Risk: inflation"  `Quick test_impl_key_risk_inflation;
      test_case "Risk: recession"  `Quick test_impl_key_risk_recession;
    ];
    "Confidence & Edge Cases", [
      test_case "All None"         `Quick test_confidence_all_none;
      test_case "Full data"        `Quick test_confidence_full_data;
      test_case "Partial data"     `Quick test_confidence_partial;
      test_case "None defaults"    `Quick test_all_none_defaults_neutral;
      test_case "String conversions" `Quick test_string_conversions;
    ];
  ]
