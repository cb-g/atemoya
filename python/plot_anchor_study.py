"""(80) The anchor study's year-ahead excess over SPY by margin-of-safety quintile, as strip
plots with the medians marked and the counts in the labels.

    uv run python/plot_anchor_study.py [--out output/anchor_study] [--horizon 252]

Reads output/anchor_study/records.jsonl, written by the study. A picture of a sample, not of
a result: every point is one (name, quarter-end) row, the median is a line, and nothing is
fitted. Refused rows are drawn as their own group so the reader sees what the refusals
preceded beside what the anchors did."""

# pyright: reportUnknownMemberType=false
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import cast

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import anchor_study as study  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("quintile 1", "quintile 2", "quintile 3", "quintile 4", "quintile 5", "refused")
COLOURS = {"quintile 1": "#b02a37", "quintile 2": "#c9784a", "quintile 3": "#6c757d", "quintile 4": "#4c8a6e", "quintile 5": "#1f6f8b", "refused": "#a0a0a0"}


def group_of(r: dict[str, object]) -> str | None:
    if r.get("status") == "Failed":
        return "refused"
    q = r.get("mos_quintile")
    return f"quintile {q}" if isinstance(q, int) else None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=study.OUT)
    parser.add_argument("--horizon", type=int, default=252)
    args = parser.parse_args(argv)
    out: Path = args.out
    horizon: int = args.horizon
    rows = [cast(dict[str, object], json.loads(l)) for l in (out / "records.jsonl").read_text().splitlines() if l.strip()]
    values: dict[str, list[float]] = {g: [] for g in GROUPS}
    for r in rows:
        g = group_of(r)
        x = cast(dict[str, object], r.get("excess") or {}).get(str(horizon))
        if g is not None and isinstance(x, (int, float)):
            values[g].append(float(x))
    rng = np.random.default_rng(80)   # the jitter is presentation, seeded so the picture repeats
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for k, g in enumerate(GROUPS):
        ys = values[g]
        if not ys:
            continue
        xs = k + rng.uniform(-0.28, 0.28, size=len(ys))
        ax.scatter(xs, ys, s=12, alpha=0.55, color=COLOURS[g], linewidths=0)
        if len(ys) >= study.MIN_CELL:
            med = statistics.median(ys)
            ax.hlines(med, k - 0.38, k + 0.38, color=COLOURS[g], linewidth=2.2)
    ax.axhline(0.0, color="#333333", linewidth=0.8)
    # the axis is cut at -1 and +2 so the anchors' strips are legible; every point beyond is
    # counted in the label rather than drawn, since one refused name's forty-fold year
    # would otherwise flatten five quintiles into a line
    ax.set_ylim(-1.0, 2.0)
    beyond = {g: sum(1 for y in values[g] if y > 2.0 or y < -1.0) for g in GROUPS}
    ax.set_xticks(range(len(GROUPS)))
    ax.set_xticklabels([f"{g}\nn={len(values[g])}" + (f", {beyond[g]} beyond the axis" if beyond[g] else "")
                        + (f"\nmedian {statistics.median(values[g]):+.3f}" if len(values[g]) >= study.MIN_CELL else "") for g in GROUPS], fontsize=8)
    ax.set_ylabel(f"excess over {study.BENCHMARK} at +{horizon} trading days")
    ax.set_title("What the anchors preceded (80): one point per name and quarter-end; the line is the median where ten or more; nothing fitted", fontsize=10)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.tight_layout()
    path = out / f"anchor_study_{horizon}.png"
    fig.savefig(path, dpi=130)
    sys.stdout.write(f"wrote {path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
