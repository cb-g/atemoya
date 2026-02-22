#!/usr/bin/env python3
"""
Top-change snippet surfacing for human review.

Ranks and surfaces the most significant narrative changes for manual labeling.
Integrates embedding deltas, hedging changes, and commitment shifts.

Volume is the enemy - surface only what matters.

Usage:
    from surface.ranker import SnippetRanker

    ranker = SnippetRanker()
    top_snippets = ranker.rank_changes(changes, hedging, commitment)
"""

import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from ontology import SignalCategory, SignalDirection, Signal, signal_tag, SIGNAL_TAGS


@dataclass
class RankedSnippet:
    """A ranked snippet for human review."""
    rank: int
    ticker: str
    filing_date: str
    section: str
    text: str
    prior_text: Optional[str]

    # Scores (0-1 scale)
    embedding_delta: float  # Semantic change score
    hedging_delta: float  # Hedging change score
    commitment_delta: float  # Commitment change score
    composite_score: float  # Weighted combination

    # Flags
    is_new: bool  # No prior match
    is_removed: bool  # Topic removed in current
    hedging_increased: bool
    commitment_decreased: bool

    # Metadata
    word_count: int
    paragraph_index: int
    suggested_tags: list[str]  # Suggested ontology tags


@dataclass
class RankingConfig:
    """Configuration for snippet ranking."""
    # Score weights (must sum to 1.0)
    embedding_weight: float = 0.5
    hedging_weight: float = 0.25
    commitment_weight: float = 0.25

    # Thresholds
    min_embedding_delta: float = 0.3  # Minimum semantic change
    min_composite_score: float = 0.2  # Minimum to surface

    # Limits
    max_snippets_per_ticker: int = 10
    max_snippets_total: int = 50
    min_word_count: int = 50  # Skip tiny snippets


