#!/usr/bin/env python3
"""
Visualize Market Regime Forecast results — multi-model comparison dashboard
with consensus overview.

Reads JSON output from each model and produces:
- 4 model panels showing individual classifications
- 1 consensus panel synthesizing all models
"""

import json
import sys
import argparse
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

setup_dark_mode()

MODEL_NAMES = {
    'basic': 'Basic (GARCH+HMM)',
    'ms-garch': 'MS-GARCH',
    'bocpd': 'BOCPD',
    'gp': 'Gaussian Process',
}

MODEL_DESCRIPTIONS = {
    'basic': 'Separate GARCH vol + HMM trend on full history',
    'ms-garch': 'Unified model: vol params change with regime',
    'bocpd': 'Bayesian changepoint: stats since last break',
    'gp': 'Non-parametric smooth trend + uncertainty',
}

MODEL_DETAILS = {
    'basic': (
        'Fits GARCH(1,1) for vol clustering and a 3-state HMM for trend.\n'
        'Vol regime by percentile vs 5-year history.\n'
        'Best for: stable, interpretable baseline.'
    ),
    'ms-garch': (
        'Each vol regime has its own GARCH parameters.\n'
        'Classifies by which learned cluster fits today.\n'
        'Best for: detecting when the vol process itself changed.'
    ),
    'bocpd': (
        'Tracks run-length distribution since last changepoint.\n'
        'Classifies by current-segment statistics only.\n'
        'Best for: early warning that a new regime just started.'
    ),
    'gp': (
        'Fits smooth Matern 5/2 kernel, takes derivative for trend.\n'
        'Short memory (60d), quantifies forecast uncertainty.\n'
        'Best for: recent momentum shifts and anomaly detection.'
    ),
}

TREND_COLORS = {
    'Bull': COLORS['green'],
    'Bear': COLORS['red'],
    'Sideways': COLORS['yellow'],
}

VOL_COLORS = {
    'HighVol': COLORS['red'],
    'High Volatility': COLORS['red'],
    'NormalVol': COLORS['cyan'],
    'Normal Volatility': COLORS['cyan'],
    'LowVol': COLORS['green'],
    'Low Volatility': COLORS['green'],
}

STAR_CHAR = '\u2605'  # filled star
EMPTY_STAR = '\u2606'  # empty star


def load_model_result(path: Path) -> dict | None:
    """Load a model JSON result file."""
    if path is None or not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def normalize_vol(vol: str) -> str:
    """Normalize vol regime names for consensus counting."""
    vol_lower = vol.lower().replace(' ', '')
    if 'high' in vol_lower:
        return 'High'
    elif 'low' in vol_lower:
        return 'Low'
    else:
        return 'Normal'


