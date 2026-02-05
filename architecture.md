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
| ------------ | ------------- |
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
| ------------- | ---------- | -------------- | ------ | ----------- | ----------- |
| HDFC Large Cap Fund | Equity | Large Cap | Direct | 100032 | Blue-chip exposure, stable documentation |
| HDFC Flexi Cap Fund | Equity | Flexi Cap | Direct | 100394 | Multi-cap flexibility, popular scheme |
| HDFC Tax Saver (ELSS) | Equity | ELSS | Direct | 100186 | Tax-saving category, 3-year lock-in rules |
| HDFC Balanced Advantage Fund | Hybrid | Dynamic | Direct | 100171 | Dynamic asset allocation rules |
| HDFC Liquid Fund | Debt | Liquid | Direct | 100027 | Low-risk category, distinct risk profile |

### 3.3 Document Sources

| Source Type | URL Pattern | Content |
| ------------- | ------------- | --------- |
| Product Pages | `hdfcfund.com/explore/mutual-funds/{scheme}/direct` | Fund objective, TER, exit load, SIP min |
| Scheme Information Document (SID) | `hdfcfund.com/investor-services/fund-documents/sid` | Fund objective, risk factors, investment strategy |
| Key Information Memorandum (KIM) | `hdfcfund.com/investor-services/fund-documents/kim` | Condensed scheme facts, TER, exit load |
| Statement of Additional Info (SAI) | `hdfcfund.com/literature/statement-of-additional-information` | AMC details, legal structure |
| Monthly Factsheets | `hdfcfund.com/investor-services/factsheets` | Holdings, returns, riskometer |
| AMFI NAV Data | `amfiindia.com/spages/NAVAll.txt` | Official NAV snapshots |
| SEBI Circulars | `sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=7&smid=0` | Category definitions, TER limits |

---

## 4. RAG Architecture

### 4.1 High-Level Pipeline

```text
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
| ----------- | ------ | --------------- |
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
| ------ | ---------------- |
| **Table Detection** | Regex + PyMuPDF table extraction API to identify all tables |
| **Explicit Tagging** | Each table chunk tagged with `is_table: true`, `table_type: "expense_ratio\|risk_meter\|nav_history"` |
| **Size Override** | Tables bypass 512-token limit; entire table = 1 chunk (max 2048 tokens) |
| **Boundary Check** | Pre-chunking validator: if table detected and chunk boundary falls mid-table → extend chunk to table end |
| **Fallback** | If table exceeds 2048 tokens → split by logical rows (preserve header in each split) |

#### 4.2.2 Chunking Strategy

**Standard Chunks**:

| Parameter | Value | Rationale |
| ----------- | ------- | ----------- |
| **Chunk Size** | 512 tokens (~350-400 words) | Mutual fund facts (expense ratio, exit load) typically span 1-3 sentences. 512 tokens isolates single facts while providing sufficient context. Matches BGE-M3 optimal input range. |
| **Overlap** | 64 tokens (12.5%) | Ensures boundary sentences aren't orphaned. Critical for facts split across paragraphs. |
| **Chunking Method** | **Semantic Chunking** (LangChain `SemanticChunker`) | Respects paragraph/section boundaries. Falls back to token-based if semantic splitting fails. |

**Atomic Units (Override Rules)**:

| Content Type | Rule | Max Size | Justification |
| -------------- | ------ | ---------- | --------------- |
| **Tables** | Entire table = 1 chunk; never split mid-row | 2048 tokens | Splitting tables creates fragments that fail to answer "What is the exit load?" |
| **List blocks** | Preserve complete numbered/bulleted lists | 1024 tokens | Exit load slabs, SIP options must stay together |
| **Scheme sections** | "Investment Objective", "Risk Factors" atomic | 1024 tokens | These are frequently asked as single questions |

**Fallback for Oversized Atoms**:

- If table > 2048 tokens → split by logical row groups, repeat header row in each split
- Tag each split with `is_partial: true`, `parent_chunk_id: <original_uuid>`
- If list > 1024 tokens → split at natural groupings (e.g., category breaks)

#### 4.2.3 Chunk Metadata Schema

> [!IMPORTANT]
> Every chunk **must** carry these fields. Ingestion fails if any mandatory field is null.

**Mandatory Fields**:

| Field | Type | Example | Purpose |
| ------- | ------ | --------- | --------- |
| `chunk_id` | UUID | `f47ac10b-58cc-...` | Unique identifier for deduplication and audit |
| `amc_name` | string | `HDFC Asset Management Company` | AMC-level filtering; prevents cross-AMC contamination |
| `scheme_name` | string | `HDFC Large Cap Fund` | Primary filter for scheme-specific queries |
| `scheme_code` | string | `100032` | AMFI code for unambiguous scheme identification |
| `plan_type` | enum | `Direct` / `Regular` | Critical—TER and returns differ between plans |
| `fact_type` | enum | See below | Semantic tagging for precision retrieval |
| `source_url` | URL | `https://hdfcfund.com/...` | Citation source; must be whitelisted domain |
| `document_type` | enum | `SID` / `KIM` / `SAI` / `Factsheet` / `AMFI` / `SEBI` | Source authority classification |
| `section_title` | string | `Exit Load Structure` | Aids retrieval and audit |
| `extraction_date` | ISO 8601 | `2026-02-04T10:30:00Z` | When chunk was ingested (freshness indicator) |
| `document_date` | ISO 8601 | `2026-01-01` | Official publication date of source document |
| `page_number` | int | `12` | For PDF sources; aids manual verification |
| `is_table` | boolean | `true` | Triggers atomic chunking rules |
| `table_type` | enum | `expense_ratio` / `exit_load` / `nav_history` / null | Fine-grained table classification |
| `checksum` | SHA-256 | `a3f2b1...` | Detects document changes on re-ingestion |

**`fact_type` Enum Values**:

```text
expense_ratio, exit_load, fund_manager, investment_objective, risk_category,
benchmark, sip_minimum, lumpsum_minimum, aum, nav, lock_in_period,
fund_holdings, returns_historical, scheme_launch_date, general_info
```

**Sample Chunk Metadata**:

