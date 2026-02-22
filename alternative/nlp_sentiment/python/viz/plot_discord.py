#!/usr/bin/env python3
"""Discord Sentiment Dashboard Visualization.

Reads discord_analysis.json (from analyze_discord.py) and produces a 4-panel
dark-mode dashboard showing ticker mentions, sentiment distribution, channel
activity, and sentiment source breakdown.

Usage:
    uv run python plot_discord.py [--input FILE] [--output-dir DIR]
"""

import argparse
import json
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from lib.python.theme import setup_dark_mode, save_figure, KANAGAWA_DRAGON as C

setup_dark_mode()

# Channel category colors
CATEGORY_COLORS = {
    "crypto": C["orange"],
    "entertainment": C["yellow"],
    "infrastructure": C["blue"],
    "international": C["cyan"],
    "medical": C["green"],
    "retail": C["yellow"],
    "technology": C["cyan"],
    "chats": C["fg"],
    "social arb": C["green"],
}


def classify_channel(name):
    """Map channel name to category for coloring."""
    name_lower = name.lower()
    for cat in CATEGORY_COLORS:
        if cat in name_lower:
            return cat
    # Heuristic from known channel names
    crypto_words = {"bitcoin", "crypto", "meme-coin"}
    tech_words = {"aapl", "tsla", "big_tech", "ai", "humanoid", "space", "fintech",
                  "ecommerce", "fin-tech"}
    medical_words = {"healthcare", "weight-loss", "genomics", "psychedelics"}
    infra_words = {"energy", "real-estate", "commodities"}
    intl_words = {"canadian", "international", "trump", "world-conflicts"}
    retail_words = {"food", "sporting", "fashion"}
    chat_words = {"stock_trading", "long-term", "earnings", "charts", "meme-stocks"}
    research_words = {"trade-ideas", "conviction", "methodology", "app-data", "web-data"}

    for w in crypto_words:
        if w in name_lower:
            return "crypto"
    for w in tech_words:
        if w in name_lower:
            return "technology"
    for w in medical_words:
        if w in name_lower:
            return "medical"
    for w in infra_words:
        if w in name_lower:
            return "infrastructure"
    for w in intl_words:
        if w in name_lower:
            return "international"
    for w in retail_words:
        if w in name_lower:
            return "retail"
    for w in chat_words:
        if w in name_lower:
            return "chats"
    for w in research_words:
        if w in name_lower:
            return "social arb"
    return "chats"


def sentiment_color(score):
    """Map a sentiment score to a color."""
    if score > 0.15:
        return C["green"]
    elif score > 0.05:
        return C["cyan"]
    elif score > -0.05:
        return C["fg"]
    elif score > -0.15:
        return C["yellow"]
    else:
        return C["red"]


def plot_ticker_leaderboard(ax, tickers):
    """Top-left: horizontal bar chart of top tickers by mention count."""
    top = sorted(tickers.values(), key=lambda t: t["mention_count"], reverse=True)[:15]
    top.reverse()  # bottom-to-top for horizontal bars

    names = [t["ticker"] for t in top]
    counts = [t["mention_count"] for t in top]
    colors = [sentiment_color(t.get("combined_score", 0)) for t in top]

    y = np.arange(len(names))
    ax.barh(y, counts, color=colors, edgecolor=C["bg_light"], linewidth=0.5, height=0.7)

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("Mentions", fontsize=9)
    ax.set_title("TICKER MENTIONS", fontsize=11, fontweight="bold", color="white", loc="left")

    for i, c in enumerate(counts):
        ax.text(c + max(counts) * 0.02, i, str(c),
                va="center", fontsize=8, color=C["gray"])


def plot_sentiment_distribution(ax, tickers):
    """Top-right: stacked horizontal bar of bull/bear/neutral for top tickers."""
    top = sorted(tickers.values(), key=lambda t: t["mention_count"], reverse=True)[:10]
    top.reverse()

    names = [t["ticker"] for t in top]
    bullish = [t.get("bullish_count", 0) for t in top]
    neutral = [t.get("neutral_count", 0) for t in top]
    bearish = [t.get("bearish_count", 0) for t in top]

    y = np.arange(len(names))
    h = 0.6

    ax.barh(y, bullish, height=h, color=C["green"], label="Bullish",
            edgecolor=C["bg_light"], linewidth=0.5)
    ax.barh(y, neutral, height=h, left=bullish, color=C["gray"], label="Neutral",
            edgecolor=C["bg_light"], linewidth=0.5)
    left_bear = [b + n for b, n in zip(bullish, neutral)]
    ax.barh(y, bearish, height=h, left=left_bear, color=C["red"], label="Bearish",
            edgecolor=C["bg_light"], linewidth=0.5)

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("Messages", fontsize=9)
    ax.set_title("SENTIMENT DISTRIBUTION", fontsize=11, fontweight="bold", color="white", loc="left")
    ax.legend(fontsize=8, loc="lower right", framealpha=0.3)


