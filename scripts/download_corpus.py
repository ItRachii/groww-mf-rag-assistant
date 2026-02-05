"""
Data Acquisition Script for Groww Mutual Fund RAG System
Milestone 1: Download and verify all corpus documents

Usage:
    python scripts/download_corpus.py
"""

import os
import sys
import json
import hashlib
import requests
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, List, Any

# Configuration
BASE_DIR = Path(__file__).parent.parent
RAW_DATA_DIR = BASE_DIR / "data" / "raw"
MANIFEST_PATH = RAW_DATA_DIR / "corpus_manifest.json"

# Request settings
TIMEOUT = 30
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Corpus definition - 25 URLs from corpus.md
CORPUS = [
    # Product Pages (1-5)
    {"id": 1, "name": "HDFC_LargeCap_ProductPage", "url": "https://www.hdfcfund.com/explore/mutual-funds/hdfc-large-cap-fund/direct", "type": "html", "category": "Product Page", "scheme": "HDFC Large Cap Fund"},
    {"id": 2, "name": "HDFC_FlexiCap_ProductPage", "url": "https://www.hdfcfund.com/explore/mutual-funds/hdfc-flexi-cap-fund/direct", "type": "html", "category": "Product Page", "scheme": "HDFC Flexi Cap Fund"},
    {"id": 3, "name": "HDFC_ELSS_ProductPage", "url": "https://www.hdfcfund.com/explore/mutual-funds/hdfc-elss-tax-saver/direct", "type": "html", "category": "Product Page", "scheme": "HDFC Tax Saver (ELSS)"},
    {"id": 4, "name": "HDFC_BalancedAdvantage_ProductPage", "url": "https://www.hdfcfund.com/explore/mutual-funds/hdfc-balanced-advantage-fund/direct", "type": "html", "category": "Product Page", "scheme": "HDFC Balanced Advantage Fund"},
    {"id": 5, "name": "HDFC_Liquid_ProductPage", "url": "https://www.hdfcfund.com/explore/mutual-funds/hdfc-liquid-fund/direct", "type": "html", "category": "Product Page", "scheme": "HDFC Liquid Fund"},
    
    # SID Landing Page (6-10 - same page, but we'll download once)
    {"id": 6, "name": "HDFC_SID_LandingPage", "url": "https://www.hdfcfund.com/investor-services/fund-documents/sid", "type": "html", "category": "SID", "scheme": "All Schemes"},
    
    # KIM PDFs - Scheme-specific (7-11) - November 2025 versions
    {"id": 7, "name": "HDFC_LargeCap_KIM", "url": "https://files.hdfcfund.com/s3fs-public/KIM/2025-11/KIM%20-%20HDFC%20Large%20Cap%20Fund%20dated%20November%2021%2C%202025_0.pdf", "type": "pdf", "category": "KIM", "scheme": "HDFC Large Cap Fund"},
    {"id": 8, "name": "HDFC_FlexiCap_KIM", "url": "https://files.hdfcfund.com/s3fs-public/KIM/2025-11/KIM%20-%20HDFC%20Flexi%20Cap%20Fund%20dated%20November%2021%2C%202025_1.pdf", "type": "pdf", "category": "KIM", "scheme": "HDFC Flexi Cap Fund"},
    {"id": 9, "name": "HDFC_ELSS_KIM", "url": "https://files.hdfcfund.com/s3fs-public/KIM/2025-11/KIM%20-%20HDFC%20ELSS%20Tax%20Saver%20dated%20November%2021%2C%202025_0.pdf", "type": "pdf", "category": "KIM", "scheme": "HDFC Tax Saver (ELSS)"},
    {"id": 10, "name": "HDFC_BalancedAdvantage_KIM", "url": "https://files.hdfcfund.com/s3fs-public/KIM/2025-11/KIM%20-%20HDFC%20Balanced%20Advantage%20Fund%20dated%20November%2021%2C%202025_0.pdf", "type": "pdf", "category": "KIM", "scheme": "HDFC Balanced Advantage Fund"},
    {"id": 11, "name": "HDFC_Liquid_KIM", "url": "https://files.hdfcfund.com/s3fs-public/KIM/2025-11/KIM%20-%20HDFC%20Liquid%20Fund%20dated%20November%2021%2C%202025.pdf", "type": "pdf", "category": "KIM", "scheme": "HDFC Liquid Fund"},
    
    # Scheme Summary (12)
    {"id": 12, "name": "HDFC_SchemeSummary", "url": "https://www.hdfcfund.com/investor-services/fund-documents/scheme-summary", "type": "html", "category": "Scheme Summary", "scheme": "All Schemes"},
    
    # Factsheets (13)
    {"id": 13, "name": "HDFC_Factsheets", "url": "https://www.hdfcfund.com/investor-services/factsheets", "type": "html", "category": "Factsheet", "scheme": "All Schemes"},
    
    # Leaflets (14)
    {"id": 14, "name": "HDFC_Leaflets", "url": "https://www.hdfcfund.com/investor-services/fund-literature/leaflets", "type": "html", "category": "Leaflet", "scheme": "All Schemes"},
    
    # Presentations (15)
    {"id": 15, "name": "HDFC_Presentations", "url": "https://www.hdfcfund.com/investor-services/fund-literature/presentation", "type": "html", "category": "Presentation", "scheme": "All Schemes"},
    
    # SAI (16) - Updated URL path
    {"id": 16, "name": "HDFC_SAI", "url": "https://www.hdfcfund.com/investor-services/fund-documents/sai", "type": "html", "category": "SAI", "scheme": "All Schemes"},
    
    # AMFI Data (17-20) - Updated URLs
    {"id": 17, "name": "AMFI_NAV", "url": "https://www.amfiindia.com/spages/NAVAll.txt", "type": "txt", "category": "AMFI NAV", "scheme": "All Schemes"},
    {"id": 18, "name": "AMFI_SchemeMaster", "url": "https://portal.amfiindia.com/DownloadSchemeData_Po.aspx?mession=1", "type": "html", "category": "AMFI Data", "scheme": "All Schemes"},
    {"id": 19, "name": "AMFI_ResearchInfo", "url": "https://www.amfiindia.com/research-information", "type": "html", "category": "AMFI Data", "scheme": "All Schemes"},
    {"id": 20, "name": "AMFI_IndustryData", "url": "https://www.amfiindia.com/research-information/amfi-data", "type": "html", "category": "AMFI Data", "scheme": "All Schemes"},
    
    # SEBI Circulars (21-25) - Updated URLs with correct circular IDs
    {"id": 21, "name": "SEBI_Categorization", "url": "https://www.sebi.gov.in/legal/circulars/oct-2017/categorization-and-rationalization-of-mutual-fund-schemes_36199.html", "type": "html", "category": "SEBI Circular", "scheme": "All Categories"},
    {"id": 22, "name": "SEBI_TER", "url": "https://www.sebi.gov.in/legal/circulars/sep-2018/circular-on-total-expense-ratio-and-performance-disclosure-for-mutual-funds_40506.html", "type": "html", "category": "SEBI Circular", "scheme": "All Categories"},
    {"id": 23, "name": "SEBI_Riskometer", "url": "https://www.sebi.gov.in/legal/circulars/oct-2020/circular-on-product-labelling-in-mutual-funds-risk-o-meter_47778.html", "type": "html", "category": "SEBI Circular", "scheme": "All Categories"},
    {"id": 24, "name": "SEBI_ELSS", "url": "https://www.sebi.gov.in/legal/circulars/may-2022/introduction-of-passively-managed-elss-equity-linked-savings-scheme_59101.html", "type": "html", "category": "SEBI Circular", "scheme": "ELSS"},
    {"id": 25, "name": "SEBI_InvestorGrievance", "url": "https://www.sebi.gov.in/legal/circulars/dec-2020/investor-grievance-redressal-mechanism_48446.html", "type": "html", "category": "SEBI Circular", "scheme": "All Categories"},
]


