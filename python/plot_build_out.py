"""Draw a name's build-out readout (60): value per share over what the new capital earns and
how long it takes to earn it, with the price as a contour and a vertical line at the
declared return.

    uv run python/plot_build_out.py TICKER [--out output]

Reads the valuation record's build_out block from the batch's valuations.jsonl and writes
output/build_out/TICKER.png. It draws a map of what the price requires, never a value: the
record it comes from is Failed and stays so. Python owns visualisation; nothing in the batch
imports this or matplotlib."""

# pyright: reportUnknownMemberType=false
# matplotlib's Axes methods take **kwargs typed as Unknown; every call here passes only named, typed arguments.
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import boundary  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def draw(ticker: str, price: float, block: boundary.BuildOut, png: Path) -> None:
    returns = np.array(block.returns) * 100.0
    lags = np.array([row.lag_years for row in block.surface], dtype=float)
    values = np.array([row.value_per_share for row in block.surface], dtype=float)  # rows: lag, columns: return
    fig, ax = plt.subplots(figsize=(9, 6))
    mesh = ax.pcolormesh(returns, lags, values, shading="nearest", cmap="viridis")
    fig.colorbar(mesh, ax=ax, label="value per share")
    drawn = [(c.return_required * 100.0, float(c.lag_years)) for c in block.price_contour
             if c.return_required is not None]
    if drawn:
        ax.plot([r for r, _ in drawn], [l for _, l in drawn], color="white", linewidth=2.0,
                label=f"price contour ({price:.2f})")
    else:
        # A contour the surface never reaches is the readout, not a gap: say so on the picture.
        ax.plot([], [], color="white", linewidth=2.0, label=f"price {price:.2f} outside the map at every lag")
    ax.axvline(block.declared_return.value * 100.0, color="orange", linestyle="--", linewidth=1.5,
               label=f"declared return ({block.declared_return.value * 100:.1f}%)")
    ax.axhline(block.declared_lag_years.value, color="orange", linestyle=":", linewidth=1.5,
               label=f"declared lag ({block.declared_lag_years.value:.0f} years)")
    # (63) the axis is in the units the declaration is in: after depreciation, as a filing states it
    ax.set_xlabel("after-tax return on the new capital, after depreciation, % per year")
    ax.set_ylabel("years from spend to first earning")
    growth = sum(t.growth_capex for t in block.tranches)
    ax.set_title(f"{ticker}: {growth / 1e9:,.1f}bn of growth capex over {len(block.tranches)} year(s); "
                 f"standing business {block.standing_business_per_share:,.2f} per share\n"
                 f"declared {block.declared_return.value * 100:.0f}% after depreciation = "
                 f"{block.cash_return * 100:.1f}% of cash yield against a "
                 f"{block.depreciation_to_capital * 100:.1f}% maintenance charge", fontsize=10)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(png, dpi=120)
    plt.close(fig)


def find(records: Path, ticker: str) -> boundary.Valuation | None:
    for line in records.read_text().splitlines():
        if not line.strip():
            continue
        if json.loads(line).get("ticker") == ticker:
            return boundary.Valuation.from_json_string(line)
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ticker")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "output", help="the batch's --out directory")
    args = parser.parse_args(argv)
    ticker: str = args.ticker
    out: Path = args.out
    records = out / "valuations.jsonl"
    if not records.exists():
        print(f"{records} does not exist: run the batch with --out {out} first", file=sys.stderr)
        return 2
    record = find(records, ticker)
    if record is None:
        print(f"{records} carries no record for {ticker}", file=sys.stderr)
        return 2
    if record.build_out is None:
        print(f"{ticker} has no build-out readout: {record.build_out_reason or 'the record is not one this readout is about'}",
              file=sys.stderr)
        return 2
    png = out / "build_out" / f"{ticker}.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    draw(ticker, record.price if record.price is not None else float("nan"), record.build_out, png)
    reached = [c for c in record.build_out.price_contour if c.return_required is not None]
    print(f"{png}: {len(record.build_out.returns)} returns x {len(record.build_out.surface)} lags, "
          f"price contour on {len(reached)} of {len(record.build_out.price_contour)} lags")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
