#!/usr/bin/env python3
"""
Trade Logger for Skew Vertical Spreads

Logs scan results to build a forward-testing database.
Similar to earnings_vol tracking system.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import argparse

# Database path
DATABASE_FILE = "pricing/skew_verticals/data/trade_history.csv"

# Column schema
COLUMNS = [
    # Scan metadata
    'scan_date',
    'ticker',
    'expiration',
    'days_to_expiry',

    # Pre-trade data
    'spot_price',
    'spread_type',
    'long_strike',
    'short_strike',
    'debit',
    'max_profit',
    'reward_risk',
    'breakeven',

    # Skew metrics
    'atm_iv',
    'realized_vol',
    'call_skew',
    'call_skew_zscore',
    'put_skew',
    'put_skew_zscore',
    'vrp',

    # Momentum
    'return_1m',
    'return_3m',
    'momentum_score',

    # Recommendation
    'recommendation',
    'edge_score',
    'expected_value',
    'prob_profit',

    # Filters
    'passes_skew_filter',
    'passes_ivrv_filter',
    'passes_momentum_filter',

    # Post-trade results (filled later)
    'status',
    'close_date',
    'exit_spot_price',
    'actual_pnl',
    'actual_return_pct',
]

def log_scan_data(
    ticker: str,
    expiration: str,
    days_to_expiry: int,
    spot_price: float,
    spread_type: str,
    long_strike: float,
    short_strike: float,
    debit: float,
    max_profit: float,
    reward_risk: float,
    breakeven: float,
    atm_iv: float,
    realized_vol: float,
    call_skew: float,
    call_skew_zscore: float,
    put_skew: float,
    put_skew_zscore: float,
    vrp: float,
    return_1m: float,
    return_3m: float,
    momentum_score: float,
    recommendation: str,
    edge_score: float,
    expected_value: float,
    prob_profit: float,
    passes_skew_filter: bool,
    passes_ivrv_filter: bool,
    passes_momentum_filter: bool,
):
    """Log a new scan to the database."""

    db_path = Path(DATABASE_FILE)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing or create new
    if db_path.exists():
        df = pd.read_csv(db_path)
    else:
        df = pd.DataFrame(columns=COLUMNS)

    # Create new row
    new_row = {
        'scan_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'ticker': ticker,
        'expiration': expiration,
        'days_to_expiry': days_to_expiry,
        'spot_price': spot_price,
        'spread_type': spread_type,
        'long_strike': long_strike,
        'short_strike': short_strike,
        'debit': debit,
        'max_profit': max_profit,
        'reward_risk': reward_risk,
        'breakeven': breakeven,
        'atm_iv': atm_iv,
        'realized_vol': realized_vol,
        'call_skew': call_skew,
        'call_skew_zscore': call_skew_zscore,
        'put_skew': put_skew,
        'put_skew_zscore': put_skew_zscore,
        'vrp': vrp,
        'return_1m': return_1m,
        'return_3m': return_3m,
        'momentum_score': momentum_score,
        'recommendation': recommendation,
        'edge_score': edge_score,
        'expected_value': expected_value,
        'prob_profit': prob_profit,
        'passes_skew_filter': passes_skew_filter,
        'passes_ivrv_filter': passes_ivrv_filter,
        'passes_momentum_filter': passes_momentum_filter,
        'status': 'pending',
        'close_date': None,
        'exit_spot_price': None,
        'actual_pnl': None,
        'actual_return_pct': None,
    }

    # Append
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(db_path, index=False)

    print(f"\n✓ Scan logged to database: {db_path}")
    print(f"  Ticker: {ticker}")
    print(f"  Recommendation: {recommendation}")
    print(f"  Edge score: {edge_score:.0f}/100")
    print(f"  Status: pending")

def main():
    parser = argparse.ArgumentParser(description='Log scan to trade database')
    parser.add_argument('--ticker', type=str, required=True)
    parser.add_argument('--expiration', type=str, required=True)
    parser.add_argument('--days', type=int, required=True)
    parser.add_argument('--spot', type=float, required=True)
    parser.add_argument('--spread-type', type=str, required=True)
    parser.add_argument('--long-strike', type=float, required=True)
    parser.add_argument('--short-strike', type=float, required=True)
    parser.add_argument('--debit', type=float, required=True)
    parser.add_argument('--max-profit', type=float, required=True)
    parser.add_argument('--reward-risk', type=float, required=True)
    parser.add_argument('--breakeven', type=float, required=True)
    parser.add_argument('--atm-iv', type=float, required=True)
    parser.add_argument('--rv', type=float, required=True)
    parser.add_argument('--call-skew', type=float, required=True)
    parser.add_argument('--call-skew-z', type=float, required=True)
    parser.add_argument('--put-skew', type=float, required=True)
    parser.add_argument('--put-skew-z', type=float, required=True)
    parser.add_argument('--vrp', type=float, required=True)
    parser.add_argument('--return-1m', type=float, required=True)
    parser.add_argument('--return-3m', type=float, required=True)
    parser.add_argument('--momentum-score', type=float, required=True)
    parser.add_argument('--recommendation', type=str, required=True)
    parser.add_argument('--edge-score', type=float, required=True)
    parser.add_argument('--expected-value', type=float, required=True)
    parser.add_argument('--prob-profit', type=float, required=True)
    parser.add_argument('--passes-skew', type=int, required=True)
    parser.add_argument('--passes-ivrv', type=int, required=True)
    parser.add_argument('--passes-momentum', type=int, required=True)

    args = parser.parse_args()

    log_scan_data(
        ticker=args.ticker,
        expiration=args.expiration,
        days_to_expiry=args.days,
        spot_price=args.spot,
        spread_type=args.spread_type,
        long_strike=args.long_strike,
        short_strike=args.short_strike,
        debit=args.debit,
        max_profit=args.max_profit,
        reward_risk=args.reward_risk,
        breakeven=args.breakeven,
        atm_iv=args.atm_iv,
        realized_vol=args.rv,
        call_skew=args.call_skew,
        call_skew_zscore=args.call_skew_z,
        put_skew=args.put_skew,
        put_skew_zscore=args.put_skew_z,
        vrp=args.vrp,
        return_1m=args.return_1m,
        return_3m=args.return_3m,
        momentum_score=args.momentum_score,
        recommendation=args.recommendation,
        edge_score=args.edge_score,
        expected_value=args.expected_value,
        prob_profit=args.prob_profit,
        passes_skew_filter=bool(args.passes_skew),
        passes_ivrv_filter=bool(args.passes_ivrv),
        passes_momentum_filter=bool(args.passes_momentum),
    )

if __name__ == "__main__":
    main()
