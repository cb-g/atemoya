#!/usr/bin/env python3
"""
Common data structures and utilities for Discord sentiment analysis.

Used by import_discord_export.py to parse DiscordChatExporter JSON exports.
"""

import re
from dataclasses import dataclass, asdict
from typing import Optional


# Ticker pattern: $AAPL, $aapl, AAPL (when capitalized and 1-5 chars)
TICKER_PATTERN = re.compile(
    r'(?:\$([A-Za-z]{1,5}))|'  # $AAPL style
    r'(?<![A-Za-z])([A-Z]{2,5})(?![A-Za-z])'  # AAPL style (all caps, not part of word)
)

# Common words to exclude from ticker detection
TICKER_BLACKLIST = {
    # Common English words
    'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'HER',
    'WAS', 'ONE', 'OUR', 'OUT', 'HAS', 'HIS', 'HOW', 'ITS', 'MAY', 'NEW',
    'NOW', 'OLD', 'SEE', 'WAY', 'WHO', 'BOY', 'DID', 'GET', 'HIM', 'LET',
    'PUT', 'SAY', 'SHE', 'TOO', 'USE', 'DAY', 'GOT', 'HAS', 'HIM', 'HOW',
    'MAN', 'OWN', 'SAY', 'TOP', 'TWO', 'YET', 'BIG', 'ANY', 'FEW', 'END',
    'RUN', 'SET', 'TRY', 'WHY', 'ADD', 'ASK', 'BAD', 'FAR', 'LOT', 'LOW',
    'PAY', 'WIN', 'WON', 'YES', 'AGO', 'BAR', 'BIT', 'CUT', 'DUE', 'ERA',
    'FIT', 'GAP', 'HIT', 'JOB', 'KEY', 'LAW', 'LED', 'MAP', 'MET', 'NET',
    'ODD', 'PAT', 'RAW', 'RED', 'SAD', 'SIT', 'SUN', 'TAX', 'TIP', 'VIA',
    'WAR', 'WET', 'ALSO', 'JUST', 'ONLY', 'EVEN', 'BACK', 'WELL', 'MUCH',
    'SUCH', 'MOST', 'LONG', 'GOOD', 'LAST', 'COME', 'MADE', 'FIND', 'TAKE',
    'KNOW', 'LOOK', 'MAKE', 'WANT', 'GIVE', 'MANY', 'SOME', 'VERY', 'THAN',
    'THEM', 'THEN', 'INTO', 'BEEN', 'HAVE', 'WILL', 'MORE', 'WHEN', 'WHAT',
    'THIS', 'THAT', 'WITH', 'FROM', 'WERE', 'SAID', 'EACH', 'TIME', 'YEAR',
    'WORK', 'LIFE', 'NEED', 'PART', 'SURE', 'CALL', 'KEEP', 'HELP', 'TURN',
    'HAND', 'SHOW', 'PLAY', 'MOVE', 'NEXT', 'TELL', 'DOES', 'GOES', 'WENT',
    'EVER', 'STOP', 'HOLD', 'WEEK', 'SOON', 'LATE', 'HARD', 'REAL', 'BEST',
    'FACT', 'AWAY', 'ONCE', 'DONE', 'OPEN', 'SORT', 'HALF', 'SAME', 'ABLE',
    'LESS', 'FELT', 'FULL', 'HEAR', 'HOPE', 'TRUE', 'IDEA', 'RISE', 'VIEW',
    'PLAN', 'PAST', 'FORM', 'DATA', 'AREA', 'LINE', 'LIST', 'NAME', 'SIDE',
    'CASE', 'TERM', 'RATE', 'COST', 'SELL', 'SOLD', 'GETS', 'SEES', 'RUNS',
    # Words commonly found in ALL-CAPS headlines/emphasized text
    'AGAIN', 'TECH', 'WEEKS', 'BILLS', 'MUST', 'READ', 'NEVER', 'WOW', 'OK',
    'FRIED', 'FILES', 'GAINS', 'LOVED', 'SPOT', 'COVID', 'USSR', 'BRICS',
    'ROFL', 'WOOOO', 'TRUMP', 'HERE', 'THEY', 'THAN', 'THEIR', 'THERE',
    'THESE', 'THOSE', 'AFTER', 'ABOUT', 'BEING', 'COULD', 'FIRST', 'OTHER',
    'WHICH', 'WOULD', 'THINK', 'GOING', 'STILL', 'USING', 'THREE', 'TODAY',
    'DIDN', 'DOESN', 'ISN', 'AREN', 'WASN', 'WEREN', 'HASN', 'HAVEN', 'WON',
    # Finance/trading terms (not tickers)
    'USD', 'ETF', 'IPO', 'CEO', 'CFO', 'COO', 'ATH', 'ATL', 'EPS', 'ROE',
    'ROI', 'YOY', 'QOQ', 'MOM', 'DCF', 'FCF', 'GAAP', 'DTE', 'OTM', 'ITM',
    'ATM', 'YOLO', 'FOMO', 'FUD', 'HODL', 'BTFD', 'GDP', 'CPI', 'PPI',
    'FED', 'FOMC', 'EBITDA', 'NYSE', 'SEC', 'SPAC', 'REIT', 'NAV', 'AUM',
    'IRR', 'APR', 'APY', 'BPS', 'YTD', 'MTD', 'QTD', 'WSB', 'IMO', 'IMHO',
    'COGS', 'CAGR', 'GFC', 'OTC', 'ETFS', 'BNPL',
    # Common abbreviations & acronyms
    'DD', 'DM', 'OP', 'PM', 'AM', 'US', 'UK', 'EU', 'AI', 'ML', 'API',
    'USA', 'LOL', 'LMAO', 'WTF', 'OMG', 'BTW', 'TBH', 'IDK', 'SMH', 'FYI',
    'AMA', 'TIL', 'IIRC', 'AFAIK', 'TLDR', 'PSA', 'ASAP', 'FAQ', 'ETA',
    'PDF', 'URL', 'HTTP', 'HTML', 'JSON', 'CSV', 'SQL', 'FWIW',
    # AI/Tech terms (not tickers)
    'LLM', 'GPT', 'AGI', 'SEO', 'LLMS', 'GPTS', 'NLP',
    # Units and measurements
    'GW', 'MW', 'KW', 'TWH', 'GWH', 'MWH', 'KWH', 'BTU', 'PSI', 'RPM',
    'MPH', 'KPH', 'LBS', 'KGS', 'OZS', 'QTY', 'PCT', 'BPS',
    # Platforms and common internet terms
    'YT', 'FB', 'IG', 'TW', 'APP', 'IOS', 'VPN', 'DNS', 'USB', 'RAM',
    'CPU', 'GPU', 'SSD', 'HDD', 'LED', 'LCD', 'HDR', 'FPS', 'GIF', 'PNG',
    # Government agencies and organizations
    'FEMA', 'NASA', 'USDA', 'EPA', 'FDA', 'DOE', 'DOD', 'CIA', 'FBI',
    'NSA', 'IRS', 'CDC', 'WHO', 'NATO', 'OPEC', 'IMF', 'FAA', 'HHS',
    # People names/initials commonly appearing in all-caps
    'SBF', 'RFK', 'SAM',
    # Media outlets
    'NYT', 'CNBC', 'CNN', 'BBC', 'ESPN', 'HBO', 'NPR', 'PBS', 'ABC', 'NBC',
    'CBS', 'FOX', 'MSNBC',
    # Geographic abbreviations (states, cities, regions)
    'NYC', 'DC', 'LA', 'SF', 'HQ', 'GA', 'MN', 'WV', 'PA', 'NC',
    # Finance terms often appearing without $ prefix
    'PE', 'PS', 'TA', 'QT', 'ESG', 'HF', 'JV',
    # Event/conference names
    'CES',
    # Investment strategy terms
    'DCA', 'DRIP', 'IRA', 'HSA', 'LLC', 'INC', 'LTD', 'PLC', 'ETN',
    # Time-related
    'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN', 'JAN', 'FEB', 'MAR',
    'APR', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC', 'EST', 'PST',
    # Corporate titles
    'CEO', 'CTO', 'COO', 'EVP', 'SVP', 'CFO', 'CIO', 'CMO',
    # Other false positives found in data
    'TAM', 'SUV',
    # Common words from headlines (2-letter caps)
    'IN', 'ON', 'NO', 'OR', 'SO', 'TO', 'II',
    # Title abbreviations
    'VP', 'VP',
    # Private companies often mentioned
    'BD',  # Boston Dynamics (not public)
}

