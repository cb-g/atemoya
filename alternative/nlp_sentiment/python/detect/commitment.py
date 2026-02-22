#!/usr/bin/env python3
"""
Commitment strength tracking for narrative drift.

Tracks management commitment language and detects downgrades/upgrades
in commitment level over time.

Commitment ladder (descending strength):
  will > expect > anticipate > believe > intend > target > hope > monitor

Usage:
    from detect.commitment import CommitmentDetector

    detector = CommitmentDetector()
    result = detector.analyze(text)
"""

import re
from dataclasses import dataclass
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ontology import COMMITMENT_LADDER


@dataclass
class CommitmentResult:
    """Result of commitment language analysis."""
    average_commitment: float  # 0-1 average commitment strength
    weighted_commitment: float  # Weighted by frequency
    total_commitment_words: int
    word_count: int
    commitment_density: float  # Per 1000 words
    commitment_distribution: dict[str, int]  # Word -> count
    top_commitment_phrases: list[dict]  # Phrases with context
    commitment_tier: str  # High/Medium/Low


@dataclass
class CommitmentChange:
    """Change in commitment between documents."""
    current_commitment: float
    prior_commitment: float
    delta: float  # Positive = stronger commitment
    direction: str  # "upgrade", "downgrade", or "stable"
    tier_change: str  # e.g., "High -> Medium"
    word_migrations: list[dict]  # Words that changed between documents
    significant_downgrades: list[str]  # Specific downgrade examples


# Extended commitment patterns with context
COMMITMENT_PATTERNS = {
    # Strongest commitment (1.0)
    "will": {
        "strength": 1.0,
        "patterns": [
            r"\bwe\s+will\b",
            r"\bwill\s+continue\b",
            r"\bwill\s+deliver\b",
            r"\bwill\s+achieve\b",
            r"\bwill\s+execute\b",
            r"\bwill\s+grow\b",
            r"\bwill\s+increase\b",
        ]
    },

    # Strong commitment (0.8)
    "expect": {
        "strength": 0.8,
        "patterns": [
            r"\bwe\s+expect\b",
            r"\bexpect\s+to\b",
            r"\bexpecting\b",
            r"\bexpectation(?:s)?\b",
        ]
    },

    # Good commitment (0.7)
    "anticipate": {
        "strength": 0.7,
        "patterns": [
            r"\banticipate\b",
            r"\banticipating\b",
            r"\banticipated\b",
        ]
    },

    # Medium commitment (0.6)
    "believe": {
        "strength": 0.6,
        "patterns": [
            r"\bwe\s+believe\b",
            r"\bbelieve\s+(?:that|we)\b",
            r"\bour\s+belief\b",
        ]
    },

    # Moderate commitment (0.5)
    "intend": {
        "strength": 0.5,
        "patterns": [
            r"\bintend\s+to\b",
            r"\bintention\b",
            r"\bplanning\s+to\b",
            r"\bplan\s+to\b",
            r"\bour\s+plan\b",
        ]
    },

    # Target-based (0.4)
    "target": {
        "strength": 0.4,
        "patterns": [
            r"\btarget(?:ing|ed)?\b",
            r"\baim(?:ing|ed)?\s+(?:to|for)\b",
            r"\bgoal\s+(?:is|of)\b",
            r"\bobjective\b",
        ]
    },

    # Weak commitment (0.3)
    "hope": {
        "strength": 0.3,
        "patterns": [
            r"\bhope\s+to\b",
            r"\bhopeful(?:ly)?\b",
            r"\boptimistic\b",
            r"\baspir(?:e|ing|ation)\b",
        ]
    },

    # Very weak (0.2)
    "monitor": {
        "strength": 0.2,
        "patterns": [
            r"\bmonitor(?:ing)?\b",
            r"\bevaluat(?:e|ing)\b",
            r"\bassess(?:ing)?\b",
            r"\bwatch(?:ing)?\b",
            r"\btrack(?:ing)?\b",
        ]
    },

    # Weakest (0.1)
    "consider": {
        "strength": 0.1,
        "patterns": [
            r"\bconsider(?:ing)?\b",
            r"\bexplor(?:e|ing)\b",
            r"\bexamin(?:e|ing)\b",
            r"\blook(?:ing)?\s+(?:at|into)\b",
        ]
    },
}

