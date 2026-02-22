#!/usr/bin/env python3
"""
Hedging language detection for narrative drift.

Detects and quantifies uncertainty, hedging, and evasive language patterns
in corporate communications. Compares frequency vs prior periods.

Usage:
    from detect.hedging import HedgingDetector

    detector = HedgingDetector()
    result = detector.analyze(text)
"""

import re
from dataclasses import dataclass
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ontology import HEDGING_WORDS, EVASIVE_PHRASES


@dataclass
class HedgingResult:
    """Result of hedging language analysis."""
    hedging_score: float  # 0-1 normalized hedging density
    hedging_count: int  # Raw count of hedging words
    word_count: int  # Total words analyzed
    hedging_density: float  # Hedging words per 1000 words
    evasive_phrase_count: int  # Count of evasive phrases
    top_hedging_words: list[tuple[str, int]]  # Top hedging words with counts
    hedging_sentences: list[dict]  # Sentences with hedging


@dataclass
class HedgingChange:
    """Change in hedging between two documents."""
    current_score: float
    prior_score: float
    delta: float  # Positive = more hedging
    current_density: float
    prior_density: float
    density_change: float  # Percentage change
    new_hedging_patterns: list[str]  # Hedging words new to current
    removed_hedging_patterns: list[str]  # Hedging words no longer present


# Extended hedging patterns with regex
HEDGING_PATTERNS = [
    # Modal verbs expressing uncertainty
    (r"\bmay\b", "may"),
    (r"\bmight\b", "might"),
    (r"\bcould\b", "could"),
    (r"\bwould\b", "would"),

    # Uncertainty expressions
    (r"\bpossibly\b", "possibly"),
    (r"\bpotentially\b", "potentially"),
    (r"\bperhaps\b", "perhaps"),
    (r"\buncertain(?:ty)?\b", "uncertain"),
    (r"\bunknown\b", "unknown"),
    (r"\bunclear\b", "unclear"),

    # Difficulty/challenge language
    (r"\bchalleng(?:e|es|ing)\b", "challenge"),
    (r"\bdifficult(?:y|ies)?\b", "difficult"),
    (r"\bhard(?:er)?\b", "hard"),

    # Risk/concern language
    (r"\brisk(?:s|y)?\b", "risk"),
    (r"\bconcern(?:s|ed)?\b", "concern"),
    (r"\bcautious(?:ly)?\b", "cautious"),
    (r"\bworr(?:y|ied|ies)\b", "worry"),

    # Volatility/instability
    (r"\bvolati(?:le|lity)\b", "volatile"),
    (r"\bunstabl(?:e|ity)\b", "unstable"),
    (r"\bfluctuat(?:e|es|ing|ion)\b", "fluctuate"),

    # Headwinds/pressure
    (r"\bheadwind(?:s)?\b", "headwind"),
    (r"\bpressure(?:s|d)?\b", "pressure"),
    (r"\bconstrain(?:t|ts|ed)?\b", "constraint"),
    (r"\blimit(?:ed|ation|ations)?\b", "limited"),

    # Softening language
    (r"\bsomewhat\b", "somewhat"),
    (r"\bslightly\b", "slightly"),
    (r"\bsomehow\b", "somehow"),
    (r"\bto some extent\b", "to some extent"),
    (r"\bto a degree\b", "to a degree"),
    (r"\brelatively\b", "relatively"),

    # Approximate language
    (r"\babout\b", "about"),
    (r"\bapproximate(?:ly)?\b", "approximately"),
    (r"\baround\b", "around"),
    (r"\broughly\b", "roughly"),
    (r"\bnearly\b", "nearly"),

    # Conditional language
    (r"\bif\b", "if"),
    (r"\bunless\b", "unless"),
    (r"\bprovided that\b", "provided that"),
    (r"\bassuming\b", "assuming"),
    (r"\bcontingent\b", "contingent"),
    (r"\bdepending\b", "depending"),

    # Temporal hedging
    (r"\bfor now\b", "for now"),
    (r"\bat this time\b", "at this time"),
    (r"\bcurrently\b", "currently"),
    (r"\btemporarily\b", "temporarily"),
    (r"\bfor the time being\b", "for the time being"),
]

