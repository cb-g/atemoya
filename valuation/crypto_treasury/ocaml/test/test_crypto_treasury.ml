(** Unit tests for crypto treasury mNAV model *)

open Crypto_treasury

(* ========== Types Tests ========== *)

let test_holding_type_of_btc_eth () =
  Alcotest.(check string) "BTC only"
    "BTC" (Types.string_of_holding_type
      (Types.holding_type_of_btc_eth ~btc_holdings:100 ~eth_holdings:0));
  Alcotest.(check string) "ETH only"
    "ETH" (Types.string_of_holding_type
      (Types.holding_type_of_btc_eth ~btc_holdings:0 ~eth_holdings:500));
  Alcotest.(check string) "Mixed"
    "Mixed" (Types.string_of_holding_type
      (Types.holding_type_of_btc_eth ~btc_holdings:100 ~eth_holdings:500));
  Alcotest.(check string) "Neither defaults to BTC"
    "BTC" (Types.string_of_holding_type
      (Types.holding_type_of_btc_eth ~btc_holdings:0 ~eth_holdings:0))

let test_string_of_holding_type () =
  Alcotest.(check string) "BTC" "BTC" (Types.string_of_holding_type Types.BTC);
  Alcotest.(check string) "ETH" "ETH" (Types.string_of_holding_type Types.ETH);
  Alcotest.(check string) "Mixed" "Mixed" (Types.string_of_holding_type Types.Mixed)

let test_string_of_signal () =
  Alcotest.(check string) "Strong Buy"
    "Strong Buy" (Types.string_of_signal Types.StrongBuy);
  Alcotest.(check string) "Buy"
    "Buy" (Types.string_of_signal Types.Buy);
  Alcotest.(check string) "Hold"
    "Hold" (Types.string_of_signal Types.Hold);
  Alcotest.(check string) "Caution"
    "Caution" (Types.string_of_signal Types.Caution);
  Alcotest.(check string) "Overvalued"
    "Overvalued" (Types.string_of_signal Types.Overvalued)

let test_signal_color () =
  Alcotest.(check string) "StrongBuy is green"
    "green" (Types.signal_color Types.StrongBuy);
  Alcotest.(check string) "Buy is green"
    "green" (Types.signal_color Types.Buy);
  Alcotest.(check string) "Hold is yellow"
    "yellow" (Types.signal_color Types.Hold);
  Alcotest.(check string) "Caution is yellow"
    "yellow" (Types.signal_color Types.Caution);
  Alcotest.(check string) "Overvalued is red"
    "red" (Types.signal_color Types.Overvalued)

let test_signal_of_mnav () =
  (* mNAV < 0.8 => Strong Buy *)
  Alcotest.(check string) "0.5 => Strong Buy"
    "Strong Buy" (Types.string_of_signal (Types.signal_of_mnav 0.5));
  Alcotest.(check string) "0.79 => Strong Buy"
    "Strong Buy" (Types.string_of_signal (Types.signal_of_mnav 0.79));
  (* 0.8 <= mNAV < 1.0 => Buy *)
  Alcotest.(check string) "0.8 => Buy"
    "Buy" (Types.string_of_signal (Types.signal_of_mnav 0.8));
  Alcotest.(check string) "0.95 => Buy"
    "Buy" (Types.string_of_signal (Types.signal_of_mnav 0.95));
  (* 1.0 <= mNAV < 1.2 => Hold *)
  Alcotest.(check string) "1.0 => Hold"
    "Hold" (Types.string_of_signal (Types.signal_of_mnav 1.0));
  Alcotest.(check string) "1.1 => Hold"
    "Hold" (Types.string_of_signal (Types.signal_of_mnav 1.1));
  (* 1.2 <= mNAV < 1.5 => Caution *)
  Alcotest.(check string) "1.2 => Caution"
    "Caution" (Types.string_of_signal (Types.signal_of_mnav 1.2));
  Alcotest.(check string) "1.4 => Caution"
    "Caution" (Types.string_of_signal (Types.signal_of_mnav 1.4));
  (* mNAV >= 1.5 => Overvalued *)
  Alcotest.(check string) "1.5 => Overvalued"
    "Overvalued" (Types.string_of_signal (Types.signal_of_mnav 1.5));
  Alcotest.(check string) "3.0 => Overvalued"
    "Overvalued" (Types.string_of_signal (Types.signal_of_mnav 3.0))

