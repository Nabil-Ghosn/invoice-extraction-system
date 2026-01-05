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

### 5. Database ODM: Beanie

**Candidates:** *PyMongo (Raw), MongoEngine (Sync), SQLModel (SQL), Beanie (Async).*

**Decision:** **Beanie** chosen mainly for **fast development**.  

* Built on `Motor` (async) + Pydantic, so LLM outputs persist directly to MongoDB with minimal code.  
* Non‑blocking writes fit our concurrent invoice processing.  
* Trade‑off: adds abstraction overhead.

### 6. Embedding Model: Google Vertex AI (`gemini-embedding-001`)

**Candidates Evaluated:**

* **Closed Source / API:**
  * **OpenAI (`text-embedding-3-large`):** High performance, standard choice.
  * **Google (`gemini-embedding-001`):** Chosen. Native integration with Gemini.
  * **LlamaCloudEmbedding**
* **Open Source / Local (SOTA):**
  * **`Alibaba-NLP/gte-Qwen2-7B-instruct`:** Currently dominates the [MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard). Exceptional performance but requires significant GPU VRAM (7B parameters) to run efficiently.
  * **`jina-embeddings-v3`:** Excellent for long-context and supports "Matryoshka" (flexible) dimensions. Great local alternative.
  * **`BAAI/bge-m3`:** Strong baseline for multi-lingual and dense retrieval.

**Decision:** **Google `gemini-embedding-001`**

**The Rationale:**

1. **Asymmetric Retrieval (Instruction-Tuned):**
    * Our use case is **Asymmetric**: mapping short, intent-driven queries (*"How much for labor?"*) to structured data blocks (*"Item: Install, Price: $500"*).
    * Unlike older symmetric models, `gemini-embedding-001` (like `Qwen2-Instruct` and `Jina-v3`) accepts **Task Instructions**. We explicitly instruct the model to optimized embeddings for `"retrieval_document"` vs `"retrieval_query"`, significantly boosting precision.
2. **MTEB "Retrieval" Metric:**
    * We focused strictly on the **Retrieval** score on MTEB. While `gte-Qwen2` scores slightly higher, the infrastructure cost of hosting a 7B parameter model locally outweighs the marginal accuracy gain for this specific task.
    * `gemini-embedding-001` consistently ranks in the top tier for retrieval while offering a serverless, managed API experience.
3. **Dimensionality:**
    * We chose **768 dimensions** to reduce storage and search latency by 75%, pairing it with **Cosine Similarity** to ensure accurate ranking of the non-normalized truncated vectors without requiring manual pre-processing.

## Section 2: Extraction Strategy

> it is helpful to distinguish between Business/Legal Requirements (what should be there) and Technical Extraction Reality (what you actually find).

### 1. Extraction The Challenge

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

## Section 3: Data Modeling & Chunking Strategy

### 1. Chunking Strategy Evaluated

We evaluated three granularities for splitting the 50+ page invoices into retrieval units.

#### Option A: Page-Level Chunking

* **Concept:** Treat each page as a single "chunk" (text + embedding).
* **Pros:** Preserves visual layout context; easy to implement.
* **Cons:** **High Noise Ratio.** A query for "total price of rivets" might retrieve a page with 50 other unrelated items. The LLM then has to hunt for the needle in the haystack.
* **Verdict:** **Rejected.**

#### Option B: Naive Line-Item Chunking

* **Concept:** Extract rows and store them individually. e.g., `{"desc": "Labor", "price": 100}`.
* **Pros:** High granularity for filtering.
* **Cons:** **Semantic Ambiguity.** "Labor" is meaningless without knowing *which* section it belongs to (e.g., "Installation" vs. "Repair") or *who* the vendor is. Vector search fails to differentiate identical items from different invoices.
* **Verdict:** **Rejected.**

#### Option C: Enriched Atomic Line Chunking (Selected)

* **Concept:** Extract per row, but **inject parent context** into every record before indexing.
* **Mechanism:**
  * Raw Row: `{"desc": "Labor", "price": 100}`
  * Enriched Row: `{"desc": "Labor", "section": "Emergency Repairs", "vendor": "Acme Corp", "invoice_id": "INV-001"}`
