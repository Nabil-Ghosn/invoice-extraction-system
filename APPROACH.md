# APPROACH

## Section 1: Technology Stack & Design Rationale

### 1. Ingestion Engine: LlamaParse

**Candidates:** *Tesseract (OCR), IBM Docling (Local), Azure Doc Intel, LlamaParse.*

* **Decision:** **LlamaParse** (Cloud API)
* **The Decider:** **Layout-Semantic Integrity (Markdown).**
  * Unlike standard OCR which outputs "text soup," LlamaParse reconstructs the **logical topology** of the document (tables, headers, nested rows) into structured Markdown. This is critical for **Level 2** invoices where tables span multiple pages; the LLM receives a coherent table structure rather than disjointed coordinates.
* **Trade-off:** **Data Privacy vs. Velocity.**
  * *Pro:* Immediate state-of-the-art table parsing without GPU infrastructure. As a cloud-native API, it eliminates the heavy infrastructure setup required by local models like Docling
  * *Con:* Document data leaves the local environment (API), a potential friction point for highly sensitive FinTech compliance.
* **Extra:** [best document parsers tradeoffs](https://www.f22labs.com/blogs/5-best-document-parsers-in-2025-tested/)

### 2. Orchestration: LlamaIndex

**Candidates:** *LangChain, PydanticAI, LlamaIndex.*

* **Decision:** **LlamaIndex**
* **The Decider:** **Data-Centric vs. Agent-Centric.**
  * While LangChain excels at conversational agents, LlamaIndex is architected specifically for **Indexing & Retrieval**. Its native `PydanticProgram` and integration with LlamaParse allow us to treat the invoice as a queryable data structure immediately, enforcing strict JSON schemas for extraction.
* **Trade-off:** **Abstraction Overhead.**
  * *Pro:* Streamlined RAG pipeline setup; less boilerplate code.
  * *Con:* High-level abstractions can obscure the underlying prompt logic, making low-level debugging harder than in a lower-level library like LangChain

### 3. LLM: Google Gemini 2.5 Flash

**Candidates:** *GPT-4o, Llama 3 (Local), Gemini 2.5 Flash.*

* **Decision:** **Google Gemini 2.5 Flash**
* **The Decider:** **Cost & 1-Million Token Context Window.**
  * This is the "Level 2" enabler. A 50-page invoice can consume 30k+ tokens. Flash allows us to ingest the **entire document context** in a single pass, eliminating the risk of losing column headers across page breaks.
* **Trade-off:** **Rate Limits.**
  * *Pro:* High throughput and 10x cheaper than GPT-4o.
  * *Con:* Heavy reliance on Vertex AI quotas; requires robust back-off/retry logic during batch processing.

### 4. Database: MongoDB Atlas

**Candidates:** *PostgreSQL (pgvector), Pinecone, Qdrant, MongoDB.*

* **Decision:** **MongoDB Atlas (Vector Search)**
* **The Decider:**
  * **Document‑Native Model:** Invoices are hierarchical (Invoice → Line Items). MongoDB stores the full structure, metadata, and embeddings in a single atomic document, eliminating joins and multi‑system coordination.
  * **Unified Retrieval:** Metadata filtering and semantic search run in one query path. Vector DB (e.g., Qdrant or Pinecone) requires pairing with another database for full invoice storage.
  * **Scalability:** MongoDB provides built‑in sharding, consistent writes, and predictable performance for mixed workloads (updates + search + filtering).
* **Trade-off:** **Specialization.**
  * *Pro:* One system for documents, metadata, and vectors; simpler DevOps and schema evolution.
  * *Con:* Less efficient than a Data Warehouse for massive analytical aggregations (e.g., "Sum total of all invoices ever"). Pure vector engines like Qdrant outperform MongoDB in raw ANN throughput.

## Section 2: Extraction Strategy

> it is helpful to distinguish between Business/Legal Requirements (what should be there) and Technical Extraction Reality (what you actually find).

### 1. The Challenge

Level 2 invoices (50+ pages) present two specific failure modes for extraction:

1. **Headless Tables:** Page 2 contains a grid of numbers without column headers (continuation of Page 1).
2. **Shifting Schemas:** Page 10 might introduce a *new* table (e.g., "Usage Details") with different columns than Page 2 ("Recurring Charges").

### 2. Evaluated Strategies

#### Option A: Whole-Document Context (The "Context Stuffing" approach)

* *Logic:* Feed all 50 pages into Gemini 2.5 Flash in one prompt.
* *Verdict:* **Discarded.**
* *Reason:* While context windows allow this, accuracy degrades on the "middle bits" (Lost in the Middle phenomenon). It is also prohibitively expensive and hard to debug which specific page caused a hallucination.

#### Option B: Parallel Map-Reduce (The "Stateless" approach)

* *Logic:* Process all pages simultaneously. Inject Page 1 (or first few pages to avoid **Headless Resolution**) headers into every page.
* *Verdict:* **Discarded.**
* *Reason:* Fails on  **Shifting Schemas**. If Page 10 starts a *new* table, forcing Page 1's headers (from the parallel context) will cause extraction errors. It assumes a static table structure which implies a false reality for complex invoices.

#### Option C: Sequential Rolling Context (Selected Strategy)

* *Logic:* Process pages strictly in order (1 → 2 → 3). The output of Page $N$ includes a "State Object" (current table schema, active section) passed as input to Page $N+1$.
* *Verdict:* **Selected.**

### 3. Final Decision: The Sequential Chain with Dynamic State

We adopt a **Stateful Sequential Extraction** pipeline. This mimics human reading behavior: we remember the context of the previous page to understand the current one.

**Why this wins:**

* **Drift Handling:** If Page 5 switches from "Services" to "Products," the LLM updates the state. Page 6 receives the *new* schema automatically.
* **Headless Resolution:** Page 2 receives Page 1's schema, allowing it to map raw numbers to "Unit Price" correctly even without visual headers.

**The Trade-off:**

* **Latency:** Processing is linear ($O(N)$), not parallel ($O(1)$). A 50-page invoice will take significantly longer to process.
* **Mitigation:** For a back-office extraction system, **Accuracy > Latency**. We accept higher processing time to ensure zero data loss on complex multi-table documents.
