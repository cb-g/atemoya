"""Visualization utilities for regime downside optimization results."""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path


# Kanagawa Dragon color palette (dark mode)
KANAGAWA_DRAGON = {
    'bg': '#181616',
    'fg': '#c5c9c5',
    'black': '#0d0c0c',
    'red': '#c4746e',
    'green': '#8a9a7b',
    'yellow': '#c4b28a',
    'blue': '#8ba4b0',
    'magenta': '#a292a3',
    'cyan': '#8ea4a2',
    'white': '#c5c9c5',
    'gray': '#625e5a',
}


def setup_dark_mode():
    """Configure matplotlib for Kanagawa Dragon dark mode."""
    plt.style.use('dark_background')
    plt.rcParams.update({
        'figure.facecolor': KANAGAWA_DRAGON['bg'],
        'axes.facecolor': KANAGAWA_DRAGON['bg'],
        'axes.edgecolor': KANAGAWA_DRAGON['gray'],
        'axes.labelcolor': KANAGAWA_DRAGON['fg'],
        'text.color': KANAGAWA_DRAGON['fg'],
        'xtick.color': KANAGAWA_DRAGON['fg'],
        'ytick.color': KANAGAWA_DRAGON['fg'],
        'grid.color': KANAGAWA_DRAGON['gray'],
        'legend.facecolor': KANAGAWA_DRAGON['bg'],
        'legend.edgecolor': KANAGAWA_DRAGON['gray'],
    })


def plot_portfolio_weights(results_csv: Path, output_dir: Path | None = None):
    """
    Plot portfolio weight evolution over time (constrained and frictionless).

    Args:
        results_csv: Path to results CSV file
        output_dir: Directory to save plots (None = show only)
    """
    # Set up dark mode
    setup_dark_mode()

    # Expanded, more vibrant color palette (Kanagawa-inspired but punchier)
    # Supports up to 16 assets without repetition
    colors = [
        '#7FCDCD',  # Vibrant cyan
        '#E8C547',  # Vibrant yellow
        '#D4779C',  # Vibrant magenta
        '#98C379',  # Vibrant green
        '#61AFEF',  # Vibrant blue
        '#E06C75',  # Vibrant red
        '#C678DD',  # Vibrant purple
        '#56B6C2',  # Vibrant teal
        '#E5C07B',  # Vibrant gold
        '#BE5046',  # Vibrant rust
        '#98C379',  # Vibrant lime
        '#61AFEF',  # Vibrant sky
        '#C678DD',  # Vibrant violet
        '#D19A66',  # Vibrant orange
        '#88C0D0',  # Vibrant ice
        '#BF616A',  # Vibrant crimson
    ]
    plt.rcParams['axes.prop_cycle'] = plt.cycler(color=colors)

    # Read results
    df = pd.read_csv(results_csv)
    df["date"] = pd.to_datetime(df["date"])

    # Check if we have dual results (new format)
    has_dual = "weight_constrained" in df.columns

    if has_dual:
        # New format: plot both constrained and frictionless
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

        # Constrained weights
        weights_constrained = df.pivot(
            index="date", columns="ticker", values="weight_constrained"
        )
        weights_constrained.plot.area(ax=ax1, alpha=0.7, stacked=True, linewidth=0)
        ax1.set_xlabel("Date", fontsize=12)
        ax1.set_ylabel("Portfolio Weight", fontsize=12)
        ax1.set_title("Constrained Portfolio (with turnover penalty)", fontsize=14, fontweight='bold')
        ax1.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=10)
        ax1.grid(True, alpha=0.3, linewidth=0.6)

        # Frictionless weights
        weights_frictionless = df.pivot(
            index="date", columns="ticker", values="weight_frictionless"
        )
        weights_frictionless.plot.area(ax=ax2, alpha=0.7, stacked=True, linewidth=0)
        ax2.set_xlabel("Date", fontsize=12)
        ax2.set_ylabel("Portfolio Weight", fontsize=12)
        ax2.set_title("Frictionless Portfolio (no turnover penalty)", fontsize=14, fontweight='bold')
        ax2.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=10)
        ax2.grid(True, alpha=0.3, linewidth=0.6)

    else:
        # Old format: single portfolio
        fig, ax = plt.subplots(figsize=(12, 6))
        weights = df.pivot(index="date", columns="ticker", values="weight")
        weights.plot.area(ax=ax, alpha=0.7, stacked=True, linewidth=0)
        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel("Portfolio Weight", fontsize=12)
        ax.set_title("Portfolio Allocation Over Time", fontsize=14, fontweight='bold')
        ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=10)
        ax.grid(True, alpha=0.3, linewidth=0.6)

    plt.tight_layout()

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "portfolio_weights.png"
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"Saved plot to {output_path}")