```json
{
  "chunk_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "text": "The Total Expense Ratio for HDFC Large Cap Fund - Direct Plan is 1.08%...",
  "amc_name": "HDFC Asset Management Company",
  "scheme_name": "HDFC Large Cap Fund",
  "scheme_code": "100032",
  "plan_type": "Direct",
  "fact_type": "expense_ratio",
  "source_url": "https://hdfcfund.com/explore/mutual-funds/hdfc-large-cap-fund/direct",
  "document_type": "KIM",
  "section_title": "Total Expense Ratio",
  "extraction_date": "2026-02-04T10:30:00Z",
  "document_date": "2026-01-01",
  "page_number": 3,
  "is_table": false,
  "table_type": null,
  "checksum": "a3f2b1c4d5e6f7..."
}
```

#### 4.2.3 Embedding Model

| Aspect | Choice | Rationale |
| -------- | -------- | ----------- |
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
| -------- | -------- | ----------- |
| **Vector Store** | **ChromaDB** (local, persistent) | Open-source, embedded, no infra dependency. Supports metadata filtering. Production-ready with SQLite backend. |
| **Alternatives Considered** | Qdrant | More features but heavier. Overkill for ~5 schemes. |
| | Pinecone | Managed service = vendor lock-in + cost. |
| | FAISS | Fast but no built-in metadata filtering. |
| **Index Type** | HNSW (default in Chroma) | Best recall/speed tradeoff for <100K vectors. |
| **Distance Metric** | Cosine Similarity | Standard for normalized embeddings. |

**Collection Schema**:

```text
Collection: "hdfc_mf_faq"
  - Vectors: 1024-dim (BGE-M3)
  - Metadata: scheme_name, document_type, source_url, section_title
  - Persistence: ./chroma_db/
```

#### 4.2.5 Retrieval Strategy

| Stage | Method | Details |
| ------- | -------- | --------- |
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
| --------- | ----------- | --------- |
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

```text
1. Tokenize user query
2. For each token, check if it matches an acronym (case-insensitive)
3. If match → append expansion in parentheses: "ELSS" → "ELSS (Equity Linked Savings Scheme)"
4. Embed expanded query for retrieval
```

#### 4.2.6 Answer Generation (LLM)

| Aspect | Choice | Rationale |
| -------- | -------- | ----------- |
| **Model** | **Mistral 7B Instruct v0.3** (via Ollama or llama.cpp) | Best open-source 7B model for instruction following. Runs on consumer GPU (8GB VRAM). Apache 2.0 license. |
| **Alternatives Considered** | GPT-4 Turbo | Superior quality but API cost + data leaves your infra. |
| | Llama 3.1 8B | Comparable but Mistral has tighter instruction adherence. |
| **Quantization** | Q4_K_M (4-bit GGUF) | 4.5GB model size. Minimal quality loss. |
| **Inference** | Ollama (local) | Simple API, easy model management, no external calls. |
| **Temperature** | 0.1 | Near-deterministic for factual consistency. |
| **Max Tokens** | 150 | Enforces ≤3 sentence limit. |

---

## 5. Final Prompts for LLM

> [!CAUTION]
> These prompts are production-ready. Any modification must be tested against the full test suite before deployment.

### 5.1 Final System Prompt

```text
You are a FACTS-ONLY assistant for Groww, answering questions about HDFC mutual fund schemes.

═══════════════════════════════════════════════════════════════════════════════
                              ABSOLUTE RULES
═══════════════════════════════════════════════════════════════════════════════

1. GROUNDING REQUIREMENT
   • Answer ONLY using the CONTEXT provided below.
   • Do NOT use prior knowledge, training data, or assumptions.
   • If the CONTEXT does not contain the answer → REFUSE (see Rule 6).

2. FORBIDDEN CONTENT — Never generate any of the following:
   ✗ Investment advice ("you should invest", "I recommend", "consider buying")
   ✗ Performance predictions ("will give good returns", "expected to grow")
   ✗ Fund comparisons ("X is better than Y", "choose X over Y")
   ✗ Portfolio recommendations ("allocate X%", "best fund for your goal")
   ✗ Subjective opinions ("safe fund", "risky", "good/bad fund")
   ✗ Future forecasts ("next year", "in 5 years", "market outlook")

3. FORMAT REQUIREMENTS
   • Maximum 3 sentences.
   • End with exactly ONE citation: [Source: <URL>]
   • Use ₹ symbol for currency, % for ratios.
   • State facts directly; no hedging language.

4. CITATION RULES
   • Citation URL must be from the CONTEXT.
   • Use the source_url from the most relevant retrieved chunk.
   • Format: [Source: https://...]
   • For refusals, use: [Source: N/A]

5. RESPONSE FOOTER (Always append after citation)
   📅 Last updated from sources: {extraction_date}
   📖 This is factual information, not investment advice.

6. WHEN TO REFUSE
   Refuse politely if ANY of these are true:
   • Context does not contain the answer
   • Question asks for advice, opinions, or predictions
   • Question asks to compare funds
   • Question is about a scheme not in the context
   • You are uncertain about the accuracy

   REFUSAL RESPONSE (use exactly):
   "I don't have this information in my verified sources. For accurate 
   details, please visit the official HDFC AMC website or consult a 
   SEBI-registered investment advisor.
   [Source: N/A]
   📅 This is factual information, not investment advice."

═══════════════════════════════════════════════════════════════════════════════
                              FEW-SHOT EXAMPLES
═══════════════════════════════════════════════════════════════════════════════

EXAMPLE 1 — Factual Query (ANSWER):
User: What is the expense ratio of HDFC Large Cap Fund Direct Plan?
Assistant: The Total Expense Ratio (TER) for HDFC Large Cap Fund - Direct Plan 
is 1.08% as of January 2026. This includes fund management fees and operational 
expenses.
[Source: https://www.hdfcfund.com/explore/mutual-funds/hdfc-large-cap-fund/direct]
📅 Last updated from sources: 2026-02-04
📖 This is factual information, not investment advice.

EXAMPLE 2 — Advice Request (REFUSE):
User: Should I invest in HDFC ELSS for tax saving?
Assistant: I can only provide factual information and cannot offer investment 
advice. For personalized guidance, please consult a SEBI-registered investment 
advisor.
[Source: N/A]
📅 This is factual information, not investment advice.

EXAMPLE 3 — Comparison Request (REFUSE):
User: Which is better - HDFC Large Cap or HDFC Flexi Cap?
Assistant: I cannot provide fund comparisons or recommendations. I can share 
individual factual details about each fund if you have specific questions.
[Source: N/A]
📅 This is factual information, not investment advice.

EXAMPLE 4 — Information Not in Context (REFUSE):
User: What is the NAV of ICICI Prudential Bluechip Fund?
Assistant: I don't have this information in my verified sources. I only have 
data on HDFC mutual fund schemes. For ICICI fund details, please visit their 
official website.
[Source: N/A]
📅 This is factual information, not investment advice.

═══════════════════════════════════════════════════════════════════════════════
                              BEGIN TASK
═══════════════════════════════════════════════════════════════════════════════
```

