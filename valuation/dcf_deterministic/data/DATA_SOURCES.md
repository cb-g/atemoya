# Data Sources - DCF Valuation Configuration

This document tracks the sources for all configuration data used in the DCF valuation models.

**Last Updated:** 2025-12-27

---

## Risk-Free Rates (`risk_free_rates.json`)

Government bond yields by country. These represent the risk-free rate of return for each country's sovereign debt.

### United States (USA)
- **Source:** U.S. Department of Treasury
- **URL:** https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value_month=202512
- **Rates Used:** 1y, 3y, 5y, 7y, 10y Treasury yields
- **Current Values:** 4.30%, 4.10%, 4.05%, 4.15%, 4.25%
- **Update Frequency:** Daily (use monthly average)
- **Notes:** Most liquid sovereign bond market globally

### Canada
- **Source:** Bank of Canada - Government of Canada Bond Yields
- **URL:** https://www.bankofcanada.ca/rates/interest-rates/canadian-bonds/
- **Alternative:** https://www.canada.ca/en/department-finance/services/bonds-treasury-bills.html
- **Rates Used:** 1y, 3y, 5y, 7y, 10y Government of Canada bonds
- **Current Values:** 4.20%, 3.95%, 3.80%, 3.85%, 3.95%
- **Update Frequency:** Daily
- **Notes:** AAA-rated sovereign, typically 25-50 bps below US Treasuries

### Germany
- **Source:** Deutsche Bundesbank
- **URL:** https://www.bundesbank.de/en/statistics/money-and-capital-markets/interest-rates-and-yields/daily-yields-of-current-federal-securities-772220
- **Rates Used:** 1y, 3y, 5y, 7y, 10y Bunds
- **Current Values:** 2.50%, 2.30%, 2.20%, 2.25%, 2.35%
- **Update Frequency:** Daily
- **Notes:** EUR benchmark, AAA-rated

### United Kingdom
- **Source:** UK Debt Management Office (DMO)
- **URL:** https://www.dmo.gov.uk/data/ExportReport?reportCode=D4H
- **Rates Used:** 1y, 3y, 5y, 7y, 10y Gilts
- **Current Values:** 4.20%, 3.90%, 3.80%, 3.85%, 3.95%
- **Update Frequency:** Daily
- **Notes:** GBP sovereign debt

### Japan
- **Source:** Japan Ministry of Finance / Bank of Japan
- **URL:** https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/index.htm
- **Rates Used:** 1y, 3y, 5y, 7y, 10y JGBs
- **Current Values:** 0.50%, 0.40%, 0.45%, 0.50%, 0.60%
- **Update Frequency:** Daily
- **Notes:** Extremely low rates due to BOJ yield curve control

### China
- **Source:** ChinaBond - China Central Depository & Clearing Co.
- **URL:** https://yield.chinabond.com.cn/cbweb-czb-web/czb/moreInfo?locale=en_US&nameType=1
- **Rates Used:** 1y, 3y, 5y, 7y, 10y Government bonds
- **Current Values:** 2.00%, 2.20%, 2.40%, 2.50%, 2.60%
- **Update Frequency:** Daily
- **Notes:** CNY sovereign debt

### India
- **Source:** Reserve Bank of India / World Government Bonds
- **URL:** https://www.worldgovernmentbonds.com/country/india/
- **Alternative:** https://www.rbi.org.in/Scripts/BS_ViewBulletin.aspx
- **Rates Used:** 1y, 3y, 5y, 7y, 10y Government of India bonds
- **Current Values:** 6.80%, 6.70%, 6.65%, 6.70%, 6.80%
- **Update Frequency:** Daily
- **Notes:** Higher rates reflect emerging market premium

### Singapore
- **Source:** Monetary Authority of Singapore (MAS) / Singapore Government Securities
- **URL:** https://www.mas.gov.sg/bonds-and-bills/auctions-and-issuance-calendar
- **Alternative:** https://www.worldgovernmentbonds.com/country/singapore/
- **Rates Used:** 1y, 3y, 5y, 7y, 10y Singapore Government Securities (SGS)
- **Current Values:** 3.10%, 2.90%, 2.80%, 2.85%, 2.95%
- **Update Frequency:** Daily
- **Notes:** AAA-rated sovereign, very liquid market

