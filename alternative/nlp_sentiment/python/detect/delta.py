#!/usr/bin/env python3
"""
Quarter-over-quarter embedding delta detection.

Identifies sentences and paragraphs with the highest semantic change
from prior periods or historical language centroid.

Usage:
    from detect.delta import DeltaDetector

    detector = DeltaDetector(embedder)
    changes = detector.detect_changes(current_doc, prior_doc)
"""

from dataclasses import dataclass
from typing import Optional
import numpy as np

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from embed.embedder import Embedder, compute_centroid, exponential_decay_weights


@dataclass
class ParagraphChange:
    """A detected paragraph-level change."""
    paragraph_index: int
    text: str
    delta_score: float  # Cosine distance (0-2)
    prior_text: Optional[str]  # Best matching prior paragraph
    prior_similarity: float  # Similarity to best prior match
    centroid_distance: float  # Distance from historical centroid
    is_new: bool  # True if no good prior match exists
    word_count: int


@dataclass
class DocumentChange:
    """Summary of changes in a document."""
    ticker: str
    current_date: str
    prior_date: Optional[str]
    section: str
    document_delta: float  # Document-level cosine distance
    centroid_distance: float  # Distance from historical centroid
    paragraph_changes: list[ParagraphChange]
    top_changes: list[ParagraphChange]  # Top N by delta score
    new_paragraphs: list[ParagraphChange]  # Paragraphs with no prior match
    removed_topics: list[str]  # Prior paragraphs with no current match


class DeltaDetector:
    """
    Detects semantic changes between document versions.

    Computes:
    1. Document-level delta (overall semantic shift)
    2. Paragraph-level delta (fine-grained changes)
    3. Distance from historical centroid (deviation from normal)
    4. New/removed paragraphs (structural changes)
    """

    def __init__(
        self,
        embedder: Optional[Embedder] = None,
        similarity_threshold: float = 0.7,
        new_paragraph_threshold: float = 0.5,
    ):
        """
        Initialize delta detector.

        Args:
            embedder: Embedder instance
            similarity_threshold: Below this, paragraphs are considered "changed"
            new_paragraph_threshold: Below this, paragraph is considered "new"
        """
        self.embedder = embedder or Embedder()
        self.similarity_threshold = similarity_threshold
        self.new_paragraph_threshold = new_paragraph_threshold

    def detect_changes(
        self,
        current_doc: dict,
        prior_doc: Optional[dict] = None,
        centroid: Optional[np.ndarray] = None,
        top_n: int = 10,
    ) -> DocumentChange:
        """
        Detect changes between current and prior document.

        Args:
            current_doc: Current embedded document
            prior_doc: Prior period embedded document (optional)
            centroid: Historical language centroid (optional)
            top_n: Number of top changes to surface

        Returns:
            DocumentChange with detected changes
        """
        ticker = current_doc.get("ticker", "")
        current_date = current_doc.get("filing_date", "")
        section = current_doc.get("section", "")

        prior_date = prior_doc.get("filing_date") if prior_doc else None

        # Get embeddings
        current_doc_emb = current_doc.get("document_embedding")
        current_paras = current_doc.get("paragraphs", [])

        prior_doc_emb = prior_doc.get("document_embedding") if prior_doc else None
        prior_paras = prior_doc.get("paragraphs", []) if prior_doc else []

        # Document-level delta
        doc_delta = 0.0
        if current_doc_emb is not None and prior_doc_emb is not None:
            doc_delta = 1.0 - float(np.dot(current_doc_emb, prior_doc_emb))

        # Centroid distance
        centroid_dist = 0.0
        if current_doc_emb is not None and centroid is not None:
            centroid_dist = 1.0 - float(np.dot(current_doc_emb, centroid))

        # Paragraph-level analysis
        paragraph_changes = []
        new_paragraphs = []
        matched_prior_indices = set()

        for para in current_paras:
            para_emb = para.get("embedding")
            if para_emb is None:
                continue

            # Find best matching prior paragraph
            best_prior_idx = None
            best_similarity = -1.0
            best_prior_text = None

            for i, prior_para in enumerate(prior_paras):
                prior_emb = prior_para.get("embedding")
                if prior_emb is None:
                    continue

                sim = float(np.dot(para_emb, prior_emb))
                if sim > best_similarity:
                    best_similarity = sim
                    best_prior_idx = i
                    best_prior_text = prior_para.get("text", "")

            # Compute delta score
            delta_score = 1.0 - best_similarity if best_similarity >= 0 else 1.0

            # Centroid distance for this paragraph
            para_centroid_dist = 0.0
            if centroid is not None:
                para_centroid_dist = 1.0 - float(np.dot(para_emb, centroid))

            # Determine if new paragraph
            is_new = best_similarity < self.new_paragraph_threshold

            change = ParagraphChange(
                paragraph_index=para.get("index", 0),
                text=para.get("text", ""),
                delta_score=delta_score,
                prior_text=best_prior_text if not is_new else None,
                prior_similarity=best_similarity,
                centroid_distance=para_centroid_dist,
                is_new=is_new,
                word_count=para.get("word_count", len(para.get("text", "").split())),
            )

            paragraph_changes.append(change)

            if is_new:
                new_paragraphs.append(change)

            if best_prior_idx is not None and best_similarity >= self.new_paragraph_threshold:
                matched_prior_indices.add(best_prior_idx)

        # Find removed topics (prior paragraphs with no current match)
        removed_topics = []
        for i, prior_para in enumerate(prior_paras):
            if i not in matched_prior_indices:
                prior_emb = prior_para.get("embedding")
                if prior_emb is None:
                    continue

                # Check if any current paragraph is similar
                max_sim = 0.0
                for para in current_paras:
                    para_emb = para.get("embedding")
                    if para_emb is not None:
                        sim = float(np.dot(prior_emb, para_emb))
                        max_sim = max(max_sim, sim)

                if max_sim < self.new_paragraph_threshold:
                    # This prior topic was removed/significantly changed
                    prior_text = prior_para.get("text", "")
                    # Get first sentence as summary
                    summary = prior_text.split(".")[0][:200] + "..."
                    removed_topics.append(summary)

        # Sort by delta score and get top changes
        paragraph_changes.sort(key=lambda x: x.delta_score, reverse=True)
        top_changes = paragraph_changes[:top_n]

        return DocumentChange(
            ticker=ticker,
            current_date=current_date,
            prior_date=prior_date,
            section=section,
            document_delta=doc_delta,
            centroid_distance=centroid_dist,
            paragraph_changes=paragraph_changes,
            top_changes=top_changes,
            new_paragraphs=new_paragraphs,
            removed_topics=removed_topics[:10],  # Limit
        )


