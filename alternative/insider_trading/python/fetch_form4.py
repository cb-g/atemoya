#!/usr/bin/env python3
"""
Fetch SEC Form 4 insider trading filings.

Uses SEC EDGAR API to retrieve Form 4 filings for specified tickers.
Form 4s must be filed within 2 business days of a transaction.

Usage:
    python fetch_form4.py AAPL NVDA TSLA
    python fetch_form4.py --file tickers.txt --days 30
"""

import json
import os
import sys
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET

import requests


# SEC requires identifying User-Agent
HEADERS = {
    "User-Agent": os.environ.get("SEC_EDGAR_IDENTITY", "DCF Research"),
    "Accept-Encoding": "gzip, deflate",
}

# Rate limit: SEC allows 10 requests/second
RATE_LIMIT_DELAY = 0.15


def get_cik_from_ticker(ticker: str) -> Optional[str]:
    """
    Get CIK (Central Index Key) from ticker symbol.

    Uses SEC's company tickers JSON file.
    """
    url = "https://www.sec.gov/files/company_tickers.json"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        ticker_upper = ticker.upper()
        for entry in data.values():
            if entry.get("ticker") == ticker_upper:
                # CIK needs to be zero-padded to 10 digits
                cik = str(entry.get("cik_str", ""))
                return cik.zfill(10)

        return None
    except Exception as e:
        print(f"Error fetching CIK for {ticker}: {e}", file=sys.stderr)
        return None


def fetch_form4_filings(cik: str, ticker: str, days: int = 90) -> list:
    """
    Fetch recent Form 4 filings for a company.

    Args:
        cik: Company CIK (10 digits, zero-padded)
        ticker: Ticker symbol (for reference)
        days: Number of days of history to fetch

    Returns:
        List of filing metadata dicts
    """
    # SEC's submissions endpoint
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        filings = []
        cutoff_date = datetime.now() - timedelta(days=days)

        # Recent filings are in the main object
        recent = data.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if form != "4":
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

            # Construct filing URL
            accession_clean = accession.replace("-", "")
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{accession_clean}/{primary_doc}"

            filings.append({
                "ticker": ticker,
                "cik": cik,
                "filing_date": filing_date,
                "accession": accession,
                "primary_doc": primary_doc,
                "url": filing_url,
            })

        return filings

    except Exception as e:
        print(f"Error fetching filings for {ticker}: {e}", file=sys.stderr)
        return []