# URL pattern to strip before keyword analysis
URL_PATTERN = re.compile(r'https?://\S+|www\.\S+')

# Bullish/bearish emoji mapping
EMOJI_SENTIMENT = {
    # Bullish
    '🚀': 1.0, '📈': 0.8, '💎': 0.7, '🙌': 0.5, '💪': 0.5, '🔥': 0.6,
    '✅': 0.4, '👍': 0.3, '💰': 0.6, '🤑': 0.7, '📗': 0.5, '🟢': 0.6,
    '⬆️': 0.5, '🎯': 0.4, '🏆': 0.5, '💵': 0.4, '🦍': 0.3, '🌙': 0.6,
    # Bearish
    '📉': -0.8, '💀': -0.7, '🩸': -0.8, '😱': -0.5, '😭': -0.4, '🔴': -0.6,
    '⬇️': -0.5, '🗑️': -0.6, '💩': -0.5, '🤡': -0.4, '📕': -0.5, '❌': -0.4,
    '🐻': -0.6, '☠️': -0.7, '😰': -0.3, '🆘': -0.5,
    # Neutral/uncertain
    '🤔': 0.0, '🧐': 0.0, '❓': 0.0, '🤷': 0.0,
}

# Sentiment keywords (will be compiled to word-boundary regex)
BULLISH_KEYWORDS = [
    'buy', 'buying', 'bought', 'long', 'calls', 'moon', 'mooning', 'bullish',
    'pump', 'pumping', 'rip', 'ripping', 'squeeze', 'breakout', 'gap up',
    'undervalued', 'accumulate', 'accumulating', 'load', 'loading', 'loaded',
    'oversold', 'support', 'bounce', 'bouncing', 'reversal', 'bottom',
    'bottoming', 'dip', 'discount', 'cheap', 'upside', 'bull run', 'rally',
    'rallying', 'breaking out', 'going up', 'to the moon',
]

