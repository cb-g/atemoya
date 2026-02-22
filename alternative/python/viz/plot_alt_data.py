#!/usr/bin/env python3
"""
Alternative Data Dashboard visualization.

Reads alert JSON from each alt_data sub-module and produces a combined
6-panel dashboard covering all sources.

Usage:
    python alternative/python/viz/plot_alt_data.py
    python alternative/python/viz/plot_alt_data.py --output alternative/output/alt_data_dashboard.png
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

sys.path.insert(0, str(Path(__file__).parents[3]))
from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON as COLORS, save_figure

setup_dark_mode()
C = {k: v for k, v in COLORS.items()}

ALT_DATA_ROOT = Path(__file__).parents[2]


def load_json(path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def fmt_dollar(v):
    if abs(v) >= 1e9:
        return f"${v / 1e9:.1f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.1f}M"
    if abs(v) >= 1e3:
        return f"${v / 1e3:.0f}K"
    return f"${v:.0f}"


def divider(ax, y):
    ax.plot([0.02, 0.98], [y, y], color=C["gray"], alpha=0.3, linewidth=0.5,
            transform=ax.transAxes, clip_on=False)


def draw_insider(ax, data):
    ax.set_title("Insider Trading", fontsize=11, fontweight="bold", color=C["fg"], loc="left")
    ax.set_facecolor(C["bg_light"])
    ax.axis("off")

    if not data or not data.get("summaries"):
        ax.text(0.5, 0.5, "No data", ha="center", va="center", color=C["gray"],
                fontsize=10, transform=ax.transAxes)
        return

    summaries = data["summaries"]
    y = 0.90
    step = 0.16

    ax.text(0.02, y, "Ticker", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes)
    ax.text(0.18, y, "Buys", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.32, y, "Sells", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.55, y, "Net Activity", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.80, y, "Sentiment", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    y -= 0.06
    divider(ax, y)
    y -= step * 0.4

    for s in summaries[:4]:
        ticker = s["ticker"]
        buys = s.get("buys_count", 0)
        sells = s.get("sells_count", 0)
        net = s.get("net_activity", 0)
        sentiment = s.get("sentiment", "neutral")
        sent_color = C["green"] if "bull" in sentiment else C["red"] if "bear" in sentiment else C["gray"]

        ax.text(0.02, y, ticker, fontsize=9, color=C["fg"], fontweight="bold",
                transform=ax.transAxes)
        ax.text(0.18, y, str(buys), fontsize=9, color=C["green"] if buys > 0 else C["gray"],
                transform=ax.transAxes, ha="center")
        ax.text(0.32, y, str(sells), fontsize=9, color=C["red"] if sells > 0 else C["gray"],
                transform=ax.transAxes, ha="center")
        ax.text(0.55, y, fmt_dollar(net), fontsize=9,
                color=C["green"] if net > 0 else C["red"],
                transform=ax.transAxes, ha="center")
        ax.text(0.80, y, sentiment, fontsize=9, color=sent_color,
                transform=ax.transAxes, ha="center")
        y -= step

    n_alerts = data.get("alert_count", 0)
    high_alerts = sum(1 for a in data.get("alerts", []) if a.get("priority", 0) >= 4)
    ax.text(0.02, 0.04, f"{n_alerts} alerts", fontsize=8, color=C["gray"],
            transform=ax.transAxes)
    if high_alerts:
        ax.text(0.22, 0.04, f"({high_alerts} high)", fontsize=8, color=C["orange"],
                transform=ax.transAxes)


def draw_options(ax, data):
    ax.set_title("Options Flow", fontsize=11, fontweight="bold", color=C["fg"], loc="left")
    ax.set_facecolor(C["bg_light"])
    ax.axis("off")

    if not data or not data.get("summaries"):
        ax.text(0.5, 0.5, "No data", ha="center", va="center", color=C["gray"],
                fontsize=10, transform=ax.transAxes)
        return

    summaries = data["summaries"]
    y = 0.90
    step = 0.16

    ax.text(0.02, y, "Ticker", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes)
    ax.text(0.22, y, "Call $", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.42, y, "Put $", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.60, y, "C/P", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.80, y, "Sentiment", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    y -= 0.06
    divider(ax, y)
    y -= step * 0.4

    for s in summaries[:4]:
        ticker = s["ticker"]
        call_prem = s.get("total_call_premium", 0)
        put_prem = s.get("total_put_premium", 0)
        cp_ratio = s.get("call_put_ratio", 0)
        sentiment = s.get("sentiment", "neutral")
        sent_color = (C["green"] if "bull" in sentiment
                      else C["red"] if "bear" in sentiment
                      else C["gray"])

        ax.text(0.02, y, ticker, fontsize=9, color=C["fg"], fontweight="bold",
                transform=ax.transAxes)
        ax.text(0.22, y, fmt_dollar(call_prem), fontsize=9, color=C["green"],
                transform=ax.transAxes, ha="center")
        ax.text(0.42, y, fmt_dollar(put_prem), fontsize=9, color=C["red"],
                transform=ax.transAxes, ha="center")
        ax.text(0.60, y, f"{cp_ratio:.2f}", fontsize=9,
                color=C["green"] if cp_ratio > 1.5 else C["red"] if cp_ratio < 0.67 else C["fg"],
                transform=ax.transAxes, ha="center")
        ax.text(0.80, y, sentiment.replace("_", " "), fontsize=9, color=sent_color,
                transform=ax.transAxes, ha="center")
        y -= step

    n_alerts = data.get("alert_count", 0)
    high_alerts = sum(1 for a in data.get("alerts", []) if a.get("priority", 0) >= 4)
    ax.text(0.02, 0.04, f"{n_alerts} alerts", fontsize=8, color=C["gray"],
            transform=ax.transAxes)
    if high_alerts:
        ax.text(0.22, 0.04, f"({high_alerts} high)", fontsize=8, color=C["orange"],
                transform=ax.transAxes)


def draw_shorts(ax, data):
    ax.set_title("Short Interest", fontsize=11, fontweight="bold", color=C["fg"], loc="left")
    ax.set_facecolor(C["bg_light"])
    ax.axis("off")

    if not data or not data.get("summaries"):
        ax.text(0.5, 0.5, "No data", ha="center", va="center", color=C["gray"],
                fontsize=10, transform=ax.transAxes)
        return

    summaries = sorted(data["summaries"], key=lambda s: s.get("squeeze_score", 0), reverse=True)
    y = 0.90
    step = 0.16

    ax.text(0.02, y, "Ticker", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes)
    ax.text(0.22, y, "SI %", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.40, y, "DTC", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.58, y, "Change", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.80, y, "Squeeze", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    y -= 0.06
    divider(ax, y)
    y -= step * 0.4

    for s in summaries[:4]:
        ticker = s["ticker"]
        si_pct = s.get("si_pct_float", 0)
        dtc = s.get("days_to_cover", 0)
        change = s.get("si_change_pct", 0)
        score = s.get("squeeze_score", 0)
        score_color = C["red"] if score >= 70 else C["orange"] if score >= 50 else C["yellow"] if score >= 30 else C["gray"]

        ax.text(0.02, y, ticker, fontsize=9, color=C["fg"], fontweight="bold",
                transform=ax.transAxes)
        ax.text(0.22, y, f"{si_pct:.1f}%", fontsize=9,
                color=C["red"] if si_pct > 15 else C["fg"],
                transform=ax.transAxes, ha="center")
        ax.text(0.40, y, f"{dtc:.1f}", fontsize=9,
                color=C["red"] if dtc > 5 else C["fg"],
                transform=ax.transAxes, ha="center")
        ax.text(0.58, y, f"{change:+.1f}%", fontsize=9,
                color=C["red"] if change > 10 else C["green"] if change < -10 else C["fg"],
                transform=ax.transAxes, ha="center")
        ax.text(0.80, y, f"{score}", fontsize=9, color=score_color,
                fontweight="bold", transform=ax.transAxes, ha="center")
        y -= step

    n_alerts = data.get("alert_count", 0)
    ax.text(0.02, 0.04, f"{n_alerts} alerts", fontsize=8, color=C["gray"],
            transform=ax.transAxes)


def draw_trends(ax, data):
    ax.set_title("Google Trends", fontsize=11, fontweight="bold", color=C["fg"], loc="left")
    ax.set_facecolor(C["bg_light"])
    ax.axis("off")

    if not data or not data.get("summaries"):
        ax.text(0.5, 0.5, "No data", ha="center", va="center", color=C["gray"],
                fontsize=10, transform=ax.transAxes)
        return

    summaries = sorted(data["summaries"], key=lambda s: s.get("attention_score", 0), reverse=True)
    y = 0.90
    step = 0.16

    ax.text(0.02, y, "Ticker", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes)
    ax.text(0.22, y, "Attn", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.42, y, "Brand 7d", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.62, y, "Retail %", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.85, y, "Signals", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    y -= 0.06
    divider(ax, y)
    y -= step * 0.4

    for s in summaries[:4]:
        ticker = s["ticker"]
        attn = s.get("attention_score", 0)
        brand_7d = s.get("brand_change_7d", 0)
        retail = s.get("retail_percentile", 0)
        signals = s.get("signals_detected", [])
        sig_str = ", ".join(signals) if signals else "-"
        sig_color = C["orange"] if signals else C["gray"]

        ax.text(0.02, y, ticker, fontsize=9, color=C["fg"], fontweight="bold",
                transform=ax.transAxes)
        ax.text(0.22, y, f"{attn:.0f}", fontsize=9, color=C["fg"],
                transform=ax.transAxes, ha="center")
        ax.text(0.42, y, f"{brand_7d:+.1f}%", fontsize=9,
                color=C["green"] if brand_7d > 0 else C["red"] if brand_7d < 0 else C["fg"],
                transform=ax.transAxes, ha="center")
        ax.text(0.62, y, f"{retail:.0f}%", fontsize=9, color=C["fg"],
                transform=ax.transAxes, ha="center")
        ax.text(0.85, y, sig_str[:20], fontsize=8, color=sig_color,
                transform=ax.transAxes, ha="center")
        y -= step

    n_alerts = data.get("alert_count", 0)
    ax.text(0.02, 0.04, f"{n_alerts} alerts", fontsize=8, color=C["gray"],
            transform=ax.transAxes)


def draw_sec_filings(ax, data):
    ax.set_title("SEC Filings", fontsize=11, fontweight="bold", color=C["fg"], loc="left")
    ax.set_facecolor(C["bg_light"])
    ax.axis("off")

    if not data or not data.get("summaries"):
        ax.text(0.5, 0.5, "No data", ha="center", va="center", color=C["gray"],
                fontsize=10, transform=ax.transAxes)
        return

    summaries = data["summaries"]
    y = 0.90
    step = 0.16

    ax.text(0.02, y, "Ticker", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes)
    ax.text(0.18, y, "Total", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.32, y, "8-K", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.48, y, "Material", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.64, y, "Activist", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.84, y, "Recent", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    y -= 0.06
    divider(ax, y)
    y -= step * 0.4

    for s in summaries[:4]:
        ticker = s["ticker"]
        total = s.get("total_filings", 0)
        eight_k = s.get("eight_k_count", 0)
        material = s.get("material_events", 0)
        activist = s.get("has_activist", False)
        recent = s.get("most_recent_date", "-")

        ax.text(0.02, y, ticker, fontsize=9, color=C["fg"], fontweight="bold",
                transform=ax.transAxes)
        ax.text(0.18, y, str(total), fontsize=9, color=C["fg"],
                transform=ax.transAxes, ha="center")
        ax.text(0.32, y, str(eight_k), fontsize=9,
                color=C["orange"] if eight_k > 0 else C["fg"],
                transform=ax.transAxes, ha="center")
        ax.text(0.48, y, str(material), fontsize=9,
                color=C["red"] if material > 0 else C["fg"],
                transform=ax.transAxes, ha="center")
        ax.text(0.64, y, "Yes" if activist else "No", fontsize=9,
                color=C["red"] if activist else C["gray"],
                transform=ax.transAxes, ha="center")
        ax.text(0.84, y, recent, fontsize=8, color=C["fg"],
                transform=ax.transAxes, ha="center")
        y -= step

    n_alerts = data.get("alert_count", 0)
    high_alerts = sum(1 for a in data.get("alerts", []) if a.get("priority", 0) >= 4)
    ax.text(0.02, 0.04, f"{n_alerts} alerts", fontsize=8, color=C["gray"],
            transform=ax.transAxes)
    if high_alerts:
        ax.text(0.22, 0.04, f"({high_alerts} high)", fontsize=8, color=C["orange"],
                transform=ax.transAxes)


def draw_nlp_sentiment(ax, data):
    ax.set_title("NLP Sentiment", fontsize=11, fontweight="bold", color=C["fg"], loc="left")
    ax.set_facecolor(C["bg_light"])
    ax.axis("off")

    if not data or not data.get("tickers"):
        ax.text(0.5, 0.5, "No data", ha="center", va="center", color=C["gray"],
                fontsize=10, transform=ax.transAxes)
        return

    # Sort by mention count, take top tickers with enough mentions
    tickers = sorted(data["tickers"].values(),
                     key=lambda t: t.get("mention_count", 0), reverse=True)
    tickers = [t for t in tickers if t.get("mention_count", 0) >= 3][:4]

    y = 0.90
    step = 0.16

    ax.text(0.02, y, "Ticker", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes)
    ax.text(0.18, y, "Mentions", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.38, y, "FinBERT", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.58, y, "Combined", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.75, y, "Conf", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    ax.text(0.90, y, "Signal", fontsize=8, color=C["gray"], fontweight="bold",
            transform=ax.transAxes, ha="center")
    y -= 0.06
    divider(ax, y)
    y -= step * 0.4

    for t in tickers:
        ticker = t["ticker"]
        mentions = t.get("mention_count", 0)
        finbert = t.get("finbert_score", 0)
        combined = t.get("combined_score", 0)
        confidence = t.get("confidence", 0)
        signal = t.get("signal", "neutral")
        sig_color = (C["green"] if signal == "bullish"
                     else C["red"] if signal == "bearish"
                     else C["gray"])

        ax.text(0.02, y, ticker, fontsize=9, color=C["fg"], fontweight="bold",
                transform=ax.transAxes)
        ax.text(0.18, y, str(mentions), fontsize=9, color=C["fg"],
                transform=ax.transAxes, ha="center")
        ax.text(0.38, y, f"{finbert:+.2f}", fontsize=9,
                color=C["green"] if finbert > 0.1 else C["red"] if finbert < -0.1 else C["fg"],
                transform=ax.transAxes, ha="center")
        ax.text(0.58, y, f"{combined:+.2f}", fontsize=9,
                color=C["green"] if combined > 0.1 else C["red"] if combined < -0.1 else C["fg"],
                transform=ax.transAxes, ha="center")
        ax.text(0.75, y, f"{confidence:.0%}", fontsize=9, color=C["fg"],
                transform=ax.transAxes, ha="center")
        ax.text(0.90, y, signal, fontsize=9, color=sig_color,
                transform=ax.transAxes, ha="center")
        y -= step

    total = data.get("total_tickers", len(data["tickers"]))
    ax.text(0.02, 0.04, f"{total} tickers analyzed", fontsize=8, color=C["gray"],
            transform=ax.transAxes)


def main():
    parser = argparse.ArgumentParser(description="Alternative Data Dashboard")
    parser.add_argument("--output", type=Path,
                        default=ALT_DATA_ROOT / "output" / "alt_data_dashboard.png")
    parser.add_argument("--insider", type=Path,
                        default=ALT_DATA_ROOT / "insider_trading" / "output" / "insider_alerts.json")
    parser.add_argument("--options", type=Path,
                        default=ALT_DATA_ROOT / "options_flow" / "output" / "flow_alerts.json")
    parser.add_argument("--shorts", type=Path,
                        default=ALT_DATA_ROOT / "short_interest" / "output" / "short_alerts.json")
    parser.add_argument("--trends", type=Path,
                        default=ALT_DATA_ROOT / "google_trends" / "output" / "trends_alerts.json")
    parser.add_argument("--sec", type=Path,
                        default=ALT_DATA_ROOT / "sec_filings" / "output" / "filing_alerts.json")
    parser.add_argument("--nlp", type=Path,
                        default=ALT_DATA_ROOT / "nlp_sentiment" / "data" / "discord" / "combined" / "combined_analysis.json")
    args = parser.parse_args()

    insider_data = load_json(args.insider)
    options_data = load_json(args.options)
    shorts_data = load_json(args.shorts)
    trends_data = load_json(args.trends)
    sec_data = load_json(args.sec)
    nlp_data = load_json(args.nlp)

    fig = plt.figure(figsize=(14, 13))
    gs = gridspec.GridSpec(3, 2, hspace=0.22, wspace=0.20,
                           left=0.04, right=0.96, top=0.94, bottom=0.03)

    ax_insider = fig.add_subplot(gs[0, 0])
    ax_options = fig.add_subplot(gs[0, 1])
    ax_shorts = fig.add_subplot(gs[1, 0])
    ax_trends = fig.add_subplot(gs[1, 1])
    ax_sec = fig.add_subplot(gs[2, 0])
    ax_nlp = fig.add_subplot(gs[2, 1])

    draw_insider(ax_insider, insider_data)
    draw_options(ax_options, options_data)
    draw_shorts(ax_shorts, shorts_data)
    draw_trends(ax_trends, trends_data)
    draw_sec_filings(ax_sec, sec_data)
    draw_nlp_sentiment(ax_nlp, nlp_data)

    # Suptitle with timestamp
    timestamps = []
    for d in [insider_data, options_data, shorts_data, trends_data, sec_data]:
        if d and d.get("analysis_time"):
            timestamps.append(d["analysis_time"][:16].replace("T", " "))
    ts_str = f"  ({timestamps[0]})" if timestamps else ""
    fig.suptitle(f"Alternative Data Dashboard{ts_str}",
                 fontsize=13, fontweight="bold", color=C["fg"], y=0.975)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_figure(fig, args.output)
    plt.close(fig)


if __name__ == "__main__":
    main()