def plot_risk_metrics(results_csv: Path, output_dir: Path | None = None):
    """
    Plot risk metrics evolution over time (constrained vs frictionless).

    Args:
        results_csv: Path to results CSV file
        output_dir: Directory to save plots (None = show only)
    """
    # Set up dark mode
    setup_dark_mode()

    # Read results and get unique dates
    df = pd.read_csv(results_csv)
    df["date"] = pd.to_datetime(df["date"])
    daily = df.drop_duplicates(subset=["date"])

    # Check if we have dual results
    has_dual = "lpm1_constrained" in df.columns

    if has_dual:
        # New format: plot constrained vs frictionless
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        # LPM1
        axes[0, 0].plot(
            daily["date"],
            daily["lpm1_constrained"],
            color='#E06C75',  # Vibrant red
            alpha=0.9,
            linewidth=1.5,
            label="Constrained",
        )
        axes[0, 0].plot(
            daily["date"],
            daily["lpm1_frictionless"],
            color='#7FCDCD',  # Vibrant cyan
            alpha=0.9,
            linewidth=1.5,
            linestyle="--",
            label="Frictionless",
        )
        axes[0, 0].set_title("LPM1 (Lower Partial Moment)", fontsize=14, fontweight='bold')
        axes[0, 0].set_xlabel("Date", fontsize=12)
        axes[0, 0].set_ylabel("LPM1", fontsize=12)
        axes[0, 0].legend(fontsize=10)
        axes[0, 0].grid(True, alpha=0.3, linewidth=0.6)

        # CVaR
        axes[0, 1].plot(
            daily["date"],
            daily["cvar_constrained"],
            color='#E8C547',  # Vibrant yellow
            alpha=0.9,
            linewidth=1.5,
            label="Constrained",
        )
        axes[0, 1].plot(
            daily["date"],
            daily["cvar_frictionless"],
            color='#7FCDCD',  # Vibrant cyan
            alpha=0.9,
            linewidth=1.5,
            linestyle="--",
            label="Frictionless",
        )
        axes[0, 1].set_title("CVaR 95%", fontsize=14, fontweight='bold')
        axes[0, 1].set_xlabel("Date", fontsize=12)
        axes[0, 1].set_ylabel("CVaR", fontsize=12)
        axes[0, 1].legend(fontsize=10)
        axes[0, 1].grid(True, alpha=0.3, linewidth=0.6)

        # Portfolio Beta
        axes[1, 0].plot(
            daily["date"],
            daily["beta_constrained"],
            color='#61AFEF',  # Vibrant blue
            alpha=0.9,
            linewidth=1.5,
            label="Constrained",
        )
        axes[1, 0].plot(
            daily["date"],
            daily["beta_frictionless"],
            color='#98C379',  # Vibrant green
            alpha=0.9,
            linewidth=1.5,
            linestyle="--",
            label="Frictionless",
        )
        axes[1, 0].axhline(y=0.65, color='#E06C75', linestyle=":", linewidth=1.5, label="Target (stress)")
        axes[1, 0].set_title("Portfolio Beta", fontsize=14, fontweight='bold')
        axes[1, 0].set_xlabel("Date", fontsize=12)
        axes[1, 0].set_ylabel("Beta", fontsize=12)
        axes[1, 0].legend(fontsize=10)
        axes[1, 0].grid(True, alpha=0.3, linewidth=0.6)

        # Turnover
        axes[1, 1].plot(
            daily["date"],
            daily["turnover_constrained"],
            color='#98C379',  # Vibrant green
            alpha=0.9,
            linewidth=1.5,
        )
        axes[1, 1].set_title("Portfolio Turnover (Constrained)", fontsize=14, fontweight='bold')
        axes[1, 1].set_xlabel("Date", fontsize=12)
        axes[1, 1].set_ylabel("Turnover", fontsize=12)
        axes[1, 1].grid(True, alpha=0.3, linewidth=0.6)

    else:
        # Old format: single portfolio
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        # LPM1
        axes[0, 0].plot(daily["date"], daily["lpm1"], color='#E06C75', alpha=0.9, linewidth=1.5)
        axes[0, 0].set_title("LPM1 (Lower Partial Moment)", fontsize=14, fontweight='bold')
        axes[0, 0].set_xlabel("Date", fontsize=12)
        axes[0, 0].set_ylabel("LPM1", fontsize=12)
        axes[0, 0].grid(True, alpha=0.3, linewidth=0.6)

        # CVaR
        axes[0, 1].plot(daily["date"], daily["cvar_95"], color='#E8C547', alpha=0.9, linewidth=1.5)
        axes[0, 1].set_title("CVaR 95%", fontsize=14, fontweight='bold')
        axes[0, 1].set_xlabel("Date", fontsize=12)
        axes[0, 1].set_ylabel("CVaR", fontsize=12)
        axes[0, 1].grid(True, alpha=0.3, linewidth=0.6)

        # Portfolio Beta
        axes[1, 0].plot(daily["date"], daily["beta"], color='#61AFEF', alpha=0.9, linewidth=1.5)
        axes[1, 0].axhline(y=0.65, color='#E06C75', linestyle="--", linewidth=1.5, label="Target (stress)")
        axes[1, 0].set_title("Portfolio Beta", fontsize=14, fontweight='bold')
        axes[1, 0].set_xlabel("Date", fontsize=12)
        axes[1, 0].set_ylabel("Beta", fontsize=12)
        axes[1, 0].legend(fontsize=10)
        axes[1, 0].grid(True, alpha=0.3, linewidth=0.6)

        # Turnover
        axes[1, 1].plot(daily["date"], daily["turnover"], color='#98C379', alpha=0.9, linewidth=1.5)
        axes[1, 1].set_title("Portfolio Turnover", fontsize=14, fontweight='bold')
        axes[1, 1].set_xlabel("Date", fontsize=12)
        axes[1, 1].set_ylabel("Turnover", fontsize=12)
        axes[1, 1].grid(True, alpha=0.3, linewidth=0.6)

    plt.tight_layout()

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "risk_metrics.png"
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"Saved plot to {output_path}")


