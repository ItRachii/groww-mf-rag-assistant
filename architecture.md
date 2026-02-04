# Groww Mutual Fund FAQ Chatbot — RAG Architecture Document

> **Version**: 1.0  
> **Date**: 2026-02-04  
> **Status**: Design Phase  

---

## 1. Executive Summary

This document describes a production-grade, facts-only FAQ assistant for Groww that answers factual questions about mutual fund schemes. The system uses Retrieval-Augmented Generation (RAG) to ground all responses in official public sources (AMC/AMFI/SEBI), enforces mandatory citations, and politely refuses investment advice or opinionated queries.

---

## 2. Scope & Constraints

### 2.1 In-Scope

- Factual information about mutual fund schemes (NAV, expense ratio, fund manager, objective, risk category, etc.)
- Scheme-level metadata from official AMC/AMFI/SEBI sources
- Single-citation answers (≤3 sentences)

### 2.2 Out-of-Scope

- Investment advice, return predictions, or portfolio recommendations
- PII ingestion or user-specific data handling
- Comparative analysis or "best fund" queries
- Real-time NAV updates (static snapshots only)

### 2.3 Hard Constraints

| Constraint | Enforcement |
|------------|-------------|
| Public sources only | Whitelisted domains in scraper |
| No PII | No user data stored; stateless queries |
| No advice | Refusal logic in prompt + classifier |
| ≤3 sentences | Hard token limit in generation config |
| Exactly 1 citation | Post-processing validator |
| Auditable | Full logging of query → retrieval → response |

---

## 3. Selected AMC & Schemes

### 3.1 AMC Selection: **HDFC Asset Management Company**

**Rationale**:

- One of India's largest AMCs with comprehensive public documentation
- Well-structured SID/SAI/KIM documents available on official website
- Consistent document formatting aids reliable parsing

### 3.2 Selected Schemes (5 Schemes)

| Scheme Name | Category | Sub-Category | Plan | AMFI Code | Rationale |
|-------------|----------|--------------|------|-----------|-----------|
| HDFC Large Cap Fund | Equity | Large Cap | Direct | 100032 | Blue-chip exposure, stable documentation |
| HDFC Flexi Cap Fund | Equity | Flexi Cap | Direct | 100394 | Multi-cap flexibility, popular scheme |
| HDFC Tax Saver (ELSS) | Equity | ELSS | Direct | 100186 | Tax-saving category, 3-year lock-in rules |
| HDFC Balanced Advantage Fund | Hybrid | Dynamic | Direct | 100171 | Dynamic asset allocation rules |
| HDFC Liquid Fund | Debt | Liquid | Direct | 100027 | Low-risk category, distinct risk profile |

### 3.3 Document Sources

| Source Type | URL Pattern | Content |
|-------------|-------------|---------|
| Scheme Information Document (SID) | `hdfcfund.com/literature/sid/{scheme}` | Fund objective, risk factors, investment strategy |
| Statement of Additional Info (SAI) | `hdfcfund.com/literature/sai` | AMC details, legal structure |
| Key Information Memorandum (KIM) | `hdfcfund.com/literature/kim/{scheme}` | Condensed scheme facts |
| AMFI NAV Data | `amfiindia.com/spages/NAVAll.txt` | Official NAV snapshots |
| SEBI Scheme Categories | `sebi.gov.in/legal/circulars` | Category definitions |

---

## 4. RAG Architecture

### 4.1 High-Level Pipeline

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              INGESTION PIPELINE                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  [PDF/HTML Sources] → [Document Parser] → [Chunker] → [Embedder] → [VectorDB]│
│         ↓                    ↓                ↓            ↓           ↓     │
│   SID/SAI/KIM          PyMuPDF4LLM      Semantic      BGE-M3     ChromaDB    │
│   AMFI Pages           BeautifulSoup    512 tokens               (local)     │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│                              QUERY PIPELINE                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│  [User Query] → [Refusal Check] → [Query Embed] → [Retrieve] → [Rerank]      │
│       ↓              ↓                 ↓             ↓            ↓          │
│   Sanitize      Classifier          BGE-M3      Top-20      CrossEncoder     │
│                 + Keywords                      chunks       → Top-3         │
│                                                                              │
│  [Reranked Chunks] → [LLM Generation] → [Citation Validator] → [Response]    │
│         ↓                   ↓                    ↓                 ↓         │
│    Context +            Mistral 7B         Regex + URL         Factual       │
│    Metadata             (local)            Verification        Answer        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Component Breakdown

