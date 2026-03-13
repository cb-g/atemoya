"""Portfolio analysis functions -- ported from OCaml analysis.ml."""

from datetime import datetime, timezone

from .types import (
    MarketData,
    PortfolioAnalysis,
    PortfolioPosition,
    PositionAnalysis,
    PositionType,
    Priority,
    ThesisArg,
    ThesisScore,
    TriggeredAlert,
)


def alert_to_string(kind: str, **kw) -> str:
    """Format alert message strings matching OCaml io.ml alert_to_string exactly."""
    if kind == "hit_buy_target":
        return f"Hit buy target! ${kw['current']:.2f} (target was ${kw['target']:.2f})"
    elif kind == "hit_sell_target":
        return f"Hit sell target! ${kw['current']:.2f} (target was ${kw['target']:.2f})"
    elif kind == "hit_stop_loss":
        return f"STOP LOSS TRIGGERED! ${kw['current']:.2f} (stop was ${kw['stop']:.2f})"
    elif kind == "near_buy_target":
        return f"Approaching buy target: ${kw['current']:.2f} (target ${kw['target']:.2f})"
    elif kind == "near_stop_loss":
        return f"WARNING: Near stop loss! ${kw['current']:.2f} (stop ${kw['stop']:.2f})"
    elif kind == "above_cost_basis":
        return f"Up {kw['pct']:.1f}% from cost basis (${kw['cost']:.2f} -> ${kw['current']:.2f})"
    elif kind == "below_cost_basis":
        return f"Down {abs(kw['pct']):.1f}% from cost basis (${kw['cost']:.2f} -> ${kw['current']:.2f})"
    return ""


def calculate_thesis_score(bull: list[ThesisArg], bear: list[ThesisArg]) -> ThesisScore:
    bull_score = sum(a.weight for a in bull)
    bear_score = sum(a.weight for a in bear)
    net = bull_score - bear_score

    if net > 10:
        conviction = "strong bull"
    elif net > 5:
        conviction = "moderately bullish"
    elif net > 0:
        conviction = "slightly bullish"
    elif net == 0:
        conviction = "neutral"
    elif net > -5:
        conviction = "slightly bearish"
    elif net > -10:
        conviction = "moderately bearish"
    else:
        conviction = "strong bear"

    return ThesisScore(
        bull_score=bull_score,
        bear_score=bear_score,
        net_score=net,
        conviction=conviction,
    )