class SnippetRanker:
    """
    Ranks and surfaces top-change snippets for human review.

    Combines embedding deltas with hedging and commitment analysis
    to identify the most significant narrative changes.
    """

    def __init__(self, config: Optional[RankingConfig] = None):
        """
        Initialize snippet ranker.

        Args:
            config: Ranking configuration
        """
        self.config = config or RankingConfig()

    def rank_changes(
        self,
        document_changes: list[dict],
        hedging_results: Optional[dict] = None,
        commitment_results: Optional[dict] = None,
    ) -> list[RankedSnippet]:
        """
        Rank changes across all documents.

        Args:
            document_changes: List of DocumentChange dicts from delta detector
            hedging_results: Hedging analysis by (ticker, date) key
            commitment_results: Commitment analysis by (ticker, date) key

        Returns:
            List of RankedSnippet sorted by composite score
        """
        hedging_results = hedging_results or {}
        commitment_results = commitment_results or {}

        all_snippets = []

        for doc_change in document_changes:
            ticker = doc_change.get("ticker", "")
            filing_date = doc_change.get("current_date", "")
            section = doc_change.get("section", "")

            key = (ticker, filing_date)

            # Get hedging and commitment for this document
            hedging = hedging_results.get(key, {})
            commitment = commitment_results.get(key, {})

            # Process paragraph changes
            for para in doc_change.get("paragraph_changes", []):
                snippet = self._score_paragraph(
                    para=para,
                    ticker=ticker,
                    filing_date=filing_date,
                    section=section,
                    hedging=hedging,
                    commitment=commitment,
                )

                if snippet and snippet.composite_score >= self.config.min_composite_score:
                    all_snippets.append(snippet)

            # Process new paragraphs (no prior match)
            for para in doc_change.get("new_paragraphs", []):
                snippet = self._score_new_paragraph(
                    para=para,
                    ticker=ticker,
                    filing_date=filing_date,
                    section=section,
                    hedging=hedging,
                    commitment=commitment,
                )

                if snippet and snippet.composite_score >= self.config.min_composite_score:
                    all_snippets.append(snippet)

        # Sort by composite score
        all_snippets.sort(key=lambda x: x.composite_score, reverse=True)

        # Apply limits per ticker
        ticker_counts = {}
        limited_snippets = []

        for snippet in all_snippets:
            ticker_counts[snippet.ticker] = ticker_counts.get(snippet.ticker, 0) + 1

            if ticker_counts[snippet.ticker] <= self.config.max_snippets_per_ticker:
                limited_snippets.append(snippet)

            if len(limited_snippets) >= self.config.max_snippets_total:
                break

        # Assign final ranks
        for i, snippet in enumerate(limited_snippets):
            snippet.rank = i + 1

        return limited_snippets

    def _score_paragraph(
        self,
        para: dict,
        ticker: str,
        filing_date: str,
        section: str,
        hedging: dict,
        commitment: dict,
    ) -> Optional[RankedSnippet]:
        """Score a paragraph change."""
        text = para.get("text", "")
        word_count = para.get("word_count", len(text.split()))

        if word_count < self.config.min_word_count:
            return None

        # Embedding delta (from delta detector)
        embedding_delta = para.get("delta_score", 0.0)

        if embedding_delta < self.config.min_embedding_delta:
            return None

        # Get paragraph-level hedging if available
        hedging_delta = 0.0
        hedging_increased = False
        para_hedging = hedging.get("paragraphs", {}).get(para.get("index", 0), {})
        if para_hedging:
            current_hedging = para_hedging.get("hedging_score", 0)
            prior_hedging = hedging.get("prior_paragraphs", {}).get(para.get("index", 0), {}).get("hedging_score", 0)
            hedging_delta = abs(current_hedging - prior_hedging)
            hedging_increased = current_hedging > prior_hedging

        # Get commitment change
        commitment_delta = 0.0
        commitment_decreased = False
        if commitment.get("change"):
            commitment_delta = abs(commitment["change"].get("delta", 0))
            commitment_decreased = commitment["change"].get("direction") == "downgrade"

        # Compute composite score
        composite_score = (
            self.config.embedding_weight * embedding_delta +
            self.config.hedging_weight * hedging_delta +
            self.config.commitment_weight * commitment_delta
        )

        # Suggest ontology tags based on content
        suggested_tags = self._suggest_tags(text, hedging_increased, commitment_decreased)

        return RankedSnippet(
            rank=0,  # Assigned later
            ticker=ticker,
            filing_date=filing_date,
            section=section,
            text=text[:1000],  # Truncate for display
            prior_text=para.get("prior_text", "")[:1000] if para.get("prior_text") else None,
            embedding_delta=embedding_delta,
            hedging_delta=hedging_delta,
            commitment_delta=commitment_delta,
            composite_score=composite_score,
            is_new=para.get("is_new", False),
            is_removed=False,
            hedging_increased=hedging_increased,
            commitment_decreased=commitment_decreased,
            word_count=word_count,
            paragraph_index=para.get("index", 0),
            suggested_tags=suggested_tags,
        )

    def _score_new_paragraph(
        self,
        para: dict,
        ticker: str,
        filing_date: str,
        section: str,
        hedging: dict,
        commitment: dict,
    ) -> Optional[RankedSnippet]:
        """Score a new paragraph (no prior match)."""
        text = para.get("text", "")
        word_count = para.get("word_count", len(text.split()))

        if word_count < self.config.min_word_count:
            return None

        # New paragraphs get embedding_delta boost
        embedding_delta = para.get("delta_score", 0.8)  # High by definition

        # Check for hedging in new content
        hedging_delta = 0.0
        hedging_increased = False
        para_hedging = hedging.get("paragraphs", {}).get(para.get("index", 0), {})
        if para_hedging and para_hedging.get("hedging_score", 0) > 0.3:
            hedging_delta = para_hedging["hedging_score"]
            hedging_increased = True  # New hedging content

        # Composite with new content bonus
        composite_score = (
            self.config.embedding_weight * embedding_delta +
            self.config.hedging_weight * hedging_delta +
            0.1  # Bonus for genuinely new content
        )

        suggested_tags = self._suggest_tags(text, hedging_increased, False)

        return RankedSnippet(
            rank=0,
            ticker=ticker,
            filing_date=filing_date,
            section=section,
            text=text[:1000],
            prior_text=None,
            embedding_delta=embedding_delta,
            hedging_delta=hedging_delta,
            commitment_delta=0.0,
            composite_score=composite_score,
            is_new=True,
            is_removed=False,
            hedging_increased=hedging_increased,
            commitment_decreased=False,
            word_count=word_count,
            paragraph_index=para.get("index", 0),
            suggested_tags=suggested_tags,
        )

    def _suggest_tags(
        self,
        text: str,
        hedging_increased: bool,
        commitment_decreased: bool
    ) -> list[str]:
        """Suggest ontology tags based on content."""
        text_lower = text.lower()
        suggestions = []

        # Pricing/margin signals
        if any(w in text_lower for w in ["pricing", "price increase", "price power", "margin"]):
            if hedging_increased:
                suggestions.append(signal_tag(SignalCategory.PRICING_POWER, SignalDirection.DOWN))
            else:
                suggestions.append(signal_tag(SignalCategory.PRICING_POWER, SignalDirection.UP))

        # Demand signals
        if any(w in text_lower for w in ["demand", "visibility", "pipeline", "order"]):
            direction = SignalDirection.DOWN if hedging_increased else SignalDirection.UP
            suggestions.append(signal_tag(SignalCategory.DEMAND_VISIBILITY, direction))

        # Regulatory signals
        if any(w in text_lower for w in ["regulatory", "regulation", "compliance", "government"]):
            suggestions.append(signal_tag(SignalCategory.REGULATORY_OVERHANG, SignalDirection.UP))

        # Competitive signals
        if any(w in text_lower for w in ["competitive", "competition", "market share", "competitor"]):
            direction = SignalDirection.UP if hedging_increased else SignalDirection.DOWN
            suggestions.append(signal_tag(SignalCategory.COMPETITIVE_THREAT, direction))

        # Guidance signals
        if any(w in text_lower for w in ["guidance", "outlook", "forecast", "expect"]):
            direction = SignalDirection.DOWN if commitment_decreased else SignalDirection.UP
            suggestions.append(signal_tag(SignalCategory.GUIDANCE_CONFIDENCE, direction))

        # Supply chain signals
        if any(w in text_lower for w in ["supply chain", "supply", "inventory", "supplier"]):
            suggestions.append(signal_tag(SignalCategory.SUPPLY_CHAIN, SignalDirection.DOWN if hedging_increased else SignalDirection.UP))

        return suggestions[:3]  # Limit suggestions