### Netherlands
- **Source:** Dutch State Treasury Agency (DSTA) / European Central Bank
- **URL:** https://www.dsta.nl/english/subjects/issuance/yield-curves
- **Alternative:** https://www.worldgovernmentbonds.com/country/netherlands/
- **Rates Used:** 1y, 3y, 5y, 7y, 10y Dutch Government Bonds (DSL)
- **Current Values:** 2.55%, 2.35%, 2.25%, 2.30%, 2.40%
- **Update Frequency:** Daily
- **Notes:** AAA-rated Eurozone member, very liquid

### France
- **Source:** Agence France Trésor (AFT) / European Central Bank
- **URL:** https://www.aft.gouv.fr/en/french-government-bond-yield-curves
- **Alternative:** https://www.worldgovernmentbonds.com/country/france/
- **Rates Used:** 1y, 3y, 5y, 7y, 10y OAT (Obligations Assimilables du Trésor)
- **Current Values:** 2.60%, 2.40%, 2.30%, 2.35%, 2.45%
- **Update Frequency:** Daily
- **Notes:** AA-rated Eurozone member, highly liquid

### Switzerland
- **Source:** Swiss National Bank (SNB) / Swiss Federal Finance Administration
- **URL:** https://www.snb.ch/en/the-snb/mandates-goals/statistics/statpub
- **Alternative:** https://www.worldgovernmentbonds.com/country/switzerland/
- **Rates Used:** 1y, 3y, 5y, 7y, 10y Swiss Confederation bonds
- **Current Values:** 0.95%, 0.80%, 0.75%, 0.80%, 0.90%
- **Update Frequency:** Daily
- **Notes:** AAA-rated, safe haven currency, negative/very low yields

### Taiwan
- **Source:** Central Bank of the Republic of China (Taiwan) / Bloomberg
- **URL:** https://www.cbc.gov.tw/en/lp-645-2.html
- **Alternative:** https://www.worldgovernmentbonds.com/country/taiwan/
- **Rates Used:** 1y, 3y, 5y, 7y, 10y Taiwan Government Bonds
- **Current Values:** 1.55%, 1.45%, 1.40%, 1.45%, 1.55%
- **Update Frequency:** Daily
- **Notes:** Developed Asian market, tech manufacturing hub

### South Korea
- **Source:** Korea Treasury Bond Market / Bloomberg
- **URL:** http://www.index.go.kr/eng/potal/main/EachDtlPageDetail.do?idx_cd=2743
- **Alternative:** https://www.worldgovernmentbonds.com/country/south-korea/
- **Rates Used:** 1y, 3y, 5y, 7y, 10y Korea Treasury Bonds (KTB)
- **Current Values:** 3.40%, 3.20%, 3.10%, 3.15%, 3.25%
- **Update Frequency:** Daily
- **Notes:** Developed Asian market, AA-rated

### Australia
- **Source:** Reserve Bank of Australia / Australian Office of Financial Management
- **URL:** https://www.rba.gov.au/statistics/frequency/interest-rates/
- **Alternative:** https://www.worldgovernmentbonds.com/country/australia/
- **Rates Used:** 1y, 3y, 5y, 7y, 10y Australian Government Bonds (ACGB)
- **Current Values:** 4.25%, 4.05%, 3.95%, 4.00%, 4.10%
- **Update Frequency:** Daily
- **Notes:** AAA-rated, commodity-linked economy

### Italy
- **Source:** Italian Treasury (MEF) / European Central Bank
- **URL:** http://www.dt.mef.gov.it/en/debito_pubblico/dati_statistici/
- **Alternative:** https://www.worldgovernmentbonds.com/country/italy/
- **Rates Used:** 1y, 3y, 5y, 7y, 10y BTP (Buoni del Tesoro Poliennali)
- **Current Values:** 3.15%, 2.95%, 2.85%, 2.90%, 3.00%
- **Update Frequency:** Daily
- **Notes:** Eurozone member, higher spreads due to fiscal concerns