BEARISH_KEYWORDS = [
    'sell', 'selling', 'sold', 'short', 'puts', 'dump', 'dumping', 'bearish',
    'crash', 'crashing', 'tank', 'tanking', 'drop', 'dropping', 'breakdown',
    'gap down', 'overvalued', 'distribute', 'overbought', 'resistance',
    'reject', 'rejected', 'peak', 'peaked', 'exit', 'exiting', 'expensive',
    'bubble', 'downside', 'bear market', 'going down', 'falling',
]

# Compile keyword patterns with word boundaries
BULLISH_PATTERNS = [re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE) for kw in BULLISH_KEYWORDS]
BEARISH_PATTERNS = [re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE) for kw in BEARISH_KEYWORDS]

# Context phrases that negate sentiment (e.g., "short term" is not bearish)
NEGATION_PHRASES = [
    re.compile(r'\bshort[- ]term\b', re.IGNORECASE),
    re.compile(r'\blong[- ]term\b', re.IGNORECASE),
    re.compile(r'\blong[- ]haul\b', re.IGNORECASE),
    re.compile(r'\blong[- ]run\b', re.IGNORECASE),
    re.compile(r'\bsupport[- ]level\b', re.IGNORECASE),
    re.compile(r'\bresistance[- ]level\b', re.IGNORECASE),
    re.compile(r'\bbuy[- ]and[- ]hold\b', re.IGNORECASE),
    # Product availability (not stock selling)
    re.compile(r'\bsold[- ]out\b', re.IGNORECASE),
    re.compile(r'\bstock[- ]out\b', re.IGNORECASE),
    re.compile(r'\bout[- ]of[- ]stock\b', re.IGNORECASE),
]


@dataclass
class DiscordMessage:
    """Represents a Discord message with metadata."""
    message_id: str
    channel_id: str
    channel_name: str
    server_id: str
    server_name: str
    author_id: str
    author_name: str
    content: str
    timestamp: str
    tickers_mentioned: list[str]
    emoji_sentiment: float
    keyword_sentiment: float
    reaction_score: float
    is_reply: bool
    reply_to: Optional[str]


@dataclass
class TickerMentionAggregate:
    """Aggregated sentiment data for a ticker."""
    ticker: str
    mention_count: int
    unique_authors: int
    avg_emoji_sentiment: float
    avg_keyword_sentiment: float
    avg_reaction_score: float
    bullish_count: int
    bearish_count: int
    neutral_count: int
    first_mention: str
    last_mention: str
    sample_messages: list[str]
    channels: list[str]


