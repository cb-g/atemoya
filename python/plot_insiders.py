"""The stretch chart with what the insiders did on it (66): two years of closes with the
50- and 200-day averages, shaded where either stretch count reached 3, and every
open-market purchase and sale drawn at its price on its transaction date, sized by dollars.

    uv run python/plot_insiders.py PLTR [--out output/stretch]

Replaces the stretch-only chart at output/stretch/TICKER.png. Purchases and sales only:
an award, an exercise, a withholding or a gift is not drawn, because it is not a decision
about the price. No score and no signal; the reader sees where insiders acted relative to
the path and decides what it means."""

# pyright: reportUnknownMemberType=false
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import fetch  # noqa: E402
import fetch_sec  # noqa: E402
import insiders as insiders_mod  # noqa: E402
import pit  # noqa: E402
import stretch  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def transactions_for(ticker: str, as_of: date, days: int) -> list[insiders_mod.Transaction]:
    """Every open-market purchase and sale filed on or before [as_of] whose transaction date
    falls in the drawn window."""
    sec = fetch.SecContext()
    cik, _ = fetch.cik_of(ticker, sec.tickers, None)
    if cik is None:
        return []
    index = fetch_sec.submissions(cik, sec.user_agent)
    if index is None:
        return []
    oldest = as_of - timedelta(days=days)
    out: list[insiders_mod.Transaction] = []
    for accession, filed, document in insiders_mod.form4_filings(index):
        if filed > as_of or filed < oldest - timedelta(days=fetch_sec.INSIDER_FILING_LAG_DAYS):
            continue
        path = insiders_mod.CACHE_DIR / cik / f"{accession}.xml"
        try:
            body = path.read_bytes() if path.exists() else fetch_sec._get(  # pyright: ignore[reportPrivateUsage]
                insiders_mod.document_url(cik, accession, document), sec.user_agent)
        except Exception:  # noqa: BLE001 - a document that will not come back is simply not drawn
            continue
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        found, _ = insiders_mod.parse_form4(body, accession, filed, issuer_cik=cik)
        out += found
    return [t for t in insiders_mod.deduplicate(out) if oldest <= t.transaction_date <= as_of]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ticker")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "output" / "stretch")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None,
                        help="draw the chart as it stood on this date; filings after it are not read")
    args = parser.parse_args(argv)
    ticker: str = args.ticker
    t = stretch.load_thresholds()
    h = pit.History.fetch(ticker)
    days = sorted(h.closes)
    if not days:
        print(f"{ticker}: no closes", file=sys.stderr)
        return 2
    as_of: date = args.as_of or days[-1]
    days = [d for d in days if d <= as_of]
    closes = [h.closes[d] for d in days]
    window = days[-t.history_trading_days:]

    def ma(n: int, i: int) -> float:
        return sum(closes[i - n + 1:i + 1]) / n if i + 1 >= n else float("nan")

    idx = {d: i for i, d in enumerate(days)}
    shaded = [d for d in window
              if (block := stretch.compute(h.closes, h.volumes, d, t)[0]) is not None
              and (block.stretch_low >= 3 or block.stretch_high >= 3)]
    drawn = transactions_for(ticker, as_of, (window[-1] - window[0]).days)

    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.array(window, dtype="datetime64[D]")
    ax.plot(x, [closes[idx[d]] for d in window], color="black", linewidth=1.0, label="close, split-corrected as served")
    ax.plot(x, [ma(50, idx[d]) for d in window], color="tab:blue", linewidth=0.9, label="50-day average")
    ax.plot(x, [ma(200, idx[d]) for d in window], color="tab:orange", linewidth=0.9, label="200-day average")
    for d in shaded:
        x0 = float(mdates.date2num(d))  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
        ax.axvspan(x0, x0 + 1.0, color="tab:red", alpha=0.15, linewidth=0)

    # sized by dollars against the largest drawn, so the scale is the name's own
    largest = max((abs(t_.dollars) for t_ in drawn), default=0.0)
    for code, colour, marker, label in (("P", "tab:green", "^", "insider open-market purchase"),
                                        ("S", "tab:purple", "v", "insider open-market sale")):
        side = [t_ for t_ in drawn if t_.code == code]
        if not side:
            continue
        sizes = [20.0 + 180.0 * (abs(t_.dollars) / largest if largest > 0 else 0.0) for t_ in side]
        ax.scatter(np.array([t_.transaction_date for t_ in side], dtype="datetime64[D]"),
                   [t_.price_per_share for t_ in side], s=sizes, marker=marker, color=colour,
                   alpha=0.75, edgecolors="none", zorder=3,
                   label=f"{label} ({len(side)}, sized by dollars)")

    buys = sum(t_.dollars for t_ in drawn if t_.code == "P")
    sells = sum(t_.dollars for t_ in drawn if t_.code == "S")
    ax.set_title(f"{ticker}: two years to {as_of}; shaded where stretch reached 3 ({len(shaded)} days); "
                 f"insiders bought {buys / 1e6:,.1f}m, sold {sells / 1e6:,.1f}m")
    ax.set_ylabel("close, and the price insiders transacted at")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=8)
    fig.text(0.01, 0.01, "thresholds reference/stretch.json as of " + t.as_of
             + "; Form 4 open-market purchases and sales only, awards and exercises excluded. A count and a picture, no signal.", fontsize=7)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    args.out.mkdir(parents=True, exist_ok=True)
    png = args.out / f"{ticker}.png"
    fig.savefig(png, dpi=120)
    plt.close(fig)
    print(f"{ticker}: {len(shaded)} shaded days, {len(drawn)} insider transactions drawn -> {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
