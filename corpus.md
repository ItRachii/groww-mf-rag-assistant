# Groww Mutual Fund FAQ — Corpus Definition

> **Version**: 1.0  
> **Date**: 2026-02-04  
> **Status**: Ready for Ingestion  

---

## 1. Corpus Overview

| Attribute | Value |
|-----------|-------|
| **AMC** | HDFC Asset Management Company Ltd. |
| **Number of Schemes** | 5 |
| **Total Documents** | 25 |
| **Source Domains** | `hdfcfund.com`, `amfiindia.com`, `sebi.gov.in` |
| **Document Types** | SID, KIM, Factsheet, SAI, AMFI Data, SEBI Circulars |

---

## 2. Selected Schemes

| # | Scheme Name | Category | AMFI Code | Rationale |
|---|-------------|----------|-----------|-----------|
| 1 | HDFC Top 100 Fund | Large Cap | 100032 | Blue-chip, stable documentation |
| 2 | HDFC Flexi Cap Fund | Flexi Cap | 100394 | Multi-cap flexibility |
| 3 | HDFC Tax Saver (ELSS) | ELSS | 100186 | Tax-saving, lock-in rules |
| 4 | HDFC Balanced Advantage Fund | Hybrid | 100171 | Dynamic allocation |
| 5 | HDFC Liquid Fund | Liquid | 100027 | Low-risk category |

---

## 3. Complete Corpus (25 URLs)

### 3.1 Scheme Information Documents (SID) — Fund Objectives, Risk Factors, Investment Strategy

| # | AMC | Scheme | URL | Document Type | Expected Facts |
|---|-----|--------|-----|---------------|----------------|
| 1 | HDFC AMC | HDFC Top 100 Fund | `https://www.hdfcfund.com/literature/scheme-information-document/hdfc-top-100-fund` | SID | Investment objective, asset allocation, risk factors, fund manager details |
| 2 | HDFC AMC | HDFC Flexi Cap Fund | `https://www.hdfcfund.com/literature/scheme-information-document/hdfc-flexi-cap-fund` | SID | Investment objective, multi-cap strategy, risk factors |
| 3 | HDFC AMC | HDFC Tax Saver (ELSS) | `https://www.hdfcfund.com/literature/scheme-information-document/hdfc-taxsaver` | SID | 3-year lock-in, Section 80C eligibility, investment objective |
| 4 | HDFC AMC | HDFC Balanced Advantage Fund | `https://www.hdfcfund.com/literature/scheme-information-document/hdfc-balanced-advantage-fund` | SID | Dynamic equity-debt allocation model, rebalancing rules |
| 5 | HDFC AMC | HDFC Liquid Fund | `https://www.hdfcfund.com/literature/scheme-information-document/hdfc-liquid-fund` | SID | Investment in money market instruments, maturity limits |

### 3.2 Key Information Memorandum (KIM) — Expense Ratio, Exit Load, SIP Minimums

| # | AMC | Scheme | URL | Document Type | Expected Facts |
|---|-----|--------|-----|---------------|----------------|
| 6 | HDFC AMC | HDFC Top 100 Fund | `https://www.hdfcfund.com/literature/key-information-memorandum/hdfc-top-100-fund` | KIM | TER (Regular/Direct), exit load (1% if < 1 year), min SIP ₹500 |
| 7 | HDFC AMC | HDFC Flexi Cap Fund | `https://www.hdfcfund.com/literature/key-information-memorandum/hdfc-flexi-cap-fund` | KIM | TER, exit load structure, min lumpsum ₹100 |
| 8 | HDFC AMC | HDFC Tax Saver (ELSS) | `https://www.hdfcfund.com/literature/key-information-memorandum/hdfc-taxsaver` | KIM | TER, no exit load (lock-in applies), min SIP ₹500 |
| 9 | HDFC AMC | HDFC Balanced Advantage Fund | `https://www.hdfcfund.com/literature/key-information-memorandum/hdfc-balanced-advantage-fund` | KIM | TER, exit load (1% if < 1 year), min investment |
| 10 | HDFC AMC | HDFC Liquid Fund | `https://www.hdfcfund.com/literature/key-information-memorandum/hdfc-liquid-fund` | KIM | TER (~0.20%), graded exit load (Day 1-7), min ₹100 |

### 3.3 Monthly Factsheets — Benchmark, Returns, Portfolio Holdings, Riskometer

| # | AMC | Scheme | URL | Document Type | Expected Facts |
|---|-----|--------|-----|---------------|----------------|
| 11 | HDFC AMC | HDFC Top 100 Fund | `https://www.hdfcfund.com/literature/factsheet/hdfc-top-100-fund` | Factsheet | Benchmark (Nifty 100 TRI), AUM, top 10 holdings, riskometer |
| 12 | HDFC AMC | HDFC Flexi Cap Fund | `https://www.hdfcfund.com/literature/factsheet/hdfc-flexi-cap-fund` | Factsheet | Benchmark (Nifty 500 TRI), sector allocation, returns |
| 13 | HDFC AMC | HDFC Tax Saver (ELSS) | `https://www.hdfcfund.com/literature/factsheet/hdfc-taxsaver` | Factsheet | Benchmark (Nifty 500 TRI), riskometer, 1/3/5 year returns |
| 14 | HDFC AMC | HDFC Balanced Advantage Fund | `https://www.hdfcfund.com/literature/factsheet/hdfc-balanced-advantage-fund` | Factsheet | Equity-debt split, benchmark, dynamic allocation % |
| 15 | HDFC AMC | HDFC Liquid Fund | `https://www.hdfcfund.com/literature/factsheet/hdfc-liquid-fund` | Factsheet | Benchmark (CRISIL Liquid AI), avg maturity, YTM |

