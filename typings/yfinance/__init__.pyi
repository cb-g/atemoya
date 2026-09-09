"""Minimal stub for the yfinance surface fetch.py uses; yfinance ships no types.

Keep this to what is actually called. Adding a member here is the moment to
re-verify its behaviour against the installed version (CLAUDE.md, yfinance
landmines)."""

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
