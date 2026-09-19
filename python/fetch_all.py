"""Fetch every ticker in reference/universe.json into a dated snapshot.

    uv run python/fetch_all.py [--universe FILE] [--out DIR]
    uv run python/fetch_all.py --as-of 2025-06-30          # point-in-time (17) -> data/pit/2025-06-30/
    uv run python/fetch_all.py --universe data/universe.private.json --snapshots data/snapshots-private   # a second, untracked universe (21)

Without --out the fetch lands in data/snapshots/<YYYY-MM-DD>/ (the fetch date, UTC; a
second fetch on the same date gets a -2, -3 suffix, a snapshot is never overwritten) and
data/financials becomes a symlink to it, so the batch's default input is always the latest
snapshot and every earlier one stays valuable by path. The shadow-yfinance records are part
of the snapshot. A second universe file in the same four-field format (a private one under
data/, never tracked) is fetched with --universe and its own --snapshots root; only the
default root moves data/financials. This is the fetch half of the batch; fetch.py decides
the statements provider per ticker. Valuation is the other half and never refetches:

    dune exec atemoya -- data/financials --out output
    dune exec atemoya -- data/snapshots/2026-09-19-2 --out output \
        --baseline output/run-2026-09-19/valuations.jsonl --baseline-snapshot data/snapshots/2026-09-19
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import fetch
import pit
import universe as universe_file

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
    parser.add_argument("--snapshots", type=Path, default=SNAPSHOTS, help="the dated-snapshot root; data/financials follows only the default root")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None, help="point-in-time: value as of this past date from what was known then")
    args = parser.parse_args(argv)
    universe_path: Path = args.universe
    out: Path | None = args.out
    as_of: date | None = args.as_of
    snapshots: Path = args.snapshots
    tickers = [e.ticker for e in universe_file.load(universe_path).tickers]
    print(f"{len(tickers)} tickers from {universe_path}")
    if as_of is not None:
        written = pit.run_date(as_of, tickers, histories={}, quotes={}, sec=fetch.SecContext())
        print(f"point-in-time {as_of}: {written} (batch: dune exec atemoya -- {written} --reference {written}/reference --today {as_of} --out output/pit/{as_of})")
        return 0
    if out is None:
        out = snapshot_dir(datetime.now(timezone.utc).strftime("%Y-%m-%d"), snapshots)
        code = fetch.main([*tickers, "--out", str(out), "--universe", str(universe_path)])
        if code == 0 and snapshots == SNAPSHOTS:
            point_latest(out)
            print(f"snapshot {out}; data/financials -> {os.readlink(LATEST) if LATEST.is_symlink() else LATEST}")
        elif code == 0:
            print(f"snapshot {out}; data/financials left alone (not the default snapshot root)")
        return code
    return fetch.main([*tickers, "--out", str(out), "--universe", str(universe_path)])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