def extract_tickers(text: str) -> list[str]:
    """Extract ticker symbols from message text."""
    # Strip URLs first to avoid matching ticker-like strings in URLs
    text_clean = URL_PATTERN.sub(' ', text)

    tickers = set()

    for match in TICKER_PATTERN.finditer(text_clean):
        # $AAPL style (group 1) or AAPL style (group 2)
        ticker = (match.group(1) or match.group(2) or '').upper()
        if ticker and ticker not in TICKER_BLACKLIST and len(ticker) >= 2:
            tickers.add(ticker)

    return list(tickers)


def calculate_emoji_sentiment(text: str) -> float:
    """Calculate sentiment score from emojis in text."""
    scores = []
    for emoji, score in EMOJI_SENTIMENT.items():
        count = text.count(emoji)
        if count > 0:
            scores.extend([score] * count)

    return sum(scores) / len(scores) if scores else 0.0


def calculate_keyword_sentiment(text: str) -> float:
    """Calculate sentiment score from keywords using word boundary matching."""
    # Strip URLs to avoid false positives (e.g., "dailyrip" in URL)
    text_clean = URL_PATTERN.sub(' ', text)

    # Remove negation phrases before counting (e.g., "short term" shouldn't count as bearish)
    for neg_pattern in NEGATION_PHRASES:
        text_clean = neg_pattern.sub(' ', text_clean)

    # Count bullish keywords using word boundary patterns
    bullish_count = sum(1 for pattern in BULLISH_PATTERNS if pattern.search(text_clean))

    # Count bearish keywords using word boundary patterns
    bearish_count = sum(1 for pattern in BEARISH_PATTERNS if pattern.search(text_clean))

    total = bullish_count + bearish_count
    if total == 0:
        return 0.0

    return (bullish_count - bearish_count) / total


def aggregate_by_ticker(messages: list[DiscordMessage]) -> dict[str, TickerMentionAggregate]:
    """
    Aggregate message sentiment by ticker symbol.

    Args:
        messages: List of Discord messages

    Returns:
        Dict mapping ticker to aggregated sentiment data
    """
    from collections import defaultdict

    ticker_data = defaultdict(lambda: {
        'messages': [],
        'authors': set(),
        'emoji_scores': [],
        'keyword_scores': [],
        'reaction_scores': [],
        'channels': set(),
    })

    for msg in messages:
        for ticker in msg.tickers_mentioned:
            data = ticker_data[ticker]
            data['messages'].append(msg)
            data['authors'].add(msg.author_id)
            data['emoji_scores'].append(msg.emoji_sentiment)
            data['keyword_scores'].append(msg.keyword_sentiment)
            data['reaction_scores'].append(msg.reaction_score)
            data['channels'].add(msg.channel_name)

    aggregates = {}

    for ticker, data in ticker_data.items():
        msgs = data['messages']

        # Calculate sentiment counts
        combined_scores = [
            (m.emoji_sentiment + m.keyword_sentiment + m.reaction_score) / 3
            for m in msgs
        ]
        bullish = sum(1 for s in combined_scores if s > 0.1)
        bearish = sum(1 for s in combined_scores if s < -0.1)
        neutral = len(combined_scores) - bullish - bearish

        # Sort by timestamp
        sorted_msgs = sorted(msgs, key=lambda m: m.timestamp)

        # Sample messages (top 5 most engaged)
        samples = sorted(msgs, key=lambda m: abs(m.emoji_sentiment) + abs(m.reaction_score), reverse=True)[:5]

        aggregates[ticker] = TickerMentionAggregate(
            ticker=ticker,
            mention_count=len(msgs),
            unique_authors=len(data['authors']),
            avg_emoji_sentiment=sum(data['emoji_scores']) / len(data['emoji_scores']),
            avg_keyword_sentiment=sum(data['keyword_scores']) / len(data['keyword_scores']),
            avg_reaction_score=sum(data['reaction_scores']) / len(data['reaction_scores']),
            bullish_count=bullish,
            bearish_count=bearish,
            neutral_count=neutral,
            first_mention=sorted_msgs[0].timestamp,
            last_mention=sorted_msgs[-1].timestamp,
            sample_messages=[m.content[:200] for m in samples],
            channels=list(data['channels']),
        )

    return aggregates


