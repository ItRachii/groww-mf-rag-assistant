"""
Filename Metadata Extractor for Groww Mutual Fund RAG System

Parses PDF filenames to extract scheme_name, document_type, and document_date
for use in chunk metadata during ingestion.

Filename patterns supported:
    <scheme_name>_<document_type>_<date>.PDF  (with date)
    <scheme_name>_<document_type>.PDF         (without date)

Usage:
    python scripts/filename_metadata.py                    # Run tests
    python scripts/filename_metadata.py path/to/file.pdf   # Parse single file
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List

# Known document types - order matters (longer matches first)
DOCUMENT_TYPES = [
    "SCHEME_SUMMARY_DOCUMENT",  # Must be first (longest match)
    "Fund_Facts",
    "Presentation",
    "Factsheet",
    "Leaflet",
    "SID",
    "KIM",
    "SAI",
]

# Month name to number mapping
MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def normalize_date(date_str: str) -> Optional[str]:
    """
    Convert date formats to ISO 8601 (YYYY-MM-DD).
    
    Supports:
        - "Jan_2026" -> "2026-01-01"
        - "21_Nov_2025" -> "2025-11-21"
        - "Nov_2025" -> "2025-11-01"
    
    Returns None if parsing fails.
    """
    if not date_str:
        return None
    
    # Clean and normalize input
    date_str = date_str.strip().replace("-", "_")
    parts = date_str.split("_")
    
    try:
        if len(parts) == 2:
            # Format: Month_Year (e.g., "Jan_2026")
            month_str, year_str = parts
            month = MONTH_MAP.get(month_str.lower())
            if month and year_str.isdigit():
                year = int(year_str)
                return f"{year:04d}-{month:02d}-01"
        
        elif len(parts) == 3:
            # Format: Day_Month_Year (e.g., "21_Nov_2025")
            day_str, month_str, year_str = parts
            month = MONTH_MAP.get(month_str.lower())
            if day_str.isdigit() and month and year_str.isdigit():
                day = int(day_str)
                year = int(year_str)
                # Validate date
                datetime(year, month, day)
                return f"{year:04d}-{month:02d}-{day:02d}"
    except (ValueError, KeyError):
        pass
    
    return None


def parse_filename(filename: str) -> Dict[str, Optional[str]]:
    """
    Parse a PDF filename to extract metadata.
    
    Args:
        filename: The PDF filename (with or without path)
    
    Returns:
        Dictionary with keys:
            - scheme_name: e.g., "HDFC_BalancedAdvantage"
            - document_type: e.g., "Fund_Facts", "SID", "KIM"
            - document_date: ISO 8601 date string or None
            - raw_date: Original date string from filename or None
    """
    result = {
        "scheme_name": None,
        "document_type": None,
        "document_date": None,
        "raw_date": None,
    }
    
    # Get just the filename without path and extension
    basename = Path(filename).stem  # Removes .pdf/.PDF extension
    
    if not basename:
        return result
    
    # Find the document type in the filename
    doc_type_found = None
    doc_type_pos = -1
    
    for doc_type in DOCUMENT_TYPES:
        # Case-insensitive search
        pattern = re.compile(re.escape(doc_type), re.IGNORECASE)
        match = pattern.search(basename)
        if match:
            # Keep the match that appears latest (to avoid matching within scheme name)
            if match.start() > doc_type_pos:
                doc_type_found = doc_type
                doc_type_pos = match.start()
    
    if doc_type_found is None:
        # No known document type found - try to infer from structure
        # Assume last part before date (if any) is document type
        result["scheme_name"] = basename
        return result
    
    # Extract scheme name (everything before the document type)
    scheme_name = basename[:doc_type_pos].rstrip("_")
    result["scheme_name"] = scheme_name if scheme_name else None
    result["document_type"] = doc_type_found
    
    # Extract date (everything after document type)
    after_doc_type = basename[doc_type_pos + len(doc_type_found):]
    after_doc_type = after_doc_type.lstrip("_")
    
    if after_doc_type:
        result["raw_date"] = after_doc_type
        result["document_date"] = normalize_date(after_doc_type)
    
    return result


def scan_directory(directory: str) -> List[Dict[str, Optional[str]]]:
    """
    Scan a directory for PDF files and parse their metadata.
    
    Args:
        directory: Path to directory containing PDF files
    
    Returns:
        List of parsed metadata dictionaries with 'filename' added
    """
    results = []
    dir_path = Path(directory)
    
    if not dir_path.is_dir():
        return results
    
    for pdf_file in dir_path.glob("*.pdf"):
        metadata = parse_filename(pdf_file.name)
        metadata["filename"] = pdf_file.name
        metadata["filepath"] = str(pdf_file)
        results.append(metadata)
    
    # Also check .PDF extension (case-insensitive handled by glob on Windows)
    for pdf_file in dir_path.glob("*.PDF"):
        if pdf_file.name not in [r["filename"] for r in results]:
            metadata = parse_filename(pdf_file.name)
            metadata["filename"] = pdf_file.name
            metadata["filepath"] = str(pdf_file)
            results.append(metadata)
    
    return results


def run_tests():
    """Run built-in test cases."""
    print("=" * 70)
    print("Filename Metadata Extractor - Test Suite")
    print("=" * 70)
    
    test_cases = [
        # (filename, expected_scheme, expected_type, expected_date)
        ("HDFC_BalancedAdvantage_Fund_Facts_Jan_2026.pdf", 
         "HDFC_BalancedAdvantage", "Fund_Facts", "2026-01-01"),
        
        ("HDFC_ELSS_Tax_Saver_SID_21_Nov_2025.pdf", 
         "HDFC_ELSS_Tax_Saver", "SID", "2025-11-21"),
        
        ("HDFC_ELSS_Tax_Saver_KIM_21_Nov_2025.pdf", 
         "HDFC_ELSS_Tax_Saver", "KIM", "2025-11-21"),
        
        ("HDFC_LargeCapFund_SCHEME_SUMMARY_DOCUMENT.pdf", 
         "HDFC_LargeCapFund", "SCHEME_SUMMARY_DOCUMENT", None),
        
        ("HDFC_Large_Cap_Fund_KIM.pdf", 
         "HDFC_Large_Cap_Fund", "KIM", None),
        
        ("HDFC_BalancedAdvantage_Leaflet_Nov_2025.pdf", 
         "HDFC_BalancedAdvantage", "Leaflet", "2025-11-01"),
        
        ("HDFC_ELSS_Tax_Saver_Presentation_Oct_2025.pdf", 
         "HDFC_ELSS_Tax_Saver", "Presentation", "2025-10-01"),
    ]
    
    passed = 0
    failed = 0
    
    for filename, exp_scheme, exp_type, exp_date in test_cases:
        result = parse_filename(filename)
        
        scheme_ok = result["scheme_name"] == exp_scheme
        type_ok = result["document_type"] == exp_type
        date_ok = result["document_date"] == exp_date
        
        if scheme_ok and type_ok and date_ok:
            print(f"[PASS] {filename}")
            passed += 1
        else:
            print(f"[FAIL] {filename}")
            if not scheme_ok:
                print(f"       scheme: got '{result['scheme_name']}', expected '{exp_scheme}'")
            if not type_ok:
                print(f"       type: got '{result['document_type']}', expected '{exp_type}'")
            if not date_ok:
                print(f"       date: got '{result['document_date']}', expected '{exp_date}'")
            failed += 1
    
    print("-" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    
    return failed == 0


def main():
    """Main entry point."""
    import sys
    
    if len(sys.argv) > 1:
        # Parse file(s) provided as arguments
        for filepath in sys.argv[1:]:
            if os.path.isfile(filepath):
                result = parse_filename(filepath)
                print(f"\nFile: {filepath}")
                print(f"  scheme_name:   {result['scheme_name']}")
                print(f"  document_type: {result['document_type']}")
                print(f"  document_date: {result['document_date']}")
                print(f"  raw_date:      {result['raw_date']}")
            elif os.path.isdir(filepath):
                print(f"\nDirectory: {filepath}")
                results = scan_directory(filepath)
                for r in results:
                    print(f"  {r['filename']}")
                    print(f"    -> {r['scheme_name']} | {r['document_type']} | {r['document_date']}")
    else:
        # Run tests
        success = run_tests()
        exit(0 if success else 1)


if __name__ == "__main__":
    main()
