#!/usr/bin/env python3
"""
Enhanced NLP Analysis Module

Features:
1. Temporal Analysis - Track sentiment shifts over time, momentum detection
2. Entity Linking - Map company names to tickers
3. Aspect-Based Sentiment - Categorize WHY bullish/bearish

Usage:
    python enhanced_analysis.py --input discord_messages.json --output enhanced_analysis.json
"""

import json
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# =============================================================================
# ENTITY LINKING - Map company names to tickers
# =============================================================================

# Company name to ticker mapping (extend as needed)
COMPANY_TO_TICKER = {
    # Mega caps
    "apple": "AAPL", "apple inc": "AAPL",
    "microsoft": "MSFT", "msft": "MSFT",
    "google": "GOOGL", "alphabet": "GOOGL", "goog": "GOOGL",
    "amazon": "AMZN", "aws": "AMZN",
    "meta": "META", "facebook": "META", "fb": "META",
    "nvidia": "NVDA", "jensen": "NVDA",
    "tesla": "TSLA", "elon": "TSLA", "musk": "TSLA",
    "netflix": "NFLX",
    "amd": "AMD", "advanced micro": "AMD",
    "intel": "INTC",
    "broadcom": "AVGO",
    "salesforce": "CRM",
    "oracle": "ORCL",
    "adobe": "ADBE",
    "cisco": "CSCO",
    "ibm": "IBM",

    # Finance
    "jpmorgan": "JPM", "jp morgan": "JPM", "jamie dimon": "JPM",
    "goldman": "GS", "goldman sachs": "GS",
    "morgan stanley": "MS",
    "bank of america": "BAC", "bofa": "BAC",
    "wells fargo": "WFC",
    "citigroup": "C", "citi": "C",
    "blackrock": "BLK",
    "berkshire": "BRK.B", "buffett": "BRK.B", "warren buffett": "BRK.B",
    "visa": "V",
    "mastercard": "MA",
    "paypal": "PYPL",
    "square": "SQ", "block": "SQ",
    "robinhood": "HOOD",
    "coinbase": "COIN",

    # Healthcare / Pharma
    "pfizer": "PFE",
    "moderna": "MRNA",
    "johnson & johnson": "JNJ", "j&j": "JNJ",
    "unitedhealth": "UNH",
    "eli lilly": "LLY", "lilly": "LLY",
    "novo nordisk": "NVO", "novo": "NVO", "ozempic": "NVO", "wegovy": "NVO",
    "abbvie": "ABBV",
    "merck": "MRK",
    "bristol myers": "BMY", "bristol-myers": "BMY",

    # Retail / Consumer
    "walmart": "WMT",
    "costco": "COST",
    "target": "TGT",
    "home depot": "HD",
    "lowes": "LOW", "lowe's": "LOW",
    "nike": "NKE",
    "starbucks": "SBUX",
    "mcdonalds": "MCD", "mcdonald's": "MCD",
    "coca cola": "KO", "coca-cola": "KO", "coke": "KO",
    "pepsi": "PEP", "pepsico": "PEP",
    "disney": "DIS",
    "uber": "UBER",
    "airbnb": "ABNB",
    "doordash": "DASH",

    # Energy
    "exxon": "XOM", "exxonmobil": "XOM",
    "chevron": "CVX",
    "conocophillips": "COP",
    "shell": "SHEL",
    "bp": "BP",
    "schlumberger": "SLB",

    # EV / Clean Energy
    "rivian": "RIVN",
    "lucid": "LCID",
    "nio": "NIO",
    "byd": "BYDDY",
    "enphase": "ENPH",
    "solaredge": "SEDG",
    "first solar": "FSLR",
    "plug power": "PLUG",
    "chargepoint": "CHPT",

    # Space
    "rocket lab": "RKLB", "rocketlab": "RKLB",
    "spacex": "PRIVATE:SPACEX",  # Private company marker
    "boeing": "BA",
    "lockheed": "LMT", "lockheed martin": "LMT",
    "northrop": "NOC", "northrop grumman": "NOC",
    "raytheon": "RTX",

    # Semiconductors
    "tsmc": "TSM", "taiwan semi": "TSM",
    "asml": "ASML",
    "qualcomm": "QCOM",
    "micron": "MU",
    "applied materials": "AMAT",
    "lam research": "LRCX",
    "marvell": "MRVL",

    # Other notable
    "palantir": "PLTR",
    "snowflake": "SNOW",
    "datadog": "DDOG",
    "crowdstrike": "CRWD",
    "zscaler": "ZS",
    "cloudflare": "NET",
    "shopify": "SHOP",
    "zoom": "ZM",
    "docusign": "DOCU",
    "okta": "OKTA",
    "twilio": "TWLO",
    "unity": "U",
    "roblox": "RBLX",
    "draftkings": "DKNG",
    "gamestop": "GME",
    "amc": "AMC",
    "bed bath": "BBBYQ",  # Bankrupt but still mentioned
}