(* ========== NAV Calculation Tests ========== *)

let test_calculate_nav_btc_only () =
  let nav = Mnav.calculate_nav
    ~btc_holdings:100 ~btc_price:50000.0
    ~eth_holdings:0 ~eth_price:2000.0 in
  Alcotest.(check (float 0.01)) "100 BTC at $50k"
    5_000_000.0 nav

let test_calculate_nav_eth_only () =
  let nav = Mnav.calculate_nav
    ~btc_holdings:0 ~btc_price:50000.0
    ~eth_holdings:1000 ~eth_price:2000.0 in
  Alcotest.(check (float 0.01)) "1000 ETH at $2k"
    2_000_000.0 nav

let test_calculate_nav_mixed () =
  let nav = Mnav.calculate_nav
    ~btc_holdings:10 ~btc_price:60000.0
    ~eth_holdings:500 ~eth_price:3000.0 in
  (* 10 * 60000 + 500 * 3000 = 600000 + 1500000 = 2100000 *)
  Alcotest.(check (float 0.01)) "mixed BTC+ETH"
    2_100_000.0 nav

let test_calculate_nav_zero_holdings () =
  let nav = Mnav.calculate_nav
    ~btc_holdings:0 ~btc_price:50000.0
    ~eth_holdings:0 ~eth_price:2000.0 in
  Alcotest.(check (float 0.01)) "zero holdings = 0 NAV"
    0.0 nav

(* ========== mNAV Calculation Tests ========== *)

let test_calculate_mnav_at_nav () =
  let mnav = Mnav.calculate_mnav ~market_cap:1_000_000.0 ~nav:1_000_000.0 in
  Alcotest.(check (float 0.001)) "market cap = NAV => mNAV = 1.0"
    1.0 mnav

let test_calculate_mnav_premium () =
  let mnav = Mnav.calculate_mnav ~market_cap:2_000_000.0 ~nav:1_000_000.0 in
  Alcotest.(check (float 0.001)) "2x market cap => mNAV = 2.0"
    2.0 mnav

let test_calculate_mnav_discount () =
  let mnav = Mnav.calculate_mnav ~market_cap:500_000.0 ~nav:1_000_000.0 in
  Alcotest.(check (float 0.001)) "half market cap => mNAV = 0.5"
    0.5 mnav

let test_calculate_mnav_zero_nav () =
  let mnav = Mnav.calculate_mnav ~market_cap:1_000_000.0 ~nav:0.0 in
  Alcotest.(check bool) "zero NAV => infinity"
    true (mnav = infinity)

(* ========== Premium/Discount Tests ========== *)

let test_premium_pct_at_nav () =
  let pct = Mnav.premium_pct_of_mnav 1.0 in
  Alcotest.(check (float 0.01)) "mNAV 1.0 => 0%"
    0.0 pct

let test_premium_pct_premium () =
  let pct = Mnav.premium_pct_of_mnav 1.5 in
  Alcotest.(check (float 0.01)) "mNAV 1.5 => +50%"
    50.0 pct

let test_premium_pct_discount () =
  let pct = Mnav.premium_pct_of_mnav 0.7 in
  Alcotest.(check (float 0.01)) "mNAV 0.7 => -30%"
    (-30.0) pct

(* ========== Per-Share Tests ========== *)

let test_per_share_normal () =
  let ps = Mnav.per_share ~holdings:1000 ~shares:100_000.0 in
  Alcotest.(check (float 0.0001)) "1000 BTC / 100k shares"
    0.01 ps

let test_per_share_zero_shares () =
  let ps = Mnav.per_share ~holdings:1000 ~shares:0.0 in
  Alcotest.(check (float 0.0001)) "zero shares => 0"
    0.0 ps

(* ========== Implied Price Tests ========== *)

let test_implied_prices_btc_only () =
  let (implied_btc, implied_eth) = Mnav.calculate_implied_prices
    ~btc_holdings:100 ~eth_holdings:0
    ~btc_price:50000.0 ~eth_price:2000.0
    ~market_cap:10_000_000.0 ~mnav:2.0 in
  (* implied BTC = 10_000_000 / 100 = 100_000 *)
  Alcotest.(check (float 0.01)) "implied BTC price"
    100_000.0 implied_btc;
  Alcotest.(check (float 0.01)) "no implied ETH"
    0.0 implied_eth

