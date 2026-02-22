#!/usr/bin/env python3
"""
Import Discord chat exports from DiscordChatExporter.

Parses JSON exports from DiscordChatExporter tool and converts them to
the standard format for NLP sentiment analysis.

DiscordChatExporter: https://github.com/Tyrrrz/DiscordChatExporter

Usage:
    python import_discord_export.py export1.json export2.json
    python import_discord_export.py --dir ./exports --tickers AAPL NVDA
    python import_discord_export.py --dir ./exports --days 7
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Import shared components (no external deps)
try:
    from .discord_common import (
        DiscordMessage,
        TickerMentionAggregate,
        EMOJI_SENTIMENT,
        extract_tickers,
        calculate_emoji_sentiment,
        calculate_keyword_sentiment,
        aggregate_by_ticker,
        create_document_for_pipeline,
        save_results,
    )
except ImportError:
    # Allow running as standalone script
    from discord_common import (
        DiscordMessage,
        TickerMentionAggregate,
        EMOJI_SENTIMENT,
        extract_tickers,
        calculate_emoji_sentiment,
        calculate_keyword_sentiment,
        aggregate_by_ticker,
        create_document_for_pipeline,
        save_results,
    )


def parse_export_timestamp(ts_str: str) -> datetime:
    """Parse timestamp from DiscordChatExporter format."""
    # Handle various formats
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue

    # Fallback: try to parse with fromisoformat
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except:
        return datetime.now(timezone.utc)


def calculate_reaction_score_from_export(reactions: list) -> float:
    """Calculate sentiment from exported reaction data."""
    if not reactions:
        return 0.0

    total_score = 0.0
    total_count = 0

    for reaction in reactions:
        # DiscordChatExporter format: {"emoji": {"name": "🚀"}, "count": 5}
        emoji_data = reaction.get("emoji", {})
        emoji_name = emoji_data.get("name", "")
        count = reaction.get("count", 1)

        if emoji_name in EMOJI_SENTIMENT:
            total_score += EMOJI_SENTIMENT[emoji_name] * count
            total_count += count

    return total_score / total_count if total_count > 0 else 0.0


def parse_discord_export(
    filepath: Path,
    ticker_filter: Optional[set[str]] = None,
    after_date: Optional[datetime] = None,
) -> tuple[list[DiscordMessage], dict]:
    """
    Parse a DiscordChatExporter JSON file.

    Args:
        filepath: Path to JSON export file
        ticker_filter: Optional set of tickers to filter by
        after_date: Only include messages after this date

    Returns:
        Tuple of (list of DiscordMessage, metadata dict)
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Extract metadata
    guild = data.get("guild", {})
    channel = data.get("channel", {})

    metadata = {
        "server_id": str(guild.get("id", "")),
        "server_name": guild.get("name", "Unknown Server"),
        "channel_id": str(channel.get("id", "")),
        "channel_name": channel.get("name", "unknown-channel"),
        "export_file": filepath.name,
    }

    messages = []
    raw_messages = data.get("messages", [])

    for msg in raw_messages:
        # Skip bot messages
        author = msg.get("author", {})
        if author.get("isBot", False):
            continue

        content = msg.get("content", "")
        if not content:
            continue

        # Parse timestamp
        timestamp = parse_export_timestamp(msg.get("timestamp", ""))

        # Apply date filter
        if after_date and timestamp < after_date:
            continue

        # Extract tickers
        tickers = extract_tickers(content)

        # Apply ticker filter
        if ticker_filter and not any(t in ticker_filter for t in tickers):
            continue

        # Calculate sentiment scores
        emoji_sent = calculate_emoji_sentiment(content)
        keyword_sent = calculate_keyword_sentiment(content)
        reaction_score = calculate_reaction_score_from_export(msg.get("reactions", []))

        # Check if reply
        reference = msg.get("reference", {})
        is_reply = bool(reference.get("messageId"))

        discord_msg = DiscordMessage(
            message_id=str(msg.get("id", "")),
            channel_id=metadata["channel_id"],
            channel_name=metadata["channel_name"],
            server_id=metadata["server_id"],
            server_name=metadata["server_name"],
            author_id=str(author.get("id", "")),
            author_name=author.get("name", "Unknown"),
            content=content,
            timestamp=timestamp.isoformat(),
            tickers_mentioned=tickers,
            emoji_sentiment=emoji_sent,
            keyword_sentiment=keyword_sent,
            reaction_score=reaction_score,
            is_reply=is_reply,
            reply_to=str(reference.get("messageId")) if is_reply else None,
        )
        messages.append(discord_msg)

    return messages, metadata