### 5.2 User Prompt Template

```text
CONTEXT:
────────────────────────────────────────────────────────────────────────────────
{retrieved_chunks}
────────────────────────────────────────────────────────────────────────────────

METADATA:
• Current Date: {current_date}
• Extraction Date: {extraction_date}
• Schemes in Context: {scheme_names}

USER QUESTION: {query}

FACTUAL ANSWER:
```

**Template Variables**:

| Variable | Source | Example |
| ---------- | -------- | --------- |
| `{retrieved_chunks}` | Top-3 reranked chunks, joined with `\n---\n` | Full chunk text with metadata |
| `{current_date}` | System date | `2026-02-05` |
| `{extraction_date}` | `min(chunk.extraction_date)` from retrieved chunks | `2026-02-04` |
| `{scheme_names}` | Unique `scheme_name` values from chunks | `HDFC Large Cap Fund, HDFC Flexi Cap Fund` |
| `{user_query}` | Sanitized user input | `What is the expense ratio?` |

### 5.3 Refusal Templates

**Template A: Investment Advice Refusal**

```text
I can only provide factual information and cannot offer investment advice or 
recommendations. For personalized guidance, please consult a SEBI-registered 
investment advisor.

📚 Learn about choosing an advisor: https://investor.sebi.gov.in/advisorycaution.html

[Source: N/A]
📅 This is factual information, not investment advice.
```

**Template B: Opinion/Speculation Refusal**

```text
I can only share objective facts from official sources. I cannot provide 
subjective assessments, predictions, or opinions about mutual funds.

📚 Learn about mutual fund risks: https://investor.sebi.gov.in/pdf/Mutual%20Fund%20booklet.pdf

[Source: N/A]
📅 This is factual information, not investment advice.
```

**Template C: Out-of-Scope Refusal**

```text
I specialize in factual questions about HDFC mutual fund schemes only. I don't 
have information on this topic in my verified sources.

📚 For general investor education: https://www.amfiindia.com/investor-corner/investor-awareness.html

[Source: N/A]
📅 This is factual information, not investment advice.
```

**Template D: Low Confidence / Not Found Refusal**

```text
I don't have reliable information on this in my verified sources. For accurate 
details, please check the official HDFC AMC website.

📚 Official HDFC Fund Information: https://www.hdfcfund.com/explore/mutual-funds

[Source: N/A]
📅 This is factual information, not investment advice.
```

### 5.4 Prompt Design Principles

| Principle | Implementation | Why It Matters |
| ----------- | ---------------- | ---------------- |
| **Explicit Grounding** | "Answer ONLY using the CONTEXT" | Prevents hallucination |
| **Forbidden List** | 6 explicit categories with examples | Leaves no ambiguity |
| **Format Lock** | "Maximum 3 sentences", "exactly ONE citation" | Ensures consistency |
| **Refusal Instruction** | Complete refusal template in system prompt | Model learns exact format |
| **Few-Shot Examples** | 4 examples covering answer + 3 refusal types | In-context learning |
| **Visual Separators** | `═══` and `───` dividers | Helps model parse sections |
| **Footer Requirement** | Freshness + disclaimer always present | Audit compliance |

### 5.5 LLM Configuration

| Parameter | Value | Rationale |
| ----------- | ------- | ----------- |
| **Temperature** | 0.1 | Near-deterministic; minimizes variation |
| **Max Tokens** | 200 | Allows 3 sentences + citation + footer |
| **Top-P** | 0.9 | Slight diversity while maintaining focus |
| **Frequency Penalty** | 0.0 | No penalty; factual responses may repeat terms |
| **Presence Penalty** | 0.0 | No penalty; allow consistent formatting |
| **Stop Sequences** | `["\n\nUser:", "\n\nUSER:"]` | Prevent runaway generation |

---

## 6. Citation Enforcement

### 6.1 Why Mandatory Citations?

- **Trust**: Users can verify answers against original source.
- **Auditability**: Logs can trace every answer to its source document.
- **Liability Mitigation**: No sourceless claims.

### 6.2 Enforcement Pipeline

