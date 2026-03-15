"""Valuation Panel: multi-model view per ticker.

Triages tickers, routes them to applicable valuation modules,
runs everything, and presents each model's verdict side by side.
No composite scoring — each model speaks for itself.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from valuation.panel.python.triage import (
    resolve_universe,
    triage_all,
    build_execution_plan,
)
from valuation.panel.python.execute import (
    build_ocaml,
    fetch_data,
    run_analysis,
)
from valuation.panel.python.aggregate import collect_results
from valuation.panel.python.output import (
    format_terminal,
    format_json,
    format_csv,
)

PROJECT_ROOT = Path(__file__).parents[3]


def main():
    parser = argparse.ArgumentParser(
        description="Valuation Panel: run multiple valuation models per ticker, each verdict presented as-is"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tickers", type=str, help="Comma-separated ticker list")
    group.add_argument(
        "--universe", type=str,
        help="Universe: portfolio, watchlist, all_portfolio, sp50, nasdaq30, dow30, "
             "tech, healthcare, financials, energy, ai, liquid, etc.",
    )

    parser.add_argument("--format", choices=["terminal", "json", "csv"], default="terminal")
    parser.add_argument("--include-probabilistic", action="store_true",
                        help="Include DCF probabilistic (slow, excluded by default)")
    parser.add_argument("--fresh", action="store_true",
                        help="Force re-fetch all data (ignore same-day cache)")
    parser.add_argument("--max-parallel", type=int, default=8)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--output", type=str, help="Write output to file instead of stdout")
    parser.add_argument("--notify", action="store_true", help="Send top results via ntfy")

    args = parser.parse_args()

    # Step 0: Resolve universe
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = resolve_universe(args.universe)

    if not tickers:
        print("Error: no tickers to analyze", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print(f"\nValuation Panel")
        print(f"{'=' * 50}")
        print(f"Tickers: {len(tickers)}")
        print()

    # Step 1: Triage
    if not args.quiet:
        print("Phase 0: Triaging tickers...")
    triage_results = triage_all(tickers, max_workers=min(10, len(tickers)))
    valid = [t for t in triage_results if not t.get("error")]
    failed = [t for t in triage_results if t.get("error")]

    if failed and not args.quiet:
        for t in failed:
            print(f"  [skip] {t['ticker']}: {t['error']}")

    if not valid:
        print("Error: no tickers could be triaged", file=sys.stderr)
        sys.exit(1)

    # Step 2: Build execution plan
    plan = build_execution_plan(valid, include_probabilistic=args.include_probabilistic)

    if not args.quiet:
        total_jobs = sum(len(modules) for modules in plan.values())
        print(f"  {len(plan)} tickers routed, {total_jobs} module runs planned")
        print()

    # Step 3: Build OCaml
    all_modules = set()
    for modules in plan.values():
        all_modules.update(modules)
    build_ocaml(all_modules, quiet=args.quiet)

    # Step 4: Fetch data
    if not args.quiet:
        print("\nPhase 1: Fetching data...")
    fetch_results = fetch_data(plan, fresh=args.fresh, max_parallel=args.max_parallel, quiet=args.quiet)

    # Step 5: Run analysis
    if not args.quiet:
        print("\nPhase 2: Running analysis...")
    analysis_results = run_analysis(plan, fetch_results, max_parallel=args.max_parallel, quiet=args.quiet)

    # Step 6: Aggregate results
    if not args.quiet:
        print("\nPhase 3: Aggregating results...")
    aggregated = collect_results(plan, analysis_results, triage_results)

    # Step 7: Output
    if args.format == "json":
        output_str = format_json(aggregated)
    elif args.format == "csv":
        output_str = format_csv(aggregated)
    else:
        output_str = format_terminal(aggregated)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_str)
        if not args.quiet:
            print(f"\nResults written to: {args.output}")
    else:
        print(output_str)

    # Auto-save JSON
    output_dir = PROJECT_ROOT / "valuation" / "panel" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"panel_{ts}.json"
    json_path.write_text(format_json(aggregated))

    # Notify if requested
    if args.notify:
        _send_notification(aggregated)


def _send_notification(results: list[dict]):
    """Send summary via ntfy — per-ticker, each model's verdict."""
    try:
        from lib.python.notify import send_notification
    except ImportError:
        print("Warning: notification module not available", file=sys.stderr)
        return

    lines = [f"Multi-Model Valuation — {len(results)} tickers", ""]
    for r in results[:10]:
        ticker = r["ticker"]
        price = r["current_price"]
        n = len(r["modules_run"])
        # Show modules that produced fair values
        fv_parts = []
        for mr in r["module_results"]:
            fv = mr.get("fair_value")
            signal = mr.get("signal", "")
            if fv and price:
                upside = (fv / price - 1) * 100
                short_name = mr["module"].replace("_", " ").title()[:12]
                fv_parts.append(f"{short_name}: ${fv:,.0f} ({upside:+.0f}%)")
            elif signal:
                short_name = mr["module"].replace("_", " ").title()[:12]
                fv_parts.append(f"{short_name}: {signal}")
        summary = " | ".join(fv_parts[:3])
        lines.append(f"{ticker} (${price:,.0f}, {n} models): {summary}")

    send_notification(
        title="Multi-Model Valuation",
        message="\n".join(lines),
        tags="chart_with_upwards_trend",
    )


if __name__ == "__main__":
    main()