#### 4.2.1 Document Ingestion

| Component | Tool | Justification |
|-----------|------|---------------|
| PDF Parser | **PyMuPDF4LLM** | Fast, preserves table structure, outputs clean markdown. Better than PyPDF2 for structured financial docs. |
| HTML Parser | **BeautifulSoup + requests** | Lightweight, no browser dependency. Sufficient for static AMFI pages. |
| Metadata Extractor | Custom Python | Extract: scheme name, AMFI code, document type, publication date, source URL |

**Document Preprocessing**:

- Remove headers/footers (page numbers, disclaimers repeated on every page)
- Normalize whitespace and encoding (UTF-8)
- Extract tables as structured markdown
- Tag each chunk with `source_url`, `document_type`, `scheme_name`, `extraction_date`

**Atomic Table Handling** (Critical for 100% Reliability):

| Rule | Implementation |
|------|----------------|
| **Table Detection** | Regex + PyMuPDF table extraction API to identify all tables |
| **Explicit Tagging** | Each table chunk tagged with `is_table: true`, `table_type: "expense_ratio|risk_meter|nav_history"` |
| **Size Override** | Tables bypass 512-token limit; entire table = 1 chunk (max 2048 tokens) |
| **Boundary Check** | Pre-chunking validator: if table detected and chunk boundary falls mid-table → extend chunk to table end |
| **Fallback** | If table exceeds 2048 tokens → split by logical rows (preserve header in each split) |

#### 4.2.2 Chunking Strategy

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Chunk Size** | 512 tokens | Optimal for BGE-M3 (max 8192, but 512 balances granularity vs context). Financial docs have dense info; smaller chunks = precise retrieval. |
| **Overlap** | 64 tokens (~12.5%) | Preserves context at boundaries. Important for sentences spanning chunk edges. |
| **Chunking Method** | **Semantic Chunking** (LangChain `SemanticChunker`) | Respects paragraph/section boundaries. Falls back to token-based if semantic splitting fails. |
| **Special Handling** | Tables chunked as atomic units | Tables (expense ratios, risk-o-meter) must not be split mid-row. |

**Chunk Metadata Schema**:

```
{
  "chunk_id": "uuid",
  "text": "...",
  "source_url": "https://hdfcfund.com/...",
  "scheme_name": "HDFC Large Cap Fund",
  "amfi_code": "100032",
  "document_type": "SID|SAI|KIM",
  "section_title": "Investment Objective",
  "extraction_date": "2026-02-04",
  "page_number": 12
}
```

#### 4.2.3 Embedding Model

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| **Model** | **BGE-M3** (`BAAI/bge-m3`) | State-of-the-art multilingual embedding. Handles English + Hindi mixed queries. 1024-dim vectors. Apache 2.0 license. |
| **Alternatives Considered** | `sentence-transformers/all-MiniLM-L6-v2` | Smaller (384-dim) but worse on domain-specific financial terms. |
| | OpenAI `text-embedding-3-small` | Better quality but requires API calls, adds latency, vendor lock-in. |
| **Quantization** | FP16 | Balance of quality and memory. ~1.2GB VRAM. |
| **Inference** | Local via `sentence-transformers` | No external API calls. Full data sovereignty. |

**Embedding Pipeline**:

1. Prepend instruction prefix: `"Represent this financial document for retrieval: "`
2. Batch embed (batch size = 32)
3. Normalize to unit vectors (cosine similarity)

#### 4.2.4 Vector Store

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| **Vector Store** | **ChromaDB** (local, persistent) | Open-source, embedded, no infra dependency. Supports metadata filtering. Production-ready with SQLite backend. |
| **Alternatives Considered** | Qdrant | More features but heavier. Overkill for ~5 schemes. |
| | Pinecone | Managed service = vendor lock-in + cost. |
| | FAISS | Fast but no built-in metadata filtering. |
| **Index Type** | HNSW (default in Chroma) | Best recall/speed tradeoff for <100K vectors. |
| **Distance Metric** | Cosine Similarity | Standard for normalized embeddings. |

**Collection Schema**:

```
Collection: "hdfc_mf_faq"
  - Vectors: 1024-dim (BGE-M3)
  - Metadata: scheme_name, document_type, source_url, section_title
  - Persistence: ./chroma_db/
```

#### 4.2.5 Retrieval Strategy