### Spain
- **Source:** Spanish Treasury (Tesoro Público) / European Central Bank
- **URL:** https://www.tesoro.es/en
- **Alternative:** https://www.worldgovernmentbonds.com/country/spain/
- **Rates Used:** 1y, 3y, 5y, 7y, 10y Bonos/Obligaciones del Estado
- **Current Values:** 3.00%, 2.80%, 2.70%, 2.75%, 2.85%
- **Update Frequency:** Daily
- **Notes:** Eurozone member, A-rated

### Hong Kong
- **Source:** Hong Kong Monetary Authority (HKMA)
- **URL:** https://www.hkma.gov.hk/eng/data-publications-and-research/data-and-statistics/monthly-statistical-bulletin/
- **Alternative:** https://www.worldgovernmentbonds.com/country/hong-kong/
- **Rates Used:** 1y, 3y, 5y, 7y, 10y Hong Kong Exchange Fund Notes/Bonds
- **Current Values:** 4.45%, 4.25%, 4.15%, 4.20%, 4.30%
- **Update Frequency:** Daily
- **Notes:** Pegged to USD, rates closely track US Treasuries

### British Virgin Islands
- **Source:** Uses US Treasury rates (proxy)
- **URL:** https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve
- **Rates Used:** 1y, 3y, 5y, 7y, 10y (same as USA)
- **Current Values:** 4.30%, 4.10%, 4.05%, 4.15%, 4.25%
- **Update Frequency:** Daily
- **Notes:** Offshore incorporation jurisdiction, uses USD, no sovereign bonds of its own. Companies incorporated in BVI typically operate globally. Uses US Treasuries as risk-free rate proxy.

---

## Equity Risk Premiums (`equity_risk_premiums.json`)

Expected return of equity markets above the risk-free rate. Based on historical equity returns and forward-looking models.

### Primary Source: Aswath Damodaran (NYU Stern)
- **URL:** https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html
- **Data:** Country-specific equity risk premiums updated annually
- **Methodology:** Total equity risk premium (equity return - RFR)
- **Update Frequency:** Annually (January)
- **Last Updated:** January 9, 2025
- **Note:** ERP is currency-specific. The values reflect USD-based ERP.

### Current Values (as of 2024-2025):
- **United States:** 4.33% (mature market baseline)
- **Switzerland:** 4.30% (AAA safe haven, very low risk)
- **United Kingdom:** 4.40% (Brexit uncertainty premium)
- **Canada:** 4.50% (similar to US with small premium)
- **British Virgin Islands:** 4.50% (offshore jurisdiction, uses US proxy + small premium)
- **Singapore:** 4.80% (developed Asian market)
- **Australia:** 5.20% (developed, commodity-linked)
- **Hong Kong:** 5.20% (developed, USD-pegged)
- **Germany:** 5.50% (EU risk premium)
- **France:** 5.40% (Eurozone, AA-rated)
- **Netherlands:** 5.40% (Eurozone, AAA-rated)
- **Taiwan:** 5.50% (developed Asian, geopolitical risk)
- **South Korea:** 5.80% (developed Asian, higher volatility)
- **Spain:** 6.00% (Eurozone peripheral, fiscal concerns)
- **Japan:** 6.10% (low growth, demographics, high debt)
- **Italy:** 6.20% (Eurozone peripheral, fiscal challenges)
- **China:** 7.20% (emerging market, political risk)
- **India:** 8.20% (emerging market, high growth)
- **Brazil:** 9.50% (emerging market, high volatility)

### Notes:
- Mature markets (US, Canada, UK): 4.0-5.0%
- Developed Europe (Germany): 5.0-6.0%
- Emerging Asia (China, India): 6.5-8.0%

---

## Industry Betas (`industry_betas.json`)

Unlevered betas by industry sector. Used to calculate leveraged beta for individual companies.