# Compile patterns
_COMMITMENT_COMPILED = {}
for word, info in COMMITMENT_PATTERNS.items():
    _COMMITMENT_COMPILED[word] = {
        "strength": info["strength"],
        "patterns": [re.compile(p, re.IGNORECASE) for p in info["patterns"]]
    }


def get_commitment_tier(score: float) -> str:
    """Convert commitment score to tier."""
    if score >= 0.7:
        return "High"
    elif score >= 0.4:
        return "Medium"
    else:
        return "Low"


class CommitmentDetector:
    """
    Detects and quantifies commitment language in text.

    Tracks the commitment ladder and identifies changes in commitment level.
    """

    def __init__(self):
        """Initialize commitment detector."""
        self.patterns = _COMMITMENT_COMPILED

    def analyze(self, text: str) -> CommitmentResult:
        """
        Analyze text for commitment language.

        Args:
            text: Text to analyze

        Returns:
            CommitmentResult with commitment metrics
        """
        words = text.split()
        word_count = len(words)

        if word_count == 0:
            return CommitmentResult(
                average_commitment=0.0,
                weighted_commitment=0.0,
                total_commitment_words=0,
                word_count=0,
                commitment_density=0.0,
                commitment_distribution={},
                top_commitment_phrases=[],
                commitment_tier="Low",
            )

        # Count commitment patterns
        commitment_counts = {}
        total_strength = 0.0
        total_count = 0

        for word, info in self.patterns.items():
            count = 0
            for pattern in info["patterns"]:
                matches = pattern.findall(text)
                count += len(matches)

            if count > 0:
                commitment_counts[word] = count
                total_strength += info["strength"] * count
                total_count += count

        # Calculate averages
        average_commitment = total_strength / total_count if total_count > 0 else 0.0

        # Weighted by position in text (earlier = more weight)
        weighted_commitment = self._calculate_weighted_commitment(text)

        # Density
        commitment_density = (total_count / word_count) * 1000 if word_count > 0 else 0

        # Get commitment tier
        commitment_tier = get_commitment_tier(average_commitment)

        # Find top commitment phrases with context
        top_phrases = self._find_commitment_phrases(text, top_n=10)

        return CommitmentResult(
            average_commitment=average_commitment,
            weighted_commitment=weighted_commitment,
            total_commitment_words=total_count,
            word_count=word_count,
            commitment_density=commitment_density,
            commitment_distribution=commitment_counts,
            top_commitment_phrases=top_phrases,
            commitment_tier=commitment_tier,
        )

    def _calculate_weighted_commitment(self, text: str) -> float:
        """
        Calculate commitment weighted by position.

        Earlier commitments (e.g., in opening remarks) get higher weight.
        """
        text_lower = text.lower()
        text_len = len(text_lower)

        if text_len == 0:
            return 0.0

        weighted_sum = 0.0
        weight_sum = 0.0

        for word, info in self.patterns.items():
            for pattern in info["patterns"]:
                for match in pattern.finditer(text):
                    # Position weight: 1.0 at start, 0.5 at end
                    position = match.start() / text_len
                    position_weight = 1.0 - (position * 0.5)

                    weighted_sum += info["strength"] * position_weight
                    weight_sum += position_weight

        return weighted_sum / weight_sum if weight_sum > 0 else 0.0

    def _find_commitment_phrases(self, text: str, top_n: int = 10) -> list[dict]:
        """Find commitment phrases with surrounding context."""
        phrases = []

        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)

        for i, sentence in enumerate(sentences):
            if len(sentence) < 20:
                continue

            # Check for commitment patterns in this sentence
            for word, info in self.patterns.items():
                for pattern in info["patterns"]:
                    if pattern.search(sentence):
                        phrases.append({
                            "word": word,
                            "strength": info["strength"],
                            "sentence": sentence[:300],
                            "sentence_index": i,
                        })
                        break  # One per word type per sentence

        # Sort by strength (descending)
        phrases.sort(key=lambda x: x["strength"], reverse=True)
        return phrases[:top_n]

    def compare(self, current_text: str, prior_text: str) -> CommitmentChange:
        """
        Compare commitment levels between current and prior text.

        Args:
            current_text: Current period text
            prior_text: Prior period text

        Returns:
            CommitmentChange with comparison metrics
        """
        current_result = self.analyze(current_text)
        prior_result = self.analyze(prior_text)

        delta = current_result.average_commitment - prior_result.average_commitment

        # Determine direction
        if delta > 0.1:
            direction = "upgrade"
        elif delta < -0.1:
            direction = "downgrade"
        else:
            direction = "stable"

        # Tier change
        tier_change = f"{prior_result.commitment_tier} -> {current_result.commitment_tier}"

        # Word migrations (what commitment words changed)
        word_migrations = self._analyze_word_migrations(
            current_result.commitment_distribution,
            prior_result.commitment_distribution
        )

        # Find significant downgrades
        significant_downgrades = self._find_significant_downgrades(
            current_result.top_commitment_phrases,
            prior_result.top_commitment_phrases
        )

        return CommitmentChange(
            current_commitment=current_result.average_commitment,
            prior_commitment=prior_result.average_commitment,
            delta=delta,
            direction=direction,
            tier_change=tier_change,
            word_migrations=word_migrations,
            significant_downgrades=significant_downgrades,
        )

    def _analyze_word_migrations(
        self,
        current_dist: dict[str, int],
        prior_dist: dict[str, int]
    ) -> list[dict]:
        """Analyze how commitment word usage changed."""
        migrations = []

        all_words = set(current_dist.keys()) | set(prior_dist.keys())

        for word in all_words:
            current_count = current_dist.get(word, 0)
            prior_count = prior_dist.get(word, 0)
            strength = self.patterns.get(word, {}).get("strength", 0.5)

            if current_count != prior_count:
                migrations.append({
                    "word": word,
                    "strength": strength,
                    "prior_count": prior_count,
                    "current_count": current_count,
                    "change": current_count - prior_count,
                    "direction": "increased" if current_count > prior_count else "decreased",
                })

        # Sort by strength * change magnitude
        migrations.sort(key=lambda x: abs(x["strength"] * x["change"]), reverse=True)
        return migrations[:10]

    def _find_significant_downgrades(
        self,
        current_phrases: list[dict],
        prior_phrases: list[dict]
    ) -> list[str]:
        """
        Find specific examples where commitment language was downgraded.

        For example: "we will" -> "we expect" -> "we may"
        """
        downgrades = []

        # Group prior phrases by sentence similarity
        prior_strong = [p for p in prior_phrases if p["strength"] >= 0.7]

        # Check if similar context now uses weaker language
        for prior in prior_strong[:5]:
            prior_sentence = prior["sentence"].lower()

            # Look for similar topics in current with weaker commitment
            for current in current_phrases:
                if current["strength"] < prior["strength"] - 0.2:
                    # Check for topical similarity (very simple)
                    prior_words = set(prior_sentence.split())
                    current_words = set(current["sentence"].lower().split())

                    common = len(prior_words & current_words)
                    if common >= 3:  # Some overlap
                        downgrades.append(
                            f"'{prior['word']}' ({prior['strength']:.1f}) -> "
                            f"'{current['word']}' ({current['strength']:.1f})"
                        )

        return downgrades[:5]


