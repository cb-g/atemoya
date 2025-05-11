import yfinance as yf
import json
import yaml
import traceback
from pathlib import Path

DATA_DIR = Path("src/valuation/data")
TICKERS_PATH = DATA_DIR / "tickers.yml"
OUTPUT_PATH = DATA_DIR / "valuation_data.json"
PARAMS_FILE = DATA_DIR / "params.yml"
RFR_FILE = DATA_DIR / "risk_free_rates.yml"
ERP_FILE = DATA_DIR / "erp_usd.yml"
BETA_FILE = DATA_DIR / "betas.yml"
INFLATION_FILE = DATA_DIR / "inflation.yml"
TAX_FILE = DATA_DIR / "tax_rates.yml"

def load_yaml(path: Path) -> dict:
    with path.open("r") as f:
        return yaml.safe_load(f)

risk_free_rates = load_yaml(RFR_FILE)
erp_by_country = load_yaml(ERP_FILE)
beta_data_full = load_yaml(BETA_FILE)
params = load_yaml(PARAMS_FILE)
inflation_data = load_yaml(INFLATION_FILE)
tax_rates = load_yaml(TAX_FILE)

# -----------------------------
# helper functions
# -----------------------------

def try_keys(info: dict, keys: list[str]) -> float:
    for key in keys:
        val = info.get(key)
        if val is not None and isinstance(val, (int, float)):
            return float(val)
    raise KeyError(f"None of the keys {keys} found with a usable (non-null) value.")

def extract_from_df(df, keys: list[str], name: str, flip_sign=False) -> float:
    for key in keys:
        if key in df.index:
            val = df.loc[key].dropna()
            if not val.empty:
                raw = float(val.iloc[0])
                if key in ["Other Income Expense", "Other Non Operating Income Expenses"]:
                    print(f"[WARN] Using fallback '{key}' for {name}. This may over- or underestimate true values.")
                return -raw if (flip_sign and raw > 0) else raw
    raise KeyError(f"Could not extract {name} using keys: {keys}")

def extract_from_df_with_fallback(df1, df2, keys: list[str], name: str) -> float:
    for key in keys:
        if key in df1.index:
            val = df1.loc[key].dropna()
            if not val.empty:
                if key == "Tax Effect Of Unusual Items":
                    print(f"[WARN] Using fallback '{key}' for {name}. This may not reflect full income tax expense.")
                return float(val.iloc[0])
    if df2 is not None:
        for key in keys:
            if key in df2.index:
                val = df2.loc[key].dropna()
                if not val.empty:
                    if key == "Tax Effect Of Unusual Items":
                        print(f"[WARN] Using fallback '{key}' for {name}. This may not reflect full income tax expense.")
                    return float(val.iloc[0])
    raise KeyError(f"Could not extract {name} using keys: {keys}")

def extract_current_and_previous_keys(df, keys: list[str], name: str) -> tuple[float, float]:
    for key in keys:
        if key in df.index:
            vals = df.loc[key].dropna()
            if len(vals) >= 2:
                return float(vals.iloc[0]), float(vals.iloc[1])
            elif len(vals) == 1:
                print(f"[WARN] Only one value for '{key}' — assuming Δ{name} = 0")
                return float(vals.iloc[0]), float(vals.iloc[0])
    raise KeyError(f"{name} not found in DataFrame using keys: {keys}")


def get_risk_free_rate(currency: str, country: str, duration: int = 10, ticker: str = None) -> tuple[float, str, bool]:
    data = risk_free_rates.get(currency)
    if not data:
        raise ValueError(f"[rfr] Missing risk-free data for currency '{currency}'")

    country_data = data.get(country)
    country_data_was_fallback = False

    if not country_data:
        fallback = data.get("fallback")
        if not fallback or fallback not in data:
            raise ValueError(f"[rfr] No fallback found for currency '{currency}'")
        country_data = data[fallback]
        country = fallback
        country_data_was_fallback = True

    key = f"{duration}y"
    value = country_data.get(key)
    if value is None:
        print(f"[DEBUG] Available RFR keys for {currency}/{country}: {list(country_data.keys())}")
        raise ValueError(f"[rfr] '{key}' missing or null for {currency}/{country}")

    return value / 100, country, country_data_was_fallback

def get_erp(country: str) -> float:
    if country is None:
        raise ValueError("Country is None — cannot fetch ERP")
    val = erp_by_country.get(country)
    if val is None:
        raise ValueError(f"No ERP value found for country '{country}'")
    return val

