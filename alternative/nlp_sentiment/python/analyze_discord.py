#!/usr/bin/env python3
"""Analyze Discord sentiment aggregates and produce dashboard-ready JSON.

Reads discord_aggregates.json (from import_discord_export.py) and outputs:
  - combined_analysis.json: format expected by alt_data dashboard
  - discord_analysis.json: richer output for standalone Discord viz

Usage:
    uv run python analyze_discord.py [--input DIR] [--output DIR]
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


def compute_confidence(mention_count, unique_authors):
    """Confidence score from mention count and author diversity.

    Uses log scaling so diminishing returns above ~50 mentions.
    Author diversity adds weight (many authors > one spammer).
    """
    mention_conf = min(1.0, math.log1p(mention_count) / math.log1p(50))
    author_conf = min(1.0, math.log1p(unique_authors) / math.log1p(15))
    return round(min(1.0, 0.6 * mention_conf + 0.4 * author_conf), 2)


def analyze_aggregates(aggregates, channel_meta=None):
    """Convert raw aggregates into analysis outputs.

    Args:
        aggregates: dict of ticker -> aggregate fields (from discord_aggregates.json)
        channel_meta: optional list of channel info dicts from import_metadata.json

    Returns:
        (combined_analysis, discord_analysis) tuple
    """
    now = datetime.now(timezone.utc).isoformat()

    # Build per-ticker analysis
    tickers_dashboard = {}
    tickers_rich = {}

    for ticker, agg in aggregates.items():
        mention_count = agg.get("mention_count", 0)
        unique_authors = agg.get("unique_authors", 0)
        avg_emoji = agg.get("avg_emoji_sentiment", 0.0)
        avg_keyword = agg.get("avg_keyword_sentiment", 0.0)
        avg_reaction = agg.get("avg_reaction_score", 0.0)

        combined_score = round((avg_emoji + avg_keyword + avg_reaction) / 3, 4)
        confidence = compute_confidence(mention_count, unique_authors)

        if combined_score > 0.1:
            signal = "bullish"
        elif combined_score < -0.1:
            signal = "bearish"
        else:
            signal = "neutral"

        # Dashboard format (matches draw_nlp_sentiment in plot_alt_data.py)
        tickers_dashboard[ticker] = {
            "ticker": ticker,
            "mention_count": mention_count,
            "finbert_score": 0.0,  # no FinBERT, heuristic only
            "combined_score": combined_score,
            "confidence": confidence,
            "signal": signal,
        }

        # Rich format for standalone viz
        tickers_rich[ticker] = {
            **tickers_dashboard[ticker],
            "unique_authors": unique_authors,
            "avg_emoji_sentiment": avg_emoji,
            "avg_keyword_sentiment": avg_keyword,
            "avg_reaction_score": avg_reaction,
            "bullish_count": agg.get("bullish_count", 0),
            "bearish_count": agg.get("bearish_count", 0),
            "neutral_count": agg.get("neutral_count", 0),
            "first_mention": agg.get("first_mention", ""),
            "last_mention": agg.get("last_mention", ""),
        }

    # Build category-level summary (no channel/server names)
    channels = {}
    if channel_meta:
        for ch in channel_meta:
            name = ch.get("channel_name", "unknown")
            channels[name] = {
                "message_count": ch.get("message_count", 0),
            }

    total_messages = sum(ch.get("message_count", 0) for ch in (channel_meta or []))

    combined_analysis = {
        "tickers": tickers_dashboard,
        "total_tickers": len(tickers_dashboard),
        "analysis_time": now,
    }

    discord_analysis = {
        "tickers": tickers_rich,
        "channels": channels,
        "total_messages": total_messages,
        "total_tickers": len(tickers_rich),
        "analysis_time": now,
    }

    return combined_analysis, discord_analysis


def main():
    parser = argparse.ArgumentParser(description="Analyze Discord sentiment aggregates")
    parser.add_argument(
        "--input", "-i", type=Path,
        default="alternative/nlp_sentiment/data/discord/combined",
        help="Directory containing discord_aggregates.json",
    )
    parser.add_argument(
        "--output", "-o", type=Path,
        default="alternative/nlp_sentiment/output",
        help="Output directory for analysis JSON",
    )
    args = parser.parse_args()

    # Resolve relative paths from project root
    project_root = Path(__file__).resolve().parents[3]
    input_dir = args.input if args.input.is_absolute() else project_root / args.input
    output_dir = args.output if args.output.is_absolute() else project_root / args.output

    # Load aggregates
    agg_file = input_dir / "discord_aggregates.json"
    if not agg_file.exists():
        print(f"Error: {agg_file} not found. Run import_discord_export.py first.")
        sys.exit(1)

    with open(agg_file) as f:
        aggregates = json.load(f)

    print(f"Loaded aggregates for {len(aggregates)} tickers")

    # Load channel metadata if available
    meta_file = input_dir.parent / "import_metadata.json"
    channel_meta = None
    if meta_file.exists():
        with open(meta_file) as f:
            meta = json.load(f)
        channel_meta = meta.get("channels", [])

    combined, discord = analyze_aggregates(aggregates, channel_meta)

    # Write combined_analysis.json (for alt_data dashboard)
    combined_file = input_dir / "combined_analysis.json"
    input_dir.mkdir(parents=True, exist_ok=True)
    with open(combined_file, "w") as f:
        json.dump(combined, f, indent=2)
    print(f"Saved: {combined_file}")

    # Write discord_analysis.json (for standalone viz)
    output_dir.mkdir(parents=True, exist_ok=True)
    discord_file = output_dir / "discord_analysis.json"
    with open(discord_file, "w") as f:
        json.dump(discord, f, indent=2)
    print(f"Saved: {discord_file}")

    # Summary
    sorted_tickers = sorted(
        combined["tickers"].values(),
        key=lambda t: t["mention_count"],
        reverse=True,
    )
    print(f"\nTop tickers by mentions:")
    for t in sorted_tickers[:10]:
        print(f"  {t['ticker']:6s}  {t['mention_count']:4d} mentions  "
              f"score={t['combined_score']:+.3f}  {t['signal']}")


if __name__ == "__main__":
    main()
