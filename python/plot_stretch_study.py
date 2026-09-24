"""(67) The study's forward excess at +60 by side and insider state, as strip plots with the
medians marked and the counts in the labels.

    uv run python/plot_stretch_study.py [--out output/stretch_study]

Reads output/stretch_study/episodes.jsonl, written by the study. A picture of a sample,
not of a result: every point is one episode, the median is a line, and nothing is fitted."""

# pyright: reportUnknownMemberType=false
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import stretch_study as study  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
HORIZON = "60"
STATES = ("bought", "sold", "neither", "unknown")
# unknown is not neither: one is a window read in full that held nothing, the other a window
# that could not be read at all, and a shared colour would say they were the same answer
COLOURS = {"bought": "tab:green", "sold": "tab:purple", "neither": "tab:gray", "unknown": "tab:orange"}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=study.OUT)
    args = parser.parse_args(argv)
    source = args.out / "episodes.jsonl"
    if not source.exists():
        print(f"{source} does not exist: run the study first", file=sys.stderr)
        return 2
    rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    if not rows:
        print("no episodes", file=sys.stderr)
        return 2

    groups: list[tuple[str, str, list[float]]] = []
    for side in study.SIDES:
        for state in STATES:
            values = [r["excess"][HORIZON] for r in rows
                      if r["side"] == side and r["insider_state"] == state and r["excess"][HORIZON] is not None]
            if values:
                groups.append((f"{side}\ninsiders {state}\nn={len(values)}", state, values))

    fig, ax = plt.subplots(figsize=(max(8, 1.7 * len(groups)), 6))
    rng = np.random.default_rng(0)                      # a fixed jitter: the picture is deterministic
    for i, (_label, state, values) in enumerate(groups):
        x = i + rng.uniform(-0.16, 0.16, size=len(values))
        ax.scatter(x, values, s=14, alpha=0.55, color=COLOURS[state], edgecolors="none")
        med = statistics.median(values)
        ax.plot([i - 0.3, i + 0.3], [med, med], color="black", linewidth=2.0, zorder=3)
        ax.annotate(f"{med:+.3f}" if len(values) >= study.MIN_CELL else "",
                    (i, med), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8)
    ax.axhline(0.0, color="black", linewidth=0.8, alpha=0.5)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([label for label, _, _ in groups], fontsize=8)
    ax.set_ylabel(f"+{HORIZON}-trading-day return less {study.BENCHMARK} over the same dates")
    ax.set_title(f"Stretch episodes: what followed, by side and insider state ({len(rows)} episodes)")
    ax.grid(True, axis="y", alpha=0.3)
    fig.text(0.01, 0.01, "One point per episode; the bar is the median, printed only where the cell carries "
             f"at least {study.MIN_CELL}. Descriptive: no fitted model, no statistic the sample cannot carry.",
             fontsize=7)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    png = args.out / "forward_excess_60.png"
    fig.savefig(png, dpi=120)
    plt.close(fig)
    print(f"{len(rows)} episodes, {len(groups)} cells -> {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