let test_implied_prices_eth_only () =
  let (implied_btc, implied_eth) = Mnav.calculate_implied_prices
    ~btc_holdings:0 ~eth_holdings:1000
    ~btc_price:50000.0 ~eth_price:2000.0
    ~market_cap:1_500_000.0 ~mnav:0.75 in
  (* implied ETH = 1_500_000 / 1000 = 1_500 *)
  Alcotest.(check (float 0.01)) "no implied BTC"
    0.0 implied_btc;
  Alcotest.(check (float 0.01)) "implied ETH price"
    1_500.0 implied_eth

let test_implied_prices_mixed () =
  let mnav = 1.5 in
  let (implied_btc, implied_eth) = Mnav.calculate_implied_prices
    ~btc_holdings:10 ~eth_holdings:500
    ~btc_price:60000.0 ~eth_price:3000.0
    ~market_cap:3_150_000.0 ~mnav in
  (* Mixed: implied = spot * mNAV *)
  Alcotest.(check (float 0.01)) "implied BTC = spot * mNAV"
    90_000.0 implied_btc;
  Alcotest.(check (float 0.01)) "implied ETH = spot * mNAV"
    4_500.0 implied_eth

let test_implied_prices_no_holdings () =
  let (implied_btc, implied_eth) = Mnav.calculate_implied_prices
    ~btc_holdings:0 ~eth_holdings:0
    ~btc_price:50000.0 ~eth_price:2000.0
    ~market_cap:1_000_000.0 ~mnav:1.0 in
  Alcotest.(check (float 0.01)) "no BTC" 0.0 implied_btc;
  Alcotest.(check (float 0.01)) "no ETH" 0.0 implied_eth

(* ========== Unrealized Gain Tests ========== *)

let test_unrealized_gain_profit () =
  let (gain, gain_pct) = Mnav.unrealized_gain
    ~current_price:60000.0 ~avg_cost:30000.0 ~holdings:100 in
  (* (60000 - 30000) * 100 = 3_000_000 *)
  Alcotest.(check (float 0.01)) "gain amount"
    3_000_000.0 gain;
  (* (60000/30000 - 1) * 100 = 100% *)
  Alcotest.(check (float 0.01)) "gain pct"
    100.0 gain_pct

let test_unrealized_gain_loss () =
  let (gain, gain_pct) = Mnav.unrealized_gain
    ~current_price:2000.0 ~avg_cost:2500.0 ~holdings:1000 in
  (* (2000 - 2500) * 1000 = -500_000 *)
  Alcotest.(check (float 0.01)) "loss amount"
    (-500_000.0) gain;
  (* (2000/2500 - 1) * 100 = -20% *)
  Alcotest.(check (float 0.01)) "loss pct"
    (-20.0) gain_pct

let test_unrealized_gain_zero_cost () =
  let (gain, gain_pct) = Mnav.unrealized_gain
    ~current_price:60000.0 ~avg_cost:0.0 ~holdings:100 in
  Alcotest.(check (float 0.01)) "zero cost => 0 gain" 0.0 gain;
  Alcotest.(check (float 0.01)) "zero cost => 0 pct" 0.0 gain_pct

let test_unrealized_gain_zero_holdings () =
  let (gain, gain_pct) = Mnav.unrealized_gain
    ~current_price:60000.0 ~avg_cost:30000.0 ~holdings:0 in
  Alcotest.(check (float 0.01)) "zero holdings => 0 gain" 0.0 gain;
  Alcotest.(check (float 0.01)) "zero holdings => 0 pct" 0.0 gain_pct

(* ========== Debt-to-NAV Tests ========== *)

let test_debt_to_nav_normal () =
  let ratio = Mnav.debt_to_nav ~total_debt:500_000.0 ~nav:1_000_000.0 in
  Alcotest.(check (float 0.001)) "0.5x leverage"
    0.5 ratio