| Stage | Method | Details |
|-------|--------|---------|
| **Stage 0: Confidence Gate** | Cosine similarity threshold | If **all** top-20 scores < 0.4 → immediate refusal: "I don't have this information in my sources." No LLM call. |
| **Stage 1: Dense Retrieval** | Cosine similarity on BGE-M3 embeddings | Retrieve top-20 candidates. Fast approximate search via HNSW. |
| **Stage 2: Metadata Filter** | Filter by `scheme_name` if query mentions specific scheme | Reduces noise from unrelated schemes. |
| **Stage 3: Reranking** | **Cross-Encoder Reranker** (`cross-encoder/ms-marco-MiniLM-L-6-v2`) | Rerank top-20 → top-3. Cross-encoders are more accurate than bi-encoders for final ranking. |
| **Final Output** | Top-3 chunks with metadata | Passed to LLM as context. |

**Retrieval Augmentations**:

- **Query Expansion**: For abbreviations (ELSS → "Equity Linked Savings Scheme")
- **Hybrid Search**: BM25 keyword fallback if dense retrieval returns low-confidence results (score < 0.5)

**Financial Acronym Expansion Map** (Pre-Embedding):

| Acronym | Expansion | Context |
|---------|-----------|---------|
| ELSS | Equity Linked Savings Scheme | Tax-saving mutual fund under 80C |
| NAV | Net Asset Value | Per-unit price of fund |
| SIP | Systematic Investment Plan | Regular monthly investment |
| TER | Total Expense Ratio | Annual fund management cost |
| AUM | Assets Under Management | Total fund corpus |
| SID | Scheme Information Document | Official fund prospectus |
| KIM | Key Information Memorandum | Condensed scheme facts |
| SAI | Statement of Additional Information | AMC-level disclosures |
| NFO | New Fund Offer | Initial fund launch |
| CAGR | Compound Annual Growth Rate | Annualized return metric |
| SWP | Systematic Withdrawal Plan | Regular redemption schedule |
| STP | Systematic Transfer Plan | Fund-to-fund transfers |

**Query Expansion Logic**:

```
1. Tokenize user query
2. For each token, check if it matches an acronym (case-insensitive)
3. If match → append expansion in parentheses: "ELSS" → "ELSS (Equity Linked Savings Scheme)"
4. Embed expanded query for retrieval
```

#### 4.2.6 Answer Generation (LLM)

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| **Model** | **Mistral 7B Instruct v0.3** (via Ollama or llama.cpp) | Best open-source 7B model for instruction following. Runs on consumer GPU (8GB VRAM). Apache 2.0 license. |
| **Alternatives Considered** | GPT-4 Turbo | Superior quality but API cost + data leaves your infra. |
| | Llama 3.1 8B | Comparable but Mistral has tighter instruction adherence. |
| **Quantization** | Q4_K_M (4-bit GGUF) | 4.5GB model size. Minimal quality loss. |
| **Inference** | Ollama (local) | Simple API, easy model management, no external calls. |
| **Temperature** | 0.1 | Near-deterministic for factual consistency. |
| **Max Tokens** | 150 | Enforces ≤3 sentence limit. |

---

## 5. Prompting Strategy for Factual Accuracy

### 5.1 System Prompt (Fixed)

```
You are a factual FAQ assistant for Groww, answering questions about HDFC mutual fund schemes.

STRICT RULES:
1. Answer ONLY using the provided context. Do not use prior knowledge.
2. If the context does not contain the answer, say: "I don't have this information in my sources."
3. Keep answers to 3 sentences maximum.
4. End every answer with exactly one citation in this format: [Source: <URL>]
5. Never provide investment advice, return predictions, or fund comparisons.
6. Never recommend buying, selling, or holding any fund.
7. If asked for advice or opinions, politely refuse.

CONTEXT:
{retrieved_chunks}

USER QUESTION: {query}

FACTUAL ANSWER:
```

### 5.2 Prompt Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Grounding** | Context injected verbatim before query. Model instructed to use ONLY context. |
| **Citation Format** | Explicit format `[Source: <URL>]` makes regex extraction reliable. |
| **Refusal Instruction** | Explicit prohibition of advice in system prompt. |
| **Brevity Enforcement** | "3 sentences maximum" + max_tokens=150. |
| **Hallucination Prevention** | "Do not use prior knowledge" + low temperature (0.1). |

### 5.3 Few-Shot Examples (In-Context Learning)

