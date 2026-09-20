"""Beta evidence for a book (41): per holding, a two-year weekly regression beta to the
declared index from the vendor's closes, with its standard error and R-squared. Evidence
for the holder's declaration, which the hedge never reads.

    uv run python/beta.py book.json [--out output/hedge]

Writes output/hedge/<file>/betas.txt and prints it. Weekly returns are log returns between
the last closes of consecutive ISO weeks over the two years before the latest common
close; the vendor's closes are split-adjusted as served and self-consistent within a
series, which is all a return series needs (brief 17's rule concerns comparisons across
series)."""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path

import hedge_book
import pit

REPO_ROOT = Path(__file__).resolve().parent.parent
YEARS = 2


def weekly_closes(closes: Mapping[date, float], *, end: date, years: int = YEARS) -> dict[tuple[int, int], float]:
    """The last close of each ISO week in the window."""
    start = end - timedelta(days=365 * years)
    out: dict[tuple[int, int], float] = {}
    for d in sorted(closes):
        if start <= d <= end:
            y, w, _ = d.isocalendar()
            out[(y, w)] = closes[d]
    return out


def regression(asset: Mapping[date, float], index: Mapping[date, float]) -> tuple[float, float, float, int] | None:
    """(beta, standard error, r_squared, observations) of weekly log returns, ordinary least
    squares with an intercept; None with fewer than 20 common weeks."""
    end = min(max(asset), max(index))
    a, i = weekly_closes(asset, end=end), weekly_closes(index, end=end)
    weeks = sorted(set(a) & set(i))
    xs: list[float] = []
    ys: list[float] = []
    for prev, cur in zip(weeks, weeks[1:]):
        if a[prev] > 0 and a[cur] > 0 and i[prev] > 0 and i[cur] > 0:
            xs.append(math.log(i[cur] / i[prev]))
            ys.append(math.log(a[cur] / a[prev]))
    n = len(xs)
    if n < 20:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0:
        return None
    beta = sxy / sxx
    alpha = my - beta * mx
    residuals = [y - alpha - beta * x for x, y in zip(xs, ys)]
    sse = sum(r * r for r in residuals)
    syy = sum((y - my) ** 2 for y in ys)
    se = math.sqrt(sse / (n - 2) / sxx) if n > 2 else float("nan")
    r2 = 1.0 - sse / syy if syy > 0 else 0.0
    return beta, se, r2, n


def report(book: hedge_book.Book, histories: Mapping[str, pit.History]) -> str:
    lines = [f"beta evidence (41) against {book.index}: two-year weekly log-return regression with an intercept; evidence for the declaration beside it, never the sizing input", ""]
    lines.append(f"{'ticker':8} {'declared':>9} {'as_of':>11}  {'regression':>10} {'se':>7} {'r2':>6} {'weeks':>5}  why")
    index = histories[book.index].closes
    for h in book.holdings:
        r = regression(histories[h.ticker].closes, index) if h.ticker in histories else None
        declared = "none" if h.beta is None else f"{h.beta:.2f}"
        reg = "n/a" if r is None else f"{r[0]:.2f}"
        lines.append(f"{h.ticker:8} {declared:>9} {h.beta_as_of or '':>11}  {reg:>10} {'' if r is None else f'{r[1]:.2f}':>7} {'' if r is None else f'{r[2]:.2f}':>6} {'' if r is None else r[3]:>5}  {h.beta_why or ''}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("book", type=Path)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "output" / "hedge")
    args = parser.parse_args(argv)
    book = hedge_book.load_book(args.book)
    histories = {t: pit.History.fetch(t) for t in [book.index] + [h.ticker for h in book.holdings]}
    text = report(book, histories)
    out_dir: Path = args.out / args.book.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "betas.txt").write_text(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