def build_historical_centroid(
    documents: list[dict],
    max_quarters: int = 12,
    decay_rate: float = 0.1,
) -> Optional[np.ndarray]:
    """
    Build historical language centroid from multiple documents.

    Args:
        documents: List of embedded documents (sorted by date, newest first)
        max_quarters: Maximum quarters to include
        decay_rate: Exponential decay rate for weighting

    Returns:
        Centroid embedding or None if no valid documents
    """
    # Filter documents with valid embeddings
    valid_docs = [
        d for d in documents[:max_quarters]
        if d.get("document_embedding") is not None
    ]

    if not valid_docs:
        return None

    embeddings = [d["document_embedding"] for d in valid_docs]
    weights = exponential_decay_weights(len(embeddings), decay_rate)

    return compute_centroid(embeddings, weights)


def format_change_report(change: DocumentChange) -> str:
    """
    Format a change detection result as markdown.

    Args:
        change: DocumentChange object

    Returns:
        Markdown formatted report
    """
    lines = [
        f"# Narrative Change Report: {change.ticker}",
        f"**Section:** {change.section}",
        f"**Current:** {change.current_date}",
        f"**Prior:** {change.prior_date or 'N/A'}",
        "",
        "## Summary Metrics",
        f"- Document Delta: {change.document_delta:.3f}",
        f"- Centroid Distance: {change.centroid_distance:.3f}",
        f"- New Paragraphs: {len(change.new_paragraphs)}",
        f"- Removed Topics: {len(change.removed_topics)}",
        "",
        "## Top Changes",
        "",
    ]

    for i, chg in enumerate(change.top_changes, 1):
        lines.append(f"### {i}. Delta: {chg.delta_score:.3f} (New: {chg.is_new})")
        lines.append("")
        lines.append(f"**Current:**")
        lines.append(f"> {chg.text[:500]}...")
        lines.append("")
        if chg.prior_text:
            lines.append(f"**Prior (similarity: {chg.prior_similarity:.3f}):**")
            lines.append(f"> {chg.prior_text[:500]}...")
        lines.append("")
        lines.append("---")
        lines.append("")

    if change.new_paragraphs:
        lines.append("## New Paragraphs (No Prior Match)")
        lines.append("")
        for para in change.new_paragraphs[:5]:
            lines.append(f"- {para.text[:200]}...")
        lines.append("")

    if change.removed_topics:
        lines.append("## Removed Topics")
        lines.append("")
        for topic in change.removed_topics[:5]:
            lines.append(f"- {topic}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print("Delta detector module loaded.")
    print("Use DeltaDetector class for change detection.")