Include 2-3 examples in system prompt for format consistency:

```
Example 1:
Q: What is the expense ratio of HDFC Large Cap Fund?
A: The Total Expense Ratio (TER) for HDFC Large Cap Fund - Regular Plan is 1.62% as of January 2026. This includes management fees and operational expenses. [Source: https://hdfcfund.com/literature/kim/hdfc-top-100-fund]

Example 2:
Q: Should I invest in HDFC ELSS for tax saving?
A: I cannot provide investment advice or recommendations. For personalized guidance, please consult a SEBI-registered investment advisor. [Source: N/A]
```

---

## 6. Citation Enforcement

### 6.1 Why Mandatory Citations?

- **Trust**: Users can verify answers against original source.
- **Auditability**: Logs can trace every answer to its source document.
- **Liability Mitigation**: No sourceless claims.

### 6.2 Enforcement Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                   CITATION VALIDATOR                            │
├─────────────────────────────────────────────────────────────────┤
│  [LLM Response] → [Regex Extraction] → [URL Validation] → [OK]  │
│        ↓                 ↓                   ↓             ↓    │
│   Raw text       `\[Source: (https?://[^\]]+)\]`  Domain check  │
│                                               ↓                 │
│                                     Retry if invalid            │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 Validation Rules

| Check | Action on Failure |
|-------|-------------------|
| **Regex Match** | Citation pattern `[Source: <URL>]` must exist → Retry generation (max 2 retries) |
| **URL Format** | Must be valid HTTP(S) URL → Replace with first retrieved chunk's `source_url` |
| **Domain Whitelist** | URL must be from `hdfcfund.com`, `amfiindia.com`, or `sebi.gov.in` → Replace with retrieved chunk's URL |
| **Refusal Case** | If refusal response, citation = `[Source: N/A]` is acceptable |

### 6.4 Fallback Behavior

If LLM fails to include citation after 2 retries:

1. Append citation from highest-ranked retrieved chunk's `source_url`
2. Log incident for review
3. Return answer (never return without citation)

---

## 7. Refusal Logic

### 7.1 Two-Layer Refusal System

#### Layer 1: Pre-Retrieval Classifier

**Purpose**: Block clearly off-topic or advice-seeking queries before wasting retrieval compute.

| Component | Implementation |
|-----------|----------------|
| **Method** | Keyword blocklist + Zero-shot classifier |
| **Classifier** | `facebook/bart-large-mnli` (zero-shot NLI) |
| **Labels** | `["factual question", "investment advice", "opinion request", "off-topic"]` |
| **Threshold** | If `investment advice` or `opinion request` score > 0.7 → Refuse immediately |

**Keyword Blocklist** (triggers immediate refusal):

```
["should I invest", "best fund", "which fund", "buy or sell", "recommend", 
 "better fund", "good returns", "SIP suggestion", "portfolio", "allocate"]
```

#### Layer 2: Post-Generation Validation

Even if query passes Layer 1, LLM might still generate advice. Post-process:

1. **Regex scan** for advice patterns: `"you should"`, `"I recommend"`, `"consider investing"`
2. If detected → Replace response with canned refusal:

```
"I can only provide factual information about mutual fund schemes. For 
personalized investment advice, please consult a SEBI-registered investment 
advisor. [Source: N/A]"
```

### 7.2 Refusal Response Template

```
I'm designed to answer factual questions about HDFC mutual fund schemes only. 
I cannot provide investment advice, fund comparisons, or recommendations. 
For personalized guidance, please consult a SEBI-registered advisor. [Source: N/A]
```

### 7.3 Edge Cases

| Query Type | Handling |
|------------|----------|
| "What is the return of HDFC Large Cap?" | Answer with historical return if in source docs (factual). |
| "Will HDFC Large Cap give good returns?" | Refuse (prediction/advice). |
| "Compare HDFC Large Cap and Flexi Cap" | Refuse (comparative = implicit advice). |
| "What is ELSS lock-in period?" | Answer (factual). |
| "Is ELSS good for tax saving?" | Refuse (opinion). |

---

## 8. Deployment Architecture

### 8.1 Local Deployment (Recommended for MVP)