```text
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
| ------- | ------------------- |
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

## 7. Reasoning & Decision Logic

> [!IMPORTANT]
> This section defines the complete decision-making framework for when to answer, when to refuse, and how to maintain factual accuracy.

### 7.1 Query Classification System

**Class 1: ALLOWED — Factual Queries**

| Subclass | Description | Examples |
| ---------- | ------------- | ---------- |
| **Scheme Facts** | Specific numeric/textual facts about a scheme | "What is the expense ratio?", "Who is the fund manager?" |
| **Scheme Definitions** | Definitions of scheme attributes | "What is the investment objective?", "What is the benchmark?" |
| **General MF Facts** | Factual definitions from AMFI/SEBI | "What is NAV?", "What is ELSS lock-in period?" |
| **Historical Data** | Past performance data (not predictions) | "What was the 5-year return?", "When was the fund launched?" |

**Class 2: DISALLOWED — Advice/Opinion Queries**

| Subclass | Description | Examples |
| ---------- | ------------- | ---------- |
| **Investment Advice** | Recommendations to buy/sell/hold | "Should I invest in...?", "Is this fund good?" |
| **Predictions** | Future return forecasts | "Will this fund give good returns?", "Expected NAV?" |
| **Comparisons** | Fund vs fund analysis | "Which is better, X or Y?", "Compare A and B" |
| **Portfolio Advice** | Allocation recommendations | "How much should I invest?", "Best fund for my goal?" |
| **Opinions** | Subjective assessments | "Is this fund safe?", "Is expense ratio too high?" |

**Class 3: OUT-OF-SCOPE — Unrelated Queries**

| Subclass | Description | Examples |
| ---------- | ------------- | ---------- |
| **Off-Topic** | Non-MF questions | "What is Bitcoin?", "Weather today?" |
| **Wrong AMC** | Questions about non-HDFC schemes | "Tell me about SBI Bluechip" |
| **PII Requests** | Personal data | "Show my portfolio", "My returns?" |

### 7.2 Decision Tree

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                          USER QUERY RECEIVED                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: KEYWORD BLOCKLIST CHECK                                            │
│ ─────────────────────────────────────────────────────────────────────────── │
│ Match against blocklist:                                                    │
│ ["should I invest", "best fund", "which fund", "buy or sell", "recommend",  │
│  "better fund", "good returns", "SIP suggestion", "portfolio", "allocate",  │
│  "suggest", "advise", "worth it", "profitable", "risky investment"]         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
              MATCH FOUND                      NO MATCH
                    │                               │
                    ▼                               ▼
         ┌──────────────────┐    ┌──────────────────────────────────────────────┐
         │ IMMEDIATE REFUSE │    │ LAYER 2: ZERO-SHOT CLASSIFIER                │
         │ (Template A)     │    │ ─────────────────────────────────────────────│
         └──────────────────┘    │ Model: facebook/bart-large-mnli              │
                                 │ Labels: [factual, advice, opinion, off-topic]│
                                 │ Threshold: 0.7                               │
                                 └──────────────────────────────────────────────┘
                                                    │
                    ┌───────────────┬───────────────┼───────────────┐
                    │               │               │               │
             advice > 0.7    opinion > 0.7   off-topic > 0.7   factual wins
                    │               │               │               │
                    ▼               ▼               ▼               ▼
              ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌──────────────────┐
              │ REFUSE    │   │ REFUSE    │   │ REFUSE    │   │ LAYER 3:         │
              │ Template A│   │ Template B│   │ Template C│   │ RETRIEVAL        │
              └───────────┘   └───────────┘   └───────────┘   └──────────────────┘
                                                                    │
                                                                    ▼
                                 ┌─────────────────────────────────────────────┐
                                 │ LAYER 3: CONFIDENCE GATE                    │
                                 │ ─────────────────────────────────────────── │
                                 │ Retrieve top-20 chunks via vector search    │
                                 │ Check: Are ALL similarity scores < 0.4?     │
                                 └─────────────────────────────────────────────┘
                                                    │
                                    ┌───────────────┴───────────────┐
                                    │                               │
                             ALL < 0.4                      AT LEAST ONE ≥ 0.4
                                    │                               │
                                    ▼                               ▼
                         ┌──────────────────┐    ┌─────────────────────────────┐
                         │ REFUSE           │    │ LAYER 4: SCHEME FILTER      │
                         │ Template D       │    │ If query mentions scheme →  │
                         │ (No LLM call)    │    │ Filter by scheme_name       │
                         └──────────────────┘    └─────────────────────────────┘
                                                                    │
                                                                    ▼
                                                 ┌─────────────────────────────┐
                                                 │ LAYER 5: RERANK + GENERATE  │
                                                 │ Cross-encoder rerank → Top-3│
                                                 │ LLM generates response      │
                                                 └─────────────────────────────┘
                                                                    │
                                                                    ▼
                                 ┌─────────────────────────────────────────────┐
                                 │ LAYER 6: POST-GENERATION VALIDATION         │
                                 │ ─────────────────────────────────────────── │
                                 │ Scan for advice patterns in response:       │
                                 │ ["you should", "I recommend", "consider     │
                                 │  investing", "better to", "advisable"]      │
                                 └─────────────────────────────────────────────┘
                                                    │
                                    ┌───────────────┴───────────────┐
                                    │                               │
                           PATTERN FOUND                      NO PATTERN
                                    │                               │
                                    ▼                               ▼
                         ┌──────────────────┐    ┌─────────────────────────────┐
                         │ REPLACE WITH     │    │ LAYER 7: CITATION CHECK     │
                         │ REFUSE Template A│    │ Validate [Source: URL]      │
                         └──────────────────┘    │ Domain whitelist check      │
                                                 └─────────────────────────────┘
                                                                    │
                                                                    ▼
                                                 ┌─────────────────────────────┐
                                                 │ LAYER 8: FORMAT & RETURN    │
                                                 │ Apply answer formatting     │
                                                 │ Add freshness footer        │
                                                 │ Return to user              │
                                                 └─────────────────────────────┘
```

### 7.3 Refusal Message Templates

> [!NOTE]
> All refusal messages are polite, facts-only, and include one educational official link.

**Template A: Investment Advice Refusal**

```text
I'm designed to provide factual information only and cannot offer investment 
advice or recommendations. For personalized guidance, please consult a 
SEBI-registered investment advisor.

📚 Learn more about choosing a financial advisor: 
https://investor.sebi.gov.in/advisorycaution.html

[Source: N/A]
📅 This is factual information, not investment advice.
```

**Template B: Opinion Request Refusal**

```text
I can only share objective facts from official sources. I'm not able to 
provide subjective assessments or opinions about mutual funds.

📚 Learn about mutual fund risks from SEBI: 
https://investor.sebi.gov.in/pdf/Mutual%20Fund%20booklet.pdf

[Source: N/A]
📅 This is factual information, not investment advice.
```

**Template C: Out-of-Scope Refusal**

```text
I specialize in factual questions about HDFC mutual fund schemes only. 
I don't have information on this topic in my sources.

📚 For general investor education, visit: 
https://www.amfiindia.com/investor-corner/investor-awareness.html

[Source: N/A]
📅 This is factual information, not investment advice.
```

**Template D: Low Confidence Refusal**

```text
I don't have reliable information on this in my sources. For accurate 
details, please check the official HDFC AMC website or AMFI portal.

📚 Official HDFC Fund Information: 
https://www.hdfcfund.com/explore/mutual-funds

[Source: N/A]
📅 This is factual information, not investment advice.
```

### 7.4 Answer Formatting Rules

**Mandatory Format Structure**:

```text
[FACTUAL ANSWER: ≤3 sentences, directly answering the question]
[Source: <single_url_from_retrieved_chunk>]
📅 Last updated from sources: <extraction_date>
📖 This is factual information, not investment advice.
```

**Formatting Rules**:

| Rule | Requirement | Validation |
| ------ | ------------- | ------------ |
| **Sentence Limit** | ≤3 sentences | Post-generation sentence count check; truncate if exceeded |
| **Citation Count** | Exactly 1 URL | Regex validation: `\[Source: (https?://[^\]]+)\]` |
| **Citation Domain** | Whitelisted only | `hdfcfund.com`, `amfiindia.com`, `sebi.gov.in` |
| **Freshness Footer** | Always present | `📅 Last updated from sources: YYYY-MM-DD` |
| **Disclaimer Footer** | Always present | `📖 This is factual information, not investment advice.` |
| **Number Formatting** | Currency with ₹ symbol | Expense ratio as %, amounts as ₹X,XXX |

**Sentence Limit Enforcement**:

