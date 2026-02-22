#!/usr/bin/env python3
"""
Fetch Oil & Gas reserve data from SEC 10-K filings using edgartools.

This script extracts proved reserves, production, and cost data from
the "Supplemental Information on Oil and Gas Producing Activities"
section of 10-K filings.

"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from edgar import Company, set_identity


def extract_number(text: str) -> float | None:
    """Extract a number from text, handling commas and parentheses for negatives."""
    if not text:
        return None
    # Remove commas and whitespace
    text = text.strip().replace(",", "").replace(" ", "")
    # Handle parentheses as negative
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    # Handle dashes as zero
    if text in ["-", "—", "–", ""]:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return None


def parse_reserve_table(text: str) -> dict:
    """Parse reserve quantities from supplemental O&G disclosure text."""
    reserves = {
        "proved_reserves_oil_mmbbl": None,  # Million barrels
        "proved_reserves_gas_bcf": None,    # Billion cubic feet
        "proved_reserves_boe_mmboe": None,  # Million BOE (calculated or direct)
    }

    # Normalize text: replace non-breaking spaces with regular spaces
    text = text.replace('\xa0', ' ')

    # Strategy 0 (highest priority): Look for "Total Proved Reserves" table row
    # XOM-style: "Total Proved Reserves8,488 2,478 2,429 296 37,549 19,949"
    # The last number is the oil-equivalent total in MMBOE.
    total_proved_match = re.search(
        r'Total\s+Proved\s+Reserves\s*([\d,\s]+)', text, re.IGNORECASE
    )
    if total_proved_match:
        numbers = re.findall(r'[\d,]+', total_proved_match.group(1))
        if numbers:
            last_val = extract_number(numbers[-1])
            if last_val and 500 < last_val < 50000:
                reserves["proved_reserves_boe_mmboe"] = last_val
                return reserves

    # Strategy 1: Look for narrative statements like "X billion barrels of oil-equivalent"
    # This handles CVX-style prose descriptions
    # Only match statements about TOTAL proved reserves, not subsets like "undeveloped"
    billion_boe_patterns = [
        r"(\d+\.?\d*)\s*billion\s*(?:barrels?\s*(?:of\s+)?)?oil[- ]equivalent",
        r"reserves?[^\.]{0,50}?(\d+\.?\d*)\s*billion\s*(?:barrels?|boe)",
        r"approximately\s+(\d+\.?\d*)\s*billion\s*(?:barrels?\s*(?:of\s+)?)?(?:oil[- ]equivalent|boe)",
    ]

    for pattern in billion_boe_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            # Skip matches that refer to subsets (undeveloped, developed only)
            context_start = max(0, match.start() - 150)
            context = text[context_start:match.start()].lower()
            if any(w in context for w in ['undeveloped', 'developed reserves', 'developed proved']):
                continue
            val = extract_number(match.group(1))
            if val and 1 < val < 50:
                reserves["proved_reserves_boe_mmboe"] = val * 1000
                return reserves

    # Strategy 2: Look for "Total" rows with Oil-Equivalent values
    total_patterns = [
        r"Total\s+(?:Developed|Consolidated|Proved)[^\d]*?([\d,]+)\s*$",
        r"(?:Total|Proved)\s+(?:Oil-Equivalent|BOE)[^\d]*([\d,]+)",
        r"([\d,]+)\s*(?:million\s+)?(?:barrels?\s+)?(?:oil[- ]equivalent|mmboe|boe)",
    ]

    # Strategy 2: Look for section-specific "End of 20XX" rows
    # First try to find oil-equivalent section explicitly
    current_year = 2024  # Most recent year we're looking for

    # Look for Oil-Equivalent or Crude Oil section headers and find End of Year
    for section_marker in ['Oil-Equivalent', 'Crude Oil', 'MMBOE']:
        idx = text.find(section_marker)
        if idx > 0:
            # Look at next 3000 chars for End of 2024
            section = text[idx:idx+3000]
            eoy_match = re.search(rf'End\s+of\s+{current_year}([^\n]+)', section, re.IGNORECASE)
            if eoy_match:
                line = eoy_match.group(1)
                numbers = re.findall(r'[\d,]+', line)
                if numbers and len(numbers) >= 5:
                    try:
                        last_val = float(numbers[-1].replace(',', ''))
                        # Oil-equivalent tables: 1,000-10,000 MMBOE for most E&P companies
                        if 1000 < last_val < 10000:
                            reserves["proved_reserves_boe_mmboe"] = last_val
                            return reserves
                    except ValueError:
                        pass

    # Strategy 2b: Look for "Balance as of December 31, 20XX" pattern (OXY-style)
    # First check in MMBOE section if available
    mmboe_idx = text.find('MMboe')
    if mmboe_idx < 0:
        mmboe_idx = text.lower().find('mmboe')
    if mmboe_idx > 0:
        mmboe_section = text[mmboe_idx:mmboe_idx+3000]
        balance_pattern = rf'Balance\s+as\s+of\s+December\s+31,\s+{current_year}([^\n]+)'
        balance_match = re.search(balance_pattern, mmboe_section, re.IGNORECASE)
        if balance_match:
            line = balance_match.group(1)
            numbers = re.findall(r'[\d,]+', line)
            if numbers and len(numbers) >= 2:
                try:
                    last_val = float(numbers[-1].replace(',', ''))
                    if 1000 < last_val < 10000:
                        reserves["proved_reserves_boe_mmboe"] = last_val
                        return reserves
                except ValueError:
                    pass

    # Try Balance pattern across full text as fallback
    balance_pattern = rf'Balance\s+as\s+of\s+December\s+31,\s+{current_year}([^\n]+)'
    balance_match = re.search(balance_pattern, text, re.IGNORECASE)
    if balance_match:
        line = balance_match.group(1)
        numbers = re.findall(r'[\d,]+', line)
        if numbers and len(numbers) >= 2:  # At least US, International, Total
            try:
                last_val = float(numbers[-1].replace(',', ''))
                if 1000 < last_val < 10000:
                    reserves["proved_reserves_boe_mmboe"] = last_val
                    return reserves
            except ValueError:
                pass

    # Fallback: Look for "Developed and Undeveloped" section then End of 20XX
    dev_undev_idx = text.find('Developed and Undeveloped')
    if dev_undev_idx > 0:
        section = text[dev_undev_idx:dev_undev_idx+5000]
        eoy_match = re.search(rf'End\s+of\s+{current_year}([^\n]+)', section, re.IGNORECASE)
        if eoy_match:
            line = eoy_match.group(1)
            numbers = re.findall(r'[\d,]+', line)
            if numbers and len(numbers) >= 5:
                try:
                    last_val = float(numbers[-1].replace(',', ''))
                    if 1000 < last_val < 10000:
                        reserves["proved_reserves_boe_mmboe"] = last_val
                        return reserves
                except ValueError:
                    pass

    # Last resort: Take the FIRST valid End of Year line (not largest)
    # Reserve totals typically appear early in the supplemental disclosure
    end_of_year_pattern = rf'End\s+of\s+{current_year}([^\n]+)'
    matches = list(re.finditer(end_of_year_pattern, text, re.IGNORECASE))

    for m in matches:
        line = m.group(1)
        numbers = re.findall(r'[\d,]+', line)
        if numbers and len(numbers) >= 5:  # Reserve tables typically have many columns
            try:
                last_val = float(numbers[-1].replace(',', ''))
                # Stricter bounds: 1,000-10,000 MMBOE to avoid natural gas tables
                if 1000 < last_val < 10000:
                    reserves["proved_reserves_boe_mmboe"] = last_val
                    return reserves
            except ValueError:
                pass

    # Strategy 3: Look for "Total Oil-Equivalent" or similar rows in tables
    lines = text.split('\n')

    total_boe = None
    total_oil = None
    total_gas = None

    for i, line in enumerate(lines):
        line_clean = line.strip()
        line_lower = line_clean.lower()

        # Only look at lines that specifically mention oil-equivalent or reserves
        if 'oil-equivalent' in line_lower or 'oil equivalent' in line_lower:
            # Look for "Total" in this line
            if 'total' in line_lower:
                numbers = re.findall(r'([\d,]+)', line_clean)
                for num_str in numbers:
                    val = extract_number(num_str)
                    # Sanity check: 1,000-50,000 MMBOE (1-50 billion BOE)
                    if val and 1000 < val < 50000:
                        if total_boe is None or val > total_boe:
                            total_boe = val

        # Look for proved reserves tables
        if 'proved' in line_lower and ('reserves' in line_lower or 'developed' in line_lower):
            if 'total' in line_lower:
                numbers = re.findall(r'([\d,]+)', line_clean)
                if numbers:
                    val = extract_number(numbers[-1])
                    # Sanity check: 1,000-50,000 MMBOE (1-50 billion BOE)
                    if val and 1000 < val < 50000:
                        if total_boe is None or val > total_boe:
                            total_boe = val

        # Look for crude oil totals
        if re.search(r'(?:crude\s*oil|liquids?)\s*total', line_clean, re.IGNORECASE):
            numbers = re.findall(r'([\d,]+)', line_clean)
            if numbers:
                val = extract_number(numbers[-1])
                if val and val > 100:
                    total_oil = val

        # Look for natural gas totals
        if re.search(r'natural\s*gas\s*total', line_clean, re.IGNORECASE):
            numbers = re.findall(r'([\d,]+)', line_clean)
            if numbers:
                val = extract_number(numbers[-1])
                if val and val > 100:
                    total_gas = val

    # Try specific "Total Oil-Equivalent" pattern on full text
    total_oe_pattern = r'Total\s+Oil[- ]Equivalent\s*([\d,]+)'
    match = re.search(total_oe_pattern, text, re.IGNORECASE)
    if match:
        val = extract_number(match.group(1))
        if val and 1000 < val < 50000:
            if total_boe is None or val > total_boe:
                total_boe = val

    # Assign results
    if total_boe:
        reserves["proved_reserves_boe_mmboe"] = total_boe
    if total_oil:
        reserves["proved_reserves_oil_mmbbl"] = total_oil
    if total_gas:
        reserves["proved_reserves_gas_bcf"] = total_gas

    # If we have oil and gas but no BOE, calculate it
    if reserves["proved_reserves_boe_mmboe"] is None:
        oil = reserves["proved_reserves_oil_mmbbl"] or 0
        gas = reserves["proved_reserves_gas_bcf"] or 0
        if oil > 0 or gas > 0:
            gas_boe = gas * 1000 / 6 / 1000  # BCF to MMBOE
            reserves["proved_reserves_boe_mmboe"] = oil + gas_boe

    return reserves


def parse_production_data(text: str) -> dict:
    """Parse production data from supplemental O&G disclosure."""
    production = {
        "production_oil_mbbl_day": None,   # Thousand barrels per day
        "production_gas_mmcf_day": None,   # Million cubic feet per day
        "production_boe_day": None,        # BOE per day (calculated)
        "oil_percentage": None,            # Oil % of total production
    }

    # Strategy 1a: XOM-style structured tables
    # "Oil-equivalent production4,333 3,738 3,737" (kboe/d, most recent year first)
    oe_match = re.search(
        r'Oil[- ]equivalent\s+production\s*([\d,]+)', text, re.IGNORECASE
    )
    if oe_match:
        val = extract_number(oe_match.group(1))
        if val and val > 100:  # kboe/d
            production["production_boe_day"] = val * 1000  # Convert kboe/d to boe/d

    # Strategy 1b: CVX-style "Components of Oil-Equivalent" table
    # "Total Including Affiliates8\n3,338 3,120 1,560 1,497 415 333 8,178 7,744"
    # First number after header = oil-equivalent kboe/d for most recent year
    if production["production_boe_day"] is None:
        total_incl_match = re.search(
            r'Total\s+Including\s+Affiliates\s*\d*\s*\n\s*([\d,]+)',
            text, re.IGNORECASE,
        )
        if total_incl_match:
            val = extract_number(total_incl_match.group(1))
            if val and val > 100:  # kboe/d
                production["production_boe_day"] = val * 1000

    # Strategy 1c: Narrative "X.X million barrels per day" / "X.X million barrels of oil-equivalent per day"
    if production["production_boe_day"] is None:
        narrative_match = re.search(
            r'oil[- ]equivalent\s+production\s+of\s+([\d.]+)\s+million\s+barrels\s+per\s+day',
            text, re.IGNORECASE,
        )
        if narrative_match:
            val = extract_number(narrative_match.group(1))
            if val and 0.5 < val < 20:  # million bbl/d
                production["production_boe_day"] = val * 1_000_000

    # "Total liquids production2,987 ..." (kbbl/d) — XOM-style
    liquids_match = re.search(
        r'Total\s+liquids\s+production\s*([\d,]+)', text, re.IGNORECASE
    )
    if liquids_match:
        val = extract_number(liquids_match.group(1))
        if val and val > 50:
            production["production_oil_mbbl_day"] = val  # Already in kbbl/d

    # "Total natural gas production available for sale8,078 ..." (mmcf/d)
    gas_match = re.search(
        r'Total\s+natural\s+gas\s+production\s+available\s+for\s+sale\s*([\d,]+)',
        text, re.IGNORECASE,
    )
    if gas_match:
        val = extract_number(gas_match.group(1))
        if val and val > 100:
            production["production_gas_mmcf_day"] = val

    # CVX-style: extract liquids (crude oil + NGL) from Components table
    # The table has columns: OE, Crude, NGL, Gas(MBD), Gas(MMCFD)
    # "Total Including Affiliates8\n3,338 3,120 1,560 1,497 415 333 8,178 7,744"
    # crude_2024=1,560, ngl_2024=415 → liquids = 1,975 kbbl/d
    if production["production_oil_mbbl_day"] is None:
        total_incl_match = re.search(
            r'Total\s+Including\s+Affiliates\s*\d*\s*\n\s*([\d,\s]+)',
            text, re.IGNORECASE,
        )
        if total_incl_match:
            numbers = re.findall(r'[\d,]+', total_incl_match.group(1))
            if len(numbers) >= 5:
                # Format: OE_2024, OE_2023, Crude_2024, Crude_2023, NGL_2024, NGL_2023, Gas_2024, Gas_2023
                crude_val = extract_number(numbers[2])
                ngl_val = extract_number(numbers[4]) if len(numbers) > 4 else 0
                if crude_val and crude_val > 50:
                    production["production_oil_mbbl_day"] = crude_val + (ngl_val or 0)
                if len(numbers) >= 7:
                    gas_val = extract_number(numbers[6])
                    if gas_val and gas_val > 100:
                        production["production_gas_mmcf_day"] = gas_val

    # Calculate oil % from liquids / oil-equivalent if both available
    if production["production_boe_day"] and production["production_oil_mbbl_day"]:
        liquids_boe = production["production_oil_mbbl_day"] * 1000
        production["oil_percentage"] = round(liquids_boe / production["production_boe_day"], 2)

    # Strategy 2: Regex patterns for prose-style disclosures (fallback)
    if production["production_boe_day"] is None:
        text_lower = text.lower()

        oil_patterns = [
            r"(?:oil|crude)\s+(?:production|output)[^0-9]*?(\d[\d,]*(?:\.\d+)?)\s*(?:mbbl|thousand\s+barrels)",
            r"(\d[\d,]*(?:\.\d+)?)\s*(?:mbbl|mbbls)/d",
        ]
        gas_patterns = [
            r"(?:gas|natural\s+gas)\s+(?:production|output)[^0-9]*?(\d[\d,]*(?:\.\d+)?)\s*(?:mmcf|million\s+cubic)",
            r"(\d[\d,]*(?:\.\d+)?)\s*mmcf/d",
        ]

        for pattern in oil_patterns:
            match = re.search(pattern, text_lower)
            if match:
                val = extract_number(match.group(1))
                if val and val > 0:
                    production["production_oil_mbbl_day"] = val
                    break

        for pattern in gas_patterns:
            match = re.search(pattern, text_lower)
            if match:
                val = extract_number(match.group(1))
                if val and val > 0:
                    production["production_gas_mmcf_day"] = val
                    break

        # Calculate BOE/day from components
        oil = (production["production_oil_mbbl_day"] or 0) * 1000
        gas = (production["production_gas_mmcf_day"] or 0) * 1000 / 6
        if oil > 0 or gas > 0:
            production["production_boe_day"] = oil + gas

    return production


def parse_cost_data(text: str) -> dict:
    """Parse cost data (lifting cost, finding cost) from O&G disclosure."""
    costs = {
        "lifting_cost_per_boe": None,    # $/BOE operating cost
        "finding_cost_per_boe": None,    # $/BOE F&D cost
    }

    # Strategy 1: XOM-style structured table
    # "Average production costs, per oil-equivalent barrel - total10.94 16.20 ... 10.53"
    # The "Total" section (not Consolidated/Equity sub-section) has the company-wide figure.
    # We want the last number on the LAST matching line (the "Total" section comes last).
    cost_matches = list(re.finditer(
        r'Average\s+production\s+costs,\s+per\s+oil-equivalent\s+barrel\s*-\s*total([\d\s,.]+)',
        text, re.IGNORECASE,
    ))
    if cost_matches:
        # Take the last match (the "Total" section, not Consolidated or Equity sub-sections)
        line = cost_matches[-1].group(1)
        numbers = re.findall(r'[\d]+\.[\d]+', line)
        if numbers:
            # Last number is the "Total" column
            val = extract_number(numbers[-1])
            if val and 0 < val < 100:
                costs["lifting_cost_per_boe"] = val

    # Strategy 1b: CVX-style "production cost per oil-equivalent barrel" in narrative
    # Match explicit "production cost" mentions, NOT crude oil prices
    if costs["lifting_cost_per_boe"] is None:
        cost_patterns = [
            # "production cost per oil-equivalent barrel" followed by values
            r'production\s+cost\s+per\s+oil[- ]equivalent\s+barrel[^\d]*([\d]+\.[\d]+)',
            # "$X.XX per BOE" near "lifting" or "production cost"
            r'(?:lifting|production)\s+cost[^$]{0,30}\$([\d]+\.[\d]+)\s*(?:per\s+)?(?:boe|oil[- ]equivalent)',
            r'\$([\d]+\.[\d]+)\s*(?:per\s+)?(?:boe|oil[- ]equivalent)[^\.]{0,30}(?:lifting|production\s+cost)',
        ]
        for pattern in cost_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = extract_number(match.group(1))
                if val and 0 < val < 50:  # Tighter bound to avoid matching crude prices
                    costs["lifting_cost_per_boe"] = val
                    break

    # F&D cost (rarely in 10-K, usually from investor presentations)
    fd_patterns = [
        r"(?:finding|f&d|finding\s+and\s+development)\s+cost[^$]*\$(\d+(?:\.\d+)?)",
        r"\$(\d+(?:\.\d+)?)\s*(?:per\s+)?boe.*?(?:finding|f&d)",
    ]
    text_lower = text.lower()
    for pattern in fd_patterns:
        match = re.search(pattern, text_lower)
        if match:
            val = extract_number(match.group(1))
            if val and 0 < val < 100:
                costs["finding_cost_per_boe"] = val
                break

    return costs


def fetch_og_data(ticker: str) -> dict:
    """
    Fetch O&G reserve and production data from most recent 10-K filing.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dictionary with O&G data fields
    """
    # Set identity for SEC EDGAR (required)
    edgar_id = os.environ.get("SEC_EDGAR_IDENTITY", "")
    if not edgar_id:
        raise ValueError(
            "SEC_EDGAR_IDENTITY env var not set. "
            "Set it to 'YourName email@example.com' (see .env.example)."
        )
    set_identity(edgar_id)

    print(f"Fetching SEC filings for {ticker}...")
    company = Company(ticker)

    # Get most recent 10-K filing
    filings = company.get_filings(form="10-K")
    if not filings:
        raise ValueError(f"No 10-K filings found for {ticker}")

    latest_10k = filings[0]
    print(f"Found 10-K filed {latest_10k.filing_date}")

    # Get the filing document
    filing = latest_10k.obj()

    # Extract text from the filing - combine multiple sources
    text_parts = []

    # Try to get Item 1 - Business (often contains reserve summary for CVX-style filings)
    try:
        if hasattr(filing, "__getitem__"):
            item1 = filing["Item 1"]
            if item1:
                item1_text = str(item1)
                text_parts.append(item1_text)
                print(f"Extracted Item 1 - Business ({len(item1_text)} chars)")
    except Exception as e:
        print(f"Warning: Could not extract Item 1: {e}", file=sys.stderr)

    # Try to get Item 2 - Properties (contains O&G reserve info for XOM-style)
    try:
        if hasattr(filing, "__getitem__"):
            item2 = filing["Item 2"]
            if item2:
                item2_text = str(item2)
                text_parts.append(item2_text)
                print(f"Extracted Item 2 - Properties ({len(item2_text)} chars)")
    except Exception as e:
        print(f"Warning: Could not extract Item 2: {e}", file=sys.stderr)

    # Try to get Item 8 - Financial Statements (contains supplemental O&G tables)
    try:
        if hasattr(filing, "__getitem__"):
            item8 = filing["Item 8"]
            if item8:
                item8_text = str(item8)
                # Only include relevant portions - search for O&G sections
                if "oil" in item8_text.lower() and "gas" in item8_text.lower():
                    text_parts.append(item8_text)
                    print(f"Extracted Item 8 - Financial Statements ({len(item8_text)} chars)")
    except Exception as e:
        print(f"Warning: Could not extract Item 8: {e}", file=sys.stderr)

    text = "\n\n".join(text_parts)

    # If we didn't get much, try other methods
    if len(text) < 1000:
        try:
            # Try to get full text
            if hasattr(filing, "text"):
                full_text = filing.text
            else:
                full_text = str(filing)

            # Look for supplemental O&G disclosure section
            og_section_patterns = [
                r"supplemental\s+(?:information\s+on\s+)?oil\s+and\s+gas",
                r"oil\s+and\s+gas\s+(?:producing\s+)?activities",
                r"reserve\s+quantity\s+information",
                r"disclosure\s+of\s+reserves",
            ]
            for pattern in og_section_patterns:
                match = re.search(pattern, full_text.lower())
                if match:
                    start = max(0, match.start() - 500)
                    end = min(len(full_text), match.end() + 20000)
                    text = full_text[start:end]
                    print(f"Found O&G section via pattern match ({len(text)} chars)")
                    break

            if not text:
                text = full_text[:100000]
                print(f"Using full text fallback ({len(text)} chars)")

        except Exception as e:
            print(f"Warning: Could not extract full text: {e}", file=sys.stderr)

    if not text:
        raise ValueError("Could not extract O&G information from 10-K")

    # Parse the extracted text
    reserves = parse_reserve_table(text)
    production = parse_production_data(text)
    costs = parse_cost_data(text)

    # Combine results
    og_data = {
        "ticker": ticker,
        "source": "SEC 10-K",
        "filing_date": str(latest_10k.filing_date),
        **reserves,
        **production,
        **costs,
    }

    return og_data


def main():
    parser = argparse.ArgumentParser(
        description="Fetch O&G reserve data from SEC 10-K filings"
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g., XOM)")
    parser.add_argument("--output", default="/tmp", help="Output directory for JSON")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        og_data = fetch_og_data(ticker)

        # Write to JSON
        output_file = output_dir / f"og_reserves_{ticker}.json"
        with open(output_file, "w") as f:
            json.dump(og_data, f, indent=2)

        print(f"\nO&G data written to: {output_file}")
        print(f"\nExtracted data:")
        for key, value in og_data.items():
            if value is not None:
                print(f"  {key}: {value}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