```
┌─────────────────────────────────────────────────────────────────┐
│                    LOCAL DEPLOYMENT STACK                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│   │   Gradio UI  │◄──►│   FastAPI    │◄──►│   Ollama     │      │
│   │   (Web UI)   │    │   Backend    │    │ (Mistral 7B) │      │
│   └──────────────┘    └──────────────┘    └──────────────┘      │
│          ▲                   │                                  │
│          │                   ▼                                  │
│          │            ┌───────────────┐                         │
│          │            │   ChromaDB    │                         │
│          │            │ (Vector Store)│                         │
│          │            └───────────────┘                         │
│          │                   │                                  │
│          │                   ▼                                  │
│          │            ┌──────────────┐                          │
│          └────────────│    Logs      │                          │
│                       │ (SQLite/JSON)│                          │
│                       └──────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 8 cores | 16 cores |
| **RAM** | 16 GB | 32 GB |
| **GPU** | 8 GB VRAM (RTX 3070) | 12 GB VRAM (RTX 4070) |
| **Storage** | 20 GB SSD | 50 GB SSD |
| **OS** | Ubuntu 22.04 / Windows 11 | Ubuntu 22.04 |

### 8.3 Tech Stack Summary

| Layer | Technology | Version |
|-------|------------|---------|
| **Frontend** | Gradio | 4.x |
| **Backend API** | FastAPI | 0.110+ |
| **LLM Runtime** | Ollama | Latest |
| **LLM Model** | Mistral 7B Instruct Q4_K_M | v0.3 |
| **Embedding Model** | BGE-M3 | via sentence-transformers |
| **Reranker** | cross-encoder/ms-marco-MiniLM-L-6-v2 | - |
| **Vector Store** | ChromaDB | 0.4+ |
| **PDF Parsing** | PyMuPDF4LLM | 0.0.10+ |
| **Classifier** | transformers (BART-MNLI) | 4.40+ |
| **Logging** | SQLite + structlog | - |
| **Python** | 3.11+ | - |

### 8.4 API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ask` | POST | Main query endpoint. Input: `{"query": "..."}` Output: `{"answer": "...", "citation": "...", "confidence": 0.85}` |
| `/health` | GET | Healthcheck for all components |
| `/logs` | GET | Retrieve audit logs (auth-protected) |
| `/ingest` | POST | Trigger document re-ingestion (admin) |

---

## 9. Auditability & Reproducibility

### 9.1 Logging Schema

Every query logs:

```json
{
  "timestamp": "2026-02-04T10:30:00Z",
  "query_id": "uuid",
  "user_query": "What is the expense ratio of HDFC ELSS?",
  "query_sanitized": "what is the expense ratio of hdfc elss",
  "refusal_triggered": false,
  "retrieved_chunks": [
    {"chunk_id": "abc123", "score": 0.89, "source_url": "..."},
    {"chunk_id": "def456", "score": 0.82, "source_url": "..."}
  ],
  "reranked_chunks": ["abc123", "def456", "ghi789"],
  "llm_response_raw": "...",
  "citation_extracted": "https://hdfcfund.com/...",
  "citation_valid": true,
  "final_response": "...",
  "latency_ms": 1200
}
```

### 9.2 Reproducibility Guarantees

| Aspect | Mechanism |
|--------|-----------|
| **Deterministic Retrieval** | Fixed embedding model, consistent chunking |
| **Deterministic Generation** | Temperature=0.1, seed parameter (Ollama supports) |
| **Version Pinning** | All dependencies version-locked in `requirements.txt` |
| **Document Versioning** | Extraction date stored per chunk; re-ingestion logs diff |
| **Model Versioning** | GGUF model hash stored in config |

### 9.3 Audit Trail Access

- All logs queryable via `/logs` endpoint (admin-only)
- Daily log rotation with 90-day retention
- Schema supports export to JSONL for external analysis

---

## 10. Security Considerations

| Concern | Mitigation |
|---------|------------|
| **Prompt Injection** | Input sanitization (strip special chars), system prompt isolation |
| **Data Exfiltration** | No user data stored; stateless queries |
| **Model Jailbreaking** | Refusal classifier + post-generation validation |
| **Source Integrity** | Only whitelisted domains ingested; checksums for documents |
| **API Abuse** | Rate limiting (10 req/min/IP) on public endpoints |

---

## 11. Future Enhancements (Out of Scope for MVP)

1. **Multi-AMC Support**: Extend to ICICI Prudential, SBI MF, etc.
2. **Real-Time NAV**: Integrate AMFI daily NAV API for fresh data.
3. **Hindi Language Support**: BGE-M3 already supports Hindi; add Hindi prompts.
4. **Feedback Loop**: User thumbs-up/down to fine-tune reranker.
5. **Hosted Deployment**: Containerize with Docker, deploy on AWS/GCP.