def extract_common_fields(data: dict, model_key: str = '') -> dict:
    """Extract common display fields from any model JSON."""
    regime = data.get('current_regime', {})
    etf = data.get('income_etf', {})

    trend = regime.get('trend', 'Unknown')
    vol = regime.get('volatility', 'Unknown')
    suitability = etf.get('covered_call_suitability', 0)
    recommendation = etf.get('recommendation', '')
    model = data.get('model', model_key or 'unknown')

    # Extract model-specific metrics
    extras = []

    if model == 'basic':
        confidence = regime.get('confidence', 0)
        vol_forecast = regime.get('vol_forecast', 0)
        vol_pct = regime.get('vol_percentile', 0)
        if confidence:
            extras.append(f'Confidence:  {confidence*100:.0f}%')
        if vol_forecast:
            extras.append(f'Vol Forecast: {vol_forecast*100:.1f}%')
        if vol_pct:
            extras.append(f'Vol Pctile:  {vol_pct*100:.0f}th')

        tp = regime.get('trend_probabilities', {})
        if tp:
            extras.append('')
            extras.append(f'Bull:  {tp.get("bull", 0)*100:.0f}%   '
                          f'Bear: {tp.get("bear", 0)*100:.0f}%   '
                          f'Side: {tp.get("sideways", 0)*100:.0f}%')

        garch = data.get('garch_fit', {})
        if garch:
            persistence = garch.get('persistence', 0)
            if persistence:
                extras.append(f'GARCH Persistence: {persistence:.3f}')

    elif model == 'ms-garch':
        confidence = regime.get('confidence', 0)
        if confidence:
            extras.append(f'Confidence:  {confidence*100:.0f}%')

        vol_probs = regime.get('vol_regime_probabilities', {})
        if vol_probs:
            extras.append('')
            extras.append(f'Low: {vol_probs.get("low", 0)*100:.0f}%   '
                          f'Norm: {vol_probs.get("normal", 0)*100:.0f}%   '
                          f'High: {vol_probs.get("high", 0)*100:.0f}%')

        ms_fit = data.get('ms_garch_fit', {})
        if ms_fit:
            extras.append(f'AIC: {ms_fit.get("aic", 0):.0f}  '
                          f'Converged: {"Yes" if ms_fit.get("converged") else "No"}')

    elif model == 'bocpd':
        run_len = regime.get('run_length', 0)
        stability = regime.get('regime_stability', 0)
        cp_prob = regime.get('changepoint_prob', 0)
        extras.append(f'Run Length:  {run_len} days')
        extras.append(f'Stability:   {stability*100:.0f}%')
        extras.append(f'CP Prob:     {cp_prob*100:.1f}%')

        rv_ann = regime.get('regime_vol_annual', 0)
        rm_ann = regime.get('regime_mean_annual', 0)
        if rv_ann:
            extras.append(f'Regime Vol:  {rv_ann*100:.1f}% ann.')
        if rm_ann:
            extras.append(f'Regime Ret:  {rm_ann*100:+.1f}% ann.')

        cps = data.get('changepoints', [])
        extras.append(f'Changepoints: {len(cps)} detected')

    elif model == 'gp':
        confidence = regime.get('confidence', 0)
        anomaly = regime.get('anomaly_score', 0)
        if confidence:
            extras.append(f'Confidence:   {confidence*100:.0f}%')
        if anomaly:
            extras.append(f'Anomaly:      {anomaly:.2f} sigma')

        trend_ann = regime.get('current_trend_annual', 0)
        unc_ann = regime.get('uncertainty_annual', 0)
        if trend_ann:
            extras.append(f'GP Trend:     {trend_ann*100:+.1f}% ann.')
        if unc_ann:
            extras.append(f'Uncertainty:  {unc_ann*100:.1f}% ann.')

        fc = data.get('forecast', {})
        if fc:
            extras.append(f'Forecast:     {fc.get("mean_annual", 0)*100:+.1f}% +/- '
                          f'{fc.get("std_annual", 0)*100:.1f}%')

    # Actual returns (basic and ms-garch have these)
    ret = regime.get('actual_returns', {})
    if ret:
        r1 = ret.get('return_1m', 0)
        r3 = ret.get('return_3m', 0)
        r6 = ret.get('return_6m', 0)
        extras.append('')
        extras.append(f'Returns: 1m {r1*100:+.1f}%  3m {r3*100:+.1f}%  6m {r6*100:+.1f}%')

    return {
        'model': model,
        'trend': trend,
        'vol': vol,
        'suitability': suitability,
        'recommendation': recommendation,
        'extras': extras,
    }