# Compiled regex patterns
_HEDGING_COMPILED = [(re.compile(pattern, re.IGNORECASE), name) for pattern, name in HEDGING_PATTERNS]


class HedgingDetector:
    """
    Detects hedging and uncertainty language in text.

    Quantifies hedging density and identifies specific patterns.
    """

    def __init__(self, custom_patterns: Optional[list] = None):
        """
        Initialize hedging detector.

        Args:
            custom_patterns: Additional (regex, name) patterns to include
        """
        self.patterns = list(_HEDGING_COMPILED)
        if custom_patterns:
            for pattern, name in custom_patterns:
                self.patterns.append((re.compile(pattern, re.IGNORECASE), name))

    def analyze(self, text: str) -> HedgingResult:
        """
        Analyze text for hedging language.

        Args:
            text: Text to analyze

        Returns:
            HedgingResult with hedging metrics
        """
        words = text.split()
        word_count = len(words)

        if word_count == 0:
            return HedgingResult(
                hedging_score=0.0,
                hedging_count=0,
                word_count=0,
                hedging_density=0.0,
                evasive_phrase_count=0,
                top_hedging_words=[],
                hedging_sentences=[],
            )

        # Count hedging patterns
        hedging_counts = {}
        for pattern, name in self.patterns:
            matches = pattern.findall(text)
            if matches:
                hedging_counts[name] = hedging_counts.get(name, 0) + len(matches)

        total_hedging = sum(hedging_counts.values())

        # Count evasive phrases
        text_lower = text.lower()
        evasive_count = sum(1 for phrase in EVASIVE_PHRASES if phrase in text_lower)

        # Calculate density (per 1000 words)
        hedging_density = (total_hedging / word_count) * 1000 if word_count > 0 else 0

        # Normalize to 0-1 score (based on typical range of 5-50 per 1000 words)
        hedging_score = min(1.0, hedging_density / 50.0)

        # Get top hedging words
        top_hedging = sorted(hedging_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Find sentences with hedging
        hedging_sentences = self._find_hedging_sentences(text, top_n=10)

        return HedgingResult(
            hedging_score=hedging_score,
            hedging_count=total_hedging,
            word_count=word_count,
            hedging_density=hedging_density,
            evasive_phrase_count=evasive_count,
            top_hedging_words=top_hedging,
            hedging_sentences=hedging_sentences,
        )

    def _find_hedging_sentences(self, text: str, top_n: int = 10) -> list[dict]:
        """Find sentences with the most hedging language."""
        # Simple sentence splitting
        sentences = re.split(r'(?<=[.!?])\s+', text)

        sentence_scores = []
        for i, sentence in enumerate(sentences):
            if len(sentence) < 20:
                continue

            # Count hedging in this sentence
            hedging_count = 0
            found_patterns = []
            for pattern, name in self.patterns:
                matches = pattern.findall(sentence)
                if matches:
                    hedging_count += len(matches)
                    found_patterns.append(name)

            # Check for evasive phrases
            sentence_lower = sentence.lower()
            evasive_found = [p for p in EVASIVE_PHRASES if p in sentence_lower]

            if hedging_count > 0 or evasive_found:
                sentence_scores.append({
                    "index": i,
                    "text": sentence[:500],
                    "hedging_count": hedging_count,
                    "hedging_patterns": list(set(found_patterns)),
                    "evasive_phrases": evasive_found,
                    "score": hedging_count + len(evasive_found) * 2,  # Weight evasive phrases higher
                })

        # Sort by score and return top N
        sentence_scores.sort(key=lambda x: x["score"], reverse=True)
        return sentence_scores[:top_n]

    def compare(self, current_text: str, prior_text: str) -> HedgingChange:
        """
        Compare hedging levels between current and prior text.

        Args:
            current_text: Current period text
            prior_text: Prior period text

        Returns:
            HedgingChange with comparison metrics
        """
        current_result = self.analyze(current_text)
        prior_result = self.analyze(prior_text)

        # Calculate density change
        if prior_result.hedging_density > 0:
            density_change = ((current_result.hedging_density - prior_result.hedging_density)
                            / prior_result.hedging_density) * 100
        else:
            density_change = 100.0 if current_result.hedging_density > 0 else 0.0

        # Find new/removed patterns
        current_patterns = set(p for p, _ in current_result.top_hedging_words)
        prior_patterns = set(p for p, _ in prior_result.top_hedging_words)

        new_patterns = list(current_patterns - prior_patterns)
        removed_patterns = list(prior_patterns - current_patterns)

        return HedgingChange(
            current_score=current_result.hedging_score,
            prior_score=prior_result.hedging_score,
            delta=current_result.hedging_score - prior_result.hedging_score,
            current_density=current_result.hedging_density,
            prior_density=prior_result.hedging_density,
            density_change=density_change,
            new_hedging_patterns=new_patterns,
            removed_hedging_patterns=removed_patterns,
        )


def analyze_document_hedging(document: dict, detector: Optional[HedgingDetector] = None) -> dict:
    """
    Analyze hedging in a document with paragraph-level breakdown.

    Args:
        document: Document dict with 'text' and 'paragraphs'
        detector: HedgingDetector instance

    Returns:
        Document dict augmented with hedging analysis
    """
    detector = detector or HedgingDetector()

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
            "hedging_score": para_result.hedging_score,
            "hedging_density": para_result.hedging_density,
            "hedging_count": para_result.hedging_count,
            "top_hedging_words": para_result.top_hedging_words[:5],
        })

    # Sort paragraphs by hedging score
    high_hedging_paras = sorted(
        paragraph_results,
        key=lambda x: x["hedging_score"],
        reverse=True
    )[:5]

    return {
        **document,
        "hedging_analysis": {
            "document_score": doc_result.hedging_score,
            "document_density": doc_result.hedging_density,
            "document_hedging_count": doc_result.hedging_count,
            "evasive_phrase_count": doc_result.evasive_phrase_count,
            "top_hedging_words": doc_result.top_hedging_words,
            "hedging_sentences": doc_result.hedging_sentences,
            "high_hedging_paragraphs": high_hedging_paras,
        },
        "paragraphs": paragraph_results,
    }


