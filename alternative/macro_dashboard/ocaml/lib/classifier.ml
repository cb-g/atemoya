(** Macro Environment Classifier *)

open Types

(** Classify yield curve state *)
let classify_yield_curve ~spread_10y2y ~spread_10y3m =
  let spread = match spread_10y2y with
    | Some s -> s
    | None -> (match spread_10y3m with Some s -> s | None -> 0.0)
  in
  if spread < -0.5 then DeeplyInverted
  else if spread < 0.0 then Inverted
  else if spread < 0.5 then Flat
  else Normal

(** Classify inflation regime based on core PCE/CPI *)
let classify_inflation ~core_pce ~core_cpi =
  let rate = match core_pce with
    | Some r -> r
    | None -> (match core_cpi with Some r -> r | None -> 2.0)
  in
  if rate < 0.0 then Deflation
  else if rate < 1.5 then LowInflation
  else if rate <= 2.5 then TargetInflation
  else if rate <= 4.0 then HighInflation
  else VeryHigh

(** Classify labor market state *)
let classify_labor ~unemployment ~claims =
  let u = match unemployment with Some u -> u | None -> 4.0 in
  let _claims_signal = match claims with
    | Some c when c > 300.0 -> 1  (* Elevated *)
    | Some c when c < 200.0 -> -1 (* Very low *)
    | _ -> 0
  in
  if u < 3.5 then VeryTight
  else if u < 4.0 then Tight
  else if u < 5.0 then Healthy
  else if u < 6.0 then Softening
  else Weak

(** Classify risk sentiment based on VIX *)
let classify_risk ~vix =
  let v = match vix with Some v -> v | None -> 18.0 in
  if v > 30.0 then RiskOff
  else if v > 20.0 then Cautious
  else if v > 15.0 then Neutral
  else RiskOn

(** Infer Fed stance from rates, inflation, and labor *)
let classify_fed_stance ~fed_funds ~inflation_regime ~labor_state =
  let ff = match fed_funds with Some f -> f | None -> 4.0 in

  (* Base stance from fed funds level relative to neutral (~2.5%) *)
  let rate_stance =
    if ff < 1.0 then -2      (* Very accommodative *)
    else if ff < 2.5 then -1 (* Accommodative *)
    else if ff < 4.0 then 0  (* Neutral *)
    else if ff < 5.5 then 1  (* Restrictive *)
    else 2                   (* Very restrictive *)
  in

  (* Adjust for inflation pressure *)
  let inflation_adj = match inflation_regime with
    | VeryHigh -> 1
    | HighInflation -> 1
    | TargetInflation -> 0
    | LowInflation -> -1
    | Deflation -> -1
  in

  (* Adjust for labor market *)
  let labor_adj = match labor_state with
    | VeryTight | Tight -> 1
    | Healthy -> 0
    | Softening -> -1
    | Weak -> -1
  in

  let combined = rate_stance + inflation_adj + labor_adj in
  if combined <= -3 then VeryDovish
  else if combined <= -1 then Dovish
  else if combined <= 1 then NeutralFed
  else if combined <= 3 then Hawkish
  else VeryHawkish

(** Classify economic cycle phase *)
let classify_cycle ~gdp_growth ~yield_curve ~inflation_regime ~labor_state =
  let growth = match gdp_growth with Some g -> g | None -> 2.0 in

  (* Recession: negative growth *)
  if growth < 0.0 then Recession
  else
    (* Use combination of indicators *)
    let growth_score =
      if growth > 3.0 then 2
      else if growth > 2.0 then 1
      else 0
    in

    let yield_score = match yield_curve with
      | DeeplyInverted -> -2
      | Inverted -> -1
      | Flat -> 0
      | Normal -> 1
    in

    let inflation_score = match inflation_regime with
      | Deflation -> -1
      | LowInflation -> 0
      | TargetInflation -> 1
      | HighInflation -> 2
      | VeryHigh -> 2
    in

    let labor_score = match labor_state with
      | VeryTight | Tight -> 2
      | Healthy -> 1
      | Softening -> 0
      | Weak -> -1
    in

    let total = growth_score + yield_score + inflation_score + labor_score in

    if total >= 5 then LateCycle      (* Strong growth + tight labor + inflation *)
    else if total >= 2 then MidCycle  (* Balanced expansion *)
    else EarlyCycle                   (* Early recovery *)

(** Estimate recession probability *)
let estimate_recession_prob ~yield_curve ~labor_state ~gdp_growth ~vix =
  let base_prob = 0.1 in

  (* Yield curve is the strongest predictor *)
  let yield_adj = match yield_curve with
    | DeeplyInverted -> 0.35
    | Inverted -> 0.20
    | Flat -> 0.05
    | Normal -> 0.0
  in

  (* Labor market deterioration *)
  let labor_adj = match labor_state with
    | Weak -> 0.20
    | Softening -> 0.10
    | _ -> 0.0
  in

  (* GDP weakness *)
  let gdp_adj = match gdp_growth with
    | Some g when g < 0.5 -> 0.15
    | Some g when g < 1.5 -> 0.05
    | _ -> 0.0
  in

  (* High VIX *)
  let vix_adj = match vix with
    | Some v when v > 30.0 -> 0.10
    | Some v when v > 25.0 -> 0.05
    | _ -> 0.0
  in

  min 0.95 (base_prob +. yield_adj +. labor_adj +. gdp_adj +. vix_adj)