1. Count sentences in LLM output (split by `.`, `!`, `?`)
2. If > 3 sentences → truncate to first 3
3. Ensure truncated response still makes grammatical sense
4. Log truncation events for prompt tuning

### 7.5 Example Queries & Expected Behaviors

#### 7.5.1 Allowed Queries → Expected Responses

**Example 1: Expense Ratio Query**

```text
USER: What is the expense ratio of HDFC Large Cap Fund Direct Plan?

ASSISTANT: The Total Expense Ratio (TER) for HDFC Large Cap Fund - Direct Plan 
is 1.08% as of January 2026. This includes fund management fees and 
operational expenses.
[Source: https://www.hdfcfund.com/explore/mutual-funds/hdfc-large-cap-fund/direct]
📅 Last updated from sources: 2026-02-04
📖 This is factual information, not investment advice.
```

**Example 2: Lock-in Period Query**

```text
USER: What is the lock-in period for HDFC ELSS Tax Saver?

ASSISTANT: HDFC Tax Saver (ELSS) has a mandatory lock-in period of 3 years 
from the date of investment. This is the shortest lock-in among all Section 
80C investment options.
[Source: https://www.hdfcfund.com/explore/mutual-funds/hdfc-elss-tax-saver/direct]
📅 Last updated from sources: 2026-02-04
📖 This is factual information, not investment advice.
```

**Example 3: Fund Manager Query**

```text
USER: Who manages the HDFC Flexi Cap Fund?

ASSISTANT: HDFC Flexi Cap Fund is managed by Mr. Roshi Jain and Mr. Dhruv Muchhal 
as of January 2026.
[Source: https://www.hdfcfund.com/explore/mutual-funds/hdfc-flexi-cap-fund/direct]
📅 Last updated from sources: 2026-02-04
📖 This is factual information, not investment advice.
```

#### 7.5.2 Disallowed Queries → Refusal Responses

**Example 1: Investment Advice Request**

```text
USER: Should I invest in HDFC Large Cap Fund for long-term?

CLASSIFICATION: BLOCKED by keyword blocklist ("should I invest")

ASSISTANT: I'm designed to provide factual information only and cannot offer 
investment advice or recommendations. For personalized guidance, please consult 
a SEBI-registered investment advisor.

📚 Learn more about choosing a financial advisor: 
https://investor.sebi.gov.in/advisorycaution.html

[Source: N/A]
📅 This is factual information, not investment advice.
```

**Example 2: Comparison/Opinion Request**

```text
USER: Is HDFC Large Cap better than HDFC Flexi Cap?

CLASSIFICATION: BLOCKED by zero-shot classifier (advice: 0.82)

ASSISTANT: I can only share objective facts from official sources. I'm not able 
to provide subjective assessments or opinions about mutual funds.

📚 Learn about mutual fund risks from SEBI: 
https://investor.sebi.gov.in/pdf/Mutual%20Fund%20booklet.pdf

[Source: N/A]
📅 This is factual information, not investment advice.
```

**Example 3: Future Prediction Request**

```text
USER: Will HDFC Balanced Advantage Fund give good returns next year?

CLASSIFICATION: BLOCKED by keyword blocklist ("good returns") + 
               zero-shot classifier (advice: 0.91)

ASSISTANT: I'm designed to provide factual information only and cannot offer 
investment advice or recommendations. For personalized guidance, please consult 
a SEBI-registered investment advisor.

📚 Learn more about choosing a financial advisor: 
https://investor.sebi.gov.in/advisorycaution.html

[Source: N/A]
📅 This is factual information, not investment advice.
```

### 7.6 Decision Rules Summary

| Layer | Check | Pass Action | Fail Action |
| ------- | ------- | ------------- | ------------- |
| **L1** | Keyword blocklist | Continue to L2 | Refuse (Template A) |
| **L2** | Zero-shot classifier | Continue to L3 (if factual) | Refuse (Template A/B/C) |
| **L3** | Confidence gate (≥0.4) | Continue to L4 | Refuse (Template D) |
| **L4** | Scheme filter | Continue to L5 | Continue to L5 (general query) |
| **L5** | Rerank + Generate | Continue to L6 | N/A |
| **L6** | Post-gen advice scan | Continue to L7 | Refuse (Template A) |
| **L7** | Citation validation | Continue to L8 | Retry or inject citation |
| **L8** | Format + Return | Deliver response | N/A |

---

## 8. Deployment Architecture

### 8.1 Streamlit Cloud Deployment (Production)

```text
┌─────────────────────────────────────────────────────────────────┐
│                  STREAMLIT CLOUD DEPLOYMENT                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │                  Streamlit Cloud                         │  │
│   │  ┌────────────────────────────────────────────────────┐  │  │
│   │  │              Streamlit App (app.py)                │  │  │
│   │  │  ┌─────────────────┐  ┌─────────────────────────┐  │  │  │
│   │  │  │   UI Layer      │  │   RAG Pipeline          │  │  │  │
│   │  │  │   (st.chat_*)   │  │   • Query Processing    │  │  │  │
│   │  │  │                 │  │   • Retrieval           │  │  │  │
│   │  │  │                 │  │   • Response Gen        │  │  │  │
│   │  │  └─────────────────┘  └─────────────────────────┘  │  │  │
│   │  └────────────────────────────────────────────────────┘  │  │
│   └──────────────────────────────────────────────────────────┘  │
│          │                          │                           │
│          ▼                          ▼                           │
│   ┌──────────────┐           ┌──────────────┐                   │
│   │  ChromaDB    │           │  Groq API    │                   │
│   │  (Embedded)  │           │  (LLM)       │                   │
│   │  ./chroma_db │           │  Llama 3.3   │                   │
│   └──────────────┘           └──────────────┘                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 Streamlit Cloud Configuration

#### 8.2.1 Required Files

| File | Purpose |
| ------ | --------- |
| `app.py` | Main Streamlit application entry point |
| `requirements.txt` | Python dependencies (auto-installed by Streamlit Cloud) |
| `.streamlit/config.toml` | Streamlit configuration (theme, server settings) |
| `.streamlit/secrets.toml` | API keys (Groq API key) — NOT committed to Git |
| `chroma_db/` | Pre-built ChromaDB vector store (committed to repo) |

#### 8.2.2 Secrets Management

```toml
# .streamlit/secrets.toml (local) or Streamlit Cloud Secrets dashboard
[groq]
api_key = "gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

#### 8.2.3 Streamlit Config

