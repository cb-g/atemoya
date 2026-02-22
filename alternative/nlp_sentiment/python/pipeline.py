#!/usr/bin/env python3
"""
Narrative drift detection pipeline.

End-to-end pipeline for detecting narrative changes in corporate communications.
Fetches documents, computes embeddings, detects changes, and surfaces top snippets.

Usage:
    python pipeline.py AAPL NVDA --quarters 8
    python pipeline.py --file tickers.txt --quarters 12
"""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from ontology import SignalCategory, SIGNAL_TAGS
from fetch.fetch_mda import fetch_mda_for_ticker
from fetch.fetch_transcripts import fetch_transcripts_for_ticker

from embed.embedder import Embedder, DocumentEmbedder, compute_centroid, exponential_decay_weights
from detect.delta import DeltaDetector, build_historical_centroid, format_change_report
from detect.hedging import HedgingDetector, analyze_document_hedging
from detect.commitment import CommitmentDetector, analyze_document_commitment
from surface.ranker import (
    SnippetRanker,
    RankingConfig,
    export_snippets_csv,
    export_snippets_markdown,
    format_summary_report,
)


def run_pipeline(
    tickers: list[str],
    quarters: int = 12,
    output_dir: Optional[Path] = None,
    skip_transcripts: bool = False,
    skip_mda: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Run the full narrative drift detection pipeline.

    Args:
        tickers: List of ticker symbols
        quarters: Number of quarters of history
        output_dir: Output directory (default: nlp_sentiment/output)
        skip_transcripts: Skip earnings transcript fetching
        skip_mda: Skip MD&A fetching
        verbose: Print progress messages

    Returns:
        Dict with pipeline results
    """
    output_dir = output_dir or Path(__file__).parent.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize components
    if verbose:
        print("Initializing components...")

    try:
        embedder = Embedder()
        doc_embedder = DocumentEmbedder(embedder)
    except ImportError as e:
        print(f"Warning: Could not initialize embedder: {e}")
        embedder = None
        doc_embedder = None

    delta_detector = DeltaDetector(embedder)
    hedging_detector = HedgingDetector()
    commitment_detector = CommitmentDetector()
    ranker = SnippetRanker()

    # Results storage
    all_documents = []
    all_changes = []
    hedging_results = {}
    commitment_results = {}

    # Process each ticker
    for ticker in tickers:
        if verbose:
            print(f"\n{'='*60}")
            print(f"Processing {ticker}")
            print("=" * 60)

        ticker_docs = []

        # Fetch MD&A and Risk Factors
        if not skip_mda:
            if verbose:
                print(f"\n[1/5] Fetching MD&A and Risk Factors...")

            mda_data = fetch_mda_for_ticker(ticker, quarters)

            if mda_data.get("error"):
                print(f"  MD&A Error: {mda_data['error']}")
            else:
                for doc in mda_data.get("documents", []):
                    ticker_docs.append(doc)
                if verbose:
                    print(f"  Fetched {len(mda_data.get('documents', []))} MD&A documents")

        # Fetch earnings transcripts
        if not skip_transcripts:
            if verbose:
                print(f"\n[2/5] Fetching earnings transcripts...")

            transcript_data = fetch_transcripts_for_ticker(ticker, quarters)

            if transcript_data.get("error"):
                print(f"  Transcript Error: {transcript_data['error']}")
            else:
                for doc in transcript_data.get("documents", []):
                    ticker_docs.append(doc)
                if verbose:
                    print(f"  Fetched {len(transcript_data.get('documents', []))} transcript documents")

        if not ticker_docs:
            print(f"  No documents found for {ticker}")
            continue

        # Embed documents
        if verbose:
            print(f"\n[4/5] Computing embeddings...")

        embedded_docs = []
        for doc in ticker_docs:
            if doc_embedder:
                try:
                    embedded = doc_embedder.embed_document(
                        text=doc.get("text", ""),
                        ticker=doc.get("ticker", ticker),
                        filing_date=doc.get("filing_date", ""),
                        section=doc.get("section", ""),
                    )
                    embedded_docs.append(embedded)
                except Exception as e:
                    print(f"  Embedding error: {e}")
                    embedded_docs.append(doc)  # Keep without embeddings
            else:
                embedded_docs.append(doc)

        if verbose:
            print(f"  Embedded {len(embedded_docs)} documents")

        # Group by section for change detection
        by_section = {}
        for doc in embedded_docs:
            section = doc.get("section", "unknown")
            by_section.setdefault(section, []).append(doc)

        # Detect changes within each section
        if verbose:
            print(f"\n[5/5] Detecting changes...")

        for section, section_docs in by_section.items():
            # Sort by date (newest first)
            section_docs.sort(
                key=lambda x: x.get("filing_date", ""),
                reverse=True
            )

            if len(section_docs) < 2:
                continue

            # Build historical centroid
            centroid = build_historical_centroid(section_docs[1:], max_quarters=quarters)

            # Compare current to prior
            current_doc = section_docs[0]
            prior_doc = section_docs[1]

            change = delta_detector.detect_changes(
                current_doc=current_doc,
                prior_doc=prior_doc,
                centroid=centroid,
                top_n=10,
            )

            all_changes.append(asdict(change))

            # Hedging analysis
            key = (ticker, current_doc.get("filing_date", ""))
            hedging_analysis = analyze_document_hedging(current_doc, hedging_detector)
            hedging_results[key] = hedging_analysis.get("hedging_analysis", {})

            # Commitment analysis
            commitment_analysis = analyze_document_commitment(current_doc, commitment_detector)
            commitment_results[key] = commitment_analysis.get("commitment_analysis", {})

            if verbose:
                doc_delta = change.get("document_delta", 0) if isinstance(change, dict) else change.document_delta
                print(f"  {section}: delta={doc_delta:.3f}")

        all_documents.extend(embedded_docs)

    # Rank and surface top changes
    if verbose:
        print(f"\n{'='*60}")
        print("Ranking and surfacing top changes")
        print("=" * 60)

    top_snippets = ranker.rank_changes(
        document_changes=all_changes,
        hedging_results=hedging_results,
        commitment_results=commitment_results,
    )

    if verbose:
        print(f"  Surfaced {len(top_snippets)} snippets for review")

    # Export results
    if verbose:
        print(f"\nExporting results to {output_dir}")

    # CSV for structured tracking
    csv_path = output_dir / "signals.csv"
    export_snippets_csv(top_snippets, csv_path)
    if verbose:
        print(f"  Signals: {csv_path}")

    # Markdown for human review
    snippets_dir = output_dir / "snippets"
    export_snippets_markdown(top_snippets, snippets_dir)
    if verbose:
        print(f"  Snippets: {snippets_dir}/")

    # Summary report
    summary = format_summary_report(top_snippets)
    summary_path = output_dir / "summary.md"
    with open(summary_path, "w") as f:
        f.write(summary)
    if verbose:
        print(f"  Summary: {summary_path}")

    # Raw JSON data
    data_path = output_dir / "data" / "pipeline_results.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    with open(data_path, "w") as f:
        json.dump({
            "run_time": datetime.now().isoformat(),
            "tickers": tickers,
            "quarters": quarters,
            "document_count": len(all_documents),
            "change_count": len(all_changes),
            "snippet_count": len(top_snippets),
        }, f, indent=2)

    if verbose:
        print(f"\nPipeline complete!")
        print(f"  Documents processed: {len(all_documents)}")
        print(f"  Changes detected: {len(all_changes)}")
        print(f"  Snippets surfaced: {len(top_snippets)}")

    return {
        "documents": len(all_documents),
        "changes": all_changes,
        "snippets": top_snippets,
        "output_dir": str(output_dir),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Narrative drift detection pipeline"
    )
    parser.add_argument(
        "tickers",
        nargs="*",
        help="Ticker symbols to analyze"
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="File with tickers (one per line)"
    )
    parser.add_argument(
        "--quarters",
        type=int,
        default=12,
        help="Quarters of history (default: 12)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory"
    )
    parser.add_argument(
        "--skip-transcripts",
        action="store_true",
        help="Skip earnings transcript fetching"
    )
    parser.add_argument(
        "--skip-mda",
        action="store_true",
        help="Skip MD&A fetching"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output"
    )

    args = parser.parse_args()

    # Collect tickers
    tickers = []
    if args.tickers:
        tickers.extend([t.upper() for t in args.tickers])
    if args.file and args.file.exists():
        with open(args.file) as f:
            tickers.extend([line.strip().upper() for line in f if line.strip()])

    if not tickers:
        print("Error: No tickers specified")
        print("Usage: python pipeline.py AAPL NVDA --quarters 8")
        sys.exit(1)

    # Remove duplicates preserving order
    tickers = list(dict.fromkeys(tickers))

    print(f"Narrative Drift Detection Pipeline")
    print(f"Tickers: {', '.join(tickers)}")
    print(f"Quarters: {args.quarters}")
    print()

    results = run_pipeline(
        tickers=tickers,
        quarters=args.quarters,
        output_dir=args.output,
        skip_transcripts=args.skip_transcripts,
        skip_mda=args.skip_mda,
        verbose=not args.quiet,
    )

    # Print final summary
    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)
    print(f"Documents: {results['documents']}")
    print(f"Changes: {len(results['changes'])}")
    print(f"Snippets: {len(results['snippets'])}")
    print(f"Output: {results['output_dir']}")


if __name__ == "__main__":
    main()