def get_file_extension(content_type: str, url: str, doc_type: str) -> str:
    """Determine file extension based on content type and URL."""
    if "pdf" in content_type.lower() or url.endswith(".pdf"):
        return ".pdf"
    elif "text/plain" in content_type.lower() or url.endswith(".txt"):
        return ".txt"
    elif doc_type == "txt":
        return ".txt"
    else:
        return ".html"


def calculate_checksum(content: bytes) -> str:
    """Calculate SHA-256 checksum of content."""
    return hashlib.sha256(content).hexdigest()


def download_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Download a single document and return metadata."""
    result = {
        "id": doc["id"],
        "name": doc["name"],
        "url": doc["url"],
        "category": doc["category"],
        "scheme": doc["scheme"],
        "status": "pending",
        "http_status": None,
        "file_path": None,
        "file_size_bytes": 0,
        "checksum": None,
        "content_type": None,
        "download_timestamp": None,
        "error": None,
        "warning": None,
    }
    
    try:
        print(f"  [{doc['id']:02d}] Downloading: {doc['name']}...")
        response = requests.get(doc["url"], headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        
        result["http_status"] = response.status_code
        result["content_type"] = response.headers.get("Content-Type", "unknown")
        result["download_timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        if response.status_code == 200:
            # Determine file extension
            ext = get_file_extension(result["content_type"], doc["url"], doc.get("type", "html"))
            filename = f"{doc['name']}{ext}"
            filepath = RAW_DATA_DIR / filename
            
            # Save content
            content = response.content
            with open(filepath, "wb") as f:
                f.write(content)
            
            result["file_path"] = str(filepath.relative_to(BASE_DIR))
            result["file_size_bytes"] = len(content)
            result["checksum"] = calculate_checksum(content)
            result["status"] = "success"
            
            # Warn if file is suspiciously small
            if ext == ".pdf" and len(content) < 10240:  # < 10KB
                result["warning"] = f"PDF file is only {len(content)} bytes - may be corrupted or failed download"
            elif ext == ".html" and len(content) < 1024:  # < 1KB
                result["warning"] = f"HTML file is only {len(content)} bytes - may be empty or error page"
            
            print(f"       [OK] Success: {filename} ({len(content):,} bytes)")
            
        else:
            result["status"] = "failed"
            result["error"] = f"HTTP {response.status_code}: {response.reason}"
            print(f"       [FAIL] HTTP {response.status_code}")
            
    except requests.exceptions.Timeout:
        result["status"] = "failed"
        result["error"] = "Request timeout"
        print(f"       [FAIL] Timeout")
        
    except requests.exceptions.ConnectionError as e:
        result["status"] = "failed"
        result["error"] = f"Connection error: {str(e)}"
        print(f"       [FAIL] Connection error")
        
    except Exception as e:
        result["status"] = "failed"
        result["error"] = f"Unexpected error: {str(e)}"
        print(f"       [FAIL] {str(e)}")
    
    return result


def validate_corpus(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the downloaded corpus and generate summary."""
    documents = manifest["documents"]
    
    validation = {
        "total_documents": len(documents),
        "successful_downloads": sum(1 for d in documents if d["status"] == "success"),
        "failed_downloads": sum(1 for d in documents if d["status"] == "failed"),
        "total_size_bytes": sum(d["file_size_bytes"] for d in documents),
        "warnings": [d for d in documents if d.get("warning")],
        "errors": [d for d in documents if d.get("error")],
        "all_200_ok": all(d["http_status"] == 200 for d in documents if d["http_status"]),
    }
    
    return validation


