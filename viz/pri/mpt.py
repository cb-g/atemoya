import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

frontier_df = pd.read_csv("data/pri/mpt/efficient_frontier.csv")
markers_df = pd.read_csv("data/pri/mpt/example_portfolios.csv")
tickers = markers_df.columns[3:]

cmap = plt.colormaps.get_cmap("magma")
colors = {
    "efficient frontier": cmap(0.2),
    "min-risk": cmap(0.6),
    "mid-return": cmap(0.8),
    "max-return": cmap(1.0),
}

plt.style.use("dark_background")

fig, ax = plt.subplots(figsize=(9, 6))

ax.plot(frontier_df["Risk"], frontier_df["Return"],
        label="efficient frontier",
        color=colors["efficient frontier"],
        linewidth=2,
        zorder=1)

for _, row in markers_df.iterrows():
    label = row["Portfolio"]
    x = row["Risk"]
    y = row["Return"]
    weights = [float(row[t]) for t in tickers]
    pct_weights = [f"{t}: {w*100:.1f}%" for t, w in zip(tickers, weights)]
    annotation = "\n".join(pct_weights)

    ax.scatter(x, y, s=80, color=colors[label], label=label, zorder=3)
    ax.annotate(annotation,
                (x, y),
                textcoords="offset points",
                xytext=(12, 0),
                ha='left',
                va='center',
                fontsize=8,
                color=colors[label],
                bbox=dict(boxstyle="round,pad=0.3",
                          fc='black', ec=colors[label], lw=1, alpha=0.7))

ax.set_xlabel("annualized risk (σ)", fontsize=12)
ax.set_ylabel("annualized return (μ)", fontsize=12)
ax.xaxis.set_major_formatter(PercentFormatter(1.0))
ax.yaxis.set_major_formatter(PercentFormatter(1.0))

ax.set_title("efficient frontier portfolios under mean-variance optimization\n(short-selling allowed)", fontsize=14)
ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
ax.legend(loc="lower right", fontsize=9)
plt.tight_layout()

plt.savefig("fig/pri/mpt/frontier_with_allocations.pdf", facecolor=fig.get_facecolor())
plt.savefig("fig/pri/mpt/frontier_with_allocations.svg", facecolor=fig.get_facecolor())