# Compile regex patterns for entity matching (keyed by name, not ticker)
ENTITY_PATTERNS = {
    name: re.compile(r'\b' + re.escape(name) + r'\b', re.IGNORECASE)
    for name, ticker in COMPANY_TO_TICKER.items()
}


def extract_entities(text: str) -> list[tuple[str, str]]:
    """
    Extract company mentions and map to tickers.

    Returns:
        List of (matched_text, ticker) tuples
    """
    entities = []
    text_lower = text.lower()

    for name, ticker in COMPANY_TO_TICKER.items():
        if name in text_lower:
            # Verify it's a word boundary match
            pattern = ENTITY_PATTERNS.get(name)
            if pattern and pattern.search(text):
                entities.append((name, ticker))

    return entities


# =============================================================================
# ASPECT-BASED SENTIMENT - Categorize WHY bullish/bearish
# =============================================================================

@dataclass
class AspectSentiment:
    """Sentiment for a specific aspect of a company."""
    aspect: str
    sentiment: float  # -1 to 1
    confidence: float
    evidence: list[str]  # Matching phrases


# Aspect keywords and phrases
ASPECT_PATTERNS = {
    "management": {
        "keywords": [
            "ceo", "cfo", "cto", "management", "executive", "leadership",
            "founder", "board", "director", "chairman", "president",
            "insider", "insider buying", "insider selling",
        ],
        "bullish": [
            "strong leadership", "great ceo", "smart management", "visionary",
            "insider buying", "skin in the game", "founder-led", "experienced team",
            "good capital allocation", "shareholder friendly",
        ],
        "bearish": [
            "bad management", "incompetent", "insider selling", "ceo leaving",
            "turnover", "scandal", "fraud", "lawsuit", "sec investigation",
            "poor execution", "overpaid executives",
        ],
    },
    "product": {
        "keywords": [
            "product", "service", "launch", "release", "feature", "innovation",
            "technology", "platform", "app", "software", "hardware", "device",
            "customer", "user", "adoption", "market share", "moat",
        ],
        "bullish": [
            "great product", "best in class", "innovative", "game changer",
            "strong moat", "market leader", "growing adoption", "love the product",
            "sticky customers", "high retention", "expanding tam",
        ],
        "bearish": [
            "bad product", "losing share", "outdated", "competitors catching up",
            "no moat", "commoditized", "declining users", "churn", "buggy",
            "quality issues", "recall",
        ],
    },
    "valuation": {
        "keywords": [
            "valuation", "price", "pe", "p/e", "multiple", "ev/ebitda", "peg",
            "cheap", "expensive", "undervalued", "overvalued", "fair value",
            "dcf", "intrinsic", "margin of safety", "discount", "premium",
        ],
        "bullish": [
            "undervalued", "cheap", "discount", "low multiple", "attractive valuation",
            "margin of safety", "value play", "beaten down", "oversold",
            "good entry point", "buying opportunity",
        ],
        "bearish": [
            "overvalued", "expensive", "bubble", "priced to perfection",
            "high multiple", "no margin of safety", "stretched valuation",
            "priced in", "fully valued", "overbought",
        ],
    },
    "growth": {
        "keywords": [
            "growth", "revenue", "earnings", "eps", "sales", "guidance",
            "acceleration", "deceleration", "yoy", "qoq", "beat", "miss",
            "outlook", "forecast", "estimate", "surprise",
        ],
        "bullish": [
            "accelerating growth", "beat estimates", "raised guidance",
            "strong growth", "revenue acceleration", "eps beat",
            "positive surprise", "outperform", "momentum",
        ],
        "bearish": [
            "decelerating growth", "missed estimates", "lowered guidance",
            "slowing growth", "revenue miss", "eps miss", "negative surprise",
            "underperform", "growth concerns",
        ],
    },
    "competition": {
        "keywords": [
            "competitor", "competition", "market share", "rival", "vs",
            "versus", "compared to", "alternative", "switching",
        ],
        "bullish": [
            "beating competition", "taking share", "competitive advantage",
            "winner", "best in class", "no real competition", "dominant",
        ],
        "bearish": [
            "losing to competitors", "losing share", "competition heating up",
            "commoditized", "no differentiation", "being disrupted",
        ],
    },
    "macro": {
        "keywords": [
            "fed", "rates", "inflation", "recession", "economy", "macro",
            "gdp", "unemployment", "tariff", "regulation", "policy",
            "election", "geopolitical", "war", "china", "europe",
        ],
        "bullish": [
            "rate cuts", "soft landing", "economic recovery", "tailwind",
            "beneficiary", "hedge against inflation",
        ],
        "bearish": [
            "rate hikes", "recession risk", "headwind", "tariff risk",
            "regulatory risk", "geopolitical risk", "exposure to china",
        ],
    },
}


