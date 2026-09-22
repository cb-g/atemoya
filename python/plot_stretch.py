"""Draw two years of closes with the 50- and 200-day averages, shaded where either stretch
count reached 3 (52).

    uv run python/plot_stretch.py PLTR [--out output/stretch]"""

# pyright: reportUnknownMemberType=false
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import pit  # noqa: E402
import stretch  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ticker")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "output" / "stretch")
    args = parser.parse_args(argv)
    t = stretch.load_thresholds()
    h = pit.History.fetch(args.ticker)
    days = sorted(h.closes)
    closes = [h.closes[d] for d in days]
    window = days[-t.history_trading_days:]
    def ma(n: int, i: int) -> float:
        return sum(closes[i - n + 1:i + 1]) / n if i + 1 >= n else float("nan")

    idx = {d: i for i, d in enumerate(days)}
    shaded: list[date] = []
    for d in window:
        block, _ = stretch.compute(h.closes, h.volumes, d, t)
        if block is not None and (block.stretch_low >= 3 or block.stretch_high >= 3):
            shaded.append(d)
    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.array(window, dtype="datetime64[D]")
    ax.plot(x, [closes[idx[d]] for d in window], color="black", linewidth=1.0, label="close, split-corrected as served")
    ax.plot(x, [ma(50, idx[d]) for d in window], color="tab:blue", linewidth=0.9, label="50-day average")
    ax.plot(x, [ma(200, idx[d]) for d in window], color="tab:orange", linewidth=0.9, label="200-day average")
    for d in shaded:
        x0 = float(mdates.date2num(d))  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
        ax.axvspan(x0, x0 + 1.0, color="tab:red", alpha=0.15, linewidth=0)
    ax.set_title(f"{args.ticker}: two years of closes; shaded where stretch_low or stretch_high reached 3 ({len(shaded)} days)")
    ax.set_ylabel("close")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=8)
    fig.text(0.01, 0.01, f"thresholds reference/stretch.json as of {t.as_of}; a count of measures beyond declared thresholds, no signal and no claim about what follows.", fontsize=7)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    args.out.mkdir(parents=True, exist_ok=True)
    png = args.out / f"{args.ticker}.png"
    fig.savefig(png, dpi=120)
    plt.close(fig)
    print(f"{args.ticker}: {len(shaded)} shaded days -> {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