def plot_gap_analysis(results_csv: Path, output_dir: Path | None = None):
    """
    Plot gap between constrained and frictionless portfolios.

    Args:
        results_csv: Path to results CSV file
        output_dir: Directory to save plots (None = show only)
    """
    # Set up dark mode
    setup_dark_mode()

    # Read results
    df = pd.read_csv(results_csv)
    df["date"] = pd.to_datetime(df["date"])

    # Check if we have gap metrics
    if "gap_distance" not in df.columns:
        print("No gap metrics found in results. Skipping gap analysis plot.")
        return

    # Get unique dates
    daily = df.drop_duplicates(subset=["date"])

    # Create subplots
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Gap distance (turnover)
    axes[0, 0].plot(
        daily["date"], daily["gap_distance"] * 100,
        color='#D4779C',  # Vibrant magenta
        alpha=0.9,
        linewidth=1.5
    )
    axes[0, 0].set_title("Gap Distance (Turnover Required)", fontsize=14, fontweight='bold')
    axes[0, 0].set_xlabel("Date", fontsize=12)
    axes[0, 0].set_ylabel("Gap (%)", fontsize=12)
    axes[0, 0].grid(True, alpha=0.3, linewidth=0.6)

    # Gap LPM1
    axes[0, 1].plot(daily["date"], daily["gap_lpm1"],
                    color='#E06C75',  # Vibrant red
                    alpha=0.9,
                    linewidth=1.5)
    axes[0, 1].axhline(y=0, color=KANAGAWA_DRAGON['gray'], linestyle=":", linewidth=1.5, alpha=0.7)
    axes[0, 1].set_title("Gap in LPM1 (Constrained - Frictionless)", fontsize=14, fontweight='bold')
    axes[0, 1].set_xlabel("Date", fontsize=12)
    axes[0, 1].set_ylabel("LPM1 Difference", fontsize=12)
    axes[0, 1].grid(True, alpha=0.3, linewidth=0.6)

    # Gap CVaR
    axes[1, 0].plot(daily["date"], daily["gap_cvar"],
                    color='#E8C547',  # Vibrant yellow
                    alpha=0.9,
                    linewidth=1.5)
    axes[1, 0].axhline(y=0, color=KANAGAWA_DRAGON['gray'], linestyle=":", linewidth=1.5, alpha=0.7)
    axes[1, 0].set_title("Gap in CVaR (Constrained - Frictionless)", fontsize=14, fontweight='bold')
    axes[1, 0].set_xlabel("Date", fontsize=12)
    axes[1, 0].set_ylabel("CVaR Difference", fontsize=12)
    axes[1, 0].grid(True, alpha=0.3, linewidth=0.6)

    # Gap Beta
    axes[1, 1].plot(daily["date"], daily["gap_beta"],
                    color='#61AFEF',  # Vibrant blue
                    alpha=0.9,
                    linewidth=1.5)
    axes[1, 1].axhline(y=0, color=KANAGAWA_DRAGON['gray'], linestyle=":", linewidth=1.5, alpha=0.7)
    axes[1, 1].set_title("Gap in Beta (Constrained - Frictionless)", fontsize=14, fontweight='bold')
    axes[1, 1].set_xlabel("Date", fontsize=12)
    axes[1, 1].set_ylabel("Beta Difference", fontsize=12)
    axes[1, 1].grid(True, alpha=0.3, linewidth=0.6)

    plt.tight_layout()

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "gap_analysis.png"
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"Saved plot to {output_path}")


def main():
    """Example usage of visualization functions."""
    # Get paths
    script_dir = Path(__file__).parent
    model_dir = script_dir.parent.parent

    # Example paths (update when actual results exist)
    results_csv = model_dir / "output" / "optimization_results.csv"
    output_dir = model_dir / "output"

    if not results_csv.exists():
        print(f"Results file not found: {results_csv}")
        print("Run the optimization first to generate results.")
        return

    print("Generating visualizations...")
    plot_portfolio_weights(results_csv, output_dir)
    plot_risk_metrics(results_csv, output_dir)
    plot_gap_analysis(results_csv, output_dir)
    print("Done!")


if __name__ == "__main__":
    main()
