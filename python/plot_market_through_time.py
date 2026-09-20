"""Draw the two medians through time (37): the market's p_below_anchor_path and the
belief's probability_overpaid, per panel date, over the dates that have a market-implied
block; the dates without one are left blank and named in the caption.

    uv run python/plot_market_through_time.py [--panel output/pit/panel.jsonl] [--out output/pit/market_through_time.png]

No statistic: two lines of medians, read by eye."""

# pyright: reportUnknownMemberType=false
# matplotlib's Axes methods take **kwargs typed as Unknown; every call here passes only named, typed arguments.
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
PANEL = REPO_ROOT / "output" / "pit" / "panel.jsonl"
PNG = REPO_ROOT / "output" / "pit" / "market_through_time.png"


def medians(rows: list[dict[str, object]]) -> tuple[list[tuple[date, float, float | None]], list[date]]:
    """Per date with a block: (date, median p_below_anchor_path, median probability_overpaid
    over the names with both, None when none has a belief); and the dates without a block."""
    by_date: dict[date, list[dict[str, object]]] = {}
    for r in rows:
        by_date.setdefault(date.fromisoformat(str(r["as_of"])), []).append(r)
    with_block: list[tuple[date, float, float | None]] = []
    blank: list[date] = []
    for d in sorted(by_date):
        block = [r for r in by_date[d] if isinstance(r.get("p_below_anchor_path"), float)]
        if not block:
            blank.append(d)
            continue
        market = statistics.median(float(r["p_below_anchor_path"]) for r in block)  # pyright: ignore[reportArgumentType]
        beliefs = [float(r["probability_overpaid"]) for r in block if isinstance(r.get("probability_overpaid"), float)]  # pyright: ignore[reportArgumentType]
        with_block.append((d, market, statistics.median(beliefs) if beliefs else None))
    return with_block, blank


def draw(points: list[tuple[date, float, float | None]], blank: list[date], png: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    dates = np.array([d for d, _, _ in points], dtype="datetime64[D]")
    ax.plot(dates, np.array([m for _, m, _ in points]), marker="o", color="tab:blue", label="median p_below_anchor_path (market, risk-neutral)")
    belief_dates = np.array([d for d, _, b in points if b is not None], dtype="datetime64[D]")
    ax.plot(belief_dates, np.array([b for _, _, b in points if b is not None]), marker="s", color="tab:orange", label="median probability_overpaid (declared belief)")
    ax.set_ylim(-0.02, 1.02)
    ax.set_ylabel("probability")
    ax.set_xlabel("panel date")
    ax.set_title("the market's belief and the declared belief through time: medians per panel date")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    caption = (f"dates without a market-implied block, left blank: {', '.join(d.isoformat() for d in blank)}" if blank else "every panel date has a block")
    caption += ". Risk-neutral: the market's number embeds its risk pricing and is not a forecast. No statistic."
    fig.text(0.01, 0.01, caption, fontsize=8, wrap=True)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(png, dpi=120)
    plt.close(fig)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", type=Path, default=PANEL)
    parser.add_argument("--out", type=Path, default=PNG)
    args = parser.parse_args(argv)
    panel: Path = args.panel
    out: Path = args.out
    rows = [json.loads(line) for line in panel.read_text().splitlines() if line.strip()]
    points, blank = medians([{str(k): v for k, v in r.items()} for r in rows])  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType, reportUnknownMemberType]
    if not points:
        print("no panel date has a market-implied block; nothing to draw", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    draw(points, blank, out)
    for d, m, b in points:
        print(f"{d}: market {m:.2f}, belief {'none' if b is None else f'{b:.2f}'}")
    print(f"blank: {', '.join(d.isoformat() for d in blank) or 'none'} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
