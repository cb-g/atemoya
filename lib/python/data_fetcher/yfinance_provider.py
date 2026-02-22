"""
Yahoo Finance data provider implementation.

This is the default provider using the yfinance library.
Free, no API key required, but rate-limited and less reliable.
"""

import math
from datetime import datetime
from typing import Optional
import sys

from .base import (
    DataProvider,
    OHLCV,
    TickerInfo,
    OptionChain,
    OptionContract,
    CryptoPrice,
    FinancialStatements,
    ExtendedTickerInfo,
    DividendData,
)

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    yf = None


class YFinanceProvider(DataProvider):
    """Yahoo Finance data provider."""

    @property
    def name(self) -> str:
        return "yfinance"

    def is_available(self) -> bool:
        return YFINANCE_AVAILABLE

    def fetch_ohlcv(
        self,
        ticker: str,
        period: str = "3mo",
        interval: str = "1d"
    ) -> Optional[OHLCV]:
        if not self.is_available():
            return None

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period, interval=interval)

            if hist.empty:
                return None

            return OHLCV(
                dates=[d.strftime("%Y-%m-%d") for d in hist.index],
                open=hist["Open"].tolist(),
                high=hist["High"].tolist(),
                low=hist["Low"].tolist(),
                close=hist["Close"].tolist(),
                volume=hist["Volume"].tolist(),
            )
        except Exception as e:
            print(f"yfinance error fetching {ticker}: {e}", file=sys.stderr)
            return None

    def fetch_ticker_info(self, ticker: str) -> Optional[TickerInfo]:
        if not self.is_available():
            return None

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            price = info.get("currentPrice") or info.get("regularMarketPrice", 0.0)
            market_cap = info.get("marketCap", 0.0)
            shares = info.get("sharesOutstanding", 0.0)

            return TickerInfo(
                ticker=ticker,
                price=float(price) if price else 0.0,
                market_cap=float(market_cap) if market_cap else 0.0,
                shares_outstanding=float(shares) if shares else 0.0,
                currency=info.get("currency", "USD"),
                country=info.get("country", "USA"),
                industry=info.get("industry", "Unknown"),
                total_debt=float(info.get("totalDebt", 0.0) or 0.0),
            )
        except Exception as e:
            print(f"yfinance error fetching info for {ticker}: {e}", file=sys.stderr)
            return None

    def fetch_option_chain(
        self,
        ticker: str,
        expiry: Optional[str] = None
    ) -> Optional[OptionChain]:
        if not self.is_available():
            return None

        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            underlying_price = info.get("currentPrice") or info.get("regularMarketPrice", 0.0)

            expiries = list(stock.options)
            if not expiries:
                return None

            calls = []
            puts = []

            # Fetch specific expiry or first available
            target_expiries = [expiry] if expiry else expiries[:3]  # Limit to 3 expiries

            for exp in target_expiries:
                if exp not in expiries:
                    continue

                opt = stock.option_chain(exp)

                def _safe_int(val, default=0):
                    """Convert to int, handling NaN."""
                    if val is None or (isinstance(val, float) and math.isnan(val)):
                        return default
                    return int(val)

                def _safe_float(val, default=0.0):
                    """Convert to float, handling NaN."""
                    if val is None or (isinstance(val, float) and math.isnan(val)):
                        return default
                    return float(val)

                # Process calls
                for _, row in opt.calls.iterrows():
                    calls.append(OptionContract(
                        strike=float(row["strike"]),
                        expiry=exp,
                        option_type="call",
                        bid=_safe_float(row.get("bid", 0)),
                        ask=_safe_float(row.get("ask", 0)),
                        last=_safe_float(row.get("lastPrice", 0)),
                        volume=_safe_int(row.get("volume", 0)),
                        open_interest=_safe_int(row.get("openInterest", 0)),
                        implied_volatility=_safe_float(row.get("impliedVolatility", 0)),
                    ))

                # Process puts
                for _, row in opt.puts.iterrows():
                    puts.append(OptionContract(
                        strike=float(row["strike"]),
                        expiry=exp,
                        option_type="put",
                        bid=_safe_float(row.get("bid", 0)),
                        ask=_safe_float(row.get("ask", 0)),
                        last=_safe_float(row.get("lastPrice", 0)),
                        volume=_safe_int(row.get("volume", 0)),
                        open_interest=_safe_int(row.get("openInterest", 0)),
                        implied_volatility=_safe_float(row.get("impliedVolatility", 0)),
                    ))

            return OptionChain(
                ticker=ticker,
                underlying_price=float(underlying_price),
                expiries=expiries,
                calls=calls,
                puts=puts,
            )
        except Exception as e:
            print(f"yfinance error fetching options for {ticker}: {e}", file=sys.stderr)
            return None

    def fetch_crypto_price(self, symbol: str) -> Optional[CryptoPrice]:
        if not self.is_available():
            return None

        try:
            # yfinance uses -USD suffix for crypto
            yf_symbol = f"{symbol}-USD"
            crypto = yf.Ticker(yf_symbol)
            info = crypto.info

            price = info.get("regularMarketPrice", 0.0)
            if not price:
                return None

            return CryptoPrice(
                symbol=symbol,
                price_usd=float(price),
                market_cap=float(info.get("marketCap", 0) or 0),
                volume_24h=float(info.get("volume24Hr", 0) or info.get("regularMarketVolume", 0) or 0),
                timestamp=datetime.now().isoformat(),
            )
        except Exception as e:
            print(f"yfinance error fetching crypto {symbol}: {e}", file=sys.stderr)
            return None

    def fetch_multiple_ohlcv(
        self,
        tickers: list[str],
        period: str = "3mo",
        interval: str = "1d"
    ) -> dict[str, OHLCV]:
        """Optimized batch fetch using yfinance download."""
        if not self.is_available():
            return {}

        try:
            # yfinance supports batch downloads
            data = yf.download(
                tickers,
                period=period,
                interval=interval,
                group_by="ticker",
                progress=False,
                auto_adjust=True,
            )

            results = {}

            if len(tickers) == 1:
                # Single ticker - different structure
                ticker = tickers[0]
                if not data.empty:
                    results[ticker] = OHLCV(
                        dates=[d.strftime("%Y-%m-%d") for d in data.index],
                        open=data["Open"].tolist(),
                        high=data["High"].tolist(),
                        low=data["Low"].tolist(),
                        close=data["Close"].tolist(),
                        volume=data["Volume"].tolist(),
                    )
            else:
                # Multiple tickers - grouped by ticker
                for ticker in tickers:
                    try:
                        ticker_data = data[ticker]
                        if not ticker_data.empty:
                            results[ticker] = OHLCV(
                                dates=[d.strftime("%Y-%m-%d") for d in ticker_data.index],
                                open=ticker_data["Open"].tolist(),
                                high=ticker_data["High"].tolist(),
                                low=ticker_data["Low"].tolist(),
                                close=ticker_data["Close"].tolist(),
                                volume=ticker_data["Volume"].tolist(),
                            )
                    except (KeyError, AttributeError):
                        continue

            return results
        except Exception as e:
            print(f"yfinance batch download error: {e}", file=sys.stderr)
            # Fallback to individual fetches
            return super().fetch_multiple_ohlcv(tickers, period, interval)

    def fetch_financial_statements(self, ticker: str) -> Optional[FinancialStatements]:
        """Fetch financial statements from yfinance."""
        if not self.is_available():
            return None

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # Get annual financials
            income_stmt = stock.income_stmt
            balance_sheet = stock.balance_sheet
            cash_flow = stock.cashflow

            if income_stmt.empty:
                return None

            # Helper to safely extract values
            def get_row(df, keys, default=0.0):
                for key in keys if isinstance(keys, list) else [keys]:
                    if key in df.index:
                        values = df.loc[key].tolist()
                        return [float(v) if v == v else 0.0 for v in values]  # NaN check
                return [default] * len(df.columns)

            fiscal_years = [d.strftime("%Y") for d in income_stmt.columns]

            return FinancialStatements(
                ticker=ticker,
                currency=info.get("currency", "USD"),
                revenue=get_row(income_stmt, ["Total Revenue", "Revenue"]),
                operating_income=get_row(income_stmt, ["Operating Income", "EBIT"]),
                net_income=get_row(income_stmt, ["Net Income", "Net Income Common Stockholders"]),
                ebitda=get_row(income_stmt, ["EBITDA", "Normalized EBITDA"]),
                total_assets=get_row(balance_sheet, ["Total Assets"]),
                total_debt=get_row(balance_sheet, ["Total Debt", "Long Term Debt"]),
                cash=get_row(balance_sheet, ["Cash And Cash Equivalents", "Cash"]),
                total_equity=get_row(balance_sheet, ["Total Equity Gross Minority Interest", "Stockholders Equity"]),
                operating_cash_flow=get_row(cash_flow, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]),
                capital_expenditure=get_row(cash_flow, ["Capital Expenditure", "Capital Expenditures"]),
                free_cash_flow=get_row(cash_flow, ["Free Cash Flow"]),
                fiscal_years=fiscal_years,
            )
        except Exception as e:
            print(f"yfinance error fetching financials for {ticker}: {e}", file=sys.stderr)
            return None

    def fetch_extended_info(self, ticker: str) -> Optional[ExtendedTickerInfo]:
        """Fetch extended ticker info with valuation metrics."""
        if not self.is_available():
            return None

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            price = info.get("currentPrice") or info.get("regularMarketPrice", 0.0)

            return ExtendedTickerInfo(
                ticker=ticker,
                price=float(price) if price else 0.0,
                market_cap=float(info.get("marketCap", 0) or 0),
                shares_outstanding=float(info.get("sharesOutstanding", 0) or 0),
                currency=info.get("currency", "USD"),
                country=info.get("country", "USA"),
                industry=info.get("industry", "Unknown"),
                total_debt=float(info.get("totalDebt", 0) or 0),
                # Valuation
                pe_ratio=float(info.get("trailingPE", 0) or 0),
                forward_pe=float(info.get("forwardPE", 0) or 0),
                pb_ratio=float(info.get("priceToBook", 0) or 0),
                ps_ratio=float(info.get("priceToSalesTrailing12Months", 0) or 0),
                ev_ebitda=float(info.get("enterpriseToEbitda", 0) or 0),
                # Growth
                revenue_growth=float(info.get("revenueGrowth", 0) or 0),
                earnings_growth=float(info.get("earningsGrowth", 0) or 0),
                # Profitability
                profit_margin=float(info.get("profitMargins", 0) or 0),
                operating_margin=float(info.get("operatingMargins", 0) or 0),
                roe=float(info.get("returnOnEquity", 0) or 0),
                roa=float(info.get("returnOnAssets", 0) or 0),
                # Other
                beta=float(info.get("beta", 1.0) or 1.0),
                fifty_two_week_high=float(info.get("fiftyTwoWeekHigh", 0) or 0),
                fifty_two_week_low=float(info.get("fiftyTwoWeekLow", 0) or 0),
                average_volume=int(info.get("averageVolume", 0) or 0),
                sector=info.get("sector", "Unknown"),
            )
        except Exception as e:
            print(f"yfinance error fetching extended info for {ticker}: {e}", file=sys.stderr)
            return None

    def fetch_dividends(self, ticker: str) -> Optional[DividendData]:
        """Fetch dividend data and history."""
        if not self.is_available():
            return None

        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            dividends = stock.dividends

            dividend_rate = float(info.get("dividendRate", 0) or 0)
            current_price = float(info.get("currentPrice", 0) or info.get("regularMarketPrice", 0) or 0)

            # Calculate dividend yield - prefer rate/price calculation when available
            # Fall back to yfinance's dividendYield (which may need normalization)
            if dividend_rate > 0 and current_price > 0:
                dividend_yield = dividend_rate / current_price
            else:
                # For ETFs like SPY, dividendRate is often None but dividendYield is set
                raw_yield = float(info.get("dividendYield", 0) or 0)
                # Normalize: yfinance sometimes returns 1.07 meaning 1.07% (should be 0.0107)
                # If yield seems like a percentage (> 0.20), divide by 100
                if raw_yield > 0.20:
                    dividend_yield = raw_yield / 100.0
                else:
                    dividend_yield = raw_yield

            if dividend_yield == 0:
                # No dividends
                return DividendData(
                    ticker=ticker,
                    dividend_yield=0.0,
                    annual_dividend=0.0,
                    payout_ratio=0.0,
                    dividend_growth_5y=0.0,
                    ex_dividend_date=None,
                    dividend_history=[],
                )

            # Build dividend history
            history = []
            if not dividends.empty:
                for date, amount in dividends.items():
                    history.append((date.strftime("%Y-%m-%d"), float(amount)))

            # Calculate 5-year growth if enough history
            growth_5y = 0.0
            if len(history) >= 20:  # Roughly 5 years of quarterly dividends
                old_annual = sum(h[1] for h in history[-20:-16])
                new_annual = sum(h[1] for h in history[-4:])
                if old_annual > 0:
                    growth_5y = (new_annual / old_annual) ** 0.2 - 1

            return DividendData(
                ticker=ticker,
                dividend_yield=dividend_yield,
                annual_dividend=float(info.get("dividendRate", 0) or 0),
                payout_ratio=float(info.get("payoutRatio", 0) or 0),
                dividend_growth_5y=growth_5y,
                ex_dividend_date=info.get("exDividendDate"),
                dividend_history=history[-20:],  # Last 20 payments
            )
        except Exception as e:
            print(f"yfinance error fetching dividends for {ticker}: {e}", file=sys.stderr)
            return None