### 3.4 Statement of Additional Information (SAI) — AMC Details, Legal Structure

| # | AMC | Scheme | URL | Document Type | Expected Facts |
|---|-----|--------|-----|---------------|----------------|
| 16 | HDFC AMC | All Schemes | `https://www.hdfcfund.com/literature/statement-of-additional-information` | SAI | AMC registration, trustee details, investor rights, grievance process |

### 3.5 AMFI Official Data — NAV, AUM, Scheme Codes

| # | AMC | Scheme | URL | Document Type | Expected Facts |
|---|-----|--------|-----|---------------|----------------|
| 17 | AMFI | All Schemes | `https://www.amfiindia.com/spages/NAVAll.txt` | NAV Data | Daily NAV for all schemes, scheme codes |
| 18 | AMFI | All Schemes | `https://www.amfiindia.com/research-information/other-data/scheme-master` | Scheme Master | ISIN, scheme type, launch date, registrar |
| 19 | AMFI | All Schemes | `https://www.amfiindia.com/research-information/aum-data/aum-month-end` | AUM Data | Monthly AUM by scheme |
| 20 | AMFI | All Schemes | `https://www.amfiindia.com/investor-corner/knowledge-center/what-is-mutual-fund` | Knowledge Base | MF basics, NAV definition, SIP explanation |

### 3.6 SEBI Regulatory References — Category Definitions, TER Limits, Riskometer Rules

| # | AMC | Scheme | URL | Document Type | Expected Facts |
|---|-----|--------|-----|---------------|----------------|
| 21 | SEBI | All Categories | `https://www.sebi.gov.in/legal/circulars/oct-2017/categorization-and-rationalization-of-mutual-fund-schemes_36199.html` | Circular | Large Cap = top 100 stocks, Flexi Cap rules, ELSS definition |
| 22 | SEBI | All Categories | `https://www.sebi.gov.in/legal/circulars/sep-2018/total-expense-ratio-of-mutual-fund-schemes_40505.html` | Circular | TER slabs by AUM, max 2.25% for equity |
| 23 | SEBI | All Categories | `https://www.sebi.gov.in/legal/circulars/oct-2020/circular-on-product-labeling-in-mutual-funds-_47868.html` | Circular | Riskometer categories (Low to Very High), color codes |
| 24 | SEBI | ELSS | `https://www.sebi.gov.in/legal/circulars/jun-2017/guidelines-for-filing-of-draft-scheme-information-document-sid-for-equity-linked-savings-scheme-elss_35135.html` | Circular | 3-year lock-in mandate, Section 80C limit |
| 25 | SEBI | Capital Gains | `https://www.sebi.gov.in/legal/circulars/mar-2023/rationalization-of-investor-grievance-redressal-mechanism_68744.html` | Circular | Investor grievance process, statement access |

---

## 4. Expected Facts Coverage Matrix

| Fact Category | Source Documents | Count |
|---------------|------------------|-------|
| **Investment Objective** | SID (1-5) | 5 |
| **Expense Ratio (TER)** | KIM (6-10), SEBI (22) | 6 |
| **Exit Load** | KIM (6-10) | 5 |
| **SIP Minimum** | KIM (6-10) | 5 |
| **Lumpsum Minimum** | KIM (6-10) | 5 |
| **Lock-in Period** | SID (3), KIM (8), SEBI (24) | 3 |
| **Benchmark Index** | Factsheet (11-15) | 5 |
| **Riskometer** | Factsheet (11-15), SEBI (23) | 6 |
| **Fund Manager** | SID (1-5), Factsheet (11-15) | 10 |
| **Portfolio Holdings** | Factsheet (11-15) | 5 |
| **NAV** | AMFI (17) | 1 |
| **AUM** | Factsheet (11-15), AMFI (19) | 6 |
| **Category Definition** | SEBI (21) | 1 |
| **Capital Gains/Statement** | SEBI (25) | 1 |

---

## 5. Document Ingestion Schedule

| Document Type | Refresh Frequency | Validation Method |
|---------------|-------------------|-------------------|
| SID | Annually / On amendment | Checksum + date header |
| KIM | Annually / On amendment | Checksum + date header |
| Factsheet | Monthly (by 10th) | Date in filename |
| SAI | Annually | Checksum |
| AMFI NAV | Daily (skip weekends) | Row count validation |
| AMFI AUM | Monthly | Date header |
| SEBI Circulars | On publication | Manual review |

---

## 6. URL Verification Checklist

| # | URL Status | Last Verified | Notes |
|---|------------|---------------|-------|
| 1-5 | ⏳ Pending | — | Verify PDF/HTML availability |
| 6-10 | ⏳ Pending | — | Verify TER tables extractable |
| 11-15 | ⏳ Pending | — | Verify monthly update |
| 16 | ⏳ Pending | — | Single document for all schemes |
| 17-20 | ⏳ Pending | — | AMFI pages may require parsing |
| 21-25 | ⏳ Pending | — | SEBI PDFs, check circular numbers |

> [!IMPORTANT]
> Run URL health check before ingestion. Mark each as ✅ after verification.

---

## 7. Corpus Statistics (Estimated)

| Metric | Estimate |
|--------|----------|
| **Total Documents** | 25 |
| **Total Pages (PDF)** | ~300-400 |
| **Estimated Tokens** | ~150,000-200,000 |
| **Chunks (@ 512 tokens)** | ~300-400 |
| **Vector DB Size** | ~50-100 MB |

---

*Corpus definition for Groww RAG MVP — Official Sources Only*
