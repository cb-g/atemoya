#!/usr/bin/env python3
"""
Monte Carlo Expected Value Calculator

Uses GBM (Geometric Brownian Motion) to simulate price paths and calculate
expected value of vertical spreads.
"""

import numpy as np
import pandas as pd
from pathlib import Path
import argparse
import json

def simulate_gbm_paths(
    spot: float,
    volatility: float,
    days: int,
    num_paths: int = 10000,
    drift: float = 0.0
) -> np.ndarray:
    """
    Simulate price paths using Geometric Brownian Motion.

    Args:
        spot: Current stock price
        volatility: Annualized volatility (e.g., 0.25 for 25%)
        days: Days to expiration
        num_paths: Number of simulation paths
        drift: Daily drift (can use momentum signal)

    Returns:
        Array of terminal prices (num_paths,)
    """

    # Convert to time in years
    T = days / 365.0

    # GBM formula: S_T = S_0 * exp((μ - σ²/2)T + σ√T * Z)
    # where Z ~ N(0,1)

    dt = T
    sqrt_dt = np.sqrt(dt)

    # Generate random normal draws
    Z = np.random.standard_normal(num_paths)

    # Calculate terminal prices
    terminal_prices = spot * np.exp(
        (drift - 0.5 * volatility**2) * dt + volatility * sqrt_dt * Z
    )

    return terminal_prices

def calculate_spread_payoff(
    terminal_price: float,
    long_strike: float,
    short_strike: float,
    debit: float,
    spread_type: str
) -> float:
    """
    Calculate payoff of vertical spread at expiration.

    Returns net P&L (payoff - initial debit).
    """

    if spread_type == "bull_call":
        # Long call payoff
        long_payoff = max(0, terminal_price - long_strike)
        # Short call payoff (negative)
        short_payoff = -max(0, terminal_price - short_strike)
        total_payoff = long_payoff + short_payoff
        # Net P&L
        pnl = total_payoff - debit
        return pnl

    elif spread_type == "bear_put":
        # Long put payoff
        long_payoff = max(0, long_strike - terminal_price)
        # Short put payoff (negative)
        short_payoff = -max(0, short_strike - terminal_price)
        total_payoff = long_payoff + short_payoff
        # Net P&L
        pnl = total_payoff - debit
        return pnl

    else:
        return 0.0

def monte_carlo_expected_value(
    spot: float,
    volatility: float,
    days: int,
    long_strike: float,
    short_strike: float,
    debit: float,
    spread_type: str,
    num_paths: int = 10000,
    drift: float = 0.0
) -> dict:
    """
    Calculate expected value using Monte Carlo simulation.

    Returns:
        dict with:
            - expected_value: Mean P&L
            - expected_return_pct: Expected return as % of debit
            - prob_profit: Probability of profit
            - percentiles: P&L percentiles (10th, 25th, 50th, 75th, 90th)
            - win_rate: % of paths that are profitable
    """

    # Simulate terminal prices
    terminal_prices = simulate_gbm_paths(
        spot=spot,
        volatility=volatility,
        days=days,
        num_paths=num_paths,
        drift=drift
    )

    # Calculate P&L for each path
    pnls = np.array([
        calculate_spread_payoff(
            terminal_price=price,
            long_strike=long_strike,
            short_strike=short_strike,
            debit=debit,
            spread_type=spread_type
        )
        for price in terminal_prices
    ])

    # Calculate statistics
    expected_value = np.mean(pnls)
    expected_return_pct = (expected_value / debit * 100) if debit > 0 else 0
    prob_profit = np.mean(pnls > 0)

    percentiles = {
        'p10': np.percentile(pnls, 10),
        'p25': np.percentile(pnls, 25),
        'p50': np.percentile(pnls, 50),
        'p75': np.percentile(pnls, 75),
        'p90': np.percentile(pnls, 90),
    }

    return {
        'expected_value': expected_value,
        'expected_return_pct': expected_return_pct,
        'prob_profit': prob_profit,
        'percentiles': percentiles,
        'num_paths': num_paths,
    }

def calculate_edge_adjusted_ev(
    spot: float,
    volatility: float,
    days: int,
    long_strike: float,
    short_strike: float,
    debit: float,
    spread_type: str,
    momentum_score: float,
    num_paths: int = 10000
) -> dict:
    """
    Calculate EV with momentum-adjusted drift.

    momentum_score: -1 to +1
    Positive momentum adds upward drift for calls, downward for puts.
    """

    # Convert momentum score to drift
    # Assume strong momentum (±1.0) corresponds to ±10% annualized drift
    annual_drift = momentum_score * 0.10
    drift = annual_drift

    result = monte_carlo_expected_value(
        spot=spot,
        volatility=volatility,
        days=days,
        long_strike=long_strike,
        short_strike=short_strike,
        debit=debit,
        spread_type=spread_type,
        num_paths=num_paths,
        drift=drift
    )

    result['momentum_score'] = momentum_score
    result['annual_drift'] = annual_drift

    return result

def main():
    parser = argparse.ArgumentParser(description='Monte Carlo EV calculator')
    parser.add_argument('--spot', type=float, required=True, help='Current stock price')
    parser.add_argument('--volatility', type=float, required=True, help='Annualized volatility (e.g., 0.25)')
    parser.add_argument('--days', type=int, required=True, help='Days to expiration')
    parser.add_argument('--long-strike', type=float, required=True, help='Long strike')
    parser.add_argument('--short-strike', type=float, required=True, help='Short strike')
    parser.add_argument('--debit', type=float, required=True, help='Net debit paid')
    parser.add_argument('--spread-type', type=str, required=True, choices=['bull_call', 'bear_put'],
                       help='Spread type')
    parser.add_argument('--momentum-score', type=float, default=0.0,
                       help='Momentum score (-1 to +1, default 0)')
    parser.add_argument('--num-paths', type=int, default=10000,
                       help='Number of simulation paths (default 10000)')

    args = parser.parse_args()

    print(f"\n=== Monte Carlo Expected Value ===")
    print(f"Spot: ${args.spot:.2f}")
    print(f"Volatility: {args.volatility*100:.1f}%")
    print(f"Days: {args.days}")
    print(f"Spread: {args.spread_type}")
    print(f"Long strike: ${args.long_strike:.2f}")
    print(f"Short strike: ${args.short_strike:.2f}")
    print(f"Debit: ${args.debit:.2f}")
    print(f"Momentum score: {args.momentum_score:.2f}")

    result = calculate_edge_adjusted_ev(
        spot=args.spot,
        volatility=args.volatility,
        days=args.days,
        long_strike=args.long_strike,
        short_strike=args.short_strike,
        debit=args.debit,
        spread_type=args.spread_type,
        momentum_score=args.momentum_score,
        num_paths=args.num_paths
    )

    print(f"\n=== Results ({result['num_paths']} paths) ===")
    print(f"Expected value: ${result['expected_value']:.2f}")
    print(f"Expected return: {result['expected_return_pct']:.1f}%")
    print(f"Probability of profit: {result['prob_profit']*100:.1f}%")

    print(f"\nP&L Percentiles:")
    print(f"  10th: ${result['percentiles']['p10']:.2f}")
    print(f"  25th: ${result['percentiles']['p25']:.2f}")
    print(f"  50th: ${result['percentiles']['p50']:.2f}")
    print(f"  75th: ${result['percentiles']['p75']:.2f}")
    print(f"  90th: ${result['percentiles']['p90']:.2f}")

    if result['expected_value'] > 0:
        print(f"\n✓ POSITIVE expected value")
    else:
        print(f"\n✗ Negative expected value")

if __name__ == "__main__":
    main()