let test_debt_to_nav_no_debt () =
  let ratio = Mnav.debt_to_nav ~total_debt:0.0 ~nav:1_000_000.0 in
  Alcotest.(check (float 0.001)) "no debt"
    0.0 ratio

let test_debt_to_nav_zero_nav () =
  let ratio = Mnav.debt_to_nav ~total_debt:500_000.0 ~nav:0.0 in
  Alcotest.(check (float 0.001)) "zero NAV => 0"
    0.0 ratio

(* ========== Format Currency Tests ========== *)

let test_format_currency_trillions () =
  let s = Mnav.format_currency 1.5e12 in
  Alcotest.(check string) "$1.50T" "$1.50T" s

let test_format_currency_billions () =
  let s = Mnav.format_currency 29.4e9 in
  Alcotest.(check string) "$29.40B" "$29.40B" s

let test_format_currency_millions () =
  let s = Mnav.format_currency 175.2e6 in
  Alcotest.(check string) "$175.20M" "$175.20M" s

let test_format_currency_small () =
  let s = Mnav.format_currency 12345.67 in
  Alcotest.(check string) "$12345.67" "$12345.67" s

let test_format_currency_custom_decimals () =
  let s = Mnav.format_currency ~decimals:0 1.5e12 in
  Alcotest.(check string) "$2T with 0 decimals" "$2T" s

(* ========== Full Metrics Calculation Tests ========== *)

(** Helper to create a company_data record *)
let make_company ~ticker ~name ~price ~market_cap ~shares ~debt =
  Types.({
    ticker; name; price; market_cap;
    shares_outstanding = shares;
    industry = "Crypto Treasury";
    total_debt = debt;
    total_cash = 0.0;
  })

let test_full_metrics_btc_at_nav () =
  (* A company whose market cap exactly equals its BTC NAV *)
  let company = make_company
    ~ticker:"TEST"
    ~name:"Test Corp"
    ~price:100.0
    ~market_cap:5_000_000.0
    ~shares:50_000.0
    ~debt:0.0 in
  let m = Mnav.calculate_mnav_metrics
    ~company
    ~btc_holdings:100 ~btc_price:50_000.0
    ~eth_holdings:0 ~eth_price:0.0
    ~btc_avg_cost:0.0 ~eth_avg_cost:0.0 in
  (* NAV = 100 * 50000 = 5_000_000 *)
  Alcotest.(check (float 0.01)) "nav" 5_000_000.0 m.nav;
  (* mNAV = 5M / 5M = 1.0 *)
  Alcotest.(check (float 0.001)) "mnav = 1.0" 1.0 m.mnav;
  (* Premium = 0% *)
  Alcotest.(check (float 0.01)) "premium = 0%" 0.0 m.premium_pct;
  (* Signal = Hold (1.0 <= mNAV < 1.2) *)
  Alcotest.(check string) "signal" "Hold" (Types.string_of_signal m.signal);
  (* Holding type = BTC *)
  Alcotest.(check string) "holding type" "BTC"
    (Types.string_of_holding_type m.holding_type);
  (* BTC per share = 100 / 50000 = 0.002 *)
  Alcotest.(check (float 0.0001)) "btc per share" 0.002 m.btc_per_share;
  (* Implied BTC = 5M / 100 = 50000 *)
  Alcotest.(check (float 0.01)) "implied BTC" 50_000.0 m.implied_btc_price;
  (* No debt *)
  Alcotest.(check (float 0.001)) "debt/nav = 0" 0.0 m.debt_to_nav