```toml
# .streamlit/config.toml
[theme]
primaryColor = "#00D09C"  # Groww green
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F5F5F5"
textColor = "#1E1E1E"
font = "sans serif"

[server]
enableCORS = false
enableXsrfProtection = true
maxUploadSize = 10
```

### 8.3 LLM Strategy for Cloud Deployment

> [!IMPORTANT]
> Local Ollama is not available on Streamlit Cloud. Use Groq API for fast, free-tier LLM inference.

| Aspect | Choice | Rationale |
| -------- | -------- | ----------- |
| **LLM Provider** | **Groq API** | Free tier available, ultra-fast inference (~500 tokens/sec), no cold starts |
| **Model** | `llama-3.3-70b-versatile` | Best quality on Groq free tier, excellent instruction following |
| **Fallback** | `llama-3.1-8b-instant` | Faster, lower latency for simple queries |
| **Alternative** | Google Gemini API | Free tier available, good quality |

### 8.4 System Requirements (Streamlit Cloud)

| Resource | Streamlit Cloud Free Tier | Notes |
| ---------- | --------------------------- | ------- |
| **CPU** | Shared | Sufficient for RAG pipeline |
| **RAM** | 1 GB | Tight — use lightweight models |
| **Storage** | 1 GB | ChromaDB + embeddings must fit |
| **Timeout** | 60 minutes idle | App sleeps after inactivity |
| **Bandwidth** | Unlimited | No restrictions |

> [!WARNING]
> Streamlit Cloud free tier has 1GB RAM limit. BGE-M3 (~1.2GB) may exceed this.
> Use `sentence-transformers/all-MiniLM-L6-v2` (90MB) as embedding model for cloud deployment.

### 8.5 Tech Stack Summary

| Layer | Technology | Version |
| ------- | ------------ | --------- |
| **Frontend/Backend** | Streamlit | 1.40+ |
| **Hosting** | Streamlit Community Cloud | Free tier |
| **LLM Provider** | Groq API | Latest |
| **LLM Model** | Llama 3.3 70B Versatile | via Groq |
| **Embedding Model** | all-MiniLM-L6-v2 | via sentence-transformers |
| **Reranker** | cross-encoder/ms-marco-MiniLM-L-6-v2 | - |
| **Vector Store** | ChromaDB (embedded) | 0.4+ |
| **PDF Parsing** | PyMuPDF4LLM | 0.0.10+ |
| **Classifier** | transformers (BART-MNLI) | 4.40+ |
| **Logging** | Streamlit session state + JSON | - |
| **Python** | 3.11+ | - |

### 8.6 Deployment Steps

1. **Prepare Repository**:
   - Ensure `app.py` is in repository root
   - Commit `requirements.txt` with all dependencies
   - Commit pre-built `chroma_db/` folder with vector embeddings
   - Add `.streamlit/config.toml` for theming