def adjust_erp_for_currency(erp_usd: float, source_country: str, target_country: str, year: int = 2025) -> float:
    try:
        infl_us = inflation_data[source_country]["inflation"][year] / 100
        infl_target = inflation_data[target_country]["inflation"][year] / 100
        print(f"[DEBUG] ERP_USD: {erp_usd}, Infl_US: {infl_us}, Infl_{target_country}: {infl_target}")
        adjusted = (1 + erp_usd) * ((1 + infl_target) / (1 + infl_us)) - 1
        return adjusted
    except KeyError as e:
        print(f"[WARN] Inflation data missing for ERP adjustment: {e}")
        return erp_usd

def get_beta(yf_industry: str) -> float:
    mapping = beta_data_full.get("Industry Mapping", {})
    industry_data = beta_data_full.get("Industry Data", {})

    damodaran_industry = None
    for damo_label, aliases in mapping.items():
        if yf_industry in aliases:
            damodaran_industry = damo_label
            break

    if damodaran_industry is None:
        raise ValueError(f"Industry '{yf_industry}' not found in Industry Mapping")

    entry = industry_data.get(damodaran_industry)
    if not entry or "Unlevered Beta" not in entry:
        raise ValueError(f"No Unlevered Beta found for mapped industry '{damodaran_industry}'")

    return entry["Unlevered Beta"]

# -----------------------------
# per-ticker data extraction
# -----------------------------