def sanitize_channel_name(name: str) -> str:
    """Convert channel name to safe directory name."""
    import re
    # Remove emojis and special characters, keep alphanumeric and hyphens
    safe = re.sub(r'[^\w\s-]', '', name)
    safe = re.sub(r'\s+', '_', safe.strip())
    return safe[:50] or 'unknown_channel'


def import_exports(
    files: list[Path],
    ticker_filter: Optional[list[str]] = None,
    days: Optional[int] = None,
    output_dir: Optional[Path] = None,
) -> dict:
    """
    Import multiple Discord export files.

    Saves each channel separately and creates a combined aggregate.

    Args:
        files: List of JSON export files to import
        ticker_filter: Optional list of tickers to filter by
        days: Only include messages from last N days
        output_dir: Output directory for results

    Returns:
        Dict with import results
    """
    ticker_set = set(t.upper() for t in ticker_filter) if ticker_filter else None
    after_date = None
    if days:
        after_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Group messages by channel
    channel_data: dict[str, dict] = {}  # channel_id -> {messages, metadata}
    all_messages = []
    all_metadata = []

    for filepath in files:
        if not filepath.exists():
            print(f"Warning: File not found: {filepath}", file=sys.stderr)
            continue

        if not filepath.suffix.lower() == '.json':
            print(f"Warning: Skipping non-JSON file: {filepath}", file=sys.stderr)
            continue

        print(f"Importing: {filepath.name}...")

        try:
            messages, metadata = parse_discord_export(
                filepath,
                ticker_filter=ticker_set,
                after_date=after_date,
            )

            if messages:
                channel_id = metadata['channel_id']
                channel_name = metadata['channel_name']
                server_name = metadata['server_name']

                # Initialize or append to channel data
                if channel_id not in channel_data:
                    channel_data[channel_id] = {
                        'messages': [],
                        'metadata': metadata,
                        'channel_name': channel_name,
                        'server_name': server_name,
                    }
                channel_data[channel_id]['messages'].extend(messages)

                all_messages.extend(messages)
                all_metadata.append(metadata)

            print(f"  Found {len(messages)} messages")
        except Exception as e:
            print(f"  Error: {e}", file=sys.stderr)

    if not all_messages:
        print("No messages found matching criteria")
        return {"messages": 0, "tickers": 0}

    # Set up output directory
    output_dir = output_dir or Path(__file__).parent.parent.parent / "data" / "discord"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save each channel separately
    print(f"\nSaving {len(channel_data)} channel(s)...")
    for channel_id, data in channel_data.items():
        channel_name = data['channel_name']
        server_name = data['server_name']
        messages = data['messages']

        # Create safe directory name: server_channel
        dir_name = f"{sanitize_channel_name(server_name)}_{sanitize_channel_name(channel_name)}"
        channel_dir = output_dir / dir_name

        # Deduplicate messages by ID (in case of overlapping exports)
        seen_ids = set()
        unique_messages = []
        for msg in messages:
            if msg.message_id not in seen_ids:
                seen_ids.add(msg.message_id)
                unique_messages.append(msg)

        # Aggregate for this channel
        channel_aggregates = aggregate_by_ticker(unique_messages)

        # Save channel data
        save_results(unique_messages, channel_aggregates, channel_dir, quiet=True)
        print(f"  {dir_name}/: {len(unique_messages)} messages, {len(channel_aggregates)} tickers")

    # Create combined aggregates across all channels
    print(f"\nCreating combined aggregates...")
    combined_dir = output_dir / "combined"

    # Deduplicate all messages
    seen_ids = set()
    unique_all = []
    for msg in all_messages:
        if msg.message_id not in seen_ids:
            seen_ids.add(msg.message_id)
            unique_all.append(msg)

    combined_aggregates = aggregate_by_ticker(unique_all)
    save_results(unique_all, combined_aggregates, combined_dir)

    # Save import metadata
    meta_file = output_dir / "import_metadata.json"
    with open(meta_file, 'w') as f:
        json.dump({
            "import_time": datetime.now(timezone.utc).isoformat(),
            "files_imported": len(all_metadata),
            "channels_imported": len(channel_data),
            "total_messages": len(unique_all),
            "tickers_found": list(combined_aggregates.keys()),
            "channels": [
                {
                    "channel_id": cid,
                    "channel_name": data['channel_name'],
                    "server_name": data['server_name'],
                    "message_count": len(data['messages']),
                }
                for cid, data in channel_data.items()
            ],
            "sources": all_metadata,
        }, f, indent=2)

    return {
        "messages": len(unique_all),
        "tickers": len(combined_aggregates),
        "channels": len(channel_data),
        "aggregates": combined_aggregates,
        "output_dir": str(output_dir),
    }