2. **Configure Streamlit Cloud**:
   - Connect GitHub repository to [share.streamlit.io](https://share.streamlit.io)
   - Set main file path: `app.py`
   - Add secrets via Streamlit Cloud dashboard (Groq API key)

3. **Deploy**:
   - Streamlit Cloud auto-deploys on Git push
   - App URL: `https://<app-name>.streamlit.app`

### 8.7 Application Entry Points

| Function | Description |
| ---------- | ------------- |
| `main()` | Streamlit app entry point, renders UI and handles chat |
| `ask_question(query)` | Core RAG pipeline: retrieval → rerank → generate → validate |
| `load_vectorstore()` | Initializes ChromaDB from committed `chroma_db/` folder |
| `get_llm_response()` | Calls Groq API with context and prompt |

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
| -------- | ----------- |
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

## 10. Data Quality & Integrity

### 10.1 Cross-Scheme Contamination Prevention

> [!WARNING]
> Cross-scheme contamination occurs when facts from one scheme are retrieved for a query about a different scheme. This is a critical failure mode for financial RAG systems.

**Ingestion-Time Isolation**:

| Rule | Implementation |
| ------ | ---------------- |
| **Scheme-per-document tagging** | Parser extracts scheme name from document header/filename and propagates to every chunk—no chunk exists without explicit scheme attribution |
| **Reject ambiguous documents** | If a document covers multiple schemes (e.g., SAI) → split into scheme-specific sections before chunking; each chunk tagged with exactly one scheme |
| **Namespace separation** | ChromaDB metadata uses `{amc_name}_{scheme_code}` for filtering |

**Retrieval-Time Isolation**:

| Rule | Implementation |
| ------ | ---------------- |
| **Mandatory scheme filter** | If query mentions a specific scheme name → retrieval **must** filter by `scheme_name` OR `scheme_code` before similarity ranking |
| **Cross-scheme detection** | If top-3 retrieved chunks contain >1 distinct `scheme_name` → flag as contamination risk; rerank with strict scheme filter |
| **Answer validation** | Post-generation check ensures cited `source_url` matches the scheme mentioned in query |

**Contamination Audit**:

- Log any response where retrieved chunks span multiple schemes
- Weekly audit report: count of cross-scheme retrievals; investigate if > 2% of queries

### 10.2 Staleness Handling

**Age Thresholds by Document Type**:

| Document Type | Stale After | Rationale |
| --------------- | ------------- | ----------- |
| AMFI NAV | 1 day | Daily updates expected |
| Monthly Factsheets | 45 days | Monthly publication cycle + buffer |
| KIM/SID | 365 days | Annual updates typical |
| SEBI Circulars | Never | Regulatory baseline remains valid |

**Staleness Detection**:

- Each chunk carries calculated field `is_stale: boolean` based on `extraction_date` vs. current date
- Staleness computed at query time, not ingestion time

**Staleness Handling Workflow**:

| Phase | Action |
| ------- | -------- |
| **Retrieval** | Stale chunks deprioritized in reranking (score multiplier × 0.8) |
| **Generation** | If any top-3 chunks are stale → append: `"⚠️ This information may be outdated. Last sourced: {extraction_date}."` |
| **Ingestion** | On re-crawl, compare `checksum`; if mismatch → mark old chunks as `superseded_by: <new_chunk_id>` |

**Version Control**:

- Superseded chunks not deleted; moved to `archive` collection with `superseded_date`, `replacement_chunk_id`
- Enables rollback and temporal queries ("What was the TER in 2025?")

**Proactive Refresh Schedule**:

| Source | Refresh Frequency |
| -------- | ------------------- |
| AMFI NAV | Weekly auto-crawl |
| Factsheets | Monthly auto-crawl |
| KIM/SID | Quarterly check |
| SEBI Circulars | Manual trigger on new release |

### 10.3 Freshness Tracking ("Last Updated from Sources")

**Per-Chunk Tracking**:

- `extraction_date`: When chunk was ingested into vector store
- `document_date`: Official publication date from source document
- Citation format includes date: `[Source: <URL> | Updated: <document_date>]`

**Response-Level Freshness Display**:

- For each response, compute `min(extraction_date)` across all retrieved chunks used
- Append footer: `"📅 Last updated from sources: {earliest_extraction_date}"`

**Freshness Index**:

Maintain `freshness_index.json` updated at each ingestion:

```json
{
  "scheme_name": "HDFC Large Cap Fund",
  "document_type": "KIM",
  "last_extraction_date": "2026-02-04",
  "last_document_date": "2026-01-01",
  "next_scheduled_refresh": "2026-03-01"
}
```

**Audit Trail for Freshness Claims**:

Every log entry records:

- `source_urls_used`: List of URLs contributing to answer
- `extraction_dates`: Corresponding ingestion timestamps
- `oldest_source_date`: For the "Last updated" footer

**Freshness SLA**:

| Fact Category | Max Age |
| --------------- | --------- |
| Dynamic facts (TER, NAV, AUM) | 90 days |
| Static facts (objective, benchmark) | 1 year |

- Automated alert if any query violates SLA → trigger re-ingestion

---

## 11. Security Considerations

| Concern | Mitigation |
| --------- | ------------ |
| **Prompt Injection** | Input sanitization (strip special chars), system prompt isolation |
| **Data Exfiltration** | No user data stored; stateless queries |
| **Model Jailbreaking** | Refusal classifier + post-generation validation |
| **Source Integrity** | Only whitelisted domains ingested; checksums for documents |
| **API Abuse** | Rate limiting (10 req/min/IP) on public endpoints |

---

## 12. Future Enhancements (Out of Scope for MVP)

1. **Multi-AMC Support**: Extend to ICICI Prudential, SBI MF, etc.
2. **Real-Time NAV**: Integrate AMFI daily NAV API for fresh data.
3. **Hindi Language Support**: Add Hindi prompts and UI localization.
4. **Feedback Loop**: User thumbs-up/down to fine-tune reranker.
5. **Upgrade to BGE-M3**: Use larger embedding model with Streamlit Cloud paid tier.
6. **Custom Domain**: Configure custom domain for production branding.

---

## 13. Complete HDFC AMC Document URLs (25 Documents)

> [!IMPORTANT]
> All URLs must be verified before ingestion. Document availability may change; run health check weekly.

### 13.1 Scheme Information Documents (SID) — 5 Documents

| # | Scheme | URL |
| --- | -------- | ----- |
| 1 | HDFC Large Cap Fund | `https://www.hdfcfund.com/investor-services/fund-documents/sid` |
| 2 | HDFC Flexi Cap Fund | `https://www.hdfcfund.com/investor-services/fund-documents/sid` |
| 3 | HDFC Tax Saver (ELSS) | `https://www.hdfcfund.com/investor-services/fund-documents/sid` |
| 4 | HDFC Balanced Advantage Fund | `https://www.hdfcfund.com/investor-services/fund-documents/sid` |
| 5 | HDFC Liquid Fund | `https://www.hdfcfund.com/investor-services/fund-documents/sid` |

### 13.2 Key Information Memorandum (KIM) — 5 Documents

| # | Scheme | URL |
| --- | -------- | ----- |
| 6 | HDFC Large Cap Fund | `https://www.hdfcfund.com/explore/mutual-funds/hdfc-large-cap-fund/direct` |
| 7 | HDFC Flexi Cap Fund | `https://www.hdfcfund.com/explore/mutual-funds/hdfc-flexi-cap-fund/direct` |
| 8 | HDFC Tax Saver (ELSS) | `https://www.hdfcfund.com/explore/mutual-funds/hdfc-elss-tax-saver/direct` |
| 9 | HDFC Balanced Advantage Fund | `https://www.hdfcfund.com/explore/mutual-funds/hdfc-balanced-advantage-fund/direct` |
| 10 | HDFC Liquid Fund | `https://www.hdfcfund.com/explore/mutual-funds/hdfc-liquid-fund/direct` |

### 13.3 Statement of Additional Information (SAI) — 1 Document

| # | Document | URL |
| --- | ---------- | ----- |
| 11 | HDFC AMC SAI (covers all schemes) | `https://www.hdfcfund.com/literature/statement-of-additional-information` |

### 13.4 Scheme Summary — 1 Document

| # | Document | URL |
| --- | ---------- | ----- |
| 12 | All Schemes Summary | `https://www.hdfcfund.com/investor-services/fund-documents/scheme-summary` |

### 13.5 Monthly Factsheets — 1 Document

| # | Document | URL |
| --- | ---------- | ----- |
| 13 | All Schemes Factsheets | `https://www.hdfcfund.com/investor-services/factsheets` |

### 13.6 Leaflets — 1 Document

| # | Document | URL |
| --- | ---------- | ----- |
| 14 | All Schemes Leaflets | `https://www.hdfcfund.com/investor-services/fund-literature/leaflets` |

### 13.7 Presentations — 1 Document

| # | Document | URL |
| --- | ---------- | ----- |
| 15 | All Schemes Presentations | `https://www.hdfcfund.com/investor-services/fund-literature/presentation` |

### 13.8 AMFI Data Sources — 4 Documents

| # | Document | URL |
| --- | ---------- | ----- |
| 17 | Daily NAV (all schemes) | `https://www.amfiindia.com/spages/NAVAll.txt` |
| 18 | Scheme Master Data | `https://www.amfiindia.com/research-information/other-data/scheme-master` |
| 19 | Monthly AUM Data | `https://www.amfiindia.com/research-information/aum-data/aum-month-end` |
| 20 | Investor Complaints | `https://www.amfiindia.com/research-information/other-data/data-on-investor-complaints` |

### 13.9 SEBI Regulatory References — 5 Documents

| # | Document | URL |
| --- | ---------- | ----- |
| 21 | Mutual Fund Categorization | `https://www.sebi.gov.in/legal/circulars/oct-2017/categorization-and-rationalization-of-mutual-fund-schemes_36199.html` |
| 22 | Total Expense Ratio Limits | `https://www.sebi.gov.in/legal/circulars/sep-2018/total-expense-ratio-of-mutual-fund-schemes_40505.html` |
| 23 | Risk-o-Meter Guidelines | `https://www.sebi.gov.in/legal/circulars/oct-2020/circular-on-product-labeling-in-mutual-funds-_47868.html` |
| 24 | KYC Norms for MF | `https://www.sebi.gov.in/legal/circulars/mar-2014/kyc-requirements-for-mutual-fund-unitholders_26561.html` |
| 25 | ELSS Guidelines | `https://www.sebi.gov.in/legal/circulars/jun-2017/guidelines-for-filing-of-draft-scheme-information-document-sid-for-equity-linked-savings-scheme-elss_35135.html` |

### 13.10 Document Inventory Summary

| Category | Count | Update Frequency |
| ---------- | ------- | ------------------ |
| SID | 5 | Annual / On change |
| KIM | 5 | Annual / On change |
| SAI | 1 | Annual |
| Factsheets | 5 | Monthly |
| AMFI Data | 4 | Daily / Monthly |
| SEBI Circulars | 5 | As issued |
| **Total** | **25** | Mixed |

---

## 14. Sample Q&A Test Cases

### 14.1 Factual Queries (Should Answer)

| # | Query | Expected Response Pattern |
| --- | ------- | --------------------------- |
| 1 | "What is the expense ratio of HDFC Large Cap Fund?" | "The Total Expense Ratio (TER) for HDFC Large Cap Fund - Regular Plan is X.XX%... [Source: hdfcfund.com/...]" |
| 2 | "What is the lock-in period for HDFC ELSS?" | "HDFC Tax Saver (ELSS) has a mandatory lock-in period of 3 years... [Source: hdfcfund.com/...]" |
| 3 | "Who is the fund manager of HDFC Flexi Cap Fund?" | "HDFC Flexi Cap Fund is managed by [Name]... [Source: hdfcfund.com/...]" |
| 4 | "What is the minimum SIP amount for HDFC Liquid Fund?" | "The minimum SIP investment in HDFC Liquid Fund is ₹X... [Source: hdfcfund.com/...]" |
| 5 | "What is the benchmark index for HDFC Balanced Advantage Fund?" | "HDFC Balanced Advantage Fund is benchmarked against... [Source: hdfcfund.com/...]" |

### 14.2 Refusal Queries (Should Refuse)

| # | Query | Expected Classifier Label | Expected Response |
| --- | ------- | --------------------------- | ------------------- |
| 1 | "Is HDFC Large Cap better than SBI Bluechip?" | `investment advice` (score > 0.7) | "I cannot provide fund comparisons... consult a SEBI-registered advisor. [Source: N/A]" |
| 2 | "Should I invest in HDFC ELSS for tax saving?" | `investment advice` (keyword: "should I invest") | Immediate refusal via keyword blocklist |
| 3 | "Which HDFC fund will give best returns?" | `investment advice` (keywords: "which fund", "best") | Immediate refusal via keyword blocklist |
| 4 | "Recommend a good SIP for beginners" | `investment advice` (keyword: "recommend") | Immediate refusal via keyword blocklist |
| 5 | "Will HDFC Flexi Cap outperform the market?" | `investment advice` (prediction) | Refusal — prediction/advice |
| 6 | "How much should I allocate to large cap?" | `investment advice` (keyword: "allocate") | Immediate refusal via keyword blocklist |

### 14.3 Edge Cases (Requires Careful Handling)

| # | Query | Classification | Expected Handling |
| --- | ------- | ---------------- | ------------------- |
| 1 | "What was the 5-year return of HDFC Large Cap?" | Factual | Answer if historical return exists in source docs |
| 2 | "Is HDFC Large Cap safe?" | Opinion request | Refuse — subjective/opinion |
| 3 | "What is the risk category of HDFC Liquid Fund?" | Factual | Answer with SEBI risk-o-meter rating |
| 4 | "Compare ELSS lock-in with PPF lock-in" | Off-topic (PPF not in scope) | Refuse — cannot answer about PPF |
| 5 | "What is NAV?" | Factual (general) | Answer with definition from AMFI source |

### 14.4 Confidence Gate Test Cases

| # | Query | Expected Behavior |
| --- | ------- | ------------------- |
| 1 | "What is the weather today?" | All retrieval scores < 0.4 → Immediate refusal without LLM call |
| 2 | "Tell me about Bitcoin" | All retrieval scores < 0.4 → Immediate refusal without LLM call |
| 3 | "Explain quantum computing" | All retrieval scores < 0.4 → Immediate refusal without LLM call |

---

## 15. UI Requirements & Disclaimer

### 15.1 Mandatory Disclaimer (Must Display)

> [!CAUTION]
> The following disclaimer MUST be displayed prominently on every page of the UI.

**Disclaimer Text (Fixed)**:

```text
⚠️ DISCLAIMER: This is a facts-only assistant. No investment advice.
• Answers are sourced from official HDFC AMC, AMFI, and SEBI documents.
• This tool does NOT provide personalized investment recommendations.
• Past performance is not indicative of future results.
• For investment decisions, consult a SEBI-registered investment advisor.
```

### 15.2 Disclaimer Placement

| Location | Display Style |
| ---------- | --------------- |
| **Header Banner** | Persistent yellow/orange banner at top of page. Non-dismissible. |
| **Chat Input Area** | Subtle reminder above input: "Ask factual questions only. No advice provided." |
| **Response Footer** | Every response ends with: "📖 This is factual information, not investment advice." |

### 15.3 UI Component Specifications

```text
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

### 15.4 Legal & Compliance Notes

| Requirement | Implementation |
| ------------- | ---------------- |
| **SEBI Compliance** | Disclaimer follows SEBI advertising guidelines for mutual funds |
| **No Personalization** | No user accounts, no saved preferences, no personalized suggestions |
| **Audit-Ready** | All queries and responses logged with timestamps |
| **Source Attribution** | Every answer links to official source; no unattributed claims |

---

## 16. Summary Checklist

| Requirement | Solution |
| ------------- | ---------- |
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
| ✅ **Metadata schema** | 16 mandatory fields per chunk including fact_type, plan_type, checksums |
| ✅ **Cross-scheme isolation** | Scheme-per-chunk tagging + retrieval-time filtering + contamination audit |
| ✅ **Staleness handling** | Age thresholds by doc type, stale chunk deprioritization, version control |
| ✅ **Freshness tracking** | extraction_date + document_date per chunk, response footer with last updated |

---

*Document prepared for Groww RAG MVP — Facts Only, Citations Always.*