def analyze_aspects(text: str) -> dict[str, AspectSentiment]:
    """
    Analyze sentiment by aspect (management, product, valuation, etc.)

    Returns:
        Dict mapping aspect name to AspectSentiment
    """
    text_lower = text.lower()
    results = {}

    for aspect, patterns in ASPECT_PATTERNS.items():
        # Check if this aspect is mentioned
        aspect_mentioned = any(kw in text_lower for kw in patterns["keywords"])

        if not aspect_mentioned:
            continue

        # Count bullish/bearish signals
        bullish_matches = []
        bearish_matches = []

        for phrase in patterns["bullish"]:
            if phrase in text_lower:
                bullish_matches.append(phrase)

        for phrase in patterns["bearish"]:
            if phrase in text_lower:
                bearish_matches.append(phrase)

        # Calculate sentiment
        total = len(bullish_matches) + len(bearish_matches)
        if total > 0:
            sentiment = (len(bullish_matches) - len(bearish_matches)) / total
            confidence = min(total / 3, 1.0)  # More matches = more confidence
        else:
            sentiment = 0.0
            confidence = 0.3  # Low confidence if aspect mentioned but no clear signal

        results[aspect] = AspectSentiment(
            aspect=aspect,
            sentiment=sentiment,
            confidence=confidence,
            evidence=bullish_matches + bearish_matches,
        )

    return results


# =============================================================================
# TEMPORAL ANALYSIS - Track sentiment over time
# =============================================================================

@dataclass
class TemporalWindow:
    """Sentiment data for a time window."""
    start: str
    end: str
    message_count: int
    avg_sentiment: float
    bullish_count: int
    bearish_count: int
    neutral_count: int
    momentum: float  # Change from previous window
    tickers: list[str]


@dataclass
class SentimentShift:
    """Detected sentiment shift/reversal."""
    ticker: str
    timestamp: str
    previous_sentiment: float
    new_sentiment: float
    shift_magnitude: float
    direction: str  # "bullish_reversal" or "bearish_reversal"
    evidence: list[str]


