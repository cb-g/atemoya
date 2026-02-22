"""Fetchers for SEC filings, earnings transcripts, and social media."""

from .fetch_mda import fetch_mda_for_ticker, extract_section
from .fetch_transcripts import fetch_transcripts_for_ticker

# Common Discord types and utilities
from .discord_common import (
    DiscordMessage,
    TickerMentionAggregate,
    extract_tickers,
    calculate_emoji_sentiment,
    calculate_keyword_sentiment,
    aggregate_by_ticker,
    create_document_for_pipeline,
    save_results as save_discord_results,
)

# Discord export importer (uses DiscordChatExporter JSON exports)
from .import_discord_export import (
    import_exports,
    import_from_directory,
    parse_discord_export,
)

__all__ = [
    # SEC/Transcripts
    "fetch_mda_for_ticker",
    "extract_section",
    "fetch_transcripts_for_ticker",
    # Discord common
    "DiscordMessage",
    "TickerMentionAggregate",
    "aggregate_by_ticker",
    "create_document_for_pipeline",
    # Discord import
    "import_exports",
    "import_from_directory",
    "parse_discord_export",
]