---

## 12. Complete HDFC AMC Document URLs (25 Documents)

> [!IMPORTANT]
> All URLs must be verified before ingestion. Document availability may change; run health check weekly.

### 12.1 Scheme Information Documents (SID) — 5 Documents

| # | Scheme | URL |
|---|--------|-----|
| 1 | HDFC Large Cap Fund | `https://www.hdfcfund.com/explore/mutual-funds/hdfc-large-cap-fund/direct` |
| 2 | HDFC Flexi Cap Fund | `https://www.hdfcfund.com/literature/scheme-information-document/hdfc-flexi-cap-fund` |
| 3 | HDFC Tax Saver (ELSS) | `https://www.hdfcfund.com/literature/scheme-information-document/hdfc-taxsaver` |
| 4 | HDFC Balanced Advantage Fund | `https://www.hdfcfund.com/literature/scheme-information-document/hdfc-balanced-advantage-fund` |
| 5 | HDFC Liquid Fund | `https://www.hdfcfund.com/literature/scheme-information-document/hdfc-liquid-fund` |

### 12.2 Key Information Memorandum (KIM) — 5 Documents

| # | Scheme | URL |
|---|--------|-----|
| 6 | HDFC Large Cap Fund | `https://www.hdfcfund.com/explore/mutual-funds/hdfc-large-cap-fund/direct` |
| 7 | HDFC Flexi Cap Fund | `https://www.hdfcfund.com/literature/key-information-memorandum/hdfc-flexi-cap-fund` |
| 8 | HDFC Tax Saver (ELSS) | `https://www.hdfcfund.com/literature/key-information-memorandum/hdfc-taxsaver` |
| 9 | HDFC Balanced Advantage Fund | `https://www.hdfcfund.com/literature/key-information-memorandum/hdfc-balanced-advantage-fund` |
| 10 | HDFC Liquid Fund | `https://www.hdfcfund.com/literature/key-information-memorandum/hdfc-liquid-fund` |

### 12.3 Statement of Additional Information (SAI) — 1 Document

| # | Document | URL |
|---|----------|-----|
| 11 | HDFC AMC SAI (covers all schemes) | `https://www.hdfcfund.com/literature/statement-of-additional-information` |

### 12.4 Monthly Factsheets — 5 Documents

| # | Scheme | URL |
|---|--------|-----|
| 12 | HDFC Large Cap Fund | `https://www.hdfcfund.com/explore/mutual-funds/hdfc-large-cap-fund/direct` |
| 13 | HDFC Flexi Cap Fund | `https://www.hdfcfund.com/literature/factsheet/hdfc-flexi-cap-fund` |
| 14 | HDFC Tax Saver (ELSS) | `https://www.hdfcfund.com/literature/factsheet/hdfc-taxsaver` |
| 15 | HDFC Balanced Advantage Fund | `https://www.hdfcfund.com/literature/factsheet/hdfc-balanced-advantage-fund` |
| 16 | HDFC Liquid Fund | `https://www.hdfcfund.com/literature/factsheet/hdfc-liquid-fund` |

### 12.5 AMFI Data Sources — 4 Documents

| # | Document | URL |
|---|----------|-----|
| 17 | Daily NAV (all schemes) | `https://www.amfiindia.com/spages/NAVAll.txt` |
| 18 | Scheme Master Data | `https://www.amfiindia.com/research-information/other-data/scheme-master` |
| 19 | Monthly AUM Data | `https://www.amfiindia.com/research-information/aum-data/aum-month-end` |
| 20 | Investor Complaints | `https://www.amfiindia.com/research-information/other-data/data-on-investor-complaints` |

### 12.6 SEBI Regulatory References — 5 Documents

| # | Document | URL |
|---|----------|-----|
| 21 | Mutual Fund Categorization | `https://www.sebi.gov.in/legal/circulars/oct-2017/categorization-and-rationalization-of-mutual-fund-schemes_36199.html` |
| 22 | Total Expense Ratio Limits | `https://www.sebi.gov.in/legal/circulars/sep-2018/total-expense-ratio-of-mutual-fund-schemes_40505.html` |
| 23 | Risk-o-Meter Guidelines | `https://www.sebi.gov.in/legal/circulars/oct-2020/circular-on-product-labeling-in-mutual-funds-_47868.html` |
| 24 | KYC Norms for MF | `https://www.sebi.gov.in/legal/circulars/mar-2014/kyc-requirements-for-mutual-fund-unitholders_26561.html` |
| 25 | ELSS Guidelines | `https://www.sebi.gov.in/legal/circulars/jun-2017/guidelines-for-filing-of-draft-scheme-information-document-sid-for-equity-linked-savings-scheme-elss_35135.html` |