def analyze_document_commitment(document: dict, detector: Optional[CommitmentDetector] = None) -> dict:
    """
    Analyze commitment in a document with paragraph-level breakdown.

    Args:
        document: Document dict with 'text' and 'paragraphs'
        detector: CommitmentDetector instance

    Returns:
        Document dict augmented with commitment analysis
    """
    detector = detector or CommitmentDetector()

    # Document-level analysis
    full_text = document.get("text", "")
    doc_result = detector.analyze(full_text)

    # Paragraph-level analysis
    paragraphs = document.get("paragraphs", [])
    paragraph_results = []

    for para in paragraphs:
        para_text = para.get("text", "")
        para_result = detector.analyze(para_text)

        paragraph_results.append({
            **para,
            "commitment_score": para_result.average_commitment,
            "commitment_tier": para_result.commitment_tier,
            "commitment_density": para_result.commitment_density,
        })

    # Find paragraphs with weakest commitment
    weak_commitment_paras = sorted(
        [p for p in paragraph_results if p.get("commitment_score", 0) > 0],
        key=lambda x: x["commitment_score"]
    )[:5]

    return {
        **document,
        "commitment_analysis": {
            "document_commitment": doc_result.average_commitment,
            "weighted_commitment": doc_result.weighted_commitment,
            "commitment_tier": doc_result.commitment_tier,
            "commitment_density": doc_result.commitment_density,
            "commitment_distribution": doc_result.commitment_distribution,
            "top_commitment_phrases": doc_result.top_commitment_phrases,
            "weak_commitment_paragraphs": weak_commitment_paras,
        },
        "paragraphs": paragraph_results,
    }