def draw_model_panel(ax, fields: dict, model_key: str):
    """Draw a single model's regime summary panel."""
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    model_name = MODEL_NAMES.get(model_key, model_key)
    model_desc = MODEL_DESCRIPTIONS.get(model_key, '')
    trend = fields['trend']
    vol = fields['vol']
    suitability = fields['suitability']
    recommendation = fields['recommendation']
    extras = fields['extras']

    trend_color = TREND_COLORS.get(trend, COLORS['fg'])
    vol_color = VOL_COLORS.get(vol, COLORS['fg'])

    # Model title
    ax.text(0.5, 0.96, model_name, fontsize=16, fontweight='bold',
            color=COLORS['fg'], ha='center', va='top', transform=ax.transAxes)

    # Model description (what it measures)
    ax.text(0.5, 0.89, model_desc, fontsize=9, color=COLORS['gray'],
            ha='center', va='top', transform=ax.transAxes, style='italic')

    # Divider
    ax.axhline(y=0.85, xmin=0.1, xmax=0.9, color=COLORS['gray'], linewidth=1, alpha=0.6)

    # Regime classification
    ax.text(0.5, 0.80, f'Trend: {trend}', fontsize=14, fontweight='bold',
            color=trend_color, ha='center', va='top', transform=ax.transAxes)
    ax.text(0.5, 0.72, f'Vol: {vol}', fontsize=14, fontweight='bold',
            color=vol_color, ha='center', va='top', transform=ax.transAxes)

    # Suitability stars
    stars = STAR_CHAR * suitability + EMPTY_STAR * (5 - suitability)
    star_color = COLORS['green'] if suitability >= 4 else (
        COLORS['yellow'] if suitability >= 3 else COLORS['red'])
    ax.text(0.5, 0.63, f'{stars}  ({suitability}/5)', fontsize=13,
            color=star_color, ha='center', va='top', transform=ax.transAxes)

    # Recommendation (word-wrap long text)
    import textwrap
    rec_lines = textwrap.fill(recommendation, width=50)
    ax.text(0.5, 0.56, rec_lines, fontsize=9, color=COLORS['fg'],
            ha='center', va='top', transform=ax.transAxes, style='italic',
            linespacing=1.3)

    # Extra metrics — shift down based on recommendation length
    rec_lines_count = len(rec_lines.split('\n'))
    metrics_y = 0.49 - max(0, (rec_lines_count - 1) * 0.04)
    if extras:
        metrics_text = '\n'.join(extras)
        ax.text(0.5, metrics_y, metrics_text, fontsize=8.5, color=COLORS['fg'],
                ha='center', va='top', transform=ax.transAxes,
                family='monospace', linespacing=1.3,
                bbox=dict(boxstyle='round,pad=0.5', facecolor=COLORS['bg_light'],
                          edgecolor=COLORS['gray'], alpha=0.6, linewidth=0.8))


def draw_empty_panel(ax, model_key: str):
    """Draw placeholder for a model that wasn't run."""
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    model_name = MODEL_NAMES.get(model_key, model_key)
    ax.text(0.5, 0.5, f'{model_name}\n\n(not run)', fontsize=14,
            color=COLORS['gray'], ha='center', va='center', transform=ax.transAxes)


def build_consensus(all_fields: list[dict]) -> dict:
    """Build consensus from all model results."""
    n = len(all_fields)
    if n == 0:
        return {}

    # Count trend votes
    trend_votes = Counter(f['trend'] for f in all_fields)
    consensus_trend, trend_count = trend_votes.most_common(1)[0]
    trend_unanimous = trend_count == n

    # Count vol votes (normalized)
    vol_votes = Counter(normalize_vol(f['vol']) for f in all_fields)
    consensus_vol, vol_count = vol_votes.most_common(1)[0]
    vol_unanimous = vol_count == n

    # Average suitability
    avg_suitability = np.mean([f['suitability'] for f in all_fields])

    # Find dissenters
    trend_dissenters = [(f['model'], f['trend']) for f in all_fields if f['trend'] != consensus_trend]
    vol_dissenters = [(f['model'], normalize_vol(f['vol'])) for f in all_fields
                      if normalize_vol(f['vol']) != consensus_vol]

    # Agreement level
    agreement = (trend_count + vol_count) / (2 * n)

    return {
        'n_models': n,
        'consensus_trend': consensus_trend,
        'trend_count': trend_count,
        'trend_unanimous': trend_unanimous,
        'trend_dissenters': trend_dissenters,
        'trend_votes': dict(trend_votes),
        'consensus_vol': consensus_vol,
        'vol_count': vol_count,
        'vol_unanimous': vol_unanimous,
        'vol_dissenters': vol_dissenters,
        'vol_votes': dict(vol_votes),
        'avg_suitability': avg_suitability,
        'agreement': agreement,
    }