* **Verdict:** **Selected.** This maximizes retrieval precision while maintaining semantic context.

### 2. Data Modeling Architecture

> we need to separate the Extraction Schema (how we talk to the LLM) from the Storage/Retrieval Schema (how we talk to the database/RAG engine).

We architect the system with two distinct data layers. While enterprise systems often separate *Domain Entities* from *Database Models* (ORM), we have chosen to **collapse these into a single layer** to reduce boilerplate complexity for this specific assignment scope. However, we strictly enforce a separation between **Extraction** and **Storage**.

#### A. Extraction Schema (Input)

* **Purpose:** LLM Output Generation.
* **Characteristics:** Loose, tolerant of nulls.
* **Key Design:** Uses a `PageState` object to handle table headers across page breaks.

```python
class InvoicePage(BaseModel):
    # Critical for sequential processing
    next_page_state: PageState
    # Any global invoice data (ID, Date, Vendor) found strictly on this page.
    invoice_context: InvoiceContext | None
    # Line items detected on this page
    line_items: list[LineItem]
```

#### B. Storage Schema (Output)

* **Purpose:** Database Storage (MongoDB) & Retrieval.
* **Characteristics:** flattened hierarchy, per line items.
* **Structure:** We use two collections to optimize for MongoDB's document limits and vector search.

**Collection 1: `invoices` (Parent)**
Stores global metadata for filtering.

**Collection 2: `line_items` (Child)**
The atomic unit of retrieval.

* **Key Design:** The Flattening Strategy

By flattening `line_items` into their own collection rather than nesting them inside `invoices`:

1. **Granular Vector Search:** We can find specific *items* ("maintenance") without retrieving the whole invoice.
2. **Scalability:** Avoids MongoDB's 16MB document size limit on massive 500+ page invoices.
3. **Hybrid Filtering:** Allows queries like `find({ "invoice_id": "X", "page_number": 3 })` efficiently.

## Section 4: Indexing & Retrieval Strategy

### 1. The Retrieval Challenge

Users require **Hybrid Queries** that combine strict constraints ("Page 3", "Date > 2024") with fuzzy semantic intent ("Maintenance items", "Items from Amzon").
The core challenge is balancing **Precision** (Exact matches for Page Numbers) with **Recall** (Handling typos like "Amzon" or semantic variations like "Laptop" vs "MacBook").

### 2. Core Philosophy: Canonical vs. Semantic Separation

We categorize metadata fields into two distinct buckets to determine their retrieval behavior:

| Category | Fields | Behavior | Rationale |
| :--- | :--- | :--- | :--- |
| **Canonical** | `page_number`, `invoice_date`, `total_amount` | **Strict Pre-Filter** | "Page 3" is a mathematical constant. It must never return Page 4, regardless of vector similarity. |
| **Semantic** | `sender_name`, `description`, `section` | **Vector + Fuzzy Search** | Vendors and Descriptions are prone to OCR errors or user typos ("Amzon"). Strict filtering here causes zero-result failures. |
| **Identifier** | `invoice_id` | **Strict w/ Fallback** | We attempt exact match first. If 0 results, we fall back to fuzzy matching to catch OCR errors (e.g., `l` vs `1`). |

### 3. Strategies Evaluated

* **Option A: Post-Filtered Vector Search**
  * *Logic:* Vector search global database → Filter results in memory.
  * *Verdict:* **Rejected.** Inefficient. Top-k results might be entirely filtered out if the specific invoice is not in the global top matches.
* **Option B: Strict Pre-Filtering on All Fields**
  * *Logic:* Database Filter `sender="Amzon"` AND `page=3`.
  * *Verdict:* **Rejected.** Brittle. A typo in the user query ("Amzon") results in 0 matches, even if the vector model understands the intent.