def import_from_directory(
    directory: Path,
    ticker_filter: Optional[list[str]] = None,
    days: Optional[int] = None,
    output_dir: Optional[Path] = None,
) -> dict:
    """
    Import all JSON exports from a directory.

    Args:
        directory: Directory containing JSON export files
        ticker_filter: Optional list of tickers to filter by
        days: Only include messages from last N days
        output_dir: Output directory for results

    Returns:
        Dict with import results
    """
    if not directory.exists():
        print(f"Error: Directory not found: {directory}", file=sys.stderr)
        return {"messages": 0, "tickers": 0}

    json_files = list(directory.glob("*.json"))

    if not json_files:
        print(f"No JSON files found in {directory}")
        return {"messages": 0, "tickers": 0}

    print(f"Found {len(json_files)} JSON files in {directory}")

    return import_exports(
        files=json_files,
        ticker_filter=ticker_filter,
        days=days,
        output_dir=output_dir,
    )


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Import Discord chat exports from DiscordChatExporter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Import specific files
    python import_discord_export.py export1.json export2.json

    # Import all JSON files from a directory
    python import_discord_export.py --dir ./discord_exports

    # Filter by tickers
    python import_discord_export.py --dir ./exports --tickers AAPL NVDA TSLA

    # Only last 7 days of messages
    python import_discord_export.py --dir ./exports --days 7

DiscordChatExporter Download:
    https://github.com/Tyrrrz/DiscordChatExporter/releases

Export Command (CLI):
    ./DiscordChatExporter.Cli export -t "USER_TOKEN" -c CHANNEL_ID -f Json

Note: Use your Discord user token (from browser dev tools), not a bot token.
      Get token: Browser DevTools > Network > filter "api" > Headers > Authorization
        """
    )

    parser.add_argument(
        'files',
        nargs='*',
        type=Path,
        help='JSON export files to import'
    )
    parser.add_argument(
        '--dir',
        type=Path,
        help='Directory containing JSON export files'
    )
    parser.add_argument(
        '--tickers',
        type=str,
        nargs='+',
        help='Filter by ticker mentions'
    )
    parser.add_argument(
        '--days',
        type=int,
        help='Only include messages from last N days'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output directory'
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.files and not args.dir:
        print("Error: Must specify files or --dir", file=sys.stderr)
        parser.print_help()
        sys.exit(1)

    # Import from directory or files
    if args.dir:
        results = import_from_directory(
            directory=args.dir,
            ticker_filter=args.tickers,
            days=args.days,
            output_dir=args.output,
        )
    else:
        results = import_exports(
            files=args.files,
            ticker_filter=args.tickers,
            days=args.days,
            output_dir=args.output,
        )

    print(f"\nImport complete: {results['messages']} messages, {results['tickers']} tickers")


if __name__ == '__main__':
    main()
