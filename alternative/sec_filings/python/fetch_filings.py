#!/usr/bin/env python3
"""
Fetch SEC EDGAR filings for tickers.

Retrieves recent SEC filings including:
- 8-K: Material events (acquisitions, earnings, officer changes)
- 10-K: Annual reports
- 10-Q: Quarterly reports
- 13D/G: >5% ownership positions
- DEF 14A: Proxy statements

Usage:
    python fetch_filings.py AAPL NVDA TSLA
    python fetch_filings.py --file tickers.txt --days 30
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests


# SEC requires identifying User-Agent
HEADERS = {
    "User-Agent": os.environ.get("SEC_EDGAR_IDENTITY", "DCF Research"),
    "Accept-Encoding": "gzip, deflate",
}

# Rate limit: SEC allows 10 requests/second
RATE_LIMIT_DELAY = 0.15

# 8-K Item descriptions
ITEM_8K_DESCRIPTIONS = {
    "1.01": "Entry into Material Definitive Agreement",
    "1.02": "Termination of Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership",
    "1.04": "Mine Safety",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of Direct Financial Obligation",
    "2.04": "Triggering Events That Accelerate Obligations",
    "2.05": "Costs Associated with Exit or Disposal Activities",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting or Transfer",
    "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Security Holders",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure of Directors or Certain Officers",
    "5.03": "Amendments to Articles of Incorporation or Bylaws",
    "5.04": "Temporary Suspension of Trading Under Employee Benefit Plans",
    "5.05": "Amendment to Code of Ethics",
    "5.06": "Change in Shell Company Status",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "5.08": "Shareholder Nominations",
    "6.01": "ABS Informational and Computational Material",
    "6.02": "Change of Servicer or Trustee",
    "6.03": "Change in Credit Enhancement",
    "6.04": "Failure to Make a Required Distribution",
    "6.05": "Securities Act Updating Disclosure",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}

# High-priority 8-K items (most actionable)
HIGH_PRIORITY_ITEMS = {"1.01", "1.02", "2.01", "2.02", "5.02", "7.01"}


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


def fetch_company_filings(cik: str, ticker: str, days: int = 30, form_types: list = None) -> list:
    """
    Fetch recent filings for a company.

    Args:
        cik: Company CIK (10 digits, zero-padded)
        ticker: Ticker symbol
        days: Number of days of history
        form_types: List of form types to include (None = all)

    Returns:
        List of filing metadata dicts
    """
    if form_types is None:
        form_types = ["8-K", "10-K", "10-Q", "13D", "13G", "DEF 14A", "S-1", "4"]

    url = f"https://data.sec.gov/submissions/CIK{cik}.json"

    try:
        time.sleep(RATE_LIMIT_DELAY)
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        company_name = data.get("name", ticker)
        filings = []
        cutoff_date = datetime.now() - timedelta(days=days)

        recent = data.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        descriptions = recent.get("primaryDocDescription", [])

        for i, form in enumerate(forms):
            # Filter by form type
            form_match = False
            for ft in form_types:
                if form.startswith(ft) or form == ft:
                    form_match = True
                    break

            if not form_match:
                continue

            filing_date = dates[i] if i < len(dates) else None
            if not filing_date:
                continue

            try:
                date_obj = datetime.strptime(filing_date, "%Y-%m-%d")
                if date_obj < cutoff_date:
                    continue
            except ValueError:
                continue

            accession = accessions[i] if i < len(accessions) else ""
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""
            description = descriptions[i] if i < len(descriptions) else ""

            # Construct filing URL
            accession_clean = accession.replace("-", "")
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{accession_clean}/{primary_doc}"
            index_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{accession_clean}/"

            filings.append({
                "ticker": ticker,
                "company": company_name,
                "cik": cik,
                "form": form,
                "filing_date": filing_date,
                "accession": accession,
                "description": description,
                "url": filing_url,
                "index_url": index_url,
            })

        return filings

    except Exception as e:
        print(f"Error fetching filings for {ticker}: {e}", file=sys.stderr)
        return []


def parse_8k_items(filing: dict) -> list:
    """
    Parse 8-K filing to extract item numbers.

    Returns list of item dicts with number, title, and priority.
    """
    index_url = filing.get("index_url", "")
    if not index_url:
        return []

    try:
        time.sleep(RATE_LIMIT_DELAY)
        resp = requests.get(index_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()

        # Look for 8-K document in the index
        html = resp.text

        # Find the main 8-K document
        doc_pattern = r'href="([^"]+\.htm)"'
        doc_matches = re.findall(doc_pattern, html)

        # Try to fetch and parse the 8-K document
        for doc in doc_matches:
            if "8k" in doc.lower() or "8-k" in doc.lower():
                if doc.startswith("/"):
                    doc_url = "https://www.sec.gov" + doc
                else:
                    doc_url = index_url + doc

                time.sleep(RATE_LIMIT_DELAY)
                doc_resp = requests.get(doc_url, headers=HEADERS, timeout=30)
                if doc_resp.status_code == 200:
                    items = extract_8k_items(doc_resp.text)
                    if items:
                        return items

        # Fallback: try to extract from description or accession
        return extract_items_from_description(filing.get("description", ""))

    except Exception:
        return extract_items_from_description(filing.get("description", ""))


def extract_8k_items(html_content: str) -> list:
    """Extract 8-K item numbers from HTML content."""
    items = []

    # Pattern to match "Item X.XX" in various formats
    item_pattern = r'Item\s+(\d+\.\d+)'
    matches = re.findall(item_pattern, html_content, re.IGNORECASE)

    seen = set()
    for item_num in matches:
        if item_num not in seen:
            seen.add(item_num)
            items.append({
                "item": item_num,
                "title": ITEM_8K_DESCRIPTIONS.get(item_num, "Unknown"),
                "priority": "high" if item_num in HIGH_PRIORITY_ITEMS else "normal",
            })

    return items


def extract_items_from_description(description: str) -> list:
    """Extract items from filing description if available."""
    items = []

    item_pattern = r'(\d+\.\d+)'
    matches = re.findall(item_pattern, description)

    seen = set()
    for item_num in matches:
        if item_num not in seen and item_num in ITEM_8K_DESCRIPTIONS:
            seen.add(item_num)
            items.append({
                "item": item_num,
                "title": ITEM_8K_DESCRIPTIONS.get(item_num, "Unknown"),
                "priority": "high" if item_num in HIGH_PRIORITY_ITEMS else "normal",
            })

    return items


def classify_filing_importance(filing: dict) -> dict:
    """
    Classify filing importance and generate signal info.

    Returns dict with importance score and classification.
    """
    form = filing.get("form", "")
    items = filing.get("items", [])

    importance = 50  # Base score
    classification = "routine"
    signal_type = None

    # 8-K importance based on items
    if form.startswith("8-K"):
        high_priority_count = sum(1 for i in items if i.get("priority") == "high")

        if high_priority_count > 0:
            importance = 70 + (high_priority_count * 10)
            classification = "material_event"

            # Specific signals
            item_nums = {i.get("item") for i in items}
            if "2.02" in item_nums:
                signal_type = "earnings"
            elif "2.01" in item_nums:
                signal_type = "acquisition"
            elif "5.02" in item_nums:
                signal_type = "executive_change"
            elif "1.01" in item_nums:
                signal_type = "material_agreement"
            elif "7.01" in item_nums:
                signal_type = "reg_fd"
        else:
            importance = 40
            classification = "routine_8k"

    # 10-K/10-Q are periodic reports
    elif form.startswith("10-K"):
        importance = 60
        classification = "annual_report"
        signal_type = "annual_report"
    elif form.startswith("10-Q"):
        importance = 55
        classification = "quarterly_report"
        signal_type = "quarterly_report"

    # 13D/G are activist/ownership signals
    elif form.startswith("13D"):
        importance = 85
        classification = "activist_position"
        signal_type = "activist_13d"
    elif form.startswith("13G"):
        importance = 65
        classification = "passive_position"
        signal_type = "passive_13g"

    # Proxy statements
    elif form.startswith("DEF 14A"):
        importance = 50
        classification = "proxy"
        signal_type = "proxy"

    # S-1 is IPO/offering
    elif form.startswith("S-1"):
        importance = 75
        classification = "registration"
        signal_type = "offering"

    return {
        "importance": min(importance, 100),
        "classification": classification,
        "signal_type": signal_type,
    }


def fetch_ticker_filings(ticker: str, days: int = 30) -> dict:
    """
    Fetch and parse all relevant filings for a ticker.

    Args:
        ticker: Stock ticker symbol
        days: Number of days of history

    Returns:
        Dict with all filings and summary
    """
    print(f"  Fetching CIK...", end=" ", flush=True)
    cik = get_cik_from_ticker(ticker)

    if not cik:
        print("NOT FOUND")
        return {
            "ticker": ticker,
            "fetch_time": datetime.now().isoformat(),
            "error": f"Could not find CIK for {ticker}",
        }

    print(f"CIK: {cik}")

    print(f"  Fetching filings...", end=" ", flush=True)
    filings = fetch_company_filings(cik, ticker, days)
    print(f"Found {len(filings)} filings")

    if not filings:
        return {
            "ticker": ticker,
            "cik": cik,
            "fetch_time": datetime.now().isoformat(),
            "days_lookback": days,
            "filing_count": 0,
            "filings": [],
            "summary": {},
        }

    # Parse and classify filings
    processed_filings = []
    form_counts = {}

    for filing in filings:
        form = filing.get("form", "")

        # Count by form type
        form_base = form.split("/")[0]
        form_counts[form_base] = form_counts.get(form_base, 0) + 1

        # Parse 8-K items
        if form.startswith("8-K"):
            print(f"  Parsing 8-K {filing.get('filing_date')}...", end="\r", flush=True)
            items = parse_8k_items(filing)
            filing["items"] = items

        # Classify importance
        classification = classify_filing_importance(filing)
        filing.update(classification)

        processed_filings.append(filing)

    print(f"  Processed {len(processed_filings)} filings                    ")

    # Generate summary
    material_events = [f for f in processed_filings if f.get("importance", 0) >= 70]
    eight_k_count = sum(1 for f in processed_filings if f.get("form", "").startswith("8-K"))

    summary = {
        "total_filings": len(processed_filings),
        "form_counts": form_counts,
        "material_events": len(material_events),
        "eight_k_count": eight_k_count,
        "has_activist_filing": any(f.get("signal_type") == "activist_13d" for f in processed_filings),
        "has_earnings": any(f.get("signal_type") == "earnings" for f in processed_filings),
    }

    return {
        "ticker": ticker,
        "cik": cik,
        "company": processed_filings[0].get("company", ticker) if processed_filings else ticker,
        "fetch_time": datetime.now().isoformat(),
        "days_lookback": days,
        "filing_count": len(processed_filings),
        "filings": processed_filings,
        "summary": summary,
        "error": None,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch SEC EDGAR filings")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols")
    parser.add_argument("--file", type=Path, help="File with tickers (one per line)")
    parser.add_argument("--days", type=int, default=30, help="Days of history to fetch")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent.parent / "data" / "sec_filings.json")

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
        print("Usage: python fetch_filings.py AAPL NVDA TSLA", file=sys.stderr)
        sys.exit(1)

    # Remove duplicates
    tickers = list(dict.fromkeys(tickers))

    print(f"Fetching SEC filings for {len(tickers)} ticker(s) (last {args.days} days)...\n")

    results = []
    for ticker in tickers:
        print(f"\n{ticker}:")
        data = fetch_ticker_filings(ticker, args.days)
        results.append(data)

        # Print summary
        if data.get("error"):
            print(f"  ERROR: {data['error']}")
        else:
            summary = data.get("summary", {})
            print(f"  Total: {summary.get('total_filings', 0)} | "
                  f"8-K: {summary.get('eight_k_count', 0)} | "
                  f"Material: {summary.get('material_events', 0)}")

    # Save results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "fetch_time": datetime.now().isoformat(),
        "days_lookback": args.days,
        "ticker_count": len(results),
        "tickers": results,
    }

    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\n\nResults saved to {args.output}")

    # Print summary table
    print("\n" + "=" * 75)
    print("SEC FILINGS SUMMARY")
    print("=" * 75)
    print(f"{'Ticker':<8} {'Total':>8} {'8-K':>6} {'10-K':>6} {'10-Q':>6} {'13D/G':>6} {'Material':>10}")
    print("-" * 75)

    for r in results:
        if r.get("error"):
            print(f"{r['ticker']:<8} {'ERROR':>8}")
            continue

        s = r.get("summary", {})
        fc = s.get("form_counts", {})

        print(f"{r['ticker']:<8} {s.get('total_filings', 0):>8} "
              f"{fc.get('8-K', 0):>6} {fc.get('10-K', 0):>6} "
              f"{fc.get('10-Q', 0):>6} {fc.get('13D', 0) + fc.get('13G', 0):>6} "
              f"{s.get('material_events', 0):>10}")

    # Print material events
    all_material = []
    for r in results:
        if not r.get("error"):
            for f in r.get("filings", []):
                if f.get("importance", 0) >= 70:
                    all_material.append(f)

    if all_material:
        print("\n" + "-" * 75)
        print("MATERIAL EVENTS (Importance >= 70)")
        print("-" * 75)
        print(f"{'Date':<12} {'Ticker':<8} {'Form':<10} {'Signal':<20} {'Items':<20}")
        print("-" * 75)

        for f in sorted(all_material, key=lambda x: x.get("filing_date", ""), reverse=True)[:15]:
            items_str = ", ".join(i.get("item", "") for i in f.get("items", []))[:18]
            signal = f.get("signal_type", "N/A") or "N/A"
            print(f"{f.get('filing_date', 'N/A'):<12} {f.get('ticker', '?'):<8} "
                  f"{f.get('form', '?'):<10} {signal:<20} {items_str:<20}")


if __name__ == "__main__":
    main()