let test_full_metrics_btc_at_premium () =
  let company = make_company
    ~ticker:"MSTR"
    ~name:"MicroStrategy"
    ~price:200.0
    ~market_cap:10_000_000.0
    ~shares:50_000.0
    ~debt:1_000_000.0 in
  let m = Mnav.calculate_mnav_metrics
    ~company
    ~btc_holdings:100 ~btc_price:50_000.0
    ~eth_holdings:0 ~eth_price:0.0
    ~btc_avg_cost:30_000.0 ~eth_avg_cost:0.0 in
  (* NAV = 5M, market cap = 10M => mNAV = 2.0 *)
  Alcotest.(check (float 0.001)) "mnav = 2.0" 2.0 m.mnav;
  (* Premium = 100% *)
  Alcotest.(check (float 0.01)) "premium = 100%" 100.0 m.premium_pct;
  (* Signal = Overvalued (mNAV >= 1.5) *)
  Alcotest.(check string) "signal" "Overvalued" (Types.string_of_signal m.signal);
  (* Implied BTC = 10M / 100 = 100_000 *)
  Alcotest.(check (float 0.01)) "implied BTC" 100_000.0 m.implied_btc_price;
  (* Unrealized gain: (50000-30000)*100 = 2_000_000 *)
  Alcotest.(check (float 0.01)) "btc unrealized gain" 2_000_000.0 m.btc_unrealized_gain;
  (* Unrealized gain %: (50000/30000 - 1)*100 = 66.67% *)
  Alcotest.(check (float 0.01)) "btc unrealized gain pct"
    66.67 m.btc_unrealized_gain_pct;
  (* Debt/NAV = 1M / 5M = 0.2 *)
  Alcotest.(check (float 0.001)) "debt/nav" 0.2 m.debt_to_nav

let test_full_metrics_eth_at_discount () =
  let company = make_company
    ~ticker:"ETHZ"
    ~name:"ETHZilla"
    ~price:3.0
    ~market_cap:60_000.0
    ~shares:20_000.0
    ~debt:0.0 in
  let m = Mnav.calculate_mnav_metrics
    ~company
    ~btc_holdings:0 ~btc_price:50_000.0
    ~eth_holdings:100 ~eth_price:2_000.0
    ~btc_avg_cost:0.0 ~eth_avg_cost:2_500.0 in
  (* NAV = 100 * 2000 = 200_000 *)
  Alcotest.(check (float 0.01)) "nav" 200_000.0 m.nav;
  (* mNAV = 60_000 / 200_000 = 0.3 *)
  Alcotest.(check (float 0.001)) "mnav = 0.3" 0.3 m.mnav;
  (* Premium = -70% *)
  Alcotest.(check (float 0.01)) "discount = -70%" (-70.0) m.premium_pct;
  (* Signal = Strong Buy (mNAV < 0.8) *)
  Alcotest.(check string) "signal" "Strong Buy" (Types.string_of_signal m.signal);
  (* Holding type = ETH *)
  Alcotest.(check string) "holding type" "ETH"
    (Types.string_of_holding_type m.holding_type);
  (* Implied ETH = 60_000 / 100 = 600 *)
  Alcotest.(check (float 0.01)) "implied ETH" 600.0 m.implied_eth_price;
  (* ETH unrealized loss: (2000-2500)*100 = -50_000 *)
  Alcotest.(check (float 0.01)) "eth unrealized gain" (-50_000.0) m.eth_unrealized_gain;
  (* ETH unrealized loss %: (2000/2500 - 1)*100 = -20% *)
  Alcotest.(check (float 0.01)) "eth unrealized gain pct"
    (-20.0) m.eth_unrealized_gain_pct

let test_full_metrics_mixed_holdings () =
  let company = make_company
    ~ticker:"HIVE"
    ~name:"HIVE Digital"
    ~price:2.0
    ~market_cap:500_000.0
    ~shares:250_000.0
    ~debt:50_000.0 in
  let m = Mnav.calculate_mnav_metrics
    ~company
    ~btc_holdings:2 ~btc_price:60_000.0
    ~eth_holdings:100 ~eth_price:3_000.0
    ~btc_avg_cost:24_000.0 ~eth_avg_cost:1_800.0 in
  (* BTC value = 2 * 60000 = 120_000 *)
  Alcotest.(check (float 0.01)) "btc value" 120_000.0 m.btc_value;
  (* ETH value = 100 * 3000 = 300_000 *)
  Alcotest.(check (float 0.01)) "eth value" 300_000.0 m.eth_value;
  (* NAV = 120_000 + 300_000 = 420_000 *)
  Alcotest.(check (float 0.01)) "nav" 420_000.0 m.nav;
  (* mNAV = 500_000 / 420_000 = 1.190... *)
  let expected_mnav = 500_000.0 /. 420_000.0 in
  Alcotest.(check (float 0.001)) "mnav" expected_mnav m.mnav;
  (* Holding type = Mixed *)
  Alcotest.(check string) "holding type" "Mixed"
    (Types.string_of_holding_type m.holding_type);
  (* Debt/NAV = 50_000 / 420_000 *)
  let expected_dtn = 50_000.0 /. 420_000.0 in
  Alcotest.(check (float 0.001)) "debt/nav" expected_dtn m.debt_to_nav;
  (* Total unrealized gain = BTC gain + ETH gain *)
  (* BTC: (60000-24000)*2 = 72000, ETH: (3000-1800)*100 = 120000 *)
  Alcotest.(check (float 0.01)) "total unrealized gain"
    192_000.0 m.total_unrealized_gain

