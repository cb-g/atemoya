import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm
from datetime import datetime
import matplotlib.gridspec as gridspec

### single-asset plots

csv_path = "data/val/dcf/output_of_probabilistic.csv"
sim_paths = {
    "fcfe": "data/val/dcf/output_simulations_fcfe.csv",
    "fcff": "data/val/dcf/output_simulations_fcff.csv"
}
output_dir = "fig/val/dcf_probabilistic/single_asset"
os.makedirs(output_dir, exist_ok=True)

plt.style.use("dark_background")
cmap = plt.colormaps.get_cmap("magma")

curve_color = cmap(0.8)
price_color = cmap(0.95)

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

df = pd.read_csv(csv_path, dtype=str)
sim_dfs = {
    model: pd.read_csv(path, dtype=str)
    for model, path in sim_paths.items()
}

for _, row in df.iterrows():
    ticker = row['ticker']

    for model in ['fcfe', 'fcff']:
        try:
            ivps = float(row[f'ivps_{model}'])
            std_total = float(row[f'std_{model}']) # std dev of intrinsic value (per share)
            price = float(row['price']) # market price
            dist = row[f'{model}_distribution'].strip().lower()
        except Exception:
            continue

        if dist != "gaussian":
            continue

        std = std_total  # already per-share

        # ----- intrinsic value distribution plot -----
        sim_df = sim_dfs[model]
        if ticker not in sim_df.columns:
            continue
        sims = sim_df[ticker].dropna().astype(float)
        if sims.empty or len(sims) < 10:
            continue

        from scipy.stats import gaussian_kde

        kde = gaussian_kde(sims, bw_method="scott")
        x = np.linspace(np.percentile(sims, 0.5), np.percentile(sims, 99.5), 1000)
        y = kde(x)


        fig, ax = plt.subplots(figsize=(8, 6))
        ax.plot(x, y, lw=2, color=curve_color, label='Intrinsic Value Distribution')
        ax.axvline(price, color=price_color, linestyle='--', lw=2, label=f"Market Price = ${price:.2f}")

        ax.set_title(f"{ticker} Intrinsic Value Distribution ({model.upper()})", fontsize=13)
        ax.set_xlabel("Intrinsic Value ($)", fontsize=11)
        ax.set_ylabel("Probability Density", fontsize=11)
        ax.legend(fontsize=9)
        ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.5)

        # compute probability asset is undervalued (in $ space)
        surplus_abs_mean = ivps - price
        prob_undervalued_abs = (sims > price).mean()
        prob_overvalued_abs = 1 - prob_undervalued_abs

        annotation_text_abs = (
            f"P(value surplus > 0): {prob_undervalued_abs:.1%}\n"
            f"P(value surplus < 0): {prob_overvalued_abs:.1%}"
        )

        ax.annotate(annotation_text_abs,
                    xy=(0.05, 0.95),
                    xycoords="axes fraction",
                    fontsize=10,
                    color=curve_color,
                    verticalalignment="top",
                    bbox=dict(boxstyle="round,pad=0.4",
                              fc="black",
                              ec=curve_color,
                              alpha=0.7))

        plt.tight_layout()

        base_name = f"{ticker}_{model}_{timestamp}"
        pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
        svg_path = os.path.join(output_dir, f"{base_name}.svg")

        plt.savefig(pdf_path, facecolor=fig.get_facecolor())
        plt.savefig(svg_path, facecolor=fig.get_facecolor())
        plt.close()

        # ----- value surplus percentage distribution -----
        # calculate surplus % mean and std
        surplus_pct_mean = (ivps - price) / price * 100
        surplus_pct_std = std / price * 100

        # compute probability of being undervalued / overvalued
        surplus_pct_sims = (sims - price) / price * 100
        kde_pct = gaussian_kde(surplus_pct_sims, bw_method="scott")
        x_pct = np.linspace(np.percentile(surplus_pct_sims, 0.5),
                            np.percentile(surplus_pct_sims, 99.5), 1000)
        y_pct = kde_pct(x_pct)

        prob_undervalued = (surplus_pct_sims > 0).mean()
        prob_overvalued = 1 - prob_undervalued

        fig2, ax2 = plt.subplots(figsize=(8, 6))
        ax2.plot(x_pct, y_pct, lw=2, color=curve_color, label='Value Surplus % Distribution')
        ax2.axvline(0, color=price_color, linestyle='--', lw=2, label="Market Price (0%)")

        # annotate probability
        annotation_text = (
            f"P(value surplus > 0): {prob_undervalued:.1%}\n"
            f"P(value surplus < 0): {prob_overvalued:.1%}"
        )
        ax2.annotate(annotation_text,
                     xy=(0.05, 0.95),
                     xycoords="axes fraction",
                     fontsize=10,
                     color=curve_color,
                     verticalalignment="top",
                     bbox=dict(boxstyle="round,pad=0.4",
                               fc="black",
                               ec=curve_color,
                               alpha=0.7))

        ax2.set_title(f"{ticker} Value Surplus (% of Price) ({model.upper()})", fontsize=13)
        ax2.set_xlabel("Value Surplus (%)", fontsize=11)
        ax2.set_ylabel("Probability Density", fontsize=11)
        ax2.legend(fontsize=9)
        ax2.grid(True, linestyle=":", linewidth=0.5, alpha=0.5)
        plt.tight_layout()

        base_name_pct = f"{ticker}_{model}_pct_{timestamp}"
        pdf_pct_path = os.path.join(output_dir, f"{base_name_pct}.pdf")
        svg_pct_path = os.path.join(output_dir, f"{base_name_pct}.svg")

        plt.savefig(pdf_pct_path, facecolor=fig2.get_facecolor())
        plt.savefig(svg_pct_path, facecolor=fig2.get_facecolor())
        plt.close()


