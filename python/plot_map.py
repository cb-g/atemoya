"""Draw a name's belief map (23): fair value over growth held for N years, the price
contour, and a vertical line at the observed starting growth.

    uv run python/plot_map.py TICKER [--out output]

Reads output/maps/TICKER.json, written by the batch, and writes output/maps/TICKER.png.
Python owns visualisation; nothing in the batch imports this or matplotlib."""

# pyright: reportUnknownMemberType=false
# matplotlib's Axes methods take **kwargs typed as Unknown; every call here passes only named, typed arguments.
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LogNorm  # noqa: E402

import boundary  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def draw(grid: boundary.BeliefGrid, png: Path) -> None:
    growth = np.array(grid.growth_grid) * 100.0
    years = np.array(grid.horizon_grid, dtype=float)
    values = np.array(grid.fair_values, dtype=float)  # rows: growth, columns: years
    positive = np.where(values > 0, values, np.nan)
    fig, ax = plt.subplots(figsize=(9, 6))
    mesh = ax.pcolormesh(growth, years, positive.T, shading="nearest", cmap="viridis",
                         norm=LogNorm(vmin=float(np.nanmin(positive)), vmax=float(np.nanmax(positive))))
    fig.colorbar(mesh, ax=ax, label="fair value per share (log scale)")
    contour_g = [p.growth.value * 100.0 if p.growth.value is not None else np.nan for p in grid.price_contour]
    contour_n = [float(p.years) for p in grid.price_contour]
    ax.plot(contour_g, contour_n, color="white", linewidth=2.0, label=f"price contour ({grid.price:.2f})")
    ax.axvline(grid.observed_growth * 100.0, color="orange", linestyle="--", linewidth=1.5,
               label=f"observed starting growth ({grid.observed_growth * 100:.1f}%)")
    ax.set_xlabel("growth held, % per year (no decay)")
    ax.set_ylabel("years held, then terminal")
    ax.set_title(f"{grid.ticker}: {grid.map_model}")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(png, dpi=120)
    plt.close(fig)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ticker")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "output", help="the batch's --out directory")
    args = parser.parse_args(argv)
    ticker: str = args.ticker
    out: Path = args.out
    source = out / "maps" / f"{ticker}.json"
    if not source.exists():
        print(f"{source} does not exist: the batch writes it for an Ok record on a growth-then-terminal path", file=sys.stderr)
        return 2
    grid = boundary.BeliefGrid.from_json_string(source.read_text())
    png = out / "maps" / f"{ticker}.png"
    draw(grid, png)
    print(f"{png}: {len(grid.growth_grid)} growth levels x {len(grid.horizon_grid)} horizons, price {grid.price}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