(** Classify full macro environment *)
let classify (snapshot : macro_snapshot) : macro_environment =
  let yield_curve = classify_yield_curve
    ~spread_10y2y:snapshot.rates.spread_10y2y
    ~spread_10y3m:snapshot.rates.spread_10y3m
  in

  let inflation_regime = classify_inflation
    ~core_pce:snapshot.inflation.core_pce_yoy
    ~core_cpi:snapshot.inflation.core_cpi_yoy
  in

  let labor_state = classify_labor
    ~unemployment:snapshot.employment.unemployment_rate
    ~claims:snapshot.employment.initial_claims
  in

  let risk_sentiment = classify_risk
    ~vix:snapshot.market.vix
  in

  let fed_stance = classify_fed_stance
    ~fed_funds:snapshot.rates.fed_funds
    ~inflation_regime
    ~labor_state
  in

  let cycle_phase = classify_cycle
    ~gdp_growth:snapshot.growth.gdp_growth
    ~yield_curve
    ~inflation_regime
    ~labor_state
  in

  let recession_probability = estimate_recession_prob
    ~yield_curve
    ~labor_state
    ~gdp_growth:snapshot.growth.gdp_growth
    ~vix:snapshot.market.vix
  in

  (* Confidence based on data availability *)
  let data_points = [
    snapshot.rates.fed_funds; snapshot.rates.spread_10y2y;
    snapshot.inflation.core_pce_yoy; snapshot.employment.unemployment_rate;
    snapshot.growth.gdp_growth; snapshot.market.vix;
  ] in
  let available = List.fold_left (fun acc opt ->
    acc +. (match opt with Some _ -> 1.0 | None -> 0.0)
  ) 0.0 data_points in
  let confidence = available /. float_of_int (List.length data_points) in

  {
    cycle_phase;
    yield_curve;
    inflation_regime;
    labor_state;
    risk_sentiment;
    fed_stance;
    recession_probability;
    confidence;
  }

(** Generate investment implications *)
let investment_implications (env : macro_environment) : investment_implications =
  let equity_outlook = match env.cycle_phase, env.risk_sentiment with
    | Recession, _ -> "Underweight - Defensive positioning"
    | LateCycle, RiskOff -> "Underweight - Reduce risk"
    | LateCycle, _ -> "Neutral - Quality focus"
    | MidCycle, RiskOn -> "Overweight - Favorable conditions"
    | MidCycle, _ -> "Neutral to Overweight"
    | EarlyCycle, _ -> "Overweight - Recovery plays"
  in

  let bond_outlook = match env.yield_curve, env.fed_stance with
    | DeeplyInverted, VeryHawkish -> "Short duration - Rate risk"
    | Inverted, Hawkish -> "Short duration - Curve normalization expected"
    | _, VeryDovish | _, Dovish -> "Extend duration - Rates falling"
    | Normal, NeutralFed -> "Neutral duration"
    | _ -> "Neutral - Monitor Fed"
  in

  let sector_tilts = match env.cycle_phase with
    | EarlyCycle ->
        ["Financials"; "Consumer Discretionary"; "Industrials"; "Small Caps"]
    | MidCycle ->
        ["Technology"; "Communication Services"; "Industrials"]
    | LateCycle ->
        ["Healthcare"; "Consumer Staples"; "Utilities"; "Energy"]
    | Recession ->
        ["Utilities"; "Consumer Staples"; "Healthcare"; "Gold"]
  in

  let risk_level = match env.risk_sentiment, env.recession_probability with
    | RiskOff, _ -> "High - Reduce exposure"
    | _, p when p > 0.5 -> "High - Recession risk elevated"
    | Cautious, _ -> "Elevated - Maintain hedges"
    | Neutral, _ -> "Moderate - Normal positioning"
    | RiskOn, _ -> "Low - Favorable conditions"
  in

  let key_risks =
    let risks = ref [] in

    if env.recession_probability > 0.3 then
      risks := "Recession risk from inverted yield curve" :: !risks;

    (match env.inflation_regime with
      | VeryHigh | HighInflation ->
          risks := "Persistent inflation forcing Fed tightening" :: !risks
      | Deflation ->
          risks := "Deflationary spiral risk" :: !risks
      | _ -> ());

    (match env.labor_state with
      | Weak | Softening ->
          risks := "Labor market deterioration" :: !risks
      | VeryTight ->
          risks := "Wage-price spiral from tight labor" :: !risks
      | _ -> ());

    (match env.risk_sentiment with
      | RiskOff -> risks := "Credit stress and deleveraging" :: !risks
      | RiskOn -> risks := "Complacency - potential for volatility spike" :: !risks
      | _ -> ());

    (match env.yield_curve with
      | DeeplyInverted ->
          risks := "Yield curve historically predicts recession in 12-18 months" :: !risks
      | _ -> ());

    List.rev !risks
  in

  { equity_outlook; bond_outlook; sector_tilts; risk_level; key_risks }
