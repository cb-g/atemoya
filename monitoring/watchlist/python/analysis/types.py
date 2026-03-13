"""Portfolio watchlist types -- ported from OCaml types.ml."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PositionType(Enum):
    LONG = "Long"
    SHORT = "Short"
    WATCHING = "Watching"


@dataclass
class ThesisArg:
    arg: str
    weight: int  # 1-10 scale


@dataclass
class PriceLevels:
    buy_target: Optional[float] = None
    sell_target: Optional[float] = None
    stop_loss: Optional[float] = None


@dataclass
class PositionInfo:
    pos_type: PositionType
    shares: float
    avg_cost: float


@dataclass
class PortfolioPosition:
    ticker: str
    name: str
    position: PositionInfo
    levels: PriceLevels
    bull: list[ThesisArg] = field(default_factory=list)
    bear: list[ThesisArg] = field(default_factory=list)
    catalysts: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class MarketData:
    current_price: float
    prev_close: float
    change_1d_pct: float
    change_5d_pct: float
    high_52w: float
    low_52w: float
    fetch_time: str = ""


@dataclass
class ThesisScore:
    bull_score: int
    bear_score: int
    net_score: int
    conviction: str


class Priority(Enum):
    URGENT = "URGENT"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    INFO = "INFO"


@dataclass
class TriggeredAlert:
    ticker: str
    priority: Priority
    message: str


@dataclass
class PositionAnalysis:
    position: PortfolioPosition
    market: Optional[MarketData]
    thesis: ThesisScore
    pnl_pct: Optional[float]
    pnl_abs: Optional[float]
    alerts: list[TriggeredAlert] = field(default_factory=list)


@dataclass
class PortfolioAnalysis:
    run_time: str
    positions: list[PositionAnalysis]
    total_value: Optional[float]
    total_cost: Optional[float]
    total_pnl_pct: Optional[float]
    all_alerts: list[TriggeredAlert] = field(default_factory=list)