def generate_multi_asset_plots(model: str):

    sim_path = f"data/val/dcf/output_simulations_{model}.csv"
    price_path = "data/val/dcf/market_prices.csv"
    output_dir = "fig/val/dcf_probabilistic/multi_asset"
    os.makedirs(output_dir, exist_ok=True)

    plt.style.use("dark_background")
    cmap = plt.colormaps.get_cmap("magma")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    sim_df = pd.read_csv(sim_path)
    price_df = pd.read_csv(price_path, dtype=str)
    price_df["price"] = price_df["price"].astype(float)

    tickers = sim_df.columns.tolist()
    prices = price_df.set_index("ticker").loc[tickers]["price"].values

    sim_matrix = sim_df.to_numpy()
    surplus_pct = (sim_matrix - prices) / prices

    mu = surplus_pct.mean(axis=0)
    cov = np.cov(surplus_pct, rowvar=False)
    n_assets = len(tickers)
    n_portfolios = 10_000

    # === Plot 1: μ vs σ ===
    weights_sigma = np.random.dirichlet(np.ones(n_assets), size=n_portfolios)
    port_returns_sigma = weights_sigma @ mu
    port_risks_sigma = np.sqrt(np.einsum('ij,jk,ik->i', weights_sigma, cov, weights_sigma))

    idx_min_risk = np.argmin(port_risks_sigma)
    idx_max_return_sigma = np.argmax(port_returns_sigma)

    key_indices_sigma = {
        "min-risk": idx_min_risk,
        "max-return": idx_max_return_sigma
    }

    key_colors_sigma = {
        "min-risk": cmap(0.4),
        "max-return": cmap(0.8)
    }

    marker_styles = {
        "min-risk": "s",
        "max-return": "^",
        "min-prob-loss": "D"
    }

    # analytic efficient frontier
    inv_cov = np.linalg.inv(cov)
    ones = np.ones(n_assets)

    w_min_var = inv_cov @ ones
    w_min_var /= ones @ inv_cov @ ones
    mu_mv = w_min_var @ mu
    sigma_mv = np.sqrt(w_min_var @ cov @ w_min_var)

    def solve_efficient_portfolio(mu_target):
        A = ones @ inv_cov @ ones
        B = ones @ inv_cov @ mu
        C = mu @ inv_cov @ mu
        D = A * C - B ** 2

        lambda1 = (C - B * mu_target) / D
        lambda2 = (A * mu_target - B) / D

        weights = lambda1 * (inv_cov @ ones) + lambda2 * (inv_cov @ mu)
        return weights

    mu_targets = np.linspace(mu_mv, max(mu) * 0.99, 200)
    frontier_returns, frontier_risks = [], []
    for mu_tgt in mu_targets:
        w = solve_efficient_portfolio(mu_tgt)
        frontier_returns.append(w @ mu)
        frontier_risks.append(np.sqrt(w @ cov @ w))

    # --- plot: efficient frontier ---
    fig = plt.figure(figsize=(13, 6))
    gs = gridspec.GridSpec(1, 2, width_ratios=[3, 1])
    ax1 = fig.add_subplot(gs[0])

    sc1 = ax1.scatter(port_risks_sigma, port_returns_sigma,
                      c=port_returns_sigma / port_risks_sigma,
                      cmap=cmap, s=4, alpha=0.7)
    ax1.plot(frontier_risks, frontier_returns, color='white', lw=1.8, label="Analytic Efficient Frontier")

    ax1.scatter(sigma_mv, mu_mv, s=90, color='cyan', marker='X', zorder=5)
    ax1.annotate("analytic min-risk",
                 xy=(sigma_mv, mu_mv),
                 xytext=(sigma_mv + 0.03, mu_mv - 0.5),
                 fontsize=9, color='cyan', fontweight='bold',
                 arrowprops=dict(arrowstyle="->", lw=0.8, color='cyan'))

    x_span = port_risks_sigma.max() - port_risks_sigma.min()
    y_span = port_returns_sigma.max() - port_returns_sigma.min()

    for label, idx in key_indices_sigma.items():
        x, y = port_risks_sigma[idx], port_returns_sigma[idx]
        ax1.scatter(x, y, s=80, color=key_colors_sigma[label], marker=marker_styles[label])

        # scaled offsets for clock-like label placement
        if label == "max-return":
            dx, dy = -0.2 * x_span, 0.1 * y_span
        elif label == "min-risk":
            dx, dy = 0.0 * x_span, 0.25 * y_span
        else:
            dx, dy = 0.05 * x_span, 0.0 * y_span

        ax1.annotate(label,
                    xy=(x, y),
                    xytext=(x + dx, y + dy),
                    fontsize=9,
                    color=key_colors_sigma[label],
                    fontweight='bold',
                    ha='center' if dx == 0 else 'right',
                    va='bottom',
                    arrowprops=dict(
                        arrowstyle="->",
                        lw=0.8,
                        color=key_colors_sigma[label],
                        shrinkA=0,
                        shrinkB=0
                    ))

    ax1.set_title(f"Efficient Frontier (μ vs σ) – {model.upper()}", fontsize=14)
    ax1.set_xlabel("Intrinsic Value Risk (σ)", fontsize=12)
    ax1.set_ylabel("Expected Value Surplus Return (μ)", fontsize=12)
    ax1.grid(True, linestyle=":", alpha=0.5)
    cb1 = fig.colorbar(sc1, ax=ax1)
    cb1.set_label("Sharpe-like Ratio (μ / σ)", fontsize=10)

    # side panel
    ax_text = fig.add_subplot(gs[1])
    ax_text.axis("off")

    for i, (label, idx) in enumerate(key_indices_sigma.items()):
        w = weights_sigma[idx]
        summary = "\n".join(f"{tickers[j]}: {100*w[j]:.2f}%" for j in range(n_assets))
        ax_text.text(0.01, 1.0 - 0.34 * i, f"{label}:\n{summary}",
                     fontsize=9, color=key_colors_sigma[label], va="top")

    summary_mv = "\n".join(f"{tickers[j]}: {100*w_min_var[j]:.2f}%" for j in range(n_assets))
    ax_text.text(0.01, 1.0 - 0.34 * len(key_indices_sigma), "analytic min-risk:\n" + summary_mv,
                 fontsize=9, color='cyan', va="top")

    plt.tight_layout()
    plt.savefig(f"{output_dir}/efficient_frontier_stddev_{model}_{timestamp}.pdf", facecolor=fig.get_facecolor())
    plt.savefig(f"{output_dir}/efficient_frontier_stddev_{model}_{timestamp}.svg", facecolor=fig.get_facecolor())
    plt.close()

    # --- plot 2: probability of value surplus < 0 ---
    weights_prob = np.random.dirichlet(np.ones(n_assets), size=n_portfolios)
    port_returns_prob = weights_prob @ mu
    portfolio_surplus_paths = surplus_pct @ weights_prob.T
    p_negative = (portfolio_surplus_paths < 0).mean(axis=0)

    mask = p_negative > 1e-6
    p_negative_valid = p_negative[mask]
    port_returns_valid = port_returns_prob[mask]
    weights_valid = weights_prob[mask]

    ratio = port_returns_valid / (p_negative_valid + 1e-4)
    tail_sharpelike_ratio = np.sign(ratio) * np.log1p(np.abs(ratio))

    idx_min_prob_neg = np.argmin(p_negative_valid)
    idx_max_return_prob = np.argmax(port_returns_valid)

    key_indices_prob = {
        "min-prob-loss": idx_min_prob_neg,
        "max-return": idx_max_return_prob
    }

    key_colors_prob = {
        "min-prob-loss": cmap(1.0),
        "max-return": cmap(0.8)
    }

    fig = plt.figure(figsize=(13, 6))
    gs = gridspec.GridSpec(1, 2, width_ratios=[3, 1])
    ax2 = fig.add_subplot(gs[0])

    sc2 = ax2.scatter(p_negative_valid, port_returns_valid,
                      c=tail_sharpelike_ratio,
                      cmap=cmap, s=4, alpha=0.7)

    x_span = p_negative_valid.max() - p_negative_valid.min()
    y_span = port_returns_valid.max() - port_returns_valid.min()

    for label, idx in key_indices_prob.items():
        x, y = p_negative_valid[idx], port_returns_valid[idx]
        ax2.scatter(x, y, s=80, color=key_colors_prob[label], marker=marker_styles[label])

        # scaled offsets for clock positions
        if label == "max-return":
            dx, dy = 0.3 * x_span, 0.0 * y_span
        elif label == "min-prob-loss":
            dx, dy = 0.3 * x_span, 0.0 * y_span
        else:
            dx, dy = 0.1 * x_span, 0.0 * y_span

        ax2.annotate(label,
                    xy=(x, y),
                    xytext=(x + dx, y + dy),
                    fontsize=9,
                    color=key_colors_prob[label],
                    fontweight='bold',
                    ha='center' if dx == 0 else 'right',
                    va='bottom',
                    arrowprops=dict(
                        arrowstyle="->",
                        lw=0.8,
                        color=key_colors_prob[label],
                        shrinkA=0,
                        shrinkB=0
                    ))

    ax2.set_title(f"μ vs P(Value Surplus < 0) – {model.upper()}", fontsize=14)
    ax2.set_xlabel("Probability Value Surplus < 0", fontsize=12)
    ax2.set_ylabel("Expected Value Surplus Return (μ)", fontsize=12)
    ax2.grid(True, linestyle=":", alpha=0.5)
    cb2 = fig.colorbar(sc2, ax=ax2)
    cb2.set_label("signed log(1 + |μ / P(VS < 0)|)", fontsize=10)

    ax_text = fig.add_subplot(gs[1])
    ax_text.axis("off")
    for i, (label, idx) in enumerate(key_indices_prob.items()):
        w = weights_valid[idx]
        summary = "\n".join(f"{tickers[j]}: {100*w[j]:.2f}%" for j in range(n_assets))
        ax_text.text(0.01, 1.0 - 0.34 * i, f"{label}:\n{summary}",
                     fontsize=9, color=key_colors_prob[label], va="top")

    plt.tight_layout()
    plt.savefig(f"{output_dir}/efficient_frontier_probability_{model}_{timestamp}.pdf", facecolor=fig.get_facecolor())
    plt.savefig(f"{output_dir}/efficient_frontier_probability_{model}_{timestamp}.svg", facecolor=fig.get_facecolor())
    plt.close()


for model in ['fcfe', 'fcff']:
    generate_multi_asset_plots(model)