### 12.7 Document Inventory Summary

| Category | Count | Update Frequency |
|----------|-------|------------------|
| SID | 5 | Annual / On change |
| KIM | 5 | Annual / On change |
| SAI | 1 | Annual |
| Factsheets | 5 | Monthly |
| AMFI Data | 4 | Daily / Monthly |
| SEBI Circulars | 5 | As issued |
| **Total** | **25** | Mixed |

---

## 13. Sample Q&A Test Cases

### 13.1 Factual Queries (Should Answer)

| # | Query | Expected Response Pattern |
|---|-------|---------------------------|
| 1 | "What is the expense ratio of HDFC Large Cap Fund?" | "The Total Expense Ratio (TER) for HDFC Large Cap Fund - Regular Plan is X.XX%... [Source: hdfcfund.com/...]" |
| 2 | "What is the lock-in period for HDFC ELSS?" | "HDFC Tax Saver (ELSS) has a mandatory lock-in period of 3 years... [Source: hdfcfund.com/...]" |
| 3 | "Who is the fund manager of HDFC Flexi Cap Fund?" | "HDFC Flexi Cap Fund is managed by [Name]... [Source: hdfcfund.com/...]" |
| 4 | "What is the minimum SIP amount for HDFC Liquid Fund?" | "The minimum SIP investment in HDFC Liquid Fund is ₹X... [Source: hdfcfund.com/...]" |
| 5 | "What is the benchmark index for HDFC Balanced Advantage Fund?" | "HDFC Balanced Advantage Fund is benchmarked against... [Source: hdfcfund.com/...]" |

### 13.2 Refusal Queries (Should Refuse)

| # | Query | Expected Classifier Label | Expected Response |
|---|-------|---------------------------|-------------------|
| 1 | "Is HDFC Large Cap better than SBI Bluechip?" | `investment advice` (score > 0.7) | "I cannot provide fund comparisons... consult a SEBI-registered advisor. [Source: N/A]" |
| 2 | "Should I invest in HDFC ELSS for tax saving?" | `investment advice` (keyword: "should I invest") | Immediate refusal via keyword blocklist |
| 3 | "Which HDFC fund will give best returns?" | `investment advice` (keywords: "which fund", "best") | Immediate refusal via keyword blocklist |
| 4 | "Recommend a good SIP for beginners" | `investment advice` (keyword: "recommend") | Immediate refusal via keyword blocklist |
| 5 | "Will HDFC Flexi Cap outperform the market?" | `investment advice` (prediction) | Refusal — prediction/advice |
| 6 | "How much should I allocate to large cap?" | `investment advice` (keyword: "allocate") | Immediate refusal via keyword blocklist |

### 13.3 Edge Cases (Requires Careful Handling)

| # | Query | Classification | Expected Handling |
|---|-------|----------------|-------------------|
| 1 | "What was the 5-year return of HDFC Large Cap?" | Factual | Answer if historical return exists in source docs |
| 2 | "Is HDFC Large Cap safe?" | Opinion request | Refuse — subjective/opinion |
| 3 | "What is the risk category of HDFC Liquid Fund?" | Factual | Answer with SEBI risk-o-meter rating |
| 4 | "Compare ELSS lock-in with PPF lock-in" | Off-topic (PPF not in scope) | Refuse — cannot answer about PPF |
| 5 | "What is NAV?" | Factual (general) | Answer with definition from AMFI source |

### 13.4 Confidence Gate Test Cases

| # | Query | Expected Behavior |
|---|-------|-------------------|
| 1 | "What is the weather today?" | All retrieval scores < 0.4 → Immediate refusal without LLM call |
| 2 | "Tell me about Bitcoin" | All retrieval scores < 0.4 → Immediate refusal without LLM call |
| 3 | "Explain quantum computing" | All retrieval scores < 0.4 → Immediate refusal without LLM call |

---

## 14. UI Requirements & Disclaimer

### 14.1 Mandatory Disclaimer (Must Display)

