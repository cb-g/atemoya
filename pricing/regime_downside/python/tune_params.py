"""Parameter tuning for regime downside optimization."""

import json
import subprocess
import itertools
from pathlib import Path
import pandas as pd
import numpy as np


def run_backtest(params_dict, output_suffix=""):
    """
    Run backtest with given parameters.

    Args:
        params_dict: Dictionary of parameters
        output_suffix: Suffix for output files

    Returns:
        Dictionary with performance metrics
    """
    # Write parameters to temp file
    params_file = Path("pricing/regime_downside/data/params_temp.json")
    with open(params_file, 'w') as f:
        json.dump(params_dict, f, indent=2)

    # Run backtest
    cmd = [
        "opam", "exec", "--", "dune", "exec", "regime_downside", "--",
        "-tickers", "AAPL,GOOGL,MSFT,NVDA",
        "-start", "1000"
    ]

    try:
        # Temporarily replace params.json
        original_params = Path("pricing/regime_downside/data/params.json")
        backup_params = Path("pricing/regime_downside/data/params_backup.json")

        # Backup original
        if original_params.exists():
            original_params.rename(backup_params)

        params_file.rename(original_params)

        # Run backtest
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes max
        )

        # Restore original params
        original_params.rename(params_file)
        if backup_params.exists():
            backup_params.rename(original_params)

        if result.returncode != 0:
            print(f"Error running backtest: {result.stderr}")
            return None

        # Parse results
        return parse_results(result.stdout, params_dict)

    except subprocess.TimeoutExpired:
        print("Backtest timed out")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def parse_results(stdout, params):
    """Parse backtest output for performance metrics."""
    lines = stdout.split('\n')

    metrics = {
        'params': params,
        'n_rebalances': 0,
        'total_turnover': 0.0,
        'avg_turnover': 0.0
    }

    for line in lines:
        if 'Number of rebalances:' in line:
            metrics['n_rebalances'] = int(line.split(':')[1].strip())
        elif 'Total turnover:' in line:
            metrics['total_turnover'] = float(line.split(':')[1].strip())
        elif 'Average turnover per rebalance:' in line:
            metrics['avg_turnover'] = float(line.split(':')[1].strip())

    # Read results CSV for more detailed metrics
    results_file = Path("pricing/regime_downside/output/optimization_results.csv")
    if results_file.exists():
        df = pd.read_csv(results_file)

        # Get unique dates
        daily = df.drop_duplicates(subset=['date'])

        metrics['avg_lpm1'] = daily['lpm1'].mean()
        metrics['avg_cvar'] = daily['cvar_95'].mean()
        metrics['avg_beta'] = daily['beta'].mean()
        metrics['std_beta'] = daily['beta'].std()

    return metrics