def create_document_for_pipeline(
    ticker: str,
    messages: list[DiscordMessage],
    aggregate: TickerMentionAggregate,
) -> dict:
    """
    Create a document in the format expected by the NLP pipeline.

    Args:
        ticker: Ticker symbol
        messages: Messages mentioning this ticker
        aggregate: Aggregated sentiment data

    Returns:
        Document dict compatible with pipeline
    """
    from collections import defaultdict
    from datetime import datetime, timezone

    # Combine messages into paragraphs (group by hour)
    hourly_groups = defaultdict(list)
    for msg in messages:
        try:
            ts = datetime.fromisoformat(msg.timestamp.replace('Z', '+00:00'))
        except:
            ts = datetime.now(timezone.utc)
        hour_key = ts.strftime('%Y-%m-%d %H:00')
        hourly_groups[hour_key].append(msg)

    paragraphs = []
    for hour, hour_msgs in sorted(hourly_groups.items()):
        combined_text = '\n'.join(m.content for m in hour_msgs)
        paragraphs.append({
            'text': combined_text,
            'position': len(paragraphs),
            'timestamp': hour,
            'message_count': len(hour_msgs),
            'authors': list(set(m.author_name for m in hour_msgs)),
        })

    return {
        'ticker': ticker,
        'source': 'discord',
        'doc_type': 'chat_aggregate',
        'date': datetime.now(timezone.utc).isoformat(),
        'period': f"Last {len(hourly_groups)} hours",
        'metadata': {
            'mention_count': aggregate.mention_count,
            'unique_authors': aggregate.unique_authors,
            'channels': aggregate.channels,
            'sentiment': {
                'emoji': aggregate.avg_emoji_sentiment,
                'keyword': aggregate.avg_keyword_sentiment,
                'reaction': aggregate.avg_reaction_score,
            },
            'distribution': {
                'bullish': aggregate.bullish_count,
                'bearish': aggregate.bearish_count,
                'neutral': aggregate.neutral_count,
            },
        },
        'paragraphs': paragraphs,
        'full_text': '\n\n'.join(p['text'] for p in paragraphs),
    }


def save_results(
    messages: list[DiscordMessage],
    aggregates: dict[str, TickerMentionAggregate],
    output_dir,
    quiet: bool = False,
):
    """Save fetched data to files.

    Args:
        messages: List of Discord messages
        aggregates: Dict of ticker aggregates
        output_dir: Output directory path
        quiet: If True, suppress summary output (for per-channel saves)
    """
    import json
    from pathlib import Path

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save raw messages
    messages_file = output_dir / 'discord_messages.json'
    with open(messages_file, 'w') as f:
        json.dump([asdict(m) for m in messages], f, indent=2)
    if not quiet:
        print(f"Saved {len(messages)} messages to {messages_file}")

    # Save aggregates
    aggregates_file = output_dir / 'discord_aggregates.json'
    with open(aggregates_file, 'w') as f:
        json.dump({k: asdict(v) for k, v in aggregates.items()}, f, indent=2)
    if not quiet:
        print(f"Saved aggregates for {len(aggregates)} tickers to {aggregates_file}")

    # Save pipeline-compatible documents
    docs_dir = output_dir / 'documents'
    docs_dir.mkdir(exist_ok=True)

    for ticker, agg in aggregates.items():
        ticker_msgs = [m for m in messages if ticker in m.tickers_mentioned]
        doc = create_document_for_pipeline(ticker, ticker_msgs, agg)

        doc_file = docs_dir / f'discord_{ticker}.json'
        with open(doc_file, 'w') as f:
            json.dump(doc, f, indent=2)

    if not quiet:
        print(f"Saved {len(aggregates)} pipeline documents to {docs_dir}")

        # Print summary
        print("\n" + "=" * 60)
        print("DISCORD SENTIMENT SUMMARY")
        print("=" * 60)

        # Sort by mention count
        sorted_aggs = sorted(aggregates.values(), key=lambda a: a.mention_count, reverse=True)

        for agg in sorted_aggs[:20]:  # Top 20
            combined_sent = (agg.avg_emoji_sentiment + agg.avg_keyword_sentiment + agg.avg_reaction_score) / 3

            if combined_sent > 0.1:
                signal = "🟢 BULLISH"
            elif combined_sent < -0.1:
                signal = "🔴 BEARISH"
            else:
                signal = "⚪ NEUTRAL"

            print(f"\n{agg.ticker}: {agg.mention_count} mentions by {agg.unique_authors} users")
            print(f"  Signal: {signal} (score: {combined_sent:.2f})")
            print(f"  Distribution: {agg.bullish_count}↑ / {agg.neutral_count}— / {agg.bearish_count}↓")
            print(f"  Channels: {', '.join(agg.channels[:3])}")