(* ========== Sort Tests ========== *)

let test_sort_by_mnav () =
  let company1 = make_company ~ticker:"A" ~name:"A" ~price:100.0
    ~market_cap:2_000_000.0 ~shares:10_000.0 ~debt:0.0 in
  let company2 = make_company ~ticker:"B" ~name:"B" ~price:50.0
    ~market_cap:500_000.0 ~shares:10_000.0 ~debt:0.0 in
  let company3 = make_company ~ticker:"C" ~name:"C" ~price:75.0
    ~market_cap:1_000_000.0 ~shares:10_000.0 ~debt:0.0 in
  let m1 = Mnav.calculate_mnav_metrics ~company:company1
    ~btc_holdings:20 ~btc_price:50_000.0
    ~eth_holdings:0 ~eth_price:0.0
    ~btc_avg_cost:0.0 ~eth_avg_cost:0.0 in
  let m2 = Mnav.calculate_mnav_metrics ~company:company2
    ~btc_holdings:20 ~btc_price:50_000.0
    ~eth_holdings:0 ~eth_price:0.0
    ~btc_avg_cost:0.0 ~eth_avg_cost:0.0 in
  let m3 = Mnav.calculate_mnav_metrics ~company:company3
    ~btc_holdings:20 ~btc_price:50_000.0
    ~eth_holdings:0 ~eth_price:0.0
    ~btc_avg_cost:0.0 ~eth_avg_cost:0.0 in
  (* m1: mNAV = 2M/1M = 2.0, m2: mNAV = 0.5M/1M = 0.5, m3: mNAV = 1M/1M = 1.0 *)
  let sorted = Mnav.sort_by_mnav [m1; m2; m3] in
  let tickers = List.map (fun (m : Types.mnav_metrics) -> m.ticker) sorted in
  Alcotest.(check (list string)) "sorted by mNAV ascending"
    ["B"; "C"; "A"] tickers

(* ========== Edge Case Tests ========== *)

let test_metrics_zero_shares () =
  let company = make_company
    ~ticker:"ZERO"
    ~name:"Zero Shares"
    ~price:100.0
    ~market_cap:1_000_000.0
    ~shares:0.0
    ~debt:0.0 in
  let m = Mnav.calculate_mnav_metrics
    ~company
    ~btc_holdings:10 ~btc_price:50_000.0
    ~eth_holdings:0 ~eth_price:0.0
    ~btc_avg_cost:0.0 ~eth_avg_cost:0.0 in
  Alcotest.(check (float 0.001)) "nav per share = 0" 0.0 m.nav_per_share;
  Alcotest.(check (float 0.0001)) "btc per share = 0" 0.0 m.btc_per_share

let test_metrics_large_mnav () =
  (* Tesla-like scenario: huge market cap, small BTC holdings *)
  let company = make_company
    ~ticker:"TSLA"
    ~name:"Tesla"
    ~price:400.0
    ~market_cap:1.5e12
    ~shares:3.75e9
    ~debt:0.0 in
  let m = Mnav.calculate_mnav_metrics
    ~company
    ~btc_holdings:9720 ~btc_price:65_000.0
    ~eth_holdings:0 ~eth_price:0.0
    ~btc_avg_cost:32_000.0 ~eth_avg_cost:0.0 in
  (* NAV = 9720 * 65000 = 631_800_000 *)
  Alcotest.(check (float 1.0)) "nav"
    631_800_000.0 m.nav;
  (* mNAV should be very large *)
  Alcotest.(check bool) "very large mNAV"
    true (m.mnav > 1000.0);
  Alcotest.(check string) "overvalued signal"
    "Overvalued" (Types.string_of_signal m.signal)

