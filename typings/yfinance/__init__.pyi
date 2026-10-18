"""Minimal stub for the yfinance surface fetch.py uses; yfinance ships no types.

Keep this to what is actually called. Adding a member here is the moment to
re-verify its behaviour against the installed version: prices are split-adjusted
even with auto_adjust=False (that flag disables only the dividend adjustment), and
.info returns empty fields rather than erroring under concurrent load, so nothing
here may route or select on it alone. Confirmed on yfinance 1.7.0 for the split
behaviour; re-verify the rest before relying on it."""

import pandas as pd

__version__: str

class Ticker:
    def __init__(self, ticker: str) -> None: ...
    @property
    def info(self) -> dict[str, object]: ...
    @property
    def income_stmt(self) -> pd.DataFrame: ...
    @property
    def balance_sheet(self) -> pd.DataFrame: ...
    @property
    def cashflow(self) -> pd.DataFrame: ...
    def history(self, *, start: str | None = ..., end: str | None = ..., auto_adjust: bool = ...) -> pd.DataFrame: ...
    @property
    def splits(self) -> pd.Series: ...