def analyze_temporal(
    messages: list[dict],
    window_hours: int = 24,
) -> dict:
    """
    Analyze sentiment over time.

    Args:
        messages: List of message dicts with timestamp and sentiment
        window_hours: Size of time windows in hours

    Returns:
        Dict with temporal analysis results
    """
    if not messages:
        return {"windows": [], "shifts": [], "momentum": {}}

    # Parse timestamps and sort
    for msg in messages:
        try:
            ts_str = msg.get("timestamp", "")
            if ts_str:
                msg["_parsed_ts"] = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            else:
                msg["_parsed_ts"] = datetime.now()
        except:
            msg["_parsed_ts"] = datetime.now()

    messages_sorted = sorted(messages, key=lambda m: m["_parsed_ts"])

    if not messages_sorted:
        return {"windows": [], "shifts": [], "momentum": {}}

    # Group into time windows
    start_time = messages_sorted[0]["_parsed_ts"]
    end_time = messages_sorted[-1]["_parsed_ts"]

    windows = []
    current_start = start_time
    window_delta = timedelta(hours=window_hours)

    while current_start <= end_time:
        current_end = current_start + window_delta

        # Get messages in this window
        window_msgs = [
            m for m in messages_sorted
            if current_start <= m["_parsed_ts"] < current_end
        ]

        if window_msgs:
            # Get sentiment scores
            sentiments = []
            for m in window_msgs:
                # Try FinBERT first, fall back to keyword
                if "finbert_sentiment" in m:
                    sentiments.append(m["finbert_sentiment"]["score"])
                else:
                    sentiments.append(m.get("keyword_sentiment", 0))

            avg_sent = sum(sentiments) / len(sentiments)
            bullish = sum(1 for s in sentiments if s > 0.2)
            bearish = sum(1 for s in sentiments if s < -0.2)
            neutral = len(sentiments) - bullish - bearish

            # Collect tickers
            tickers = set()
            for m in window_msgs:
                tickers.update(m.get("tickers_mentioned", []))

            # Calculate momentum (change from previous window)
            momentum = 0.0
            if windows:
                momentum = avg_sent - windows[-1].avg_sentiment

            windows.append(TemporalWindow(
                start=current_start.isoformat(),
                end=current_end.isoformat(),
                message_count=len(window_msgs),
                avg_sentiment=avg_sent,
                bullish_count=bullish,
                bearish_count=bearish,
                neutral_count=neutral,
                momentum=momentum,
                tickers=list(tickers),
            ))

        current_start = current_end

    # Detect sentiment shifts by ticker
    shifts = detect_sentiment_shifts(messages_sorted, window_hours)

    # Calculate overall momentum by ticker
    momentum_by_ticker = calculate_ticker_momentum(messages_sorted)

    return {
        "windows": [asdict(w) for w in windows],
        "shifts": [asdict(s) for s in shifts],
        "momentum": momentum_by_ticker,
    }