def check_price_alerts(
    pos: PortfolioPosition, market: MarketData | None
) -> list[TriggeredAlert]:
    if market is None:
        return []

    alerts: list[TriggeredAlert] = []
    price = market.current_price
    cost = pos.position.avg_cost
    is_short = pos.position.pos_type == PositionType.SHORT

    # Stop loss
    stop = pos.levels.stop_loss
    if stop is not None:
        if (not is_short and price <= stop) or (is_short and price >= stop):
            alerts.append(TriggeredAlert(
                ticker=pos.ticker,
                priority=Priority.URGENT,
                message=alert_to_string("hit_stop_loss", current=price, stop=stop),
            ))
        elif (not is_short and price <= stop * 1.05) or (is_short and price >= stop * 0.95):
            alerts.append(TriggeredAlert(
                ticker=pos.ticker,
                priority=Priority.HIGH,
                message=alert_to_string("near_stop_loss", current=price, stop=stop),
            ))

    # Buy target (longs and watching only)
    if not is_short:
        target = pos.levels.buy_target
        if target is not None:
            if price <= target:
                alerts.append(TriggeredAlert(
                    ticker=pos.ticker,
                    priority=Priority.HIGH,
                    message=alert_to_string("hit_buy_target", current=price, target=target),
                ))
            elif price <= target * 1.05:
                alerts.append(TriggeredAlert(
                    ticker=pos.ticker,
                    priority=Priority.NORMAL,
                    message=alert_to_string("near_buy_target", current=price, target=target),
                ))

    # Sell target
    sell = pos.levels.sell_target
    if sell is not None:
        if (not is_short and price >= sell) or (is_short and price <= sell):
            alerts.append(TriggeredAlert(
                ticker=pos.ticker,
                priority=Priority.HIGH,
                message=alert_to_string("hit_sell_target", current=price, target=sell),
            ))

    # P&L alerts
    if pos.position.pos_type == PositionType.LONG and cost > 0.0:
        pnl_pct = (price - cost) / cost * 100.0
        if pnl_pct >= 20.0:
            alerts.append(TriggeredAlert(
                ticker=pos.ticker,
                priority=Priority.INFO,
                message=alert_to_string("above_cost_basis", current=price, cost=cost, pct=pnl_pct),
            ))
        elif pnl_pct <= -10.0:
            alerts.append(TriggeredAlert(
                ticker=pos.ticker,
                priority=Priority.NORMAL,
                message=alert_to_string("below_cost_basis", current=price, cost=cost, pct=pnl_pct),
            ))
    elif pos.position.pos_type == PositionType.SHORT and cost > 0.0:
        pnl_pct = (cost - price) / cost * 100.0
        if pnl_pct >= 20.0:
            alerts.append(TriggeredAlert(
                ticker=pos.ticker,
                priority=Priority.INFO,
                message=alert_to_string("above_cost_basis", current=price, cost=cost, pct=pnl_pct),
            ))
        elif pnl_pct <= -10.0:
            alerts.append(TriggeredAlert(
                ticker=pos.ticker,
                priority=Priority.NORMAL,
                message=alert_to_string("below_cost_basis", current=price, cost=cost, pct=pnl_pct),
            ))

    return alerts


def analyze_position(
    pos: PortfolioPosition, market_data: dict[str, MarketData]
) -> PositionAnalysis:
    market = market_data.get(pos.ticker)
    thesis = calculate_thesis_score(pos.bull, pos.bear)

    pnl_pct = None
    pnl_abs = None
    if market is not None:
        if pos.position.pos_type == PositionType.LONG and pos.position.avg_cost > 0.0:
            pnl_pct = (market.current_price - pos.position.avg_cost) / pos.position.avg_cost * 100.0
            pnl_abs = (market.current_price - pos.position.avg_cost) * pos.position.shares
        elif pos.position.pos_type == PositionType.SHORT and pos.position.avg_cost > 0.0:
            pnl_pct = (pos.position.avg_cost - market.current_price) / pos.position.avg_cost * 100.0
            pnl_abs = (pos.position.avg_cost - market.current_price) * pos.position.shares

    alerts = check_price_alerts(pos, market)

    return PositionAnalysis(
        position=pos,
        market=market,
        thesis=thesis,
        pnl_pct=pnl_pct,
        pnl_abs=pnl_abs,
        alerts=alerts,
    )


def run_analysis(
    positions: list[PortfolioPosition], market_data: dict[str, MarketData]
) -> PortfolioAnalysis:
    now = datetime.now(timezone.utc)
    run_time = now.strftime("%Y-%m-%d %H:%M:%S UTC")

    analyses = [analyze_position(p, market_data) for p in positions]
    all_alerts = [a for pa in analyses for a in pa.alerts]

    # Portfolio totals (Long + Short only, exclude Watching)
    held = [a for a in analyses if a.position.position.pos_type in (PositionType.LONG, PositionType.SHORT)]
    total_cost = sum(a.position.position.avg_cost * a.position.position.shares for a in held)
    total_value = sum(
        a.market.current_price * a.position.position.shares
        for a in held if a.market is not None
    )
    total_pnl_pct = (
        (total_value - total_cost) / total_cost * 100.0 if total_cost > 0.0 else None
    )

    return PortfolioAnalysis(
        run_time=run_time,
        positions=analyses,
        total_value=total_value if total_value > 0.0 else None,
        total_cost=total_cost if total_cost > 0.0 else None,
        total_pnl_pct=total_pnl_pct,
        all_alerts=all_alerts,
    )
