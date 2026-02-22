#!/usr/bin/env python3
"""Macro Dashboard Visualization.

This product uses the FRED® API but is not endorsed or certified by the
Federal Reserve Bank of St. Louis.
FRED® API Terms of Use: https://fred.stlouisfed.org/docs/api/terms_of_use.html

Data sources: Federal Reserve Board, BLS, BEA, U.S. Census Bureau, via FRED.
No machine learning or AI training is performed on FRED data.

Reads the classified environment JSON from the OCaml engine and produces
a visual dashboard with regime indicators, key metrics, and positioning.

Usage:
    uv run python plot_dashboard.py [--input ../output/environment.json]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[4]))

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as C, save_figure

setup_dark_mode()

# Regime color mapping
REGIME_COLORS = {
    # Cycle
    "Early Cycle (Recovery)": C["green"],
    "Mid Cycle (Expansion)": C["cyan"],
    "Late Cycle (Peak)": C["yellow"],
    "Recession (Contraction)": C["red"],
    # Yield curve
    "Normal (Upward Sloping)": C["green"],
    "Flat": C["yellow"],
    "Inverted": C["orange"],
    "Deeply Inverted": C["red"],
    # Inflation
    "Deflation": C["blue"],
    "Low Inflation": C["cyan"],
    "At Target": C["green"],
    "Elevated": C["yellow"],
    "Very High": C["red"],
    # Labor
    "Very Tight": C["orange"],
    "Tight": C["yellow"],
    "Healthy": C["green"],
    "Softening": C["yellow"],
    "Weak": C["red"],
    # Risk
    "Risk-On": C["green"],
    "Neutral": C["cyan"],
    "Cautious": C["yellow"],
    "Risk-Off": C["red"],
    # Fed
    "Very Dovish": C["green"],
    "Dovish": C["cyan"],
    "Neutral ": C["fg"],  # trailing space to distinguish from risk Neutral
    "Hawkish": C["yellow"],
    "Very Hawkish": C["red"],
}


def get_color(label):
    """Get color for a regime label, with fallback."""
    return REGIME_COLORS.get(label, C["fg"])


def style_ax(ax, title=None):
    """Apply standard dark-mode styling to an axes."""
    ax.set_facecolor(C["bg_light"])
    ax.tick_params(colors="white", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(C["gray"])
    if title:
        ax.set_title(title, color="white", fontsize=11, fontweight="bold", pad=8)


def plot_regime_panel(ax, regime):
    """Draw the regime classification panel with colored indicators."""
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(C["bg_light"])
    for spine in ax.spines.values():
        spine.set_color(C["gray"])

    fields = [
        ("Cycle Phase", regime.get("cycle_phase", "N/A")),
        ("Yield Curve", regime.get("yield_curve", "N/A")),
        ("Inflation", regime.get("inflation", "N/A")),
        ("Labor Market", regime.get("labor_market", "N/A")),
        ("Risk Sentiment", regime.get("risk_sentiment", "N/A")),
        ("Fed Stance", regime.get("fed_stance", "N/A")),
    ]

    y_start = 0.82
    y_step = 0.12

    ax.text(0.5, 0.97, "ECONOMIC REGIME", color="white", fontsize=12,
            fontweight="bold", ha="center", va="top", transform=ax.transAxes)

    for i, (label, value) in enumerate(fields):
        y = y_start - i * y_step
        color = get_color(value)

        # Label
        ax.text(0.05, y, label + ":", color=C["gray"], fontsize=9,
                va="center", transform=ax.transAxes)
        # Value with colored indicator
        ax.plot(0.52, y, "s", color=color, markersize=8,
                transform=ax.transAxes, clip_on=False)
        ax.text(0.56, y, value, color=color, fontsize=10,
                fontweight="bold", va="center", transform=ax.transAxes)

    # Recession probability
    rec_prob = regime.get("recession_probability", 0)
    conf = regime.get("confidence", 0)
    if isinstance(rec_prob, (int, float)):
        prob_pct = rec_prob * 100 if rec_prob <= 1 else rec_prob
        prob_color = C["green"] if prob_pct < 20 else C["yellow"] if prob_pct < 40 else C["red"]
        ax.text(0.05, 0.06, "Recession Prob:", color=C["gray"], fontsize=9,
                va="center", transform=ax.transAxes)
        ax.text(0.56, 0.06, f"{prob_pct:.0f}%", color=prob_color, fontsize=10,
                fontweight="bold", va="center", transform=ax.transAxes)

    if isinstance(conf, (int, float)):
        conf_pct = conf * 100 if conf <= 1 else conf
        ax.text(0.82, 0.06, f"(conf: {conf_pct:.0f}%)", color=C["gray"],
                fontsize=8, va="center", transform=ax.transAxes)


def _draw_metrics_panel(ax, title, items):
    """Draw a text-based metrics panel with colored values.

    items: list of (label, formatted_value, color)
    """
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(C["bg_light"])
    for spine in ax.spines.values():
        spine.set_color(C["gray"])

    ax.text(0.5, 0.97, title, color="white", fontsize=12,
            fontweight="bold", ha="center", va="top", transform=ax.transAxes)

    if not items:
        ax.text(0.5, 0.5, "No data available", color=C["gray"], fontsize=10,
                ha="center", va="center", transform=ax.transAxes)
        return

    y_start = 0.78
    y_step = min(0.13, 0.78 / max(len(items), 1))

    for i, (label, value_str, color) in enumerate(items):
        y = y_start - i * y_step
        ax.text(0.05, y, label + ":", color=C["gray"], fontsize=9,
                va="center", transform=ax.transAxes)
        ax.plot(0.52, y, "s", color=color, markersize=8,
                transform=ax.transAxes, clip_on=False)
        ax.text(0.56, y, value_str, color=color, fontsize=10,
                fontweight="bold", va="center", transform=ax.transAxes)


def plot_rates_panel(ax, rates):
    """Draw interest rates metrics panel."""
    items = []

    fed = rates.get("fed_funds")
    if fed is not None:
        items.append(("Fed Funds", f"{fed:.2f}%", C["cyan"]))

    t2y = rates.get("treasury_2y")
    if t2y is not None:
        items.append(("2Y Treasury", f"{t2y:.2f}%", C["cyan"]))

    t10y = rates.get("treasury_10y")
    if t10y is not None:
        items.append(("10Y Treasury", f"{t10y:.2f}%", C["cyan"]))

    spread = rates.get("spread_10y2y")
    if spread is not None:
        color = C["red"] if spread < 0 else C["green"]
        items.append(("10Y-2Y Spread", f"{spread:+.2f}%", color))

    _draw_metrics_panel(ax, "INTEREST RATES", items)


def plot_market_panel(ax, market):
    """Draw market indicators metrics panel."""
    items = []

    vix = market.get("vix")
    if vix is not None:
        color = C["red"] if vix > 25 else C["yellow"] if vix > 18 else C["green"]
        items.append(("VIX", f"{vix:.1f}", color))

    sp = market.get("sp500_ytd")
    if sp is not None:
        color = C["green"] if sp > 0 else C["red"]
        items.append(("S&P 500 YTD", f"{sp:+.1f}%", color))

    _draw_metrics_panel(ax, "MARKET INDICATORS", items)


def plot_implications_panel(ax, impl):
    """Draw investment implications panel."""
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(C["bg_light"])
    for spine in ax.spines.values():
        spine.set_color(C["gray"])

    ax.text(0.5, 0.97, "INVESTMENT POSITIONING", color="white", fontsize=12,
            fontweight="bold", ha="center", va="top", transform=ax.transAxes)

    equity = impl.get("equity_outlook", "N/A")
    bonds = impl.get("bond_outlook", "N/A")
    risk = impl.get("risk_level", "N/A")
    sectors = impl.get("sector_tilts", [])
    risks = impl.get("key_risks", [])

    # Equity outlook color
    eq_color = C["green"] if "Overweight" in equity else C["red"] if "Underweight" in equity else C["yellow"]
    # Risk level color
    risk_color = C["red"] if "High" in risk else C["yellow"] if "Elevated" in risk else C["green"] if "Low" in risk else C["cyan"]

    y = 0.78
    ax.text(0.05, y, "Equity:", color=C["gray"], fontsize=9,
            va="center", transform=ax.transAxes)
    ax.text(0.25, y, equity, color=eq_color, fontsize=9,
            fontweight="bold", va="center", transform=ax.transAxes)

    y -= 0.1
    ax.text(0.05, y, "Bonds:", color=C["gray"], fontsize=9,
            va="center", transform=ax.transAxes)
    ax.text(0.25, y, bonds, color=C["cyan"], fontsize=9,
            fontweight="bold", va="center", transform=ax.transAxes)

    y -= 0.1
    ax.text(0.05, y, "Risk:", color=C["gray"], fontsize=9,
            va="center", transform=ax.transAxes)
    ax.text(0.25, y, risk, color=risk_color, fontsize=9,
            fontweight="bold", va="center", transform=ax.transAxes)

    y -= 0.12
    ax.text(0.05, y, "Sector Tilts:", color=C["gray"], fontsize=9,
            va="center", transform=ax.transAxes)
    if sectors:
        sector_str = ", ".join(sectors)
        ax.text(0.05, y - 0.08, sector_str, color=C["fg"], fontsize=9,
                va="center", transform=ax.transAxes, style="italic")

    y -= 0.22
    if risks:
        ax.text(0.05, y, "Key Risks:", color=C["gray"], fontsize=9,
                va="center", transform=ax.transAxes)
        for i, r in enumerate(risks[:4]):
            ax.text(0.05, y - 0.08 - i * 0.07, f"  {r}", color=C["orange"],
                    fontsize=8, va="center", transform=ax.transAxes)


def plot_inflation_panel(ax, inflation):
    """Draw inflation metrics panel."""
    items = []

    pce = inflation.get("core_pce_yoy")
    if pce is not None:
        color = C["red"] if pce > 3 else C["yellow"] if pce > 2.5 else C["green"]
        items.append(("Core PCE YoY", f"{pce:.1f}%", color))

    cpi = inflation.get("core_cpi_yoy")
    if cpi is not None:
        color = C["red"] if cpi > 3 else C["yellow"] if cpi > 2.5 else C["green"]
        items.append(("Core CPI YoY", f"{cpi:.1f}%", color))

    _draw_metrics_panel(ax, "INFLATION", items)


def plot_employment_panel(ax, employment):
    """Draw employment metrics panel."""
    items = []

    unemp = employment.get("unemployment")
    if unemp is not None:
        color = C["green"] if unemp < 4.5 else C["yellow"] if unemp < 6 else C["red"]
        items.append(("Unemployment", f"{unemp:.1f}%", color))

    claims = employment.get("initial_claims")
    if claims is not None:
        color = C["green"] if claims < 250000 else C["yellow"] if claims < 350000 else C["red"]
        items.append(("Initial Claims", f"{claims:,.0f}", color))

    _draw_metrics_panel(ax, "EMPLOYMENT", items)


def plot_dashboard(data, output_dir):
    """Create the macro dashboard figure."""
    regime = data.get("regime", {})
    rates = data.get("rates", {})
    inflation = data.get("inflation", {})
    employment = data.get("employment", {})
    market = data.get("market", {})
    impl = data.get("implications", {})
    timestamp = data.get("timestamp", "")[:10]

    fig = plt.figure(figsize=(16, 12))
    fig.patch.set_facecolor(C["bg"])
    fig.suptitle(f"Macro Economic Dashboard  —  {timestamp}",
                 fontsize=14, fontweight="bold", color="white", y=0.98)

    gs = gridspec.GridSpec(3, 2, figure=fig, height_ratios=[1.2, 0.8, 0.8],
                           hspace=0.25, wspace=0.25)

    # Top-left: Regime classification
    ax_regime = fig.add_subplot(gs[0, 0])
    plot_regime_panel(ax_regime, regime)

    # Top-right: Investment implications
    ax_impl = fig.add_subplot(gs[0, 1])
    plot_implications_panel(ax_impl, impl)

    # Middle-left: Interest rates
    ax_rates = fig.add_subplot(gs[1, 0])
    plot_rates_panel(ax_rates, rates)

    # Middle-right: Market indicators
    ax_market = fig.add_subplot(gs[1, 1])
    plot_market_panel(ax_market, market)

    # Bottom-left: Inflation
    ax_infl = fig.add_subplot(gs[2, 0])
    plot_inflation_panel(ax_infl, inflation)

    # Bottom-right: Employment
    ax_emp = fig.add_subplot(gs[2, 1])
    plot_employment_panel(ax_emp, employment)

    # FRED API attribution
    fig.text(0.5, 0.01,
             "Source: Federal Reserve Board, BLS, BEA, U.S. Census Bureau, via FRED. "
             "This product uses the FRED® API but is not endorsed or certified "
             "by the Federal Reserve Bank of St. Louis.",
             ha="center", va="bottom", fontsize=7, color=C["gray"],
             style="italic")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "macro_dashboard.png"
    save_figure(fig, output_file, dpi=150)
    plt.close()
    print(f"Saved: {output_file} and {output_file.with_suffix('.svg')}")


def main():
    parser = argparse.ArgumentParser(description="Plot macro dashboard")
    parser.add_argument("--input", "-i", type=str,
                        default="alternative/macro_dashboard/output/environment.json",
                        help="Input JSON from OCaml classifier")
    parser.add_argument("--output-dir", "-o", type=str,
                        default="alternative/macro_dashboard/output",
                        help="Output directory for plots")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        # Try relative to project root
        project_root = Path(__file__).parents[4]
        input_path = project_root / input_path

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        print("Run the macro dashboard pipeline first:")
        print("  1. uv run python alternative/macro_dashboard/python/fetch/fetch_macro.py")
        print("  2. dune exec macro_dashboard -- alternative/macro_dashboard/data/macro_data.json --output alternative/macro_dashboard/output/environment.json")
        sys.exit(1)

    with open(input_path) as f:
        data = json.load(f)

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        project_root = Path(__file__).parents[4]
        output_dir = project_root / output_dir

    plot_dashboard(data, output_dir)


if __name__ == "__main__":
    main()