def detect_sentiment_shifts(
    messages: list[dict],
    window_hours: int = 24,
    threshold: float = 0.5,
) -> list[SentimentShift]:
    """
    Detect significant sentiment reversals for tickers.
    """
    shifts = []

    # Group messages by ticker
    ticker_msgs = defaultdict(list)
    for msg in messages:
        for ticker in msg.get("tickers_mentioned", []):
            ticker_msgs[ticker].append(msg)

    window_delta = timedelta(hours=window_hours)

    for ticker, msgs in ticker_msgs.items():
        if len(msgs) < 3:  # Need enough data
            continue

        msgs_sorted = sorted(msgs, key=lambda m: m["_parsed_ts"])

        # Calculate rolling sentiment
        prev_sentiment = None
        prev_window_msgs = []

        for i, msg in enumerate(msgs_sorted):
            current_ts = msg["_parsed_ts"]

            # Get messages in current window
            window_start = current_ts - window_delta
            current_window = [
                m for m in msgs_sorted
                if window_start <= m["_parsed_ts"] <= current_ts
            ]

            if len(current_window) >= 2:
                # Calculate current window sentiment
                sentiments = []
                for m in current_window:
                    if "finbert_sentiment" in m:
                        sentiments.append(m["finbert_sentiment"]["score"])
                    else:
                        sentiments.append(m.get("keyword_sentiment", 0))

                current_sentiment = sum(sentiments) / len(sentiments)

                # Check for significant shift
                if prev_sentiment is not None:
                    shift = current_sentiment - prev_sentiment

                    if abs(shift) >= threshold:
                        direction = "bullish_reversal" if shift > 0 else "bearish_reversal"

                        # Get evidence (recent messages)
                        evidence = [m.get("content", "")[:100] for m in current_window[-3:]]

                        shifts.append(SentimentShift(
                            ticker=ticker,
                            timestamp=current_ts.isoformat(),
                            previous_sentiment=prev_sentiment,
                            new_sentiment=current_sentiment,
                            shift_magnitude=abs(shift),
                            direction=direction,
                            evidence=evidence,
                        ))

                prev_sentiment = current_sentiment

    return shifts


def calculate_ticker_momentum(messages: list[dict]) -> dict:
    """
    Calculate sentiment momentum for each ticker.

    Momentum = recent sentiment - older sentiment
    """
    momentum = {}

    # Group by ticker
    ticker_msgs = defaultdict(list)
    for msg in messages:
        for ticker in msg.get("tickers_mentioned", []):
            ticker_msgs[ticker].append(msg)

    for ticker, msgs in ticker_msgs.items():
        if len(msgs) < 2:
            continue

        msgs_sorted = sorted(msgs, key=lambda m: m["_parsed_ts"])

        # Split into first half and second half
        mid = len(msgs_sorted) // 2
        first_half = msgs_sorted[:mid]
        second_half = msgs_sorted[mid:]

        def avg_sentiment(msg_list):
            sents = []
            for m in msg_list:
                if "finbert_sentiment" in m:
                    sents.append(m["finbert_sentiment"]["score"])
                else:
                    sents.append(m.get("keyword_sentiment", 0))
            return sum(sents) / len(sents) if sents else 0

        old_sent = avg_sentiment(first_half)
        new_sent = avg_sentiment(second_half)

        momentum[ticker] = {
            "old_sentiment": old_sent,
            "new_sentiment": new_sent,
            "momentum": new_sent - old_sent,
            "direction": "improving" if new_sent > old_sent else "deteriorating",
            "message_count": len(msgs),
        }

    return momentum


# =============================================================================
# MAIN ENHANCED ANALYSIS
# =============================================================================

