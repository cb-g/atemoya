#!/usr/bin/env python3
"""
Train linear regression model for pre-earnings straddle prediction.

Fits coefficients on historical earnings data:
  predicted_return = intercept
    + c1 * (current_implied / last_implied)
    + c2 * (current_implied - last_realized)
    + c3 * (current_implied / avg_implied)
    + c4 * (current_implied - avg_realized)

Output: model_coefficients.csv
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np


def load_earnings_history(filepath: Path) -> dict:
    """Load earnings history grouped by ticker."""
    tickers = {}
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row["ticker"]
            if ticker not in tickers:
                tickers[ticker] = []
            tickers[ticker].append(
                {
                    "date": row["date"],
                    "implied_move": float(row["implied_move"]),
                    "realized_move": float(row["realized_move"]),
                }
            )
    return tickers


def build_features(events: list) -> tuple:
    """Build feature matrix and target vector from sequential events.

    For each event i (starting from i=1), uses events[0..i-1] as history
    to compute the 4 signals, and realized/implied - 1 as the target.
    """
    X = []
    y = []

    for i in range(1, len(events)):
        current = events[i]
        history = events[:i]

        current_implied = current["implied_move"]
        last_implied = history[-1]["implied_move"]
        last_realized = history[-1]["realized_move"]
        avg_implied = np.mean([e["implied_move"] for e in history])
        avg_realized = np.mean([e["realized_move"] for e in history])

        if last_implied <= 0 or avg_implied <= 0:
            continue

        features = [
            current_implied / last_implied,
            current_implied - last_realized,
            current_implied / avg_implied,
            current_implied - avg_realized,
        ]

        target = current["realized_move"] / current["implied_move"] - 1.0
        X.append(features)
        y.append(target)

    return np.array(X), np.array(y)


def fit_ols(X: np.ndarray, y: np.ndarray) -> tuple:
    """Ordinary least squares with intercept."""
    n = X.shape[0]
    X_aug = np.column_stack([np.ones(n), X])
    # Normal equation: beta = (X'X)^{-1} X'y
    beta = np.linalg.lstsq(X_aug, y, rcond=None)[0]
    intercept = beta[0]
    coefficients = beta[1:]
    return intercept, coefficients


def main():
    parser = argparse.ArgumentParser(description="Train pre-earnings straddle model")
    parser.add_argument(
        "--data-dir",
        type=str,
        default="pricing/pre_earnings_straddle/data",
        help="Data directory with earnings_history.csv",
    )

    args = parser.parse_args()
    data_dir = Path(args.data_dir)

    history_file = data_dir / "earnings_history.csv"
    if not history_file.exists():
        print(f"Error: {history_file} not found. Run fetch_earnings_data.py first.")
        sys.exit(1)

    tickers = load_earnings_history(history_file)
    print(f"Loaded earnings data for {len(tickers)} ticker(s): {', '.join(tickers.keys())}")

    # Pool all tickers for training
    all_X = []
    all_y = []
    for ticker, events in tickers.items():
        if len(events) < 3:
            print(f"  {ticker}: {len(events)} events (skipping, need >= 3)")
            continue
        X, y = build_features(events)
        print(f"  {ticker}: {len(events)} events -> {len(y)} training samples")
        all_X.append(X)
        all_y.append(y)

    if not all_X:
        print("Not enough data to train. Using default coefficients.")
        intercept = 0.033
        coefficients = [-0.05, -0.04, -0.06, -0.05]
    else:
        X = np.vstack(all_X)
        y = np.concatenate(all_y)
        print(f"\nTotal training samples: {len(y)}")

        if len(y) < 5:
            print("Too few samples for reliable regression. Using default coefficients.")
            intercept = 0.033
            coefficients = [-0.05, -0.04, -0.06, -0.05]
        else:
            intercept, coefficients = fit_ols(X, y)

    print(f"\nModel coefficients:")
    print(f"  intercept:                    {intercept:.6f}")
    print(f"  coef_implied_vs_last_implied: {coefficients[0]:.6f}")
    print(f"  coef_implied_vs_last_realized:{coefficients[1]:.6f}")
    print(f"  coef_implied_vs_avg_implied:  {coefficients[2]:.6f}")
    print(f"  coef_implied_vs_avg_realized: {coefficients[3]:.6f}")

    # Save (use explicit \n line endings for OCaml compatibility)
    output_file = data_dir / "model_coefficients.csv"
    header = "intercept,coef_implied_vs_last_implied,coef_implied_vs_last_realized,coef_implied_vs_avg_implied,coef_implied_vs_avg_realized"
    values = f"{intercept:.6f}," + ",".join(f"{c:.6f}" for c in coefficients)
    with open(output_file, "w") as f:
        f.write(header + "\n")
        f.write(values + "\n")

    print(f"\nSaved to {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