* **Option C: Hybrid Scope Search (Selected)**
  * *Logic:* Apply **Strict Filters** only on Canonical fields (Page, Date). Allow **Vector/Fuzzy Search** to handle Semantic fields (Vendor, Description) within that scope.
  * *Verdict:* **Selected.** Ensures 100% scoping accuracy (no cross-page hallucinations) while remaining robust against typos.

### 4. Search Text Construction (Context Injection)

To fix the "Context-Poor Embedding" problem (where "Server" could mean IT Hardware or Food Service), we inject hierarchical context into the vector:

* **Formula:** `Context: {sender_name} ({section}) | Item: {description} ({item_code})`
* **Example:** `Context: Dell (Hardware) | Item: PowerEdge R750 (SV-99)`
* **Benefit:** This creates a "Semantic Anchor," allowing the vector model to distinguish between "Apple" (The Fruit Vendor) and "Apple" (The Tech Vendor) based on the `Context` prefix.

### 5. Implementation Details

* **Database:** MongoDB Atlas Vector Search.
* **Index Configuration:**
  * `filter` fields: `invoice_id`, `page_number`, `invoice_date`.
  * `vector` field: `vector` (768 dimensions).
  * `search` field: `sender_name`, `description` (for fuzzy keyword fallback).

## Section 6: RAG & Answer Generation Strategy

### 1. The Challenge: Ambiguity vs. Precision

Users rarely ask pure vector or pure SQL questions. They ask **Hybrid Queries**:
*"Show me maintenance costs (Semantic) on page 3 (Exact Filter)."*

