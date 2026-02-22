"""
Fixed signal ontology for narrative drift detection.

Small, fixed set of signal categories for manual labeling.
Use these tags after NLP filtering surfaces candidate snippets.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SignalDirection(Enum):
    """Direction of signal change."""
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"


class SignalCategory(Enum):
    """
    Fixed ontology of signal categories.

    Each signal represents a specific narrative dimension that can
    improve or deteriorate. Keep this list small and interpretable.
    """
    # Pricing and margin
    PRICING_POWER = "pricing_power"
    MARGIN_PRESSURE = "margin_pressure"
    COST_INFLATION = "cost_inflation"

    # Demand and visibility
    DEMAND_VISIBILITY = "demand_visibility"
    ORDER_BOOK = "order_book"
    BACKLOG = "backlog"

    # Competitive position
    COMPETITIVE_THREAT = "competitive_threat"
    MARKET_SHARE = "market_share"

    # Regulatory and legal
    REGULATORY_OVERHANG = "regulatory_overhang"
    LITIGATION_RISK = "litigation_risk"

    # Guidance and confidence
    GUIDANCE_CONFIDENCE = "guidance_confidence"
    MANAGEMENT_TONE = "management_tone"

    # Operations
    SUPPLY_CHAIN = "supply_chain"
    EXECUTION_RISK = "execution_risk"

    # Capital and liquidity
    CAPITAL_ALLOCATION = "capital_allocation"
    LIQUIDITY_CONCERN = "liquidity_concern"


@dataclass
class Signal:
    """A detected narrative signal."""
    category: SignalCategory
    direction: SignalDirection
    ticker: str
    filing_date: str
    section: str  # e.g., "mda", "risk_factors", "qa", "prepared_remarks"
    snippet_text: str
    prior_text: Optional[str]  # Comparison text from prior period
    delta_score: float  # Cosine distance from prior/centroid
    confidence: float  # 0-1 confidence in detection
    first_seen: str  # Date first detected
    human_label: Optional[str] = None  # Manual label after review
    notes: Optional[str] = None  # Analyst notes


def signal_tag(category: SignalCategory, direction: SignalDirection) -> str:
    """Generate a signal tag string (e.g., 'pricing_power_down')."""
    return f"{category.value}_{direction.value}"


def parse_signal_tag(tag: str) -> tuple[SignalCategory, SignalDirection]:
    """Parse a signal tag back into category and direction."""
    parts = tag.rsplit("_", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid signal tag: {tag}")

    category_str, direction_str = parts
    return SignalCategory(category_str), SignalDirection(direction_str)


# Pre-defined signal tags for convenience
SIGNAL_TAGS = [
    signal_tag(cat, dir)
    for cat in SignalCategory
    for dir in [SignalDirection.UP, SignalDirection.DOWN]
]


# Hedging language indicators (increase = negative signal)
HEDGING_WORDS = {
    "may", "might", "could", "possibly", "potentially",
    "uncertain", "uncertainty", "unclear", "unknown",
    "challenging", "challenges", "difficult", "difficulties",
    "risk", "risks", "concern", "concerns", "cautious",
    "volatile", "volatility", "headwind", "headwinds",
    "pressure", "pressures", "constrained", "constraints",
}

# Commitment ladder (descending strength)
COMMITMENT_LADDER = [
    ("will", 1.0),
    ("expect", 0.8),
    ("anticipate", 0.7),
    ("believe", 0.6),
    ("intend", 0.5),
    ("plan", 0.5),
    ("target", 0.4),
    ("aim", 0.4),
    ("hope", 0.3),
    ("monitor", 0.2),
    ("evaluate", 0.2),
    ("assess", 0.2),
]

# Evasive/defensive language indicators
EVASIVE_PHRASES = [
    "as i mentioned",
    "as we've discussed",
    "as you know",
    "let me be clear",
    "to be clear",
    "i think the question is",
    "that's a good question",
    "i appreciate the question",
    "let me take a step back",
    "let me give you some context",
    "it's hard to say",
    "it's difficult to predict",
    "we're still evaluating",
    "we're still assessing",
    "we're monitoring",
    "we'll see",
    "time will tell",
    "too early to say",
    "premature to",
]

# Positive/improving language indicators
IMPROVING_WORDS = {
    "accelerating", "acceleration", "momentum", "tailwind", "tailwinds",
    "strength", "strong", "robust", "solid", "resilient",
    "exceeding", "exceeded", "outperforming", "outperformed",
    "optimistic", "confident", "conviction", "visibility",
    "expanding", "expansion", "growing", "growth",
    "improving", "improvement", "better", "stronger",
}


def get_commitment_strength(word: str) -> Optional[float]:
    """Get commitment strength for a word (1.0 = strongest, 0.0 = weakest)."""
    word_lower = word.lower()
    for w, strength in COMMITMENT_LADDER:
        if w == word_lower:
            return strength
    return None


def is_hedging_word(word: str) -> bool:
    """Check if word is a hedging indicator."""
    return word.lower() in HEDGING_WORDS


def is_improving_word(word: str) -> bool:
    """Check if word indicates improvement."""
    return word.lower() in IMPROVING_WORDS


def contains_evasive_phrase(text: str) -> list[str]:
    """Find evasive phrases in text."""
    text_lower = text.lower()
    return [phrase for phrase in EVASIVE_PHRASES if phrase in text_lower]
