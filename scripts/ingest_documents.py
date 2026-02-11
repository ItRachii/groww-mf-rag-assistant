"""
Document Ingestion Script for Groww Mutual Fund RAG System
Milestone 2: Parse PDFs, chunk, embed, and store in FAISS

Usage:
    python scripts/ingest_documents.py
"""

import os
import sys
import uuid
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

# PDF parsing
import pymupdf4llm

# Text splitting
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Embeddings
from sentence_transformers import SentenceTransformer

# Vector store
import faiss
import numpy as np

# Local imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.filename_metadata import parse_filename


# Configuration
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
SCHEMES_DIR = DATA_DIR / "raw" / "schemes"
VECTOR_STORE_DIR = DATA_DIR / "vector_store"
PROCESSED_DIR = DATA_DIR / "processed"

# Chunking parameters (from architecture.md)
CHUNK_SIZE = 512  # tokens (~350-400 words)
CHUNK_OVERLAP = 64  # 12.5% overlap

# Embedding model
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024  # BGE-M3 output dimension


def parse_pdf_to_markdown(pdf_path: Path) -> str:
    """
    Parse a PDF file to markdown using PyMuPDF4LLM.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Markdown text content
    """
    try:
        md_text = pymupdf4llm.to_markdown(str(pdf_path))
        return md_text
    except Exception as e:
        print(f"    [ERROR] Failed to parse {pdf_path.name}: {e}")
        return ""


def chunk_document(
    text: str, 
    metadata: Dict[str, Any],
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP
) -> List[Dict[str, Any]]:
    """
    Split document text into chunks with metadata.
    """
    # Use RecursiveCharacterTextSplitter for semantic-aware splitting
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size * 4,  # ~4 chars per token
        chunk_overlap=chunk_overlap * 4,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    
    splits = splitter.split_text(text)
    
    chunks = []
    for i, split_text in enumerate(splits):
        chunk = {
            "chunk_id": str(uuid.uuid4()),
            "text": split_text,
            "chunk_index": i,
            "total_chunks": len(splits),
            **metadata
        }
        chunks.append(chunk)
    
    return chunks


def get_scheme_name_from_folder(folder_name: str) -> str:
    """Convert folder name to display scheme name."""
    mapping = {
        "HDFC_Large_Cap_Fund": "HDFC Large Cap Fund",
        "HDFC_Flexi_Cap_Fund": "HDFC Flexi Cap Fund",
        "HDFC_ELSS_Tax_Saver": "HDFC Tax Saver (ELSS)",
        "HDFC_Balanced_Advantage_Fund": "HDFC Balanced Advantage Fund",
        "HDFC_Liquid_Fund": "HDFC Liquid Fund",
    }
    return mapping.get(folder_name, folder_name)


def get_amfi_code(scheme_name: str) -> str:
    """Get AMFI code for a scheme."""
    mapping = {
        "HDFC Large Cap Fund": "100032",
        "HDFC Flexi Cap Fund": "100394",
        "HDFC Tax Saver (ELSS)": "100186",
        "HDFC Balanced Advantage Fund": "100171",
        "HDFC Liquid Fund": "100027",
    }
    return mapping.get(scheme_name, "unknown")