def main():
    """Main entry point for corpus download."""
    print("=" * 70)
    print("Groww Mutual Fund RAG - Corpus Download Script")
    print("=" * 70)
    print(f"\nTarget directory: {RAW_DATA_DIR}")
    print(f"Documents to download: {len(CORPUS)}")
    print("-" * 70)
    
    # Ensure output directory exists
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Download all documents
    results = []
    for doc in CORPUS:
        result = download_document(doc)
        results.append(result)
    
    # Create manifest
    manifest = {
        "corpus_name": "Groww Mutual Fund FAQ - HDFC AMC",
        "version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_file": "corpus.md",
        "documents": results,
    }
    
    # Add validation summary
    manifest["validation"] = validate_corpus(manifest)
    
    # Save manifest
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    # Print summary
    v = manifest["validation"]
    print("\n" + "=" * 70)
    print("DOWNLOAD SUMMARY")
    print("=" * 70)
    print(f"Total documents:      {v['total_documents']}")
    print(f"Successful downloads: {v['successful_downloads']}")
    print(f"Failed downloads:     {v['failed_downloads']}")
    print(f"Total size:           {v['total_size_bytes']:,} bytes ({v['total_size_bytes'] / 1024 / 1024:.2f} MB)")
    print(f"All 200 OK:           {'[YES]' if v['all_200_ok'] else '[NO]'}")
    
    if v["warnings"]:
        print(f"\n[WARN] WARNINGS ({len(v['warnings'])}):")
        for w in v["warnings"]:
            print(f"   - [{w['id']:02d}] {w['name']}: {w['warning']}")
    
    if v["errors"]:
        print(f"\n[ERROR] ERRORS ({len(v['errors'])}):")
        for e in v["errors"]:
            print(f"   - [{e['id']:02d}] {e['name']}: {e['error']}")
    
    print(f"\n[INFO] Manifest saved to: {MANIFEST_PATH}")
    print("=" * 70)
    
    # Return exit code based on success
    return 0 if v["failed_downloads"] == 0 else 1


if __name__ == "__main__":
    exit(main())