* **Vector Search** fails at exact filtering ("Page 3" isn't a semantic concept).
* **Database Queries** fail at understanding intent ("Maintenance" isn't a column).
* **Solution:** We need a system to translate Natural Language into a structured API payload *before* retrieval.

### 2. Orchestration Strategies Evaluated

#### Option A: Explicit Router (Classifier Pattern)

* **Concept:** Classify intent using small LLM $\to$ Route to hard-coded logic branches.
* **Verdict:** **Rejected.**
* **Reason:** **Separation of Intent & Extraction.** A router identifies *what* the user wants (Intent) but does not automatically extract the *details* (Parameters).
  * *The Bottleneck:* Handling hybrid queries requires maintaining a rigid web of `if/else` logic for every parameter combination.

#### Option B: ReAct Agent (Loop Pattern)

* **Concept:** Allow LLM to "Think $\to$ Act $\to$ Observe" in a loop.
* **Verdict:** **Rejected.**
* **Reason:** **Latency & Indeterminism.** Open-ended loops increase the risk of hallucination and timeouts.

#### Option C: Single-Step Function Calling (Selected)

* **Concept:** The LLM selects the tool *and* extracts the arguments in a single inference step.
* **Verdict:** **Selected.**

### 3. Final Decision: LlamaIndex Function Calling Agent

We utilize **Gemini 2.5 Flash** with **LlamaIndex** function calling.

* **The Decider: Dynamic Schema Mapping.**
    Function calling unifies **Intent Recognition** and **Parameter Extraction**.
  * It eliminates the need to hard-code specific branches for "Date Search" vs "Page Search" vs "Combined Search."
* **Trade-off:** **Dependency.** Relies on the model's ability to adhere strictly to JSON schemas (Flash excels here; smaller models struggle).

### 4. Tool Definition Strategy

We restrict the Agent to two atomic tools to prevent hallucination:

1. **`search_line_items(query: str, filters: InvoiceFilter)`**
    * **Role:** The Workhorse.
    * **Logic:** Executes the **Hybrid Scope Search** (Section 4). It performs vector search *inside* the mathematical bounds of the filters (Page, Date).
2. **`get_invoice_metadata(invoice_id: str)`**
    * **Role:** The Summarizer.
    * **Logic:** Retrieves document-level totals and vendor details when granular line-item search is unnecessary.

### 5. Grounding & Synthesis

To ensure zero-hallucination responses:

* **Negative Constraint:** System Prompt forbids general knowledge. *"If tool returns empty, state: 'No data found'."*
* **Citation Injection:** Final answers must include citations derived from the tool output (e.g., `Found item X (Page 4)`).

### 6. Answer Generation with Gemini (Top-K Retrieval)

Once the top 'k' relevant results are retrieved based on the user query, they are passed as context to a final Gemini prompt. The LLM then synthesizes this information to generate a direct and accurate answer.

## Section 7: Evaluation & Repo Structure

### 1. Project Structure

This structure enforces the **Modular Monolith** architecture, strictly separating the "Write Path" (Ingestion) from the "Read Path" (Retrieval) while sharing domain kernels.

```text
invoice-extraction-system/
├── data/                       # Sample invoices (PDFs) and Golden Truth JSONs
├── design/                     # Architecture diagrams (Mermaid/Images)
├── src/
│   ├── core/                   # SHARED KERNEL
│   │   ├── config.py           # Env vars & Settings
│   │   ├── database.py         # MongoDB/Beanie connection logic
│   │   ├── models.py           # Domain Entities (Invoice, LineItem)
│   │   └── services.py         # Shared Embedder Service
│   │
│   ├── ingestion/              # WRITE PATH (Heavy Compute)
│   │   ├── parser.py           # LlamaParse Adapter
│   │   ├── extractor.py        # LLM Chain (Stateful Extraction)
|   |   ├── cmd_repository.py   # Write path Repository
│   │   └── service.py          # Orchestrator
│   │
│   ├── retrieval/              # READ PATH (Low Latency)
│   │   ├── router.py           # LLM Intent Classifier (Function Calling)
│   │   ├── translator.py       # Query Builder (Tool -> Mongo Pipeline)
│   │   ├── repository.py       # Database Execution Layer
│   │   └── service.py          # RAG Orchestrator
│   │
│   └── main.py                 # CLI Entrypoint (Typer/Click)
│
├── tests/                      # Pytest Suite
├── .env.example                # Config Template
├── APPROACH.md                 # Design Decisions & Trade-offs (Crucial)
├── docker-compose.yml          # MongoDB Atlas or Local Mongo container
├── pyproject.toml              # Dependencies (Poetry)
└── README.md                   # Setup & Usage Instructions
```

### 2. Evaluation Strategy (In Progress)

Since we lack a massive labeled dataset, we evaluate using a **"Golden Set" Small-Scale Validation** approach.

#### A. Extraction Evaluation (Accuracy)

* **Method:** Create manual "Golden JSON" files for 3 diverse invoices (1 Simple, 1 Multi-page, 1 Complex).
* **Metrics:**
  * **Field-Level Precision:** `%` of fields (Date, Total Amount, Invoice ID) that exactly match the Golden JSON.
  * **Table Row Count:** `ABS(Extracted_Rows - Actual_Rows)`. Detects missed line items.
  * **Hallucination Check:** Verify if `Page Number` in extracted items actually exists in the PDF.

#### B. Retrieval Evaluation (Recall)

* **Method:** specialized unit tests (`tests/test_retrieval.py`) with pre-defined queries.
* **Metrics:**
  * **Hit Rate:** For the query *"Line items on page 3"*, do the returned database records strictly equal `page_number=3`?
  * **Semantic Ranking:** For *"Labor costs"*, does the top result contain "Labor" or "Work" in the description?

#### C. RAG Evaluation (Faithfulness)

* **Method:** **LLM-as-a-Judge**.
* **Process:**
    1. Generate Answer $A$ based on Context $C$.
    2. Ask a separate LLM instance: *"Does statement $A$ contain any facts not present in $C$?"*
* **Metric:** Pass/Fail on Grounding.

---

### 3. Deliverable Checklist

* [ ] **APPROACH.md:** Explains *why* MongoDB was chosen over SQL, and *why* LlamaParse was used over PyTesseract.
* [ ] **Architecture Diagram:** The Mermaid flowchart in `design/architecture.md`.
* [ ] **CLI:** `python main.py ingest --file invoice.pdf` and `python main.py ask "Total cost of labor?"`.
* [*] **Docker:** `docker-compose up -d` spins up the DB.

**This concludes the architectural design phase.**
You are now ready to generate the code.
