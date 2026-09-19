"""Fetch every ticker in reference/universe.json into a dated snapshot.

    uv run python/fetch_all.py [--universe FILE] [--out DIR]

Without --out the fetch lands in data/snapshots/<YYYY-MM-DD>/ (the fetch date, UTC; a
second fetch on the same date gets a -2, -3 suffix, a snapshot is never overwritten) and
data/financials becomes a symlink to it, so the batch's default input is always the latest
snapshot and every earlier one stays valuable by path. The shadow-yfinance records are part
of the snapshot. This is the fetch half of the batch; fetch.py decides the statements
provider per ticker. Valuation is the other half and never refetches:

    dune exec atemoya -- data/financials --out output
    dune exec atemoya -- data/snapshots/2026-09-19-2 --out output \
        --baseline output/run-2026-09-19/valuations.jsonl --baseline-snapshot data/snapshots/2026-09-19
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import fetch
import reference

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UNIVERSE = REPO_ROOT / "reference" / "universe.json"
SNAPSHOTS = REPO_ROOT / "data" / "snapshots"
LATEST = REPO_ROOT / "data" / "financials"


def snapshot_dir(today: str, root: Path = SNAPSHOTS) -> Path:
    """data/snapshots/<date>, or <date>-2, -3 ... when the date already has one."""
    candidate = root / today
    n = 2
    while candidate.exists():
        candidate = root / f"{today}-{n}"
        n += 1
    return candidate


def point_latest(snapshot: Path, latest: Path = LATEST) -> None:
    """data/financials -> the snapshot, as a relative symlink; a real directory there is
    left alone and reported, never replaced."""
    if latest.is_symlink():
        latest.unlink()
    elif latest.exists():
        print(f"{latest} is a directory, not a symlink; left in place. The snapshot is {snapshot}")
        return
    latest.symlink_to(os.path.relpath(snapshot, latest.parent))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--out", type=Path, default=None, help="a directory instead of a dated snapshot")
    args = parser.parse_args(argv)
    universe_path: Path = args.universe
    out: Path | None = args.out
    universe = reference.Universe.from_json_string(universe_path.read_text())
    tickers = [e.ticker for e in universe.tickers]
    print(f"{len(tickers)} tickers from {universe_path}")
    if out is None:
        out = snapshot_dir(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        code = fetch.main([*tickers, "--out", str(out)])
        if code == 0:
            point_latest(out)
            print(f"snapshot {out}; data/financials -> {os.readlink(LATEST) if LATEST.is_symlink() else LATEST}")
        return code
    return fetch.main([*tickers, "--out", str(out)])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