def format_commitment_report(current_result: CommitmentResult, change: Optional[CommitmentChange] = None) -> str:
    """Format commitment analysis as markdown report."""
    lines = [
        "## Commitment Analysis",
        "",
        f"**Commitment Tier:** {current_result.commitment_tier}",
        f"**Average Commitment:** {current_result.average_commitment:.2f}",
        f"**Commitment Density:** {current_result.commitment_density:.1f} per 1000 words",
        "",
        "### Commitment Word Distribution",
        "",
    ]

    # Distribution
    for word, count in sorted(
        current_result.commitment_distribution.items(),
        key=lambda x: COMMITMENT_PATTERNS.get(x[0], {}).get("strength", 0),
        reverse=True
    ):
        strength = COMMITMENT_PATTERNS.get(word, {}).get("strength", 0)
        bar = "█" * min(count, 10)
        lines.append(f"- {word} ({strength:.1f}): {count} {bar}")

    if change:
        lines.extend([
            "",
            "### Period-over-Period Change",
            "",
            f"**Direction:** {change.direction.upper()}",
            f"**Delta:** {change.delta:+.2f}",
            f"**Tier Change:** {change.tier_change}",
            "",
        ])

        if change.word_migrations:
            lines.append("**Word Migrations:**")
            for m in change.word_migrations[:5]:
                lines.append(f"- {m['word']}: {m['prior_count']} -> {m['current_count']} ({m['direction']})")

        if change.significant_downgrades:
            lines.extend([
                "",
                "**Significant Downgrades:**",
            ])
            for d in change.significant_downgrades:
                lines.append(f"- {d}")

    return "\n".join(lines)


if __name__ == "__main__":
    print("Testing commitment detector...")

    detector = CommitmentDetector()

    # Test strong commitment text
    strong_text = """
    We will continue to execute on our growth strategy. We expect revenue to
    increase by 15-20% in the coming year. Our teams will deliver on our
    product roadmap, and we anticipate strong market share gains.

    We believe our competitive position has never been stronger. We will
    invest aggressively in R&D and expect these investments to drive
    long-term value creation.
    """

    strong_result = detector.analyze(strong_text)

    print(f"\nStrong Commitment Text:")
    print(f"Average Commitment: {strong_result.average_commitment:.2f}")
    print(f"Tier: {strong_result.commitment_tier}")
    print(f"Distribution: {strong_result.commitment_distribution}")

    # Test weak commitment text
    weak_text = """
    We are monitoring the market environment carefully. We're evaluating
    several options and considering various approaches. We hope to see
    improvement, though we're assessing the situation.

    Our goal is to target modest growth, and we're looking at ways to
    optimize our operations. We're exploring opportunities that may
    arise.
    """

    weak_result = detector.analyze(weak_text)

    print(f"\nWeak Commitment Text:")
    print(f"Average Commitment: {weak_result.average_commitment:.2f}")
    print(f"Tier: {weak_result.commitment_tier}")
    print(f"Distribution: {weak_result.commitment_distribution}")

    # Test comparison
    change = detector.compare(weak_text, strong_text)
    print(f"\n\nCommitment Change (Strong -> Weak):")
    print(f"Delta: {change.delta:+.2f}")
    print(f"Direction: {change.direction}")
    print(f"Tier Change: {change.tier_change}")

    print("\n\nFormatted Report:")
    print(format_commitment_report(weak_result, change))
