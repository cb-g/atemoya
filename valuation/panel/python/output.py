"""Output formatters: terminal, JSON, CSV.

Each model's verdict is presented as-is. No cross-model composite scores —
a growth stock and a dividend aristocrat are judged by different lenses.
"""

import csv
import json
import io
from datetime import datetime


# ANSI colors
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

MODULE_NAMES = {
    "dcf_deterministic": "DCF Deterministic",
    "dcf_probabilistic": "DCF Probabilistic",
    "normalized_multiples": "Norm. Multiples",
    "garp_peg": "GARP/PEG",
    "growth_analysis": "Growth Analysis",
    "dividend_income": "Dividend Income",
    "analyst_upside": "Analyst Upside",
    "etf_analysis": "ETF Analysis",
    "dcf_reit": "REIT DCF",
    "crypto_treasury": "Crypto Treasury",
}


def format_terminal(results: list[dict]) -> str:
    """Per-ticker dashboard. Each model speaks for itself."""
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"\n{BOLD}VALUATION MULTI-MODEL DASHBOARD — {now}{RESET}")
    lines.append(f"{len(results)} tickers analyzed")
    lines.append("=" * 80)

    for i, r in enumerate(results):
        ticker = r["ticker"]
        name = r.get("company_name", ticker)
        price = r["current_price"]
        sector = r.get("sector", "")
        sec_type = r.get("security_type", "equity")
        n_run = len(r["modules_run"])
        n_fail = len(r["modules_failed"])

        if i > 0:
            lines.append("")

        # Ticker header
        type_label = f" [{sec_type.upper()}]" if sec_type != "equity" else ""
        sector_label = f"  {DIM}{sector}{RESET}" if sector else ""
        price_str = f"${price:,.2f}" if price else "n/a"
        lines.append(f"{BOLD}{ticker}{RESET} — {name}{type_label}  {price_str}{sector_label}")
        lines.append(f"  {n_run} models ran" + (f", {n_fail} failed" if n_fail else ""))
        lines.append("-" * 80)

        # Column headers
        lines.append(
            f"  {'Model':<20} {'Fair Value':>12} {'vs Price':>10}  {'Signal':<28} {'Detail'}"
        )
        lines.append(f"  {'─' * 20} {'─' * 12} {'─' * 10}  {'─' * 28} {'─' * 10}")

        for mr in r["module_results"]:
            module = mr["module"]
            fv = mr.get("fair_value")
            signal = mr.get("signal", "-")
            upside = mr.get("upside_pct")
            display_name = MODULE_NAMES.get(module, module)

            fv_str = f"${fv:,.0f}" if fv else "-"
            if upside is not None:
                color = GREEN if upside > 5 else (RED if upside < -5 else YELLOW)
                raw_upside = f"{upside:+.1f}%"
                upside_str = f"{color}{raw_upside:>10}{RESET}"
            else:
                upside_str = f"{'':>10}"

            # Detail column: confidence/score/analyst count
            conf = mr.get("confidence")
            conf_label = mr.get("confidence_label", "")
            detail = ""
            if conf is not None and conf_label:
                if isinstance(conf, float):
                    detail = f"{conf_label}={conf:.0f}%"
                else:
                    detail = f"{conf_label}={conf}"

            # For DCF deterministic, show FCFE/FCFF breakdown
            fv_details = mr.get("fair_value_details")
            if fv_details and not detail:
                parts = []
                for k, v in fv_details.items():
                    if v is not None:
                        parts.append(f"{k}=${v:,.0f}")
                if parts:
                    detail = ", ".join(parts)

            lines.append(
                f"  {display_name:<20} {fv_str:>12} {upside_str}  {signal:<28} {DIM}{detail}{RESET}"
            )

        # Failed modules
        if r["modules_failed"]:
            failed_names = [MODULE_NAMES.get(m, m) for m in r["modules_failed"]]
            lines.append(f"  {DIM}Failed: {', '.join(failed_names)}{RESET}")

        lines.append("-" * 80)

    lines.append("")
    return "\n".join(lines)


def format_json(results: list[dict]) -> str:
    """Format results as pretty JSON."""
    output = {
        "date": datetime.now().isoformat(),
        "ticker_count": len(results),
        "results": results,
    }
    return json.dumps(output, indent=2, default=str)


def format_csv(results: list[dict]) -> str:
    """Flat CSV: one row per (ticker, module) pair. Each model's verdict is its own row."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow([
        "ticker", "price", "module", "fair_value", "upside_pct",
        "signal", "confidence_label", "confidence",
    ])

    for r in results:
        price = r["current_price"]
        for mr in r["module_results"]:
            writer.writerow([
                r["ticker"],
                round(price, 2) if price else "",
                mr["module"],
                round(mr["fair_value"], 2) if mr.get("fair_value") else "",
                mr.get("upside_pct", ""),
                mr.get("signal", ""),
                mr.get("confidence_label", ""),
                mr.get("confidence", ""),
            ])

    return buf.getvalue()