> [!CAUTION]
> The following disclaimer MUST be displayed prominently on every page of the UI.

**Disclaimer Text (Fixed)**:

```
⚠️ DISCLAIMER: This is a facts-only assistant. No investment advice.
• Answers are sourced from official HDFC AMC, AMFI, and SEBI documents.
• This tool does NOT provide personalized investment recommendations.
• Past performance is not indicative of future results.
• For investment decisions, consult a SEBI-registered investment advisor.
```

### 14.2 Disclaimer Placement

| Location | Display Style |
|----------|---------------|
| **Header Banner** | Persistent yellow/orange banner at top of page. Non-dismissible. |
| **Chat Input Area** | Subtle reminder above input: "Ask factual questions only. No advice provided." |
| **Response Footer** | Every response ends with: "📖 This is factual information, not investment advice." |

### 14.3 UI Component Specifications

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ⚠️ FACTS ONLY — NO INVESTMENT ADVICE  │  [Disclaimer Banner - Yellow]      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  🏦 Groww Mutual Fund FAQ                                          │   │
│   │  Ask factual questions about HDFC mutual fund schemes               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  [Chat History Area]                                                │   │
│   │                                                                     │   │
│   │  User: What is the expense ratio of HDFC ELSS?                      │   │
│   │                                                                     │   │
│   │  Bot: The Total Expense Ratio (TER) for HDFC Tax Saver - Regular    │   │
│   │  Plan is 1.98% as of January 2026.                                  │   │
│   │  [Source: https://hdfcfund.com/literature/kim/hdfc-taxsaver]        │   │
│   │  📖 This is factual information, not investment advice.             │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  💬 Ask a question...                      [Send]                   │   │
│   │  ───────────────────────────────────────────────────────────────    │   │
│   │  ℹ️ Factual questions only. No advice provided.                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  Sources: HDFC AMC | AMFI | SEBI  •  For advice, consult a SEBI advisor     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 14.4 Legal & Compliance Notes

| Requirement | Implementation |
|-------------|----------------|
| **SEBI Compliance** | Disclaimer follows SEBI advertising guidelines for mutual funds |
| **No Personalization** | No user accounts, no saved preferences, no personalized suggestions |
| **Audit-Ready** | All queries and responses logged with timestamps |
| **Source Attribution** | Every answer links to official source; no unattributed claims |

---

## 15. Summary Checklist

| Requirement | Solution |
|-------------|----------|
| ✅ One AMC, 3-5 schemes | HDFC AMC: Large Cap, Flexi Cap, ELSS, Balanced Advantage, Liquid |
| ✅ RAG pipeline | PyMuPDF4LLM → Semantic Chunking → BGE-M3 → ChromaDB → Rerank → Mistral 7B |
| ✅ Open-source tools | All components OSS (Apache/MIT licensed) |
| ✅ Embedding model rationale | BGE-M3: multilingual, 1024-dim, local inference, SOTA quality |
| ✅ Vector store choice | ChromaDB: embedded, persistent, metadata filtering |
| ✅ Chunking strategy | 512 tokens, 64 overlap, semantic boundaries, atomic tables |
| ✅ Retrieval strategy | Confidence gate (< 0.4) → Dense (top-20) → Metadata filter → Cross-encoder rerank (top-3) |
| ✅ Prompting for accuracy | Grounding instructions, low temperature, few-shot examples |
| ✅ Citation enforcement | Regex extraction + URL validation + fallback injection |
| ✅ Refusal logic | Keyword blocklist + zero-shot classifier + post-gen validation |
| ✅ Deployment option | Local: Gradio + FastAPI + Ollama + ChromaDB |
| ✅ **Atomic table handling** | Tables tagged explicitly, bypass 512-token limit, never split mid-row |
| ✅ **Confidence thresholding** | All scores < 0.4 → immediate refusal, no LLM call |
| ✅ **Acronym expansion** | 12 financial acronyms mapped (ELSS, NAV, SIP, TER, etc.) |
| ✅ **Complete URL inventory** | 25 public URLs documented (SID, KIM, SAI, Factsheets, AMFI, SEBI) |
| ✅ **Sample test cases** | 17 test queries covering factual, refusal, edge cases, confidence gate |
| ✅ **UI disclaimer** | Mandatory "Facts-only. No investment advice." banner + footer |

---

*Document prepared for Groww RAG MVP — Facts Only, Citations Always.*
