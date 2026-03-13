"""Portfolio I/O -- ported from OCaml io.ml."""

import json
from pathlib import Path
from typing import Optional

from .types import (
    MarketData,
    PortfolioAnalysis,
    PortfolioPosition,
    PositionAnalysis,
    PositionInfo,
    PositionType,
    PriceLevels,
    Priority,
    ThesisArg,
    TriggeredAlert,
)


# --- JSON Parsing ---


def _parse_position_type(s: str) -> PositionType:
    match s.lower():
        case "long":
            return PositionType.LONG
        case "short":
            return PositionType.SHORT
        case _:
            return PositionType.WATCHING


def _parse_thesis_arg(obj: dict) -> ThesisArg:
    return ThesisArg(
        arg=obj.get("arg", ""),
        weight=int(obj.get("weight", 0)),
    )


def _parse_price_levels(obj: dict) -> PriceLevels:
    return PriceLevels(
        buy_target=obj.get("buy_target"),
        sell_target=obj.get("sell_target"),
        stop_loss=obj.get("stop_loss"),
    )


def _parse_position_info(obj: dict) -> PositionInfo:
    return PositionInfo(
        pos_type=_parse_position_type(obj.get("type", "watching")),
        shares=float(obj.get("shares", 0)),
        avg_cost=float(obj.get("avg_cost", 0)),
    )


def _parse_portfolio_position(obj: dict) -> PortfolioPosition:
    return PortfolioPosition(
        ticker=obj.get("ticker", ""),
        name=obj.get("name", ""),
        position=_parse_position_info(obj.get("position", {})),
        levels=_parse_price_levels(obj.get("levels", {})),
        bull=[_parse_thesis_arg(a) for a in obj.get("bull", [])],
        bear=[_parse_thesis_arg(a) for a in obj.get("bear", [])],
        catalysts=obj.get("catalysts", []),
        notes=obj.get("notes", ""),
    )


def load_portfolio(filepath: Path | str) -> list[PortfolioPosition]:
    with open(filepath) as f:
        data = json.load(f)
    return [_parse_portfolio_position(p) for p in data.get("positions", [])]


def _parse_market_data(obj: dict) -> MarketData:
    return MarketData(
        current_price=float(obj.get("current_price", 0)),
        prev_close=float(obj.get("prev_close", 0)),
        change_1d_pct=float(obj.get("change_1d_pct", 0)),
        change_5d_pct=float(obj.get("change_5d_pct", 0)),
        high_52w=float(obj.get("high_52w", 0)),
        low_52w=float(obj.get("low_52w", 0)),
        fetch_time=obj.get("fetch_time", ""),
    )


def load_market_data(filepath: Path | str) -> dict[str, MarketData]:
    path = Path(filepath)
    if not path.exists():
        return {}
    with open(path) as f:
        data = json.load(f)
    result = {}
    for t in data.get("tickers", []):
        if "error" in t and isinstance(t["error"], str):
            continue
        symbol = t.get("symbol", "")
        if symbol:
            result[symbol] = _parse_market_data(t)
    return result


# --- JSON Output ---


def _alert_to_json(a: TriggeredAlert) -> dict:
    return {
        "ticker": a.ticker,
        "priority": a.priority.value,
        "message": a.message,
    }


def _position_to_json(p: PositionAnalysis) -> dict:
    return {
        "ticker": p.position.ticker,
        "name": p.position.name,
        "position_type": p.position.position.pos_type.value,
        "shares": p.position.position.shares,
        "avg_cost": p.position.position.avg_cost,
        "current_price": p.market.current_price if p.market else None,
        "pnl_pct": p.pnl_pct,
        "pnl_abs": p.pnl_abs,
        "bull_score": p.thesis.bull_score,
        "bear_score": p.thesis.bear_score,
        "net_conviction": p.thesis.net_score,
        "conviction_label": p.thesis.conviction,
        "levels": {
            "buy_target": p.position.levels.buy_target,
            "sell_target": p.position.levels.sell_target,
            "stop_loss": p.position.levels.stop_loss,
        },
        "market": {
            "current_price": p.market.current_price,
            "prev_close": p.market.prev_close,
            "change_1d_pct": p.market.change_1d_pct,
            "change_5d_pct": p.market.change_5d_pct,
            "high_52w": p.market.high_52w,
            "low_52w": p.market.low_52w,
        } if p.market else None,
        "alerts": [_alert_to_json(a) for a in p.alerts],
    }