def parameter_grid_search():
    """Run grid search over parameter space."""

    # Define parameter grid
    param_grid = {
        'lambda_lpm1': [0.5, 1.0, 2.0],
        'lambda_cvar': [0.25, 0.5, 1.0],
        'transaction_cost_bps': [2.0, 5.0, 10.0],
        'turnover_penalty': [0.05, 0.1, 0.2],
        'beta_penalty': [0.5, 1.0, 2.0],
        'target_beta': [0.65],  # Fixed
        'lpm1_threshold': [-0.001],  # Fixed
        'rebalance_threshold': [0.0001, 0.0005, 0.001]
    }

    # Generate all combinations
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = list(itertools.product(*values))

    print(f"Testing {len(combinations)} parameter combinations...")
    print("=" * 60)

    results = []

    for i, combo in enumerate(combinations[:10]):  # Limit to first 10 for speed
        params_dict = dict(zip(keys, combo))

        print(f"\n[{i+1}/{min(10, len(combinations))}] Testing parameters:")
        print(f"  lambda_lpm1={params_dict['lambda_lpm1']}")
        print(f"  lambda_cvar={params_dict['lambda_cvar']}")
        print(f"  turnover_penalty={params_dict['turnover_penalty']}")
        print(f"  rebalance_threshold={params_dict['rebalance_threshold']}")

        metrics = run_backtest(params_dict)

        if metrics:
            results.append(metrics)
            print(f"  Results: {metrics['n_rebalances']} rebalances, "
                  f"avg turnover={metrics['avg_turnover']:.4f}")
        else:
            print("  Failed")

    # Save results
    results_df = pd.DataFrame(results)
    results_file = Path("pricing/regime_downside/output/tuning_results.csv")
    results_df.to_csv(results_file, index=False)

    print("\n" + "=" * 60)
    print("Tuning complete!")
    print(f"Results saved to: {results_file}")

    # Find best parameters based on multiple criteria
    if len(results) > 0:
        print("\nBest parameters by different metrics:")

        # Best by turnover control (closest to 30% annual)
        target_annual_turnover = 0.30
        days_per_year = 252
        daily_turnover_target = target_annual_turnover / days_per_year

        results_df['turnover_score'] = abs(results_df['avg_turnover'] - daily_turnover_target)
        best_turnover_idx = results_df['turnover_score'].idxmin()

        print("\n1. Best for turnover control (~30% annual):")
        print(f"   Rebalances: {results_df.loc[best_turnover_idx, 'n_rebalances']}")
        print(f"   Avg turnover: {results_df.loc[best_turnover_idx, 'avg_turnover']:.4f}")
        print(f"   Parameters: {results_df.loc[best_turnover_idx, 'params']}")

        # Best by risk control (lowest CVaR)
        if 'avg_cvar' in results_df.columns:
            best_cvar_idx = results_df['avg_cvar'].idxmin()
            print("\n2. Best for risk control (lowest CVaR):")
            print(f"   Avg CVaR: {results_df.loc[best_cvar_idx, 'avg_cvar']:.6f}")
            print(f"   Parameters: {results_df.loc[best_cvar_idx, 'params']}")

        # Recommended: balanced approach
        # Normalize metrics and create composite score
        if 'avg_cvar' in results_df.columns and 'avg_lpm1' in results_df.columns:
            results_df['norm_cvar'] = (results_df['avg_cvar'] - results_df['avg_cvar'].min()) / (results_df['avg_cvar'].max() - results_df['avg_cvar'].min() + 1e-10)
            results_df['norm_lpm1'] = (results_df['avg_lpm1'] - results_df['avg_lpm1'].min()) / (results_df['avg_lpm1'].max() - results_df['avg_lpm1'].min() + 1e-10)
            results_df['norm_turnover'] = (results_df['turnover_score'] - results_df['turnover_score'].min()) / (results_df['turnover_score'].max() - results_df['turnover_score'].min() + 1e-10)

            results_df['composite_score'] = (
                0.4 * results_df['norm_cvar'] +
                0.4 * results_df['norm_lpm1'] +
                0.2 * results_df['norm_turnover']
            )

            best_composite_idx = results_df['composite_score'].idxmin()
            print("\n3. RECOMMENDED (Balanced):")
            print(f"   Rebalances: {results_df.loc[best_composite_idx, 'n_rebalances']}")
            print(f"   Avg LPM1: {results_df.loc[best_composite_idx, 'avg_lpm1']:.6f}")
            print(f"   Avg CVaR: {results_df.loc[best_composite_idx, 'avg_cvar']:.6f}")
            print(f"   Avg turnover: {results_df.loc[best_composite_idx, 'avg_turnover']:.4f}")

            best_params = results_df.loc[best_composite_idx, 'params']
            print(f"\n   Best Parameters:")
            for k, v in best_params.items():
                print(f"     {k}: {v}")

            # Save best parameters
            best_params_file = Path("pricing/regime_downside/data/params_tuned.json")
            with open(best_params_file, 'w') as f:
                json.dump(best_params, f, indent=2)
            print(f"\n   Saved to: {best_params_file}")
            print("   To use these parameters, copy params_tuned.json to params.json")

    return results


def quick_tune():
    """Run a quick parameter tuning with fewer combinations."""

    # Smaller grid for quick testing
    param_grid = {
        'lambda_lpm1': [0.5, 1.0],
        'lambda_cvar': [0.5, 1.0],
        'transaction_cost_bps': [5.0],
        'turnover_penalty': [0.1, 0.2],
        'beta_penalty': [1.0],
        'target_beta': [0.65],
        'lpm1_threshold': [-0.001],
        'rebalance_threshold': [0.0001, 0.001]
    }

    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = list(itertools.product(*values))

    print(f"Quick tuning: Testing {len(combinations)} parameter combinations...")
    print("=" * 60)

    results = []

    for i, combo in enumerate(combinations):
        params_dict = dict(zip(keys, combo))

        print(f"\n[{i+1}/{len(combinations)}] Testing:")
        print(f"  λ_lpm1={params_dict['lambda_lpm1']}, "
              f"λ_cvar={params_dict['lambda_cvar']}, "
              f"γ={params_dict['turnover_penalty']}, "
              f"δ={params_dict['rebalance_threshold']}")

        metrics = run_backtest(params_dict)

        if metrics:
            results.append(metrics)
            print(f"  ✓ {metrics['n_rebalances']} rebalances")
        else:
            print("  ✗ Failed")

    # Save and analyze
    if results:
        results_df = pd.DataFrame(results)
        results_file = Path("pricing/regime_downside/output/quick_tuning_results.csv")
        results_df.to_csv(results_file, index=False)

        print("\n" + "=" * 60)
        print(f"Results saved to: {results_file}")

        # Find best
        if 'avg_cvar' in results_df.columns:
            best_idx = results_df['avg_cvar'].idxmin()
            best_params = results_df.loc[best_idx, 'params']

            print("\nBest parameters (lowest CVaR):")
            for k, v in best_params.items():
                print(f"  {k}: {v}")

            # Save
            best_file = Path("pricing/regime_downside/data/params_tuned.json")
            with open(best_file, 'w') as f:
                json.dump(best_params, f, indent=2)

            print(f"\nSaved to: {best_file}")

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        quick_tune()
    else:
        print("Running full parameter grid search...")
        print("This may take a while. Use --quick for faster tuning.")
        print()
        parameter_grid_search()