def parse_form4_xml(xml_content: str, filing_meta: dict) -> dict:
    """
    Parse Form 4 XML content.

    Args:
        xml_content: Raw XML string
        filing_meta: Metadata dict from fetch_form4_filings

    Returns:
        Parsed transaction dict
    """
    result = {
        "ticker": filing_meta.get("ticker"),
        "filing_date": filing_meta.get("filing_date"),
        "filing_url": filing_meta.get("url"),
        "insider": {},
        "transactions": [],
        "error": None,
    }

    try:
        # Handle XML namespaces
        xml_content = re.sub(r'\sxmlns="[^"]+"', '', xml_content)
        root = ET.fromstring(xml_content)

        # Issuer info
        issuer = root.find(".//issuer")
        if issuer is not None:
            result["company"] = issuer.findtext("issuerName", "")
            result["ticker"] = issuer.findtext("issuerTradingSymbol", filing_meta.get("ticker", ""))

        # Reporting owner (insider)
        owner = root.find(".//reportingOwner")
        if owner is not None:
            owner_id = owner.find("reportingOwnerId")
            owner_rel = owner.find("reportingOwnerRelationship")

            result["insider"] = {
                "name": owner_id.findtext("rptOwnerName", "") if owner_id is not None else "",
                "cik": owner_id.findtext("rptOwnerCik", "") if owner_id is not None else "",
                "is_director": owner_rel.findtext("isDirector", "0") == "1" if owner_rel is not None else False,
                "is_officer": owner_rel.findtext("isOfficer", "0") == "1" if owner_rel is not None else False,
                "is_ten_percent_owner": owner_rel.findtext("isTenPercentOwner", "0") == "1" if owner_rel is not None else False,
                "officer_title": owner_rel.findtext("officerTitle", "") if owner_rel is not None else "",
            }

        # Non-derivative transactions (common stock)
        for trans in root.findall(".//nonDerivativeTransaction"):
            security = trans.find("securityTitle")
            amounts = trans.find("transactionAmounts")
            coding = trans.find("transactionCoding")
            ownership = trans.find("postTransactionAmounts")

            if amounts is None:
                continue

            shares_elem = amounts.find("transactionShares")
            price_elem = amounts.find("transactionPricePerShare")

            shares = 0
            price = 0.0

            if shares_elem is not None:
                shares_val = shares_elem.findtext("value", "0")
                try:
                    shares = float(shares_val)
                except ValueError:
                    shares = 0

            if price_elem is not None:
                price_val = price_elem.findtext("value", "0")
                try:
                    price = float(price_val)
                except ValueError:
                    price = 0.0

            # Transaction code: P=Purchase, S=Sale, A=Award, etc.
            trans_code = ""
            if coding is not None:
                trans_code = coding.findtext("transactionCode", "")

            # Acquisition or disposition
            acq_disp = ""
            acq_disp_elem = amounts.find("transactionAcquiredDisposedCode")
            if acq_disp_elem is not None:
                acq_disp = acq_disp_elem.findtext("value", "")

            # Shares owned after transaction
            shares_after = 0
            if ownership is not None:
                shares_after_elem = ownership.find("sharesOwnedFollowingTransaction")
                if shares_after_elem is not None:
                    try:
                        shares_after = float(shares_after_elem.findtext("value", "0"))
                    except ValueError:
                        shares_after = 0

            transaction = {
                "security": security.findtext("value", "Common Stock") if security is not None else "Common Stock",
                "transaction_code": trans_code,
                "acquisition_disposition": acq_disp,
                "shares": shares,
                "price": price,
                "value": shares * price,
                "shares_after": shares_after,
            }

            result["transactions"].append(transaction)

        # Also check derivative transactions (options, etc.)
        for trans in root.findall(".//derivativeTransaction"):
            security = trans.find("securityTitle")
            amounts = trans.find("transactionAmounts")
            coding = trans.find("transactionCoding")

            if amounts is None:
                continue

            shares_elem = amounts.find("transactionShares")
            price_elem = amounts.find("transactionPricePerShare")

            shares = 0
            price = 0.0

            if shares_elem is not None:
                shares_val = shares_elem.findtext("value", "0")
                try:
                    shares = float(shares_val)
                except ValueError:
                    shares = 0

            if price_elem is not None:
                price_val = price_elem.findtext("value", "0")
                try:
                    price = float(price_val)
                except ValueError:
                    price = 0.0

            trans_code = ""
            if coding is not None:
                trans_code = coding.findtext("transactionCode", "")

            acq_disp = ""
            acq_disp_elem = amounts.find("transactionAcquiredDisposedCode")
            if acq_disp_elem is not None:
                acq_disp = acq_disp_elem.findtext("value", "")

            transaction = {
                "security": security.findtext("value", "Derivative") if security is not None else "Derivative",
                "transaction_code": trans_code,
                "acquisition_disposition": acq_disp,
                "shares": shares,
                "price": price,
                "value": shares * price,
                "is_derivative": True,
            }

            result["transactions"].append(transaction)

    except ET.ParseError as e:
        result["error"] = f"XML parse error: {e}"
    except Exception as e:
        result["error"] = f"Parse error: {e}"

    return result


