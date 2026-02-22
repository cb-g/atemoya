#!/usr/bin/env python3
"""
Fetch earnings call transcripts from Motley Fool.

Scrapes free earnings call transcripts and separates prepared remarks from Q&A.

Usage:
    python fetch_transcripts.py AAPL NVDA --quarters 12
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, quote

import requests
from bs4 import BeautifulSoup


# Rate limit to be respectful
RATE_LIMIT_DELAY = 1.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def search_transcripts(ticker: str, max_results: int = 20) -> list[dict]:
    """
    Search Motley Fool for earnings call transcripts.

    Args:
        ticker: Stock ticker symbol
        max_results: Maximum number of transcript URLs to return

    Returns:
        List of dicts with transcript metadata and URLs
    """
    # Try quote pages first (most reliable source for ticker-specific transcripts)
    # Try both NASDAQ and NYSE as we don't know the exchange
    exchanges = ["nasdaq", "nyse"]
    soup = None

    for exchange in exchanges:
        quote_url = f"https://www.fool.com/quote/{exchange}/{ticker.lower()}/"
        try:
            time.sleep(RATE_LIMIT_DELAY)
            resp = requests.get(quote_url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                break
        except Exception:
            continue

    # Fallback to transcript search page
    if soup is None:
        search_url = f"https://www.fool.com/earnings-call-transcripts/?q={quote(ticker)}"
        try:
            time.sleep(RATE_LIMIT_DELAY)
            resp = requests.get(search_url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            print(f"Error searching transcripts for {ticker}: {e}", file=sys.stderr)
            return []

    try:

        transcripts = []

        # Look for transcript links - Motley Fool uses various structures
        # Try multiple selector patterns
        article_links = soup.find_all("a", href=True)

        for link in article_links:
            href = link.get("href", "")

            # Filter for earnings call transcript pages
            # New URL format: /earnings/call-transcripts/YYYY/MM/DD/company-ticker-quarter-...
            # Old URL format: .../earnings-call-transcript/...
            if "/earnings/call-transcripts/" not in href.lower() and "earnings-call-transcript" not in href.lower():
                continue

            # Get link metadata
            link_text = link.get_text(strip=True).lower()
            title = link.get("title", "").lower()
            ticker_lower = ticker.lower()
            href_lower = href.lower()

            # Must mention the ticker - check multiple patterns:
            # 1. Ticker in URL slug: "apple-aapl-q4-2024-..." or "/aapl/"
            # 2. Ticker in link text or title
            ticker_in_href = (
                f"-{ticker_lower}-" in href_lower or
                f"/{ticker_lower}-" in href_lower or
                f"/{ticker_lower}/" in href_lower
            )
            ticker_in_text = ticker_lower in link_text or ticker_lower in title

            if not ticker_in_href and not ticker_in_text:
                continue

            # Build full URL
            if href.startswith("/"):
                full_url = f"https://www.fool.com{href}"
            elif href.startswith("http"):
                full_url = href
            else:
                continue

            # Extract date from URL if possible (format: YYYY/MM/DD)
            date_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", href)
            filing_date = None
            if date_match:
                filing_date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"

            # Extract quarter info from title
            quarter = extract_quarter_from_title(link_text or title)

            transcripts.append({
                "url": full_url,
                "title": link.get_text(strip=True)[:200],
                "filing_date": filing_date,
                "quarter": quarter,
            })

            if len(transcripts) >= max_results:
                break

        # Dedupe by URL (normalize to remove tracking IDs like /4056/)
        def normalize_url(url: str) -> str:
            """Remove tracking IDs from Motley Fool URLs."""
            # Pattern: /NNNN/ (4-digit tracking ID) before /earnings/
            return re.sub(r'/\d{4,5}/earnings/', '/earnings/', url)

        seen_urls = set()
        unique_transcripts = []
        for t in transcripts:
            normalized = normalize_url(t["url"])
            if normalized not in seen_urls:
                seen_urls.add(normalized)
                # Use the clean URL without tracking ID
                t["url"] = normalized
                unique_transcripts.append(t)

        return unique_transcripts

    except Exception as e:
        print(f"Error searching transcripts for {ticker}: {e}", file=sys.stderr)
        return []


def extract_quarter_from_title(title: str) -> Optional[str]:
    """Extract quarter info from transcript title."""
    title_lower = title.lower()

    # Look for Q1, Q2, Q3, Q4 patterns
    q_match = re.search(r"q([1-4])\s*(?:fy)?(\d{2,4})?", title_lower)
    if q_match:
        quarter = f"Q{q_match.group(1)}"
        if q_match.group(2):
            year = q_match.group(2)
            if len(year) == 2:
                year = f"20{year}" if int(year) < 50 else f"19{year}"
            quarter = f"{quarter} {year}"
        return quarter

    # Look for fiscal year patterns
    fy_match = re.search(r"(?:fy|fiscal\s*year)\s*(\d{2,4})", title_lower)
    if fy_match:
        return f"FY {fy_match.group(1)}"

    return None


def fetch_transcript(url: str) -> Optional[dict]:
    """
    Fetch and parse a single transcript page.

    Args:
        url: Transcript page URL

    Returns:
        Dict with parsed transcript sections or None
    """
    try:
        time.sleep(RATE_LIMIT_DELAY)
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "header", "footer", "aside"]):
            element.decompose()

        # Find the main article content - Motley Fool uses 'transcript-content' class
        article = (
            soup.find("div", class_="transcript-content") or
            soup.find("div", class_="article-body") or
            soup.find("article") or
            soup.find("div", class_=re.compile(r"article|content|transcript"))
        )

        if not article:
            # Fallback to body
            article = soup.find("body")

        if not article:
            return None

        text = article.get_text(separator="\n")

        # Parse the transcript structure
        result = parse_transcript_text(text)
        result["url"] = url

        return result

    except Exception as e:
        print(f"Error fetching transcript: {e}", file=sys.stderr)
        return None


def parse_transcript_text(text: str) -> dict:
    """
    Parse transcript text into sections.

    Separates prepared remarks from Q&A section.

    Returns:
        Dict with prepared_remarks, qa_section, and full_text
    """
    # Clean up text
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)

    # Find Q&A section start
    qa_patterns = [
        r"questions?\s*(?:and|&)\s*answers?",
        r"q\s*&\s*a\s*(?:session|section)?",
        r"(?:now|let'?s)\s*(?:open|turn)\s*(?:it\s*)?(?:up\s*)?(?:to|for)\s*questions?",
        r"operator[:\s]+.*(?:first|next)\s*question",
    ]

    qa_start = None
    text_lower = text.lower()

    for pattern in qa_patterns:
        match = re.search(pattern, text_lower)
        if match:
            # Take the earliest match
            if qa_start is None or match.start() < qa_start:
                qa_start = match.start()

    # Split into sections
    if qa_start:
        prepared_remarks = text[:qa_start].strip()
        qa_section = text[qa_start:].strip()
    else:
        # No clear Q&A section found - treat all as prepared remarks
        prepared_remarks = text.strip()
        qa_section = ""

    # Extract participants
    participants = extract_participants(text)

    # Extract speakers and their statements
    prepared_statements = extract_statements(prepared_remarks)
    qa_statements = extract_statements(qa_section) if qa_section else []

    return {
        "full_text": text.strip(),
        "prepared_remarks": prepared_remarks,
        "qa_section": qa_section,
        "prepared_statements": prepared_statements,
        "qa_statements": qa_statements,
        "participants": participants,
        "char_count": len(text),
        "word_count": len(text.split()),
    }


def extract_participants(text: str) -> list[dict]:
    """
    Extract call participants from transcript.

    Returns list of dicts with name and role.
    """
    participants = []

    # Look for participants section
    participants_match = re.search(
        r"(?:call\s*)?participants?[:\s]*(.*?)(?=\n\n|prepared\s*remarks?|$)",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if participants_match:
        participants_text = participants_match.group(1)

        # Parse individual participants
        # Common format: "Name -- Title" or "Name - Title"
        lines = participants_text.split("\n")
        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                continue

            # Try to split by -- or -
            parts = re.split(r'\s*[-–—]+\s*', line, maxsplit=1)
            if len(parts) == 2:
                participants.append({
                    "name": parts[0].strip(),
                    "role": parts[1].strip(),
                })
            elif line and not any(skip in line.lower() for skip in ["conference", "operator", "please"]):
                participants.append({
                    "name": line,
                    "role": "",
                })

    return participants[:20]  # Limit


def extract_statements(text: str) -> list[dict]:
    """
    Extract individual speaker statements from transcript text.

    Returns list of dicts with speaker and text.
    """
    statements = []

    if not text:
        return statements

    # Pattern for speaker attribution
    # Common formats:
    # "John Smith -- CEO" followed by their statement
    # "John Smith:" followed by their statement
    speaker_pattern = re.compile(
        r'^([A-Z][A-Za-z\s\.]+?)(?:\s*[-–—]+\s*[A-Za-z\s,\.]+)?[:\s]*$',
        re.MULTILINE
    )

    # Split by speaker attributions
    parts = speaker_pattern.split(text)

    current_speaker = None
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue

        # Check if this is a speaker name
        if speaker_pattern.match(part + ":"):
            current_speaker = part
        elif current_speaker and len(part) > 50:
            # This is a statement
            statements.append({
                "speaker": current_speaker,
                "text": part,
                "word_count": len(part.split()),
            })

    return statements


def split_into_paragraphs(text: str, min_length: int = 100) -> list[dict]:
    """
    Split text into paragraphs with metadata.

    Returns list of paragraph dicts.
    """
    paragraphs = []
    raw_paragraphs = re.split(r'\n\n+', text)

    for i, para in enumerate(raw_paragraphs):
        para = para.strip()
        if len(para) < min_length:
            continue

        paragraphs.append({
            "index": len(paragraphs),
            "text": para,
            "char_count": len(para),
            "word_count": len(para.split()),
        })

    return paragraphs


def fetch_transcripts_for_ticker(ticker: str, quarters: int = 12) -> dict:
    """
    Fetch earnings call transcripts for a ticker.

    Args:
        ticker: Stock ticker symbol
        quarters: Number of quarters of history to fetch

    Returns:
        Dict with transcripts and metadata
    """
    print(f"  Searching for transcripts...", end=" ", flush=True)
    transcript_links = search_transcripts(ticker, max_results=quarters + 5)
    print(f"Found {len(transcript_links)} links")

    if not transcript_links:
        return {
            "ticker": ticker,
            "error": "No transcripts found",
        }

    documents = []

    for i, link_info in enumerate(transcript_links[:quarters]):
        url = link_info.get("url", "")
        title = link_info.get("title", "")[:50]
        print(f"  Fetching {title}...", end=" ", flush=True)

        transcript = fetch_transcript(url)
        if not transcript:
            print("FAILED")
            continue

        # Extract date from link_info or transcript
        filing_date = link_info.get("filing_date") or datetime.now().strftime("%Y-%m-%d")
        quarter = link_info.get("quarter", "")

        # Create document for prepared remarks
        if transcript.get("prepared_remarks"):
            prepared_paragraphs = split_into_paragraphs(transcript["prepared_remarks"])
            documents.append({
                "ticker": ticker,
                "source": "motley_fool",
                "filing_date": filing_date,
                "quarter": quarter,
                "section": "prepared_remarks",
                "url": url,
                "text": transcript["prepared_remarks"],
                "paragraphs": prepared_paragraphs,
                "paragraph_count": len(prepared_paragraphs),
                "char_count": len(transcript["prepared_remarks"]),
                "participants": transcript.get("participants", []),
            })

        # Create document for Q&A
        if transcript.get("qa_section"):
            qa_paragraphs = split_into_paragraphs(transcript["qa_section"])
            documents.append({
                "ticker": ticker,
                "source": "motley_fool",
                "filing_date": filing_date,
                "quarter": quarter,
                "section": "qa",
                "url": url,
                "text": transcript["qa_section"],
                "paragraphs": qa_paragraphs,
                "paragraph_count": len(qa_paragraphs),
                "char_count": len(transcript["qa_section"]),
                "statements": transcript.get("qa_statements", []),
            })

        sections = []
        if transcript.get("prepared_remarks"):
            sections.append("Prepared")
        if transcript.get("qa_section"):
            sections.append("Q&A")
        print(f"{', '.join(sections) or 'None'}")

    return {
        "ticker": ticker,
        "fetch_time": datetime.now().isoformat(),
        "document_count": len(documents),
        "documents": documents,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch earnings call transcripts from Motley Fool")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols")
    parser.add_argument("--file", type=Path, help="File with tickers (one per line)")
    parser.add_argument("--quarters", type=int, default=12, help="Quarters of history to fetch")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent.parent.parent / "data" / "documents" / "transcripts.json")

    args = parser.parse_args()

    # Collect tickers
    tickers = []
    if args.tickers:
        tickers.extend([t.upper() for t in args.tickers])
    if args.file and args.file.exists():
        with open(args.file) as f:
            tickers.extend([line.strip().upper() for line in f if line.strip()])

    if not tickers:
        print("Error: No tickers specified", file=sys.stderr)
        print("Usage: python fetch_transcripts.py AAPL NVDA --quarters 12", file=sys.stderr)
        sys.exit(1)

    tickers = list(dict.fromkeys(tickers))

    print(f"Fetching transcripts for {len(tickers)} ticker(s) ({args.quarters} quarters)...\n")

    results = []
    for ticker in tickers:
        print(f"\n{ticker}:")
        data = fetch_transcripts_for_ticker(ticker, args.quarters)
        results.append(data)

        if data.get("error"):
            print(f"  ERROR: {data['error']}")
        else:
            print(f"  Total: {data.get('document_count', 0)} documents extracted")

    # Save results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "fetch_time": datetime.now().isoformat(),
        "quarters_requested": args.quarters,
        "ticker_count": len(results),
        "tickers": results,
    }

    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\n\nResults saved to {args.output}")

    # Print summary
    print("\n" + "=" * 60)
    print("TRANSCRIPT EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"{'Ticker':<8} {'Documents':>10} {'Prepared':>10} {'Q&A':>8}")
    print("-" * 60)

    for r in results:
        if r.get("error"):
            print(f"{r['ticker']:<8} {'ERROR':>10}")
            continue

        docs = r.get("documents", [])
        prepared_count = sum(1 for d in docs if d.get("section") == "prepared_remarks")
        qa_count = sum(1 for d in docs if d.get("section") == "qa")

        print(f"{r['ticker']:<8} {len(docs):>10} {prepared_count:>10} {qa_count:>8}")


if __name__ == "__main__":
    main()