### Source: Aswath Damodaran (NYU Stern)
- **URL:** http://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/Betas.html
- **Data:** Unlevered betas by industry (regression vs. market)
- **Methodology:**
  - Bottom-up beta calculation
  - Average of publicly traded firms in each industry
  - Unlevered using average D/E ratio for industry
- **Update Frequency:** Annually (January)
- **Coverage:** ~90+ industries

### Sample Industries:
- **Technology (Software):** 1.20
- **Utilities (Electric):** 0.50
- **Healthcare (Biotech):** 1.35
- **Financial Services (Banks):** 0.80
- **Consumer (Retail):** 1.00
- **Energy (Oil & Gas):** 1.15

### Notes:
- Unlevered betas are re-levered using company-specific D/E ratio
- Use Hamada formula: β_L = β_U × [1 + (1-T) × D/E]
- Fallback beta = 1.0 (market beta) for unknown industries

---

## Tax Rates (`tax_rates.json`)

Corporate income tax rates by country. Used for NOPAT calculation and unlevering/relevering betas.

### Source: OECD Tax Database & PwC Worldwide Tax Summaries
- **OECD URL:** https://www.oecd.org/tax/tax-policy/tax-database/
- **PwC URL:** https://taxsummaries.pwc.com/
- **KPMG URL:** https://home.kpmg/xx/en/home/services/tax/tax-tools-and-resources/tax-rates-online.html
- **Data:** Statutory corporate tax rates (combined federal + regional where applicable)
- **Update Frequency:** Annually (when tax law changes)
- **Coverage:** 50+ countries including all major economies

### Current Values (2025):
- **British Virgin Islands:** 0.0% (tax haven, no corporate tax)
- **Ireland:** 12.5% (attracts multinationals)
- **Hong Kong:** 16.5% (two-tier rate, low by global standards)
- **Singapore:** 17.0% (flat corporate tax rate)
- **United Kingdom:** 19.0% (one of lowest in G7)
- **Taiwan:** 20.0% (standard corporate rate)
- **United States:** 21.0% (federal, excludes state taxes)
- **Switzerland:** 21.0% (varies by canton, average)
- **Italy:** 24.0% (IRES corporate tax)
- **France:** 25.0% (standard rate for large companies)
- **China:** 25.0% (standard rate)
- **Netherlands:** 25.0% (standard rate)
- **Spain:** 25.0% (standard rate)
- **South Korea:** 25.0% (national rate, excludes local)
- **Canada:** 26.0% (combined federal 15% + provincial ~11%)
- **India:** 30.0% (for existing companies, 22% for new manufacturing)
- **Germany:** 30.0% (corporate + solidarity surcharge + trade tax)
- **Japan:** 30.0% (combined national + local)
- **Australia:** 30.0% (standard corporate rate)
- **Brazil:** 34.0% (combined federal + social contribution)

### Notes:
- Rates reflect combined federal + regional taxes where applicable
- Does not include deductions, credits, or effective tax rates
- Use statutory rate for DCF consistency
- Some industries have special rates (e.g., US REIT = 0%)

---

## Terminal Growth Rates (in `params.json`)

Long-term nominal GDP growth rates by country. Used as terminal growth rate in DCF models.

### Source: IMF World Economic Outlook (WEO) & Central Bank Projections
- **IMF WEO URL:** https://www.imf.org/en/Publications/WEO
- **Data:** Long-term GDP growth projections (nominal)
- **Methodology:** Combination of IMF projections and central bank inflation targets
- **Update Frequency:** Semi-annually (April and October WEO releases)