def draw_consensus_panel(ax, consensus: dict, all_fields: list[dict]):
    """Draw the consensus overview panel spanning full width."""
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    n = consensus['n_models']

    # Title
    ax.text(0.5, 0.95, 'Consensus Overview', fontsize=18, fontweight='bold',
            color=COLORS['fg'], ha='center', va='top', transform=ax.transAxes)
    ax.axhline(y=0.87, xmin=0.05, xmax=0.95, color=COLORS['gray'], linewidth=1, alpha=0.6)

    # Left column: Consensus classification
    x_left = 0.25

    # Trend consensus
    ct = consensus['consensus_trend']
    tc = consensus['trend_count']
    trend_color = TREND_COLORS.get(ct, COLORS['fg'])

    if consensus['trend_unanimous']:
        trend_line = f'Trend:  {ct}  ({tc}/{n} unanimous)'
    else:
        dissent_str = ', '.join(f'{MODEL_NAMES.get(m, m)}: {t}' for m, t in consensus['trend_dissenters'])
        trend_line = f'Trend:  {ct}  ({tc}/{n} agree)'

    ax.text(x_left, 0.78, trend_line, fontsize=14, fontweight='bold',
            color=trend_color, ha='center', va='top', transform=ax.transAxes)

    # Show dissenters
    if not consensus['trend_unanimous']:
        dissent_str = '  '.join(f'{MODEL_NAMES.get(m, m)}: {t}' for m, t in consensus['trend_dissenters'])
        ax.text(x_left, 0.68, f'Dissent: {dissent_str}', fontsize=10,
                color=COLORS['gray'], ha='center', va='top', transform=ax.transAxes)

    # Vol consensus
    cv = consensus['consensus_vol']
    vc = consensus['vol_count']
    vol_map = {'High': 'High Volatility', 'Normal': 'Normal Volatility', 'Low': 'Low Volatility'}
    vol_display = vol_map.get(cv, cv)
    vol_color = VOL_COLORS.get(vol_display, COLORS['fg'])

    if consensus['vol_unanimous']:
        vol_line = f'Vol:    {vol_display}  ({vc}/{n} unanimous)'
    else:
        vol_line = f'Vol:    {vol_display}  ({vc}/{n} agree)'

    y_vol = 0.56 if not consensus['trend_unanimous'] else 0.62
    ax.text(x_left, y_vol, vol_line, fontsize=14, fontweight='bold',
            color=vol_color, ha='center', va='top', transform=ax.transAxes)

    if not consensus['vol_unanimous']:
        dissent_str = '  '.join(f'{MODEL_NAMES.get(m, m)}: {v}' for m, v in consensus['vol_dissenters'])
        ax.text(x_left, y_vol - 0.10, f'Dissent: {dissent_str}', fontsize=10,
                color=COLORS['gray'], ha='center', va='top', transform=ax.transAxes)

    # Suitability
    avg_suit = consensus['avg_suitability']
    rounded_suit = int(round(avg_suit))
    stars = STAR_CHAR * rounded_suit + EMPTY_STAR * (5 - rounded_suit)
    star_color = COLORS['green'] if rounded_suit >= 4 else (
        COLORS['yellow'] if rounded_suit >= 3 else COLORS['red'])

    y_stars = y_vol - (0.18 if not consensus['vol_unanimous'] else 0.12)
    ax.text(x_left, y_stars, f'{stars}  (avg {avg_suit:.1f}/5)', fontsize=14,
            color=star_color, ha='center', va='top', transform=ax.transAxes)

    # Right column: Model roles with detailed descriptions
    x_right = 0.72

    ax.text(x_right, 0.78, 'What each model measures:', fontsize=12, fontweight='bold',
            color=COLORS['fg'], ha='center', va='top', transform=ax.transAxes)

    y_role = 0.68
    for f in all_fields:
        key = f['model']
        name = MODEL_NAMES.get(key, key)
        detail = MODEL_DETAILS.get(key, MODEL_DESCRIPTIONS.get(key, ''))
        trend_c = TREND_COLORS.get(f['trend'], COLORS['fg'])

        # Model name with its classification
        call_str = f"{f['trend']} + {normalize_vol(f['vol'])} Vol"
        ax.text(x_right, y_role, f'{name}  [{call_str}]', fontsize=11, fontweight='bold',
                color=trend_c, ha='center', va='top', transform=ax.transAxes)
        y_role -= 0.07

        # Best-for line (extract from detail)
        best_for = ''
        for line in detail.split('\n'):
            if line.startswith('Best for:'):
                best_for = line
                break
        if best_for:
            ax.text(x_right, y_role, best_for, fontsize=10, color=COLORS['fg'],
                    ha='center', va='top', transform=ax.transAxes, style='italic')
            y_role -= 0.08

    # Agreement bar at bottom
    agreement = consensus['agreement']
    agr_label = 'Strong' if agreement >= 0.875 else ('Moderate' if agreement >= 0.625 else 'Weak')
    agr_color = COLORS['green'] if agreement >= 0.875 else (
        COLORS['yellow'] if agreement >= 0.625 else COLORS['red'])

    ax.text(0.5, 0.0, f'Model Agreement: {agr_label} ({agreement*100:.0f}%)', fontsize=12,
            fontweight='bold', color=agr_color, ha='center', va='bottom', transform=ax.transAxes)


