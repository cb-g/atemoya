#!/usr/bin/env python3
"""
Fetch MD&A (Management Discussion & Analysis) and Risk Factors from SEC 10-K/10-Q filings.

Extracts specific sections from annual and quarterly reports for narrative analysis.

Usage:
    python fetch_mda.py AAPL NVDA --quarters 12
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup


# SEC requires identifying User-Agent
HEADERS = {
    "User-Agent": os.environ.get("SEC_EDGAR_IDENTITY", "DCF Research"),
    "Accept-Encoding": "gzip, deflate",
}

RATE_LIMIT_DELAY = 0.15


def get_cik_from_ticker(ticker: str) -> Optional[str]:
    """Get CIK (Central Index Key) from ticker symbol."""
    url = "https://www.sec.gov/files/company_tickers.json"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        ticker_upper = ticker.upper()
        for entry in data.values():
            if entry.get("ticker") == ticker_upper:
                cik = str(entry.get("cik_str", ""))
                return cik.zfill(10)
        return None
    except Exception as e:
        print(f"Error fetching CIK for {ticker}: {e}", file=sys.stderr)
        return None


def fetch_filing_list(cik: str, form_types: list = None, max_filings: int = 50) -> list:
    """
    Fetch list of filings for a company.

    Args:
        cik: Company CIK (10 digits)
        form_types: List of form types to include
        max_filings: Maximum number of filings to return

    Returns:
        List of filing metadata dicts
    """
    if form_types is None:
        form_types = ["10-K", "10-Q", "20-F", "6-K"]

    url = f"https://data.sec.gov/submissions/CIK{cik}.json"

    try:
        time.sleep(RATE_LIMIT_DELAY)
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        company_name = data.get("name", "")
        filings = []

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if len(filings) >= max_filings:
                break

            # Check form type match
            form_match = any(form.startswith(ft) for ft in form_types)
            if not form_match:
                continue

            filing_date = dates[i] if i < len(dates) else None
            accession = accessions[i] if i < len(accessions) else ""
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""

            accession_clean = accession.replace("-", "")
            base_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{accession_clean}/"

            filings.append({
                "form": form,
                "filing_date": filing_date,
                "accession": accession,
                "primary_doc": primary_doc,
                "base_url": base_url,
                "company_name": company_name,
            })

        return filings

    except Exception as e:
        print(f"Error fetching filing list: {e}", file=sys.stderr)
        return []


def fetch_filing_document(filing: dict) -> Optional[str]:
    """
    Fetch the primary filing document HTML.

    Returns HTML content or None on error.
    """
    base_url = filing.get("base_url", "")
    primary_doc = filing.get("primary_doc", "")

    if not base_url or not primary_doc:
        return None

    url = base_url + primary_doc

    try:
        time.sleep(RATE_LIMIT_DELAY)
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"Error fetching document: {e}", file=sys.stderr)
        return None


def extract_section(html: str, section_name: str) -> Optional[str]:
    """
    Extract a specific section from SEC filing HTML.

    Args:
        html: Filing HTML content
        section_name: Section to extract ("mda" or "risk_factors")

    Returns:
        Extracted section text or None
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style"]):
        element.decompose()

    text = soup.get_text(separator="\n")

    # Section header patterns
    if section_name == "mda":
        # Item 7 in 10-K, Item 2 in 10-Q, Item 5 in 20-F
        start_patterns = [
            r"item\s*7[.\s]*management['']?s?\s*discussion\s*and\s*analysis",
            r"item\s*2[.\s]*management['']?s?\s*discussion\s*and\s*analysis",
            r"management['']?s?\s*discussion\s*and\s*analysis\s*of\s*financial\s*condition",
            # 20-F patterns
            r"item\s*5[.\s]*operating\s*and\s*financial\s*review",
            r"operating\s*and\s*financial\s*review\s*and\s*prospects",
        ]
        end_patterns = [
            r"item\s*7a[.\s]*quantitative\s*and\s*qualitative",
            r"item\s*8[.\s]*financial\s*statements",
            r"item\s*3[.\s]*quantitative\s*and\s*qualitative",
            r"item\s*4[.\s]*controls\s*and\s*procedures",
            # 20-F patterns
            r"item\s*6[.\s]*directors",
            r"item\s*6[.\s]*senior\s*management",
        ]
    elif section_name == "risk_factors":
        # Item 1A in 10-K/10-Q, Item 3.D in 20-F
        start_patterns = [
            r"item\s*1a[.\s]*risk\s*factors",
            r"risk\s*factors",
            # 20-F patterns
            r"item\s*3\.?d[.\s]*risk\s*factors",
            r"item\s*3[.\s]*key\s*information.*risk\s*factors",
        ]
        end_patterns = [
            r"item\s*1b[.\s]*unresolved\s*staff\s*comments",
            r"item\s*2[.\s]*properties",
            r"item\s*2[.\s]*management['']?s?\s*discussion",
            # 20-F patterns
            r"item\s*4[.\s]*information\s*on\s*the\s*company",
            r"item\s*4[.\s]*history\s*and\s*development",
        ]
    else:
        return None

    # Find section start
    text_lower = text.lower()
    start_pos = None
    for pattern in start_patterns:
        match = re.search(pattern, text_lower)
        if match:
            start_pos = match.start()
            break

    if start_pos is None:
        return None

    # Find section end
    end_pos = len(text)
    for pattern in end_patterns:
        match = re.search(pattern, text_lower[start_pos + 100:])
        if match:
            end_pos = start_pos + 100 + match.start()
            break

    section_text = text[start_pos:end_pos]

    # Clean up the text
    section_text = clean_text(section_text)

    return section_text if len(section_text) > 500 else None