def run_enhanced_analysis(
    messages_file: str | Path,
    output_file: Optional[str | Path] = None,
    window_hours: int = 24,
) -> dict:
    """
    Run full enhanced analysis on Discord messages.

    Args:
        messages_file: Path to discord_messages.json
        output_file: Output file path (optional)
        window_hours: Time window size for temporal analysis

    Returns:
        Dict with all analysis results
    """
    messages_file = Path(messages_file)

    print(f"Loading messages from {messages_file}...")
    with open(messages_file) as f:
        messages = json.load(f)

    print(f"Analyzing {len(messages)} messages...")

    # 1. Entity Linking - Find additional tickers from company names
    print("  Running entity linking...")
    entity_extractions = 0
    for msg in messages:
        entities = extract_entities(msg.get("content", ""))
        if entities:
            existing_tickers = set(msg.get("tickers_mentioned", []))
            for name, ticker in entities:
                if ticker not in existing_tickers and not ticker.startswith("PRIVATE:"):
                    if "entities_found" not in msg:
                        msg["entities_found"] = []
                    msg["entities_found"].append({"name": name, "ticker": ticker})
                    msg["tickers_mentioned"] = list(existing_tickers | {ticker})
                    entity_extractions += 1

    print(f"    Found {entity_extractions} additional ticker references from company names")

    # 2. Aspect-Based Sentiment
    print("  Running aspect-based analysis...")
    aspect_counts = defaultdict(int)
    for msg in messages:
        aspects = analyze_aspects(msg.get("content", ""))
        if aspects:
            msg["aspects"] = {k: asdict(v) for k, v in aspects.items()}
            for aspect in aspects:
                aspect_counts[aspect] += 1

    print(f"    Aspect mentions: {dict(aspect_counts)}")

    # 3. Temporal Analysis
    print("  Running temporal analysis...")
    temporal = analyze_temporal(messages, window_hours)

    print(f"    Time windows: {len(temporal['windows'])}")
    print(f"    Sentiment shifts detected: {len(temporal['shifts'])}")

    # Aggregate results
    print("  Aggregating results...")

    # Aggregate aspects by ticker
    ticker_aspects = defaultdict(lambda: defaultdict(list))
    for msg in messages:
        for ticker in msg.get("tickers_mentioned", []):
            for aspect, data in msg.get("aspects", {}).items():
                ticker_aspects[ticker][aspect].append(data["sentiment"])

    # Calculate average aspect sentiment per ticker
    ticker_aspect_summary = {}
    for ticker, aspects in ticker_aspects.items():
        ticker_aspect_summary[ticker] = {
            aspect: {
                "avg_sentiment": sum(sents) / len(sents),
                "mention_count": len(sents),
            }
            for aspect, sents in aspects.items()
        }

    # Build output
    output = {
        "analysis_type": "enhanced",
        "messages_analyzed": len(messages),
        "entity_extractions": entity_extractions,
        "temporal": temporal,
        "ticker_aspects": ticker_aspect_summary,
        "aspect_summary": {
            aspect: count for aspect, count in sorted(
                aspect_counts.items(), key=lambda x: -x[1]
            )
        },
        "messages": messages,  # Include enriched messages
    }

    # Save output
    if output_file:
        output_file = Path(output_file)
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2, default=str)
        print(f"\nSaved enhanced analysis to {output_file}")

    # Print summary
    print("\n" + "=" * 60)
    print("ENHANCED NLP ANALYSIS SUMMARY")
    print("=" * 60)

    print(f"\nEntity Linking: Found {entity_extractions} company name -> ticker mappings")

    print(f"\nAspect Analysis:")
    for aspect, count in sorted(aspect_counts.items(), key=lambda x: -x[1])[:6]:
        print(f"  {aspect}: {count} mentions")

    print(f"\nTemporal Analysis:")
    print(f"  Windows: {len(temporal['windows'])}")
    print(f"  Shifts: {len(temporal['shifts'])}")

    if temporal['shifts']:
        print("\n  Recent Sentiment Shifts:")
        for shift in temporal['shifts'][:5]:
            direction = "+" if shift['direction'] == 'bullish_reversal' else "-"
            print(f"    {shift['ticker']}: {shift['previous_sentiment']:.2f} -> {shift['new_sentiment']:.2f} ({direction})")

    if temporal['momentum']:
        print("\n  Sentiment Momentum (Top Movers):")
        sorted_momentum = sorted(
            temporal['momentum'].items(),
            key=lambda x: abs(x[1]['momentum']),
            reverse=True
        )[:5]
        for ticker, data in sorted_momentum:
            arrow = "^" if data['momentum'] > 0 else "v"
            print(f"    {ticker}: {data['momentum']:+.2f} ({arrow} {data['direction']})")

    return output


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Enhanced NLP Analysis")
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input messages JSON file",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path",
    )
    parser.add_argument(
        "--window-hours", "-w",
        type=int,
        default=24,
        help="Time window size in hours (default: 24)",
    )

    args = parser.parse_args()

    run_enhanced_analysis(
        messages_file=args.input,
        output_file=args.output,
        window_hours=args.window_hours,
    )


if __name__ == "__main__":
    main()