def fetch_valuation_inputs(ticker: str) -> dict:
    yticker = yf.Ticker(ticker)
    info = yticker.info
    fin = yticker.financials
    income_stmt = yticker.income_stmt
    cashflow = yticker.cashflow
    balance = yticker.balance_sheet

    if fin is None or fin.empty:
        raise ValueError(f"No financials available for {ticker}")

    currency = info.get("currency")
    country = info.get("country")
    industry = info.get("industry")

    if not currency or not country:
        raise ValueError(f"Missing currency or country for ticker: {ticker}")

    rfr, resolved_country, rfr_fallback = get_risk_free_rate(currency, country, ticker=ticker)
    print(f"[INFO] Ticker: {ticker}")
    print(f"[INFO] Currency: {currency}, Country: {country} (RFR resolved as: {resolved_country})")

    if currency != "USD":
        if rfr_fallback:
            print(f"[WARN] No direct RFR data for {country}; using fallback ({resolved_country})")
        print(f"[INFO] Using {currency}-denominated risk-free rate for {ticker}: RFR = {rfr:.4%}")
    else:
        print(f"[INFO] Using USD-denominated risk-free rate for {ticker}: RFR = {rfr:.4%}")

    erp_usd = get_erp(country="United States")  # base USD ERP
    erp = erp_usd  # fallback
    print(f"[INFO] ERP reflects operating risk in {country}")

    # adjust ERP if the valuation is in a non-USD currency
    if currency != "USD":
        try:
            erp = adjust_erp_for_currency(erp_usd, source_country="United States", target_country=country)
            print(f"[INFO] Adjusted ERP for {ticker} ({country}/{currency}): {erp:.4f}")
        except Exception as e:
            print(f"[WARN] Could not adjust ERP for {ticker} — using USD ERP: {erp_usd:.4f}")
    else:
        print(f"[INFO] Using base USD ERP for {ticker} ({country}/{currency}): {erp:.4f}")
    
    beta_u = get_beta(industry)

    ctr = float(tax_rates.get(country, 0.25))
    print(f"[INFO] CTR for {ticker} ({country}): {ctr:.2f}")
    if country not in tax_rates:
        print(f"[WARN] No tax rate entry for {country}. Using default CTR = {ctr:.2f}")

    infl = inflation_data[country]["inflation"][2025] / 100
    raw_tgr = params.get("terminal_growth_rate", {})
    if isinstance(raw_tgr, dict):
        tgr = float(raw_tgr.get(country, raw_tgr.get("default", infl)))
    else:
        tgr = float(raw_tgr)
    
    print(f"[INFO] TGR for {ticker} set to {tgr:.4f} — expected inflation: {infl:.4f}")
    
    h = int(params.get("projection_years", 7))

    mve = try_keys(info, ["marketCap"])
    so = try_keys(info, ["sharesOutstanding"])
    try:
        dp = try_keys(info, ["dividendRate"])
    except KeyError:
        print(f"[INFO] 'dividendRate' missing for {ticker}, defaulting to 0.0")
        dp = 0.0
    mvb = try_keys(info, ["totalDebt", "longTermDebt"])
    total_debt = mvb

    # # compute total book equity (not per-share)
    # book_value_per_share = try_keys(info, ["bookValue", "commonStockEquity"])
    # bve = book_value_per_share * so

    try:
        bve = try_keys(info, ["commonStockEquity"])
    except KeyError:
        bvp = try_keys(info, ["bookValue"])
        bve = bvp * so

    interest_expense = extract_from_df(
        fin,
        ["Interest Expense", "Interest Expense Non Operating", "Net Non Operating Interest Income Expense",
        "Other Income Expense", "Other Non Operating Income Expenses"],  # New fallbacks
        "Interest Expense"
    )

    tdr = mvb / (mvb + mve)

    ni = extract_from_df_with_fallback(
        income_stmt, fin,
        ["Net Income", "Net Income Common Stockholders", "Net Income Applicable to Common Shares", "Consolidated Income"],
        "Net Income"
    )

    dp_total = dp * so
    ic = bve + mvb

    ebit = extract_from_df_with_fallback(
        income_stmt, fin,
        ["EBIT", "Operating Income", "Operating Income Before Depreciation", "Income Before Interest and Taxes"],
        "EBIT"
    )

    ite = extract_from_df_with_fallback(
        fin, income_stmt,
        ["Tax Provision", "Income Tax Expense", "Provision for Income Taxes", "Income Taxes", "Income Tax",
        "Income Tax Expense Benefit", "Current Income Tax Expense",
        "Tax Effect Of Unusual Items"],
        "Income Tax Expense"
    )

    capx = extract_from_df(
        cashflow,
        ["Capital Expenditures", "Capital Expenditure", "Purchase Of Property Plant And Equipment",
         "Investments In Property Plant And Equipment", "Purchase Of Fixed Assets",
         "Additions To Property Plant And Equipment"],
        "Capital Expenditures",
        flip_sign=True
    )

    d = extract_from_df_with_fallback(
        cashflow, fin,
        ["Depreciation", "Depreciation and Amortization", "Depreciation Amortization Depletion"],
        "Depreciation"
    )

    # ca = extract_from_df(
    #     balance,
    #     ["Total Current Assets", "Current Assets", "Total Assets Current"],
    #     "Current Assets"
    # )
    # cl = extract_from_df(
    #     balance,
    #     ["Total Current Liabilities", "Current Liabilities", "Total Liabilities Current"],
    #     "Current Liabilities"
    # )

    ca, prev_ca = extract_current_and_previous_keys(
        balance,
        ["Total Current Assets", "Current Assets", "Total Assets Current"],
        "Current Assets"
    )
    cl, prev_cl = extract_current_and_previous_keys(
        balance,
        ["Total Current Liabilities", "Current Liabilities", "Total Liabilities Current"],
        "Current Liabilities"
    )

    # get current price (fallback to previousClose if needed)
    price = info.get("currentPrice") or info.get("previousClose")
    if price is None:
        raise ValueError("Could not retrieve current stock price")


    infl = inflation_data["United States"]["inflation"][2025] / 100
    infl_target = inflation_data[country]["inflation"][2025] / 100

    return {
        "mve": mve, "mvb": mvb,
        "rfr": rfr, "beta_u": beta_u, "erp": erp,
        "interest_expense": interest_expense, "total_debt": total_debt,
        "ctr": ctr, "tdr": tdr,
        "ni": ni, "bve": bve, "dp": dp_total,
        "ebit": ebit, "ite": ite, "ic": ic,
        "capx": capx, "d": d,
        "ca": ca, "cl": cl,
        "prev_ca": prev_ca, "prev_cl": prev_cl,
        "tgr": tgr, "h": h, "so": so,
        "price": price,
        "country": country,
        "currency": currency,
        "inflation": {
            "valuation_currency": infl,
            "country": infl_target
        }
    }


# -----------------------------
# main runner
# -----------------------------

def main():
    if not TICKERS_PATH.exists():
        print(f"[ERROR] Ticker list file not found: {TICKERS_PATH}")
        return

    with TICKERS_PATH.open() as f:
        config = yaml.safe_load(f)

    tickers = config.get("tickers", [])
    if not isinstance(tickers, list) or not all(isinstance(t, str) for t in tickers):
        print("[ERROR] 'tickers' must be a list of strings.")
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("---------------------------")
    all_data = {}
    for ticker in tickers:
        print(f"[INFO] Fetching data for {ticker}...")
        try:
            data = fetch_valuation_inputs(ticker)
            all_data[ticker] = data
            print(f"[INFO] ✓ {ticker} collected")
        except Exception as e:
            print(f"[ERROR] Failed to fetch {ticker}: {e}")
            traceback.print_exc()
        print("---------------------------")

    with OUTPUT_PATH.open("w") as f:
        json.dump(all_data, f, indent=2)

    print(f"[INFO] All data saved to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
