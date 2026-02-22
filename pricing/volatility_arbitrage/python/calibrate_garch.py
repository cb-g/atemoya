#!/usr/bin/env python3
"""
Calibrate GARCH(1,1) model to historical returns
"""

import argparse
import sys
import json
from pathlib import Path

import pandas as pd
import numpy as np

try:
    from arch import arch_model
    HAS_ARCH = True
except ImportError:
    HAS_ARCH = False


def calibrate_garch(returns: np.ndarray) -> dict:
    """
    Calibrate GARCH(1,1) model

    Model: σ²_t = ω + α·r²_{t-1} + β·σ²_{t-1}

    Returns:
        {
            'omega': float,
            'alpha': float,
            'beta': float,
            'persistence': float (α + β),
            'unconditional_vol': float,
            'log_likelihood': float,
            'aic': float,
            'bic': float
        }
    """
    if not HAS_ARCH:
        # Fallback to method of moments if arch not available
        print("Warning: arch library not available, using method of moments")

        variance = np.var(returns)
        # Typical GARCH parameters
        alpha = 0.05
        beta = 0.90
        omega = variance * (1 - alpha - beta)

        return {
            'omega': omega,
            'alpha': alpha,
            'beta': beta,
            'persistence': alpha + beta,
            'unconditional_vol': np.sqrt(variance * 252),
            'log_likelihood': 0.0,
            'aic': 0.0,
            'bic': 0.0
        }

    # Fit GARCH(1,1) using arch library
    returns_pct = returns * 100  # Convert to percentage returns
    model = arch_model(returns_pct, vol='Garch', p=1, q=1, rescale=False)
    result = model.fit(disp='off')

    params = result.params

    omega = params['omega']
    alpha = params['alpha[1]']
    beta = params['beta[1]']
    persistence = alpha + beta

    if persistence >= 1.0:
        print("Warning: GARCH persistence >= 1 (non-stationary)")

    unconditional_var = omega / (1 - persistence) if persistence < 1 else omega
    unconditional_vol = np.sqrt(unconditional_var / 100.0) * np.sqrt(252)  # Annualized

    return {
        'omega': omega,
        'alpha': alpha,
        'beta': beta,
        'persistence': persistence,
        'unconditional_vol': unconditional_vol,
        'log_likelihood': result.loglikelihood,
        'aic': result.aic,
        'bic': result.bic
    }


def main():
    parser = argparse.ArgumentParser(description='Calibrate GARCH model')
    parser.add_argument('--ticker', required=True, help='Stock ticker')
    parser.add_argument('--data-dir', default='pricing/volatility_arbitrage/data')
    parser.add_argument('--output-dir', default='pricing/volatility_arbitrage/data')

    args = parser.parse_args()

    try:
        data_dir = Path(args.data_dir)
        ohlc_file = data_dir / f"{args.ticker}_ohlc.csv"

        if not ohlc_file.exists():
            raise FileNotFoundError(f"OHLC data not found: {ohlc_file}")

        # Load OHLC data
        df = pd.read_csv(ohlc_file)
        closes = df['close'].values

        # Compute log returns
        returns = np.diff(np.log(closes))

        print(f"Calibrating GARCH(1,1) for {args.ticker}")
        print(f"Sample size: {len(returns)} returns")

        # Calibrate GARCH
        params = calibrate_garch(returns)

        print("\nGARCH(1,1) Parameters:")
        print(f"  ω (omega):    {params['omega']:.6f}")
        print(f"  α (alpha):    {params['alpha']:.6f}")
        print(f"  β (beta):     {params['beta']:.6f}")
        print(f"  Persistence (α+β): {params['persistence']:.6f}")
        print(f"  Unconditional Vol: {params['unconditional_vol']*100:.2f}%")

        if HAS_ARCH:
            print(f"\nModel Fit:")
            print(f"  Log-Likelihood: {params['log_likelihood']:.2f}")
            print(f"  AIC: {params['aic']:.2f}")
            print(f"  BIC: {params['bic']:.2f}")

        # Save parameters
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{args.ticker}_garch_params.json"

        with open(output_file, 'w') as f:
            json.dump(params, f, indent=2)

        print(f"\n✓ Saved GARCH parameters to {output_file}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