### Current Values (2025):
- **Japan:** 1.0% (BOJ inflation target 2%, low real growth, aging)
- **Italy:** 1.2% (ECB target 2%, structural challenges)
- **Switzerland:** 1.3% (SNB target ~2%, mature economy)
- **Germany:** 1.5% (ECB inflation target 2%, aging demographics)
- **France:** 1.5% (ECB inflation target 2%, Eurozone member)
- **Netherlands:** 1.5% (ECB inflation target 2%, Eurozone member)
- **United Kingdom:** 1.7% (BOE inflation target 2%)
- **Spain:** 1.8% (ECB target 2%, recovering growth)
- **Canada:** 1.8% (inflation target 2%, slightly lower real growth)
- **United States:** 2.0% (inflation target ~2%, real growth ~0%)
- **British Virgin Islands:** 2.0% (uses US proxy, offshore jurisdiction)
- **Australia:** 2.2% (RBA target 2-3%, commodity economy)
- **Singapore:** 2.5% (MAS inflation target ~2%, moderate real growth)
- **Hong Kong:** 2.5% (follows US Fed, moderate growth)
- **Taiwan:** 2.8% (moderate inflation + real growth)
- **South Korea:** 3.0% (developed but higher growth potential)
- **Brazil:** 3.5% (emerging market, moderating from high growth)
- **India:** 4.0% (inflation target ~4%, high real growth)
- **China:** 4.5% (higher inflation + real growth, moderating)

### Notes:
- Terminal growth should not exceed long-term nominal GDP growth
- Emerging markets typically have higher terminal growth (3-5%)
- Mature markets typically have lower terminal growth (1.5-2.5%)
- Formula: Terminal Growth ≈ Long-term Inflation + Long-term Real GDP Growth

---

## Inflation Rates (Optional - Not Currently Used)

Forward-looking inflation projections by country. Can be used for inflation-adjusted (real) DCF valuations.

### Source: IMF World Economic Outlook Database
- **URL:** https://www.imf.org/en/Publications/WEO/weo-database/2024/April/download-entire-database
- **Indicator:** PCPIPCH - Inflation, average consumer prices (annual %)
- **Data:** Year-on-year percentage change in average consumer prices
- **Update Frequency:** Semi-annually (April and October)
- **Last Updated:** April 2024
- **Coverage:** 5-year forward projections (2024-2029)

### Sample Inflation Projections (2025-2029 avg):
- **United States:** ~2.1% (Fed target)
- **Canada:** ~1.9% (BOC target)
- **Germany:** ~2.0% (ECB target)
- **United Kingdom:** ~2.0% (BOE target)
- **Japan:** ~2.0% (BOJ target, recently achieved)
- **China:** ~2.0% (PBOC target)
- **India:** ~4.1% (RBI tolerance band upper limit)

### Notes:
- **Not currently used** - Our DCF models use nominal cash flows and nominal discount rates
- If implementing real DCF: use inflation to convert nominal to real
- Formula: Real Rate = (1 + Nominal Rate) / (1 + Inflation Rate) - 1
- Inflation data useful for sanity-checking terminal growth assumptions

---

## Update Schedule

### Quarterly Updates (Recommended):
- **Risk-Free Rates:** Check monthly, update if sustained change >25 bps
- **Equity Risk Premiums:** Review quarterly, update annually
- **Industry Betas:** Update annually (typically January)
- **Tax Rates:** Update as laws change (ad-hoc)

### Annual Review (Required):
- January: Full refresh of all parameters
- Validate against Damodaran's annual data release
- Check for major policy changes (central bank, tax law)

### Event-Driven Updates:
- Central bank policy regime change (e.g., QE → QT)
- Major tax reform legislation
- Sovereign debt crises or downgrades

---

## Data Quality Notes

### Risk-Free Rates:
- Use mid-market yields (not bid/ask)
- Use constant maturity yields (interpolated if needed)
- Prefer on-the-run securities (most liquid)
- For missing maturities, use linear interpolation

### Equity Risk Premiums:
- Historical US ERP: ~4-5% (1926-2024 arithmetic mean)
- Forward-looking models may give lower estimates (3-4%)
- Damodaran uses implied ERP from current index valuations
- Emerging markets: Add country risk premium to mature market ERP

### Industry Betas:
- Global average betas (not country-specific)
- US-centric (most data from US public companies)
- May need adjustment for international differences
- Technology sector betas have increased over time (network effects)

### Tax Rates:
- Use statutory rate, not effective rate (consistency)
- Effective rates can vary widely due to deductions
- Multi-national companies: use headquarters country rate
- Banks/REITs: may have special tax treatment