def find_form4_xml_url(filing_meta: dict) -> Optional[str]:
    """
    Find the Form 4 XML file URL in the filing directory.

    SEC filings can have various XML naming conventions.
    """
    accession = filing_meta.get("accession", "").replace("-", "")
    cik = filing_meta.get("cik", "").lstrip("0")
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"

    try:
        time.sleep(RATE_LIMIT_DELAY)
        resp = requests.get(base_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()

        # Find XML files in the directory listing
        xml_files = re.findall(r'href="([^"]+\.xml)"', resp.text)

        # Look for Form 4 XML (usually contains 'form4' in name or is the only XML)
        for xml_file in xml_files:
            if 'form4' in xml_file.lower() or 'f4' in xml_file.lower():
                # Handle both absolute and relative paths
                if xml_file.startswith('/'):
                    return "https://www.sec.gov" + xml_file
                return base_url + xml_file

        # If no form4 named file, try the first XML that's not an index
        for xml_file in xml_files:
            if 'index' not in xml_file.lower():
                if xml_file.startswith('/'):
                    return "https://www.sec.gov" + xml_file
                return base_url + xml_file

        return None
    except Exception:
        return None


def fetch_and_parse_form4(filing_meta: dict) -> dict:
    """
    Fetch Form 4 XML and parse it.

    Args:
        filing_meta: Filing metadata from fetch_form4_filings

    Returns:
        Parsed transaction dict
    """
    # First, find the actual XML file URL
    xml_url = find_form4_xml_url(filing_meta)

    if not xml_url:
        return {
            "ticker": filing_meta.get("ticker"),
            "filing_date": filing_meta.get("filing_date"),
            "filing_url": filing_meta.get("url", ""),
            "error": "Could not find Form 4 XML file",
        }

    try:
        time.sleep(RATE_LIMIT_DELAY)
        resp = requests.get(xml_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()

        return parse_form4_xml(resp.text, filing_meta)

    except Exception as e:
        return {
            "ticker": filing_meta.get("ticker"),
            "filing_date": filing_meta.get("filing_date"),
            "filing_url": xml_url,
            "error": f"Fetch error: {e}",
        }


def classify_transaction(trans: dict, insider: dict) -> dict:
    """
    Classify a transaction and assign importance score.

    Returns dict with classification info.
    """
    code = trans.get("transaction_code", "")
    acq_disp = trans.get("acquisition_disposition", "")
    value = trans.get("value", 0)
    is_derivative = trans.get("is_derivative", False)

    officer_title = insider.get("officer_title", "").upper()
    is_officer = insider.get("is_officer", False)
    is_director = insider.get("is_director", False)

    # Determine transaction type
    if code == "P":
        trans_type = "open_market_purchase"
        signal_strength = "strong"
    elif code == "S":
        trans_type = "open_market_sale"
        signal_strength = "weak"
    elif code == "A":
        trans_type = "award"
        signal_strength = "neutral"
    elif code == "M":
        trans_type = "option_exercise"
        signal_strength = "weak"  # Options exercise often followed by sale
    elif code == "G":
        trans_type = "gift"
        signal_strength = "neutral"
    elif code == "F":
        trans_type = "tax_withholding"
        signal_strength = "neutral"
    else:
        trans_type = "other"
        signal_strength = "neutral"

    # Determine if buy or sell
    if acq_disp == "A":
        direction = "buy"
    elif acq_disp == "D":
        direction = "sell"
    else:
        direction = "unknown"

    # Score insider importance (0-100)
    importance = 50  # Base score

    if "CEO" in officer_title or "CHIEF EXECUTIVE" in officer_title:
        importance = 100
    elif "CFO" in officer_title or "CHIEF FINANCIAL" in officer_title:
        importance = 90
    elif "COO" in officer_title or "CHIEF OPERATING" in officer_title:
        importance = 85
    elif "PRESIDENT" in officer_title:
        importance = 80
    elif "VP" in officer_title or "VICE PRESIDENT" in officer_title:
        importance = 60
    elif is_officer:
        importance = 55
    elif is_director:
        importance = 50

    # Value multiplier
    if value >= 1_000_000:
        value_significance = "very_high"
    elif value >= 500_000:
        value_significance = "high"
    elif value >= 100_000:
        value_significance = "moderate"
    elif value >= 10_000:
        value_significance = "low"
    else:
        value_significance = "minimal"

    return {
        "transaction_type": trans_type,
        "direction": direction,
        "signal_strength": signal_strength,
        "insider_importance": importance,
        "value_significance": value_significance,
        "is_derivative": is_derivative,
    }


def fetch_insider_transactions(ticker: str, days: int = 90) -> dict:
    """
    Fetch and parse all Form 4 filings for a ticker.

    Args:
        ticker: Stock ticker symbol
        days: Number of days of history

    Returns:
        Dict with all parsed transactions and summary
    """
    print(f"  Fetching CIK for {ticker}...", end=" ", flush=True)
    cik = get_cik_from_ticker(ticker)

    if not cik:
        print("NOT FOUND")
        return {
            "ticker": ticker,
            "fetch_time": datetime.now().isoformat(),
            "error": f"Could not find CIK for {ticker}",
        }

    print(f"CIK: {cik}")
    time.sleep(RATE_LIMIT_DELAY)

    print(f"  Fetching Form 4 filings...", end=" ", flush=True)
    filings = fetch_form4_filings(cik, ticker, days)
    print(f"Found {len(filings)} filings")

    if not filings:
        return {
            "ticker": ticker,
            "cik": cik,
            "fetch_time": datetime.now().isoformat(),
            "filings_count": 0,
            "transactions": [],
            "summary": {},
        }

    # Parse each filing
    all_transactions = []
    unique_insiders = set()

    for i, filing in enumerate(filings[:50]):  # Limit to 50 most recent
        print(f"  Parsing filing {i+1}/{min(len(filings), 50)}...", end="\r", flush=True)

        parsed = fetch_and_parse_form4(filing)

        if parsed.get("error"):
            continue

        insider = parsed.get("insider", {})
        insider_name = insider.get("name", "Unknown")
        unique_insiders.add(insider_name)

        for trans in parsed.get("transactions", []):
            classification = classify_transaction(trans, insider)

            all_transactions.append({
                "filing_date": parsed.get("filing_date"),
                "insider_name": insider_name,
                "insider_title": insider.get("officer_title", ""),
                "is_officer": insider.get("is_officer", False),
                "is_director": insider.get("is_director", False),
                **trans,
                **classification,
            })

    print(f"  Parsed {len(all_transactions)} transactions from {len(unique_insiders)} insiders")

    # Calculate summary statistics
    buys = [t for t in all_transactions if t["direction"] == "buy" and t["transaction_type"] == "open_market_purchase"]
    sells = [t for t in all_transactions if t["direction"] == "sell" and t["transaction_type"] == "open_market_sale"]

    total_buy_value = sum(t["value"] for t in buys)
    total_sell_value = sum(t["value"] for t in sells)

    # Buy/sell ratio
    if total_sell_value > 0:
        buy_sell_ratio = total_buy_value / total_sell_value
    elif total_buy_value > 0:
        buy_sell_ratio = float("inf")
    else:
        buy_sell_ratio = 0

    summary = {
        "total_filings": len(filings),
        "total_transactions": len(all_transactions),
        "unique_insiders": len(unique_insiders),
        "buys_count": len(buys),
        "sells_count": len(sells),
        "total_buy_value": total_buy_value,
        "total_sell_value": total_sell_value,
        "buy_sell_ratio": buy_sell_ratio if buy_sell_ratio != float("inf") else 999,
        "net_activity": total_buy_value - total_sell_value,
    }

    return {
        "ticker": ticker,
        "cik": cik,
        "fetch_time": datetime.now().isoformat(),
        "days_lookback": days,
        "filings_count": len(filings),
        "transactions": all_transactions,
        "summary": summary,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch SEC Form 4 insider trading data")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols")
    parser.add_argument("--file", type=Path, help="File with tickers (one per line)")
    parser.add_argument("--days", type=int, default=90, help="Days of history to fetch")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent.parent / "data" / "insider_transactions.json")

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
        print("Usage: python fetch_form4.py AAPL NVDA TSLA", file=sys.stderr)
        sys.exit(1)

    # Remove duplicates
    tickers = list(dict.fromkeys(tickers))

    print(f"Fetching Form 4 filings for {len(tickers)} ticker(s) (last {args.days} days)...\n")

    results = []
    for ticker in tickers:
        print(f"\n{ticker}:")
        data = fetch_insider_transactions(ticker, args.days)
        results.append(data)

        # Print summary
        if data.get("error"):
            print(f"  ERROR: {data['error']}")
        else:
            summary = data.get("summary", {})
            print(f"  Buys: {summary.get('buys_count', 0)} (${summary.get('total_buy_value', 0):,.0f})")
            print(f"  Sells: {summary.get('sells_count', 0)} (${summary.get('total_sell_value', 0):,.0f})")
            print(f"  Buy/Sell Ratio: {summary.get('buy_sell_ratio', 0):.2f}")

    # Save results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "fetch_time": datetime.now().isoformat(),
        "days_lookback": args.days,
        "ticker_count": len(results),
        "tickers": results,
    }

    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2, default=str)

    print(f"\n\nResults saved to {args.output}")

    # Print summary table
    print("\n" + "=" * 70)
    print("INSIDER TRADING SUMMARY")
    print("=" * 70)
    print(f"{'Ticker':<8} {'Filings':>8} {'Buys':>8} {'Sells':>8} {'Net $':>12} {'B/S Ratio':>10}")
    print("-" * 70)

    for r in results:
        if r.get("error"):
            print(f"{r['ticker']:<8} {'ERROR':>8}")
            continue

        s = r.get("summary", {})
        net = s.get("net_activity", 0)
        net_str = f"+${net:,.0f}" if net >= 0 else f"-${abs(net):,.0f}"
        ratio = s.get("buy_sell_ratio", 0)
        ratio_str = f"{ratio:.2f}" if ratio < 999 else "∞"

        print(f"{r['ticker']:<8} {s.get('total_filings', 0):>8} "
              f"{s.get('buys_count', 0):>8} {s.get('sells_count', 0):>8} "
              f"{net_str:>12} {ratio_str:>10}")


if __name__ == "__main__":
    main()