def clean_text(text: str) -> str:
    """Clean extracted text."""
    # Remove excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)

    # Remove page numbers and headers
    text = re.sub(r'\n\d+\n', '\n', text)
    text = re.sub(r'table of contents', '', text, flags=re.IGNORECASE)

    # Remove common boilerplate
    text = re.sub(r'forward[- ]looking statements?.*?(?=\n\n)', '', text, flags=re.IGNORECASE | re.DOTALL)

    return text.strip()


def extract_paragraphs(text: str, min_length: int = 100) -> list[dict]:
    """
    Split text into paragraphs with metadata.

    Returns list of paragraph dicts with text and position info.
    """
    paragraphs = []

    # Split by double newlines
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


def fetch_mda_for_ticker(ticker: str, quarters: int = 12) -> dict:
    """
    Fetch MD&A and Risk Factors for a ticker.

    Args:
        ticker: Stock ticker symbol
        quarters: Number of quarters of history to fetch

    Returns:
        Dict with extracted sections and metadata
    """
    print(f"  Fetching CIK...", end=" ", flush=True)
    cik = get_cik_from_ticker(ticker)

    if not cik:
        print("NOT FOUND")
        return {"ticker": ticker, "error": f"Could not find CIK for {ticker}"}

    print(f"CIK: {cik}")

    print(f"  Fetching filing list...", end=" ", flush=True)
    filings = fetch_filing_list(cik, ["10-K", "10-Q", "20-F", "6-K"], max_filings=quarters + 5)
    print(f"Found {len(filings)} filings")

    if not filings:
        return {
            "ticker": ticker,
            "cik": cik,
            "error": "No filings found",
        }

    documents = []

    for i, filing in enumerate(filings[:quarters]):
        form = filing.get("form", "")
        date = filing.get("filing_date", "")
        print(f"  Processing {form} {date}...", end=" ", flush=True)

        html = fetch_filing_document(filing)
        if not html:
            print("FAILED")
            continue

        # Extract MD&A
        mda_text = extract_section(html, "mda")
        if mda_text:
            mda_paragraphs = extract_paragraphs(mda_text)
            documents.append({
                "ticker": ticker,
                "form": form,
                "filing_date": date,
                "section": "mda",
                "text": mda_text,
                "paragraphs": mda_paragraphs,
                "paragraph_count": len(mda_paragraphs),
                "char_count": len(mda_text),
            })

        # Extract Risk Factors
        risk_text = extract_section(html, "risk_factors")
        if risk_text:
            risk_paragraphs = extract_paragraphs(risk_text)
            documents.append({
                "ticker": ticker,
                "form": form,
                "filing_date": date,
                "section": "risk_factors",
                "text": risk_text,
                "paragraphs": risk_paragraphs,
                "paragraph_count": len(risk_paragraphs),
                "char_count": len(risk_text),
            })

        sections_found = []
        if mda_text:
            sections_found.append("MD&A")
        if risk_text:
            sections_found.append("Risk")
        print(f"{', '.join(sections_found) or 'None'}")

    return {
        "ticker": ticker,
        "cik": cik,
        "company_name": filings[0].get("company_name", ticker) if filings else ticker,
        "fetch_time": datetime.now().isoformat(),
        "document_count": len(documents),
        "documents": documents,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch MD&A and Risk Factors from SEC filings")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols")
    parser.add_argument("--file", type=Path, help="File with tickers (one per line)")
    parser.add_argument("--quarters", type=int, default=12, help="Quarters of history to fetch")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent.parent.parent / "data" / "documents" / "mda_data.json")

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
        print("Usage: python fetch_mda.py AAPL NVDA --quarters 12", file=sys.stderr)
        sys.exit(1)

    tickers = list(dict.fromkeys(tickers))

    print(f"Fetching MD&A data for {len(tickers)} ticker(s) ({args.quarters} quarters)...\n")

    results = []
    for ticker in tickers:
        print(f"\n{ticker}:")
        data = fetch_mda_for_ticker(ticker, args.quarters)
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
    print("MD&A EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"{'Ticker':<8} {'Documents':>10} {'MD&A':>8} {'Risk':>8}")
    print("-" * 60)

    for r in results:
        if r.get("error"):
            print(f"{r['ticker']:<8} {'ERROR':>10}")
            continue

        docs = r.get("documents", [])
        mda_count = sum(1 for d in docs if d.get("section") == "mda")
        risk_count = sum(1 for d in docs if d.get("section") == "risk_factors")

        print(f"{r['ticker']:<8} {len(docs):>10} {mda_count:>8} {risk_count:>8}")


if __name__ == "__main__":
    main()