---

## Alternative Data Sources

If primary sources are unavailable:

### Risk-Free Rates:
- **Bloomberg:** USGG10YR, GDBR10, etc.
- **FRED (St. Louis Fed):** https://fred.stlouisfed.org/
- **Investing.com:** https://www.investing.com/rates-bonds/

### Equity Risk Premiums:
- **Credit Suisse Global Investment Returns Yearbook**
- **Ibbotson SBBI Yearbook**
- **Pablo Fernandez (IESE):** ERP surveys

### Industry Betas:
- **Bloomberg:** Industry betas by sector
- **S&P Capital IQ**
- **Local regression:** Calculate from peer companies

### Tax Rates:
- **KPMG Corporate Tax Tables:** https://home.kpmg/xx/en/home/services/tax/tax-tools-and-resources/tax-rates-online.html
- **Deloitte Tax Guides**
- **EY Worldwide Corporate Tax Guide**

---

## Methodology Notes

### How We Use Risk-Free Rates:
1. Load country-specific yield curve
2. Select maturity matching DCF projection horizon (default: 7-year)
3. Use as base for CAPM cost of equity calculation
4. Formula: CE = RFR + β × ERP

### How We Use Equity Risk Premiums:
1. Country-level ERP from Damodaran
2. No industry-specific adjustment (beta captures that)
3. Mature market baseline: ~4-5%
4. Emerging market: baseline + country risk premium

### How We Use Industry Betas:
1. Look up unlevered beta for company's industry
2. Relever using company's actual D/E ratio
3. Formula: β_L = β_U × [1 + (1-T) × D/E]
4. Use relevered beta in CAPM

### How We Use Tax Rates:
1. Calculate NOPAT: EBIT × (1 - T)
2. Tax shield on debt: Interest × T
3. Unlever/relever betas: (1-T) term in Hamada
4. WACC calculation: After-tax cost of debt

---

## Data Validation Checklist

Before using any configuration data:

- [ ] Source URL is accessible and current
- [ ] Data is from authoritative source (central bank, government, academic)
- [ ] Last updated date is within acceptable range (<1 year for rates)
- [ ] Values are reasonable (sanity check vs. historical ranges)
- [ ] Units are correct (decimal vs. percentage, e.g., 0.0425 = 4.25%)
- [ ] Country/industry names match yfinance conventions
- [ ] All required maturities/industries are present
- [ ] No missing or null values in critical fields

---

## Contributing Updates

When updating configuration data:

1. **Verify source:** Check URL is still valid and authoritative
2. **Document changes:** Update `last_updated` field and this file
3. **Validate values:** Ensure reasonableness (no typos like 42.5% instead of 4.25%)
4. **Test impact:** Run sample valuations to check for anomalies
5. **Commit atomically:** Update data + documentation together
6. **Add comment:** Explain reason for update (e.g., "Updated for BOC rate cut Dec 2024")

---

## Disclaimers

- **Data Accuracy:** We make best efforts to use authoritative sources, but cannot guarantee accuracy
- **Timeliness:** Configuration data may lag market changes by days or weeks
- **Simplifications:** Statutory tax rates may not reflect effective rates; betas are averages
- **Model Risk:** DCF valuations are sensitive to these inputs; verify independently for real capital allocation
- **Not Investment Advice:** This data is for educational and analytical purposes only

---

## Further Reading

- **Damodaran Online:** http://pages.stern.nyu.edu/~adamodar/ (comprehensive valuation data)
- **Damodaran's "Investment Valuation"** (3rd ed.) - Chapters on risk-free rates, ERP, and beta
- **OECD Tax Database:** https://www.oecd.org/tax/tax-policy/tax-database/
- **FRED Economic Data:** https://fred.stlouisfed.org/ (US Treasury yields)
- **BIS Statistics:** https://www.bis.org/statistics/ (international bond yields)

---

**Maintained by:** Atemoya Development Team
**Questions/Issues:** File an issue or submit a pull request with updated data