def plot_regime_comparison(results: dict, output_dir: Path, ticker: str = 'SPY'):
    """Plot model comparison dashboard with consensus panel."""
    print(f"Plotting regime comparison for {ticker}...")

    # Use GridSpec: 3 rows — top 2 rows are 2x2 model panels, bottom row is consensus
    fig = plt.figure(figsize=(16, 14))
    gs = gridspec.GridSpec(3, 2, figure=fig, height_ratios=[1, 1, 0.8],
                           hspace=0.02, wspace=0.02)

    model_keys = ['basic', 'ms-garch', 'bocpd', 'gp']
    positions = [(0, 0), (0, 1), (1, 0), (1, 1)]

    all_fields = []

    for key, (r, c) in zip(model_keys, positions):
        ax = fig.add_subplot(gs[r, c])
        data = results.get(key)
        if data is not None:
            fields = extract_common_fields(data, model_key=key)
            draw_model_panel(ax, fields, key)
            all_fields.append(fields)
        else:
            draw_empty_panel(ax, key)

    # Consensus panel (bottom, spanning both columns)
    ax_consensus = fig.add_subplot(gs[2, :])
    if len(all_fields) >= 2:
        consensus = build_consensus(all_fields)
        draw_consensus_panel(ax_consensus, consensus, all_fields)
    else:
        ax_consensus.axis('off')
        ax_consensus.text(0.5, 0.5, 'Need 2+ models for consensus', fontsize=14,
                          color=COLORS['gray'], ha='center', va='center')

    # Title
    fig.suptitle(f'{ticker} — Market Regime Forecast', fontsize=22, fontweight='bold',
                 color=COLORS['fg'], y=0.98)

    # As-of date
    for key in model_keys:
        data = results.get(key)
        if data and 'as_of_date' in data:
            fig.text(0.5, 0.005, f'As of {data["as_of_date"]}', fontsize=10,
                     color=COLORS['gray'], ha='center', va='bottom')
            break

    output_file = output_dir / f"{ticker}_regime_analysis.png"
    save_figure(fig, output_file, dpi=300)
    print(f"  Saved to {output_file}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Visualize Market Regime Forecast results")
    parser.add_argument('--basic', type=str, help='Basic model JSON output file')
    parser.add_argument('--ms-garch', type=str, help='MS-GARCH model JSON output file')
    parser.add_argument('--bocpd', type=str, help='BOCPD model JSON output file')
    parser.add_argument('--gp', type=str, help='GP model JSON output file')
    parser.add_argument('--output-dir', type=str,
                        default='pricing/market_regime_forecast/output',
                        help='Output directory for plots')
    parser.add_argument('--ticker', type=str, default='SPY', help='Ticker for plot title')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    for key, path_str in [('basic', args.basic), ('ms_garch', getattr(args, 'ms_garch', None)),
                           ('bocpd', args.bocpd), ('gp', args.gp)]:
        if path_str:
            data = load_model_result(Path(path_str))
            if data:
                display_key = key.replace('_', '-')
                results[display_key] = data

    if not results:
        print("No model results provided. Use --basic, --ms-garch, --bocpd, --gp")
        return 1

    ticker = args.ticker
    for data in results.values():
        if 'ticker' in data:
            ticker = data['ticker']
            break

    plot_regime_comparison(results, output_dir, ticker)
    print("\nVisualization complete")
    return 0


if __name__ == '__main__':
    exit(main())