def process_scheme_folder(
    folder_path: Path, 
    scheme_display_name: str
) -> List[Dict[str, Any]]:
    """
    Process all PDF files in a scheme folder.
    """
    all_chunks = []
    pdf_files = list(folder_path.glob("*.pdf"))  # Case-insensitive on Windows
    
    print(f"\n  Processing {len(pdf_files)} PDFs in {folder_path.name}...")
    
    for pdf_path in pdf_files:
        print(f"    - {pdf_path.name}")
        
        # Extract metadata from filename
        file_meta = parse_filename(pdf_path.name)
        
        # Parse PDF to markdown
        md_text = parse_pdf_to_markdown(pdf_path)
        if not md_text:
            continue
        
        # Build base metadata
        base_metadata = {
            "amc_name": "HDFC Asset Management Company",
            "scheme_name": scheme_display_name,
            "scheme_code": get_amfi_code(scheme_display_name),
            "plan_type": "Direct",
            "document_type": file_meta.get("document_type") or "Unknown",
            "document_date": file_meta.get("document_date"),
            "source_file": pdf_path.name,
            "extraction_date": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        
        # Chunk the document
        chunks = chunk_document(md_text, base_metadata)
        all_chunks.extend(chunks)
        
        print(f"      -> {len(chunks)} chunks created")
    
    return all_chunks


def create_embeddings(
    chunks: List[Dict[str, Any]], 
    model: SentenceTransformer
) -> np.ndarray:
    """
    Create embeddings for all chunks.
    """
    texts = [chunk["text"] for chunk in chunks]
    
    # Add instruction prefix for retrieval (BGE-M3 recommendation)
    prefixed_texts = [
        f"Represent this financial document for retrieval: {text}" 
        for text in texts
    ]
    
    print(f"\n  Embedding {len(texts)} chunks...")
    embeddings = model.encode(
        prefixed_texts, 
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True
    )
    
    return embeddings.astype(np.float32)


def create_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    """
    Create a FAISS index for inner product (cosine similarity on normalized vectors).
    """
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)  # Inner product for cosine similarity
    index.add(embeddings)
    return index


def save_vector_store(
    index: faiss.IndexFlatIP,
    chunks: List[Dict[str, Any]],
    output_dir: Path
) -> None:
    """
    Save FAISS index and chunk metadata to disk.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save FAISS index
    index_path = output_dir / "faiss_index.bin"
    faiss.write_index(index, str(index_path))
    print(f"    [OK] Saved FAISS index to {index_path}")
    
    # Save chunks metadata (for retrieval)
    chunks_path = output_dir / "chunks_metadata.pkl"
    with open(chunks_path, "wb") as f:
        pickle.dump(chunks, f)
    print(f"    [OK] Saved chunks metadata to {chunks_path}")
    
    # Also save as JSON for inspection
    chunks_json_path = output_dir / "chunks_metadata.json"
    with open(chunks_json_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    print(f"    [OK] Saved chunks JSON to {chunks_json_path}")


def main():
    """Main entry point for document ingestion."""
    print("=" * 70)
    print("Groww Mutual Fund RAG - Document Ingestion Pipeline")
    print("=" * 70)
    
    # Ensure directories exist
    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize embedding model
    print("\n[1/4] Loading embedding model (BGE-M3)...")
    print("      This may take a few minutes on first run...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print("      [OK] Model loaded")
    
    # Process all scheme folders
    print("\n[2/4] Processing PDF documents...")
    all_chunks = []
    
    scheme_folders = [
        f for f in SCHEMES_DIR.iterdir() 
        if f.is_dir() and f.name != "Common"
    ]
    
    for folder in scheme_folders:
        scheme_name = get_scheme_name_from_folder(folder.name)
        chunks = process_scheme_folder(folder, scheme_name)
        all_chunks.extend(chunks)
    
    print(f"\n  Total chunks created: {len(all_chunks)}")
    
    if not all_chunks:
        print("\n[ERROR] No chunks were created. Check PDF files.")
        return 1
    
    # Create embeddings
    print("\n[3/4] Creating embeddings...")
    embeddings = create_embeddings(all_chunks, model)
    print(f"      Embeddings shape: {embeddings.shape}")
    
    # Create and save FAISS index
    print("\n[4/4] Creating FAISS index and saving...")
    index = create_faiss_index(embeddings)
    save_vector_store(index, all_chunks, VECTOR_STORE_DIR)
    
    # Save processing summary
    summary = {
        "processed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total_chunks": len(all_chunks),
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "vector_store": "FAISS",
        "schemes": list(set(c["scheme_name"] for c in all_chunks)),
        "document_types": list(set(c["document_type"] for c in all_chunks)),
    }
    
    summary_path = PROCESSED_DIR / "ingestion_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    # Print summary
    print("\n" + "=" * 70)
    print("INGESTION COMPLETE")
    print("=" * 70)
    print(f"Total chunks:      {len(all_chunks)}")
    print(f"Embedding dim:     {embeddings.shape[1]}")
    print(f"Vector store:      {VECTOR_STORE_DIR}")
    print(f"Index file:        faiss_index.bin")
    print(f"Metadata file:     chunks_metadata.pkl")
    print(f"Summary saved:     {summary_path}")
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    exit(main())