def export_snippets_csv(snippets: list[RankedSnippet], output_path: Path):
    """
    Export ranked snippets to CSV for structured tracking.

    Args:
        snippets: List of ranked snippets
        output_path: Output CSV path
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "rank", "ticker", "filing_date", "section",
        "composite_score", "embedding_delta", "hedging_delta", "commitment_delta",
        "is_new", "hedging_increased", "commitment_decreased",
        "suggested_tags", "human_label", "notes",
        "text_preview", "word_count"
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for snippet in snippets:
            writer.writerow({
                "rank": snippet.rank,
                "ticker": snippet.ticker,
                "filing_date": snippet.filing_date,
                "section": snippet.section,
                "composite_score": f"{snippet.composite_score:.3f}",
                "embedding_delta": f"{snippet.embedding_delta:.3f}",
                "hedging_delta": f"{snippet.hedging_delta:.3f}",
                "commitment_delta": f"{snippet.commitment_delta:.3f}",
                "is_new": snippet.is_new,
                "hedging_increased": snippet.hedging_increased,
                "commitment_decreased": snippet.commitment_decreased,
                "suggested_tags": "|".join(snippet.suggested_tags),
                "human_label": "",  # For manual labeling
                "notes": "",  # For analyst notes
                "text_preview": snippet.text[:200].replace("\n", " "),
                "word_count": snippet.word_count,
            })


def export_snippets_markdown(snippets: list[RankedSnippet], output_dir: Path):
    """
    Export ranked snippets as markdown for human review.

    Creates one file per ticker with side-by-side comparisons.

    Args:
        snippets: List of ranked snippets
        output_dir: Output directory for markdown files
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Group by ticker
    by_ticker = {}
    for snippet in snippets:
        by_ticker.setdefault(snippet.ticker, []).append(snippet)

    for ticker, ticker_snippets in by_ticker.items():
        output_path = output_dir / f"{ticker}.md"

        lines = [
            f"# Narrative Changes: {ticker}",
            f"",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Snippets:** {len(ticker_snippets)}",
            f"",
            "---",
            "",
        ]

        for snippet in ticker_snippets:
            lines.extend([
                f"## #{snippet.rank} | Score: {snippet.composite_score:.3f}",
                "",
                f"**Date:** {snippet.filing_date} | **Section:** {snippet.section}",
                f"**Embedding Δ:** {snippet.embedding_delta:.3f} | "
                f"**Hedging Δ:** {snippet.hedging_delta:.3f} | "
                f"**Commitment Δ:** {snippet.commitment_delta:.3f}",
                "",
            ])

            # Flags
            flags = []
            if snippet.is_new:
                flags.append("🆕 NEW CONTENT")
            if snippet.hedging_increased:
                flags.append("⚠️ HEDGING UP")
            if snippet.commitment_decreased:
                flags.append("📉 COMMITMENT DOWN")

            if flags:
                lines.append(f"**Flags:** {' | '.join(flags)}")
                lines.append("")

            # Suggested tags
            if snippet.suggested_tags:
                lines.append(f"**Suggested Tags:** `{', '.join(snippet.suggested_tags)}`")
                lines.append("")

            # Current text
            lines.extend([
                "### Current",
                "",
                f"> {snippet.text}",
                "",
            ])

            # Prior text (if exists)
            if snippet.prior_text:
                lines.extend([
                    "### Prior",
                    "",
                    f"> {snippet.prior_text}",
                    "",
                ])

            # Manual annotation section
            lines.extend([
                "### Annotation",
                "",
                "**Label:** ________________",
                "",
                "**Notes:**",
                "",
                "",
                "---",
                "",
            ])

        with open(output_path, "w") as f:
            f.write("\n".join(lines))