if __name__ == "__main__":
    print("Testing hedging detector...")

    detector = HedgingDetector()

    # Test text with hedging
    hedging_text = """
    We may face challenges in the coming quarters. The market environment could
    potentially become more volatile, and we might see some pressure on margins.
    It's difficult to predict exactly how these headwinds will impact our results,
    but we're cautiously optimistic about our positioning.

    We believe our strategy will help us navigate these uncertain times, though
    there are risks we need to monitor carefully. As I mentioned earlier, we're
    evaluating several options to address these concerns.
    """

    result = detector.analyze(hedging_text)

    print(f"\nHedging Score: {result.hedging_score:.3f}")
    print(f"Hedging Density: {result.hedging_density:.1f} per 1000 words")
    print(f"Total Hedging Words: {result.hedging_count}")
    print(f"Evasive Phrases: {result.evasive_phrase_count}")
    print(f"\nTop Hedging Words:")
    for word, count in result.top_hedging_words[:5]:
        print(f"  {word}: {count}")

    print(f"\nTop Hedging Sentences:")
    for sent in result.hedging_sentences[:3]:
        print(f"  Score {sent['score']}: {sent['text'][:100]}...")

    # Test comparison
    confident_text = """
    We will continue to execute on our growth strategy. We expect strong revenue
    growth in the coming quarters and anticipate margin expansion. Our competitive
    position is strengthening, and we're confident in our ability to capture
    market share.
    """

    change = detector.compare(hedging_text, confident_text)
    print(f"\n\nComparison (hedging vs confident):")
    print(f"Current Score: {change.current_score:.3f}")
    print(f"Prior Score: {change.prior_score:.3f}")
    print(f"Delta: {change.delta:+.3f}")
    print(f"Density Change: {change.density_change:+.1f}%")