(* ========== Test Suite ========== *)

let () =
  Alcotest.run "Crypto Treasury Tests" [
    "types", [
      Alcotest.test_case "Holding type classification" `Quick test_holding_type_of_btc_eth;
      Alcotest.test_case "Holding type strings" `Quick test_string_of_holding_type;
      Alcotest.test_case "Signal strings" `Quick test_string_of_signal;
      Alcotest.test_case "Signal colors" `Quick test_signal_color;
      Alcotest.test_case "Signal of mNAV" `Quick test_signal_of_mnav;
    ];
    "nav_calculation", [
      Alcotest.test_case "NAV BTC only" `Quick test_calculate_nav_btc_only;
      Alcotest.test_case "NAV ETH only" `Quick test_calculate_nav_eth_only;
      Alcotest.test_case "NAV mixed" `Quick test_calculate_nav_mixed;
      Alcotest.test_case "NAV zero holdings" `Quick test_calculate_nav_zero_holdings;
    ];
    "mnav_calculation", [
      Alcotest.test_case "mNAV at NAV" `Quick test_calculate_mnav_at_nav;
      Alcotest.test_case "mNAV premium" `Quick test_calculate_mnav_premium;
      Alcotest.test_case "mNAV discount" `Quick test_calculate_mnav_discount;
      Alcotest.test_case "mNAV zero NAV" `Quick test_calculate_mnav_zero_nav;
    ];
    "premium_discount", [
      Alcotest.test_case "Premium at NAV" `Quick test_premium_pct_at_nav;
      Alcotest.test_case "Premium" `Quick test_premium_pct_premium;
      Alcotest.test_case "Discount" `Quick test_premium_pct_discount;
    ];
    "per_share", [
      Alcotest.test_case "Normal per share" `Quick test_per_share_normal;
      Alcotest.test_case "Zero shares" `Quick test_per_share_zero_shares;
    ];
    "implied_prices", [
      Alcotest.test_case "BTC only implied" `Quick test_implied_prices_btc_only;
      Alcotest.test_case "ETH only implied" `Quick test_implied_prices_eth_only;
      Alcotest.test_case "Mixed implied" `Quick test_implied_prices_mixed;
      Alcotest.test_case "No holdings implied" `Quick test_implied_prices_no_holdings;
    ];
    "unrealized_gain", [
      Alcotest.test_case "Profit" `Quick test_unrealized_gain_profit;
      Alcotest.test_case "Loss" `Quick test_unrealized_gain_loss;
      Alcotest.test_case "Zero cost basis" `Quick test_unrealized_gain_zero_cost;
      Alcotest.test_case "Zero holdings" `Quick test_unrealized_gain_zero_holdings;
    ];
    "debt_to_nav", [
      Alcotest.test_case "Normal leverage" `Quick test_debt_to_nav_normal;
      Alcotest.test_case "No debt" `Quick test_debt_to_nav_no_debt;
      Alcotest.test_case "Zero NAV" `Quick test_debt_to_nav_zero_nav;
    ];
    "format_currency", [
      Alcotest.test_case "Trillions" `Quick test_format_currency_trillions;
      Alcotest.test_case "Billions" `Quick test_format_currency_billions;
      Alcotest.test_case "Millions" `Quick test_format_currency_millions;
      Alcotest.test_case "Small value" `Quick test_format_currency_small;
      Alcotest.test_case "Custom decimals" `Quick test_format_currency_custom_decimals;
    ];
    "full_metrics", [
      Alcotest.test_case "BTC at NAV" `Quick test_full_metrics_btc_at_nav;
      Alcotest.test_case "BTC at premium" `Quick test_full_metrics_btc_at_premium;
      Alcotest.test_case "ETH at discount" `Quick test_full_metrics_eth_at_discount;
      Alcotest.test_case "Mixed holdings" `Quick test_full_metrics_mixed_holdings;
    ];
    "sorting", [
      Alcotest.test_case "Sort by mNAV" `Quick test_sort_by_mnav;
    ];
    "edge_cases", [
      Alcotest.test_case "Zero shares" `Quick test_metrics_zero_shares;
      Alcotest.test_case "Large mNAV (Tesla-like)" `Quick test_metrics_large_mnav;
    ];
  ]