def format_summary_report(snippets: list[RankedSnippet]) -> str:
    """Generate a summary report of all changes."""
    lines = [
        "# Narrative Change Summary",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Total Snippets:** {len(snippets)}",
        "",
    ]

    # By ticker summary
    by_ticker = {}
    for s in snippets:
        by_ticker.setdefault(s.ticker, []).append(s)

    lines.extend([
        "## By Ticker",
        "",
        "| Ticker | Count | Avg Score | Hedging↑ | Commit↓ | New |",
        "|--------|-------|-----------|----------|---------|-----|",
    ])

    for ticker, ticker_snippets in sorted(by_ticker.items()):
        avg_score = sum(s.composite_score for s in ticker_snippets) / len(ticker_snippets)
        hedging_up = sum(1 for s in ticker_snippets if s.hedging_increased)
        commit_down = sum(1 for s in ticker_snippets if s.commitment_decreased)
        new_content = sum(1 for s in ticker_snippets if s.is_new)

        lines.append(f"| {ticker} | {len(ticker_snippets)} | {avg_score:.3f} | {hedging_up} | {commit_down} | {new_content} |")

    # Top signals
    lines.extend([
        "",
        "## Top 10 Changes",
        "",
    ])

    for s in snippets[:10]:
        flags = []
        if s.hedging_increased:
            flags.append("H↑")
        if s.commitment_decreased:
            flags.append("C↓")
        if s.is_new:
            flags.append("NEW")

        flag_str = f" [{','.join(flags)}]" if flags else ""

        lines.append(f"1. **{s.ticker}** ({s.filing_date}) - Score {s.composite_score:.3f}{flag_str}")
        lines.append(f"   > {s.text[:150]}...")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print("Snippet ranker module loaded.")
    print("Use SnippetRanker class to rank and surface top changes.")
    print(f"Available ontology tags: {len(SIGNAL_TAGS)}")

    # Example usage
    print("\nExample configuration:")
    config = RankingConfig()
    print(f"  Embedding weight: {config.embedding_weight}")
    print(f"  Hedging weight: {config.hedging_weight}")
    print(f"  Commitment weight: {config.commitment_weight}")
    print(f"  Min composite score: {config.min_composite_score}")
    print(f"  Max snippets per ticker: {config.max_snippets_per_ticker}")