def save_analysis(analysis: PortfolioAnalysis, filepath: Path | str) -> None:
    obj = {
        "run_time": analysis.run_time,
        "position_count": len(analysis.positions),
        "total_alerts": len(analysis.all_alerts),
        "positions": [_position_to_json(p) for p in analysis.positions],
        "alerts": [_alert_to_json(a) for a in analysis.all_alerts],
    }
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


# --- Console Output ---

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


def print_portfolio_summary(analysis: PortfolioAnalysis) -> None:
    sep = "=" * 70
    print(f"\n{BOLD}{sep}{RESET}")
    print(f"{BOLD}                    PORTFOLIO TRACKER - {analysis.run_time}{RESET}")
    print(f"{BOLD}{sep}{RESET}")

    for pa in analysis.positions:
        _print_position_analysis(pa)

    if analysis.all_alerts:
        print(f"\n{YELLOW}>>> {len(analysis.all_alerts)} TOTAL ALERTS <<<{RESET}")
        for a in analysis.all_alerts:
            print(f"  [{a.priority.value}] {a.ticker}: {a.message}")


def _print_position_analysis(pa: PositionAnalysis) -> None:
    pos = pa.position

    # Header
    price_str = f"${pa.market.current_price:.2f}" if pa.market else "(no data)"
    if pa.pnl_pct is not None:
        color = GREEN if pa.pnl_pct >= 0 else RED
        pnl_str = f" {color}{pa.pnl_pct:+.1f}%{RESET}"
    else:
        pnl_str = ""

    if pos.position.pos_type == PositionType.WATCHING:
        pos_str = "Watching"
    elif pos.position.pos_type == PositionType.LONG:
        pos_str = f"Long {pos.position.shares:.0f} @ ${pos.position.avg_cost:.2f}"
    else:
        pos_str = f"Short {pos.position.shares:.0f} @ ${pos.position.avg_cost:.2f}"

    print(f"\n{BOLD}{pos.ticker}{RESET} - {pos_str} (now {price_str}{pnl_str})")

    # Thesis
    bull_sorted = sorted(pos.bull, key=lambda a: a.weight, reverse=True)
    bear_sorted = sorted(pos.bear, key=lambda a: a.weight, reverse=True)
    print()
    print(f"{GREEN}BULL CASE (score: {pa.thesis.bull_score}){RESET}               {RED}BEAR CASE (score: {pa.thesis.bear_score}){RESET}")
    print("-" * 70)
    for i in range(max(len(bull_sorted), len(bear_sorted))):
        if i < len(bull_sorted):
            a = bull_sorted[i]
            text = a.arg[:27] + "..." if len(a.arg) > 30 else a.arg
            bull_col = f"[{a.weight}] {text}"
        else:
            bull_col = ""
        if i < len(bear_sorted):
            a = bear_sorted[i]
            text = a.arg[:27] + "..." if len(a.arg) > 30 else a.arg
            bear_col = f"[{a.weight}] {text}"
        else:
            bear_col = ""
        print(f"{bull_col:<35} {bear_col}")

    net = pa.thesis.net_score
    color = GREEN if net > 5 else (RED if net < -5 else YELLOW)
    print(f"\nNet Conviction: {color}{net:+d} ({pa.thesis.conviction}){RESET}")

    # Levels
    parts = []
    if pos.levels.buy_target is not None:
        parts.append(f"Buy ${pos.levels.buy_target:.2f}")
    if pos.levels.stop_loss is not None:
        parts.append(f"Stop ${pos.levels.stop_loss:.2f}")
    if pos.levels.sell_target is not None:
        parts.append(f"Target ${pos.levels.sell_target:.2f}")
    if parts:
        print(f"Price Levels: {' | '.join(parts)}")

    # Catalysts
    if pos.catalysts:
        print(f"Catalysts: {', '.join(pos.catalysts)}")

    # Notes
    if pos.notes:
        print(f"Notes: {pos.notes}")

    # Alerts
    if pa.alerts:
        print(f"\n{YELLOW}ALERTS:{RESET}")
        for a in pa.alerts:
            color = RED if a.priority == Priority.URGENT else (
                YELLOW if a.priority == Priority.HIGH else (
                    CYAN if a.priority == Priority.INFO else RESET
                )
            )
            print(f"  {color}[{a.priority.value}] {a.message}{RESET}")

    print("=" * 70)