def plot_category_activity(ax, channels):
    """Bottom-left: horizontal bar chart of message volume by category."""
    if not channels:
        ax.text(0.5, 0.5, "No channel data", ha="center", va="center",
                color=C["gray"], fontsize=10, transform=ax.transAxes)
        ax.set_title("CATEGORY BREAKDOWN", fontsize=11, fontweight="bold", color="white", loc="left")
        ax.axis("off")
        return

    # Aggregate channels into categories
    cat_counts = {}
    for name, info in channels.items():
        cat = classify_channel(name).title()
        cat_counts[cat] = cat_counts.get(cat, 0) + info.get("message_count", 0)

    sorted_cats = sorted(cat_counts.items(), key=lambda kv: kv[1], reverse=True)
    sorted_cats.reverse()

    names = [c for c, _ in sorted_cats]
    counts = [n for _, n in sorted_cats]
    colors = [CATEGORY_COLORS.get(c.lower(), C["fg"]) for c in names]

    y = np.arange(len(names))
    ax.barh(y, counts, color=colors, edgecolor=C["bg_light"], linewidth=0.5, height=0.6)

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("Messages", fontsize=9)
    ax.set_title("CATEGORY BREAKDOWN", fontsize=11, fontweight="bold", color="white", loc="left")

    for i, c in enumerate(counts):
        ax.text(c + max(counts) * 0.02, i, str(c), va="center", fontsize=8, color=C["gray"])


def plot_sentiment_breakdown(ax, tickers):
    """Bottom-right: grouped bar comparing emoji/keyword/reaction scores."""
    top = sorted(tickers.values(), key=lambda t: t["mention_count"], reverse=True)[:8]

    names = [t["ticker"] for t in top]
    emoji = [t.get("avg_emoji_sentiment", 0) for t in top]
    keyword = [t.get("avg_keyword_sentiment", 0) for t in top]
    reaction = [t.get("avg_reaction_score", 0) for t in top]

    x = np.arange(len(names))
    width = 0.25

    ax.bar(x - width, emoji, width, color=C["yellow"], label="Emoji",
           edgecolor=C["bg_light"], linewidth=0.5)
    ax.bar(x, keyword, width, color=C["cyan"], label="Keyword",
           edgecolor=C["bg_light"], linewidth=0.5)
    ax.bar(x + width, reaction, width, color=C["green"], label="Reaction",
           edgecolor=C["bg_light"], linewidth=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=9, rotation=45, ha="right")
    ax.set_ylabel("Score", fontsize=9)
    ax.set_title("SENTIMENT SOURCES", fontsize=11, fontweight="bold", color="white", loc="left")
    ax.legend(fontsize=8, loc="upper right", framealpha=0.3)
    ax.axhline(y=0, color=C["gray"], linewidth=0.5, linestyle="--")
    ax.set_ylim(-0.5, 0.5)


def plot_dashboard(data, output_dir):
    """Create the Discord sentiment dashboard figure."""
    tickers = data.get("tickers", {})
    channels = data.get("channels", {})
    total_msgs = data.get("total_messages", 0)
    total_tickers = data.get("total_tickers", 0)
    analysis_time = data.get("analysis_time", "")[:10]

    fig = plt.figure(figsize=(16, 12))
    fig.patch.set_facecolor(C["bg"])
    fig.suptitle(
        f"Discord Sentiment Dashboard  —  {total_tickers} tickers from {total_msgs:,} messages  —  {analysis_time}",
        fontsize=13, fontweight="bold", color="white", y=0.98,
    )

    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.30, wspace=0.30)

    ax_lead = fig.add_subplot(gs[0, 0])
    plot_ticker_leaderboard(ax_lead, tickers)

    ax_dist = fig.add_subplot(gs[0, 1])
    plot_sentiment_distribution(ax_dist, tickers)

    ax_chan = fig.add_subplot(gs[1, 0])
    plot_category_activity(ax_chan, channels)

    ax_break = fig.add_subplot(gs[1, 1])
    plot_sentiment_breakdown(ax_break, tickers)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "discord_sentiment.png"
    save_figure(fig, output_file, dpi=150)
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Plot Discord sentiment dashboard")
    parser.add_argument(
        "--input", "-i", type=str,
        default="alternative/nlp_sentiment/output/discord_analysis.json",
        help="Input JSON from analyze_discord.py",
    )
    parser.add_argument(
        "--output-dir", "-o", type=str,
        default="alternative/nlp_sentiment/output",
        help="Output directory for plots",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[4]

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = project_root / input_path

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        print("Run analyze_discord.py first:")
        print("  uv run alternative/nlp_sentiment/python/analyze_discord.py")
        sys.exit(1)

    with open(input_path) as f:
        data = json.load(f)

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir

    plot_dashboard(data, output_dir)


if __name__ == "__main__":
    main()
