# Invoice Extraction System Architecture

## 1. Overview

This document outlines the architecture of the Invoice Extraction System, a modular application designed to parse, extract, and query complex, multi-page invoices. The system employs a **stateful extraction pipeline** to handle sophisticated layouts (e.g., headless tables, shifting schemas) and a **Retrieval-Augmented Generation (RAG)** pipeline for intelligent querying.

The core architectural pattern is a **Logical Command Query Responsibility Segregation (CQRS)** implemented within a **Modular Monolith**. This pattern strictly decouples the high-compute ingestion workload (the "Write Path") from the low-latency query workload (the "Read Path"), allowing each to be optimized independently while sharing a common domain model.

## 2. Architectural Pattern: Logical CQRS

- **Write Path (`ingestion` module):** This path is responsible for all heavy-lifting. It takes a raw PDF file and processes it through a multi-stage pipeline involving parsing, AI-driven data extraction, data enrichment, embedding, and finally, database persistence. It is optimized for accuracy and throughput, not low latency.

- **Read Path (`retrieval` module):** This path provides a user-facing query interface. It uses a series of AI and deterministic components to understand a user's query, translate it into a hybrid database query (combining metadata filters and vector search), retrieve relevant data, and synthesize a grounded answer. It is optimized for low-latency, interactive use.

- **Shared Kernel (`core` module):** This central module acts as the connective tissue, providing shared components to both paths. It defines the persistent data models, manages configuration, and offers common utilities like the embedding service, ensuring consistency and preventing code duplication.

## 3. System Components & Data Flow

The system is organized into three primary Python packages: `src/core`, `src/ingestion`, and `src/retrieval`.

```tree
src/
├── core/                  # SHARED KERNEL
│   ├── env_settings.py    # Environment variable management
│   ├── models.py          # Persistent data models for MongoDB (Beanie)
│   ├── extensive_schemas.py  # Pydantic schemas for LLM extraction (multi-page)
│   ├── extracted_schemas.py # Pydantic schemas for LLM extraction (single-page)
│   ├── prompts.py         # Centralized LLM prompts
│   └── services/
│       └── embedder.py    # Shared embedding service client
│
├── ingestion/             # WRITE PATH (Heavy Lifting)
│   ├── ingestion_service.py   # Orchestrator for the ingestion pipeline
│   ├── invoice_parser.py      # LlamaParse wrapper for PDF -> Markdown
│   ├── invoice_extractor.py   # Core LLM extraction logic (rolling context)
│   └── command_invoice_repository.py # Data access layer for writing to DB
│
└── retrieval/             # READ PATH (RAG & Search)
│   ├── retrieval_service.py   # Facade for the retrieval pipeline
│   ├── query_router.py        # LLM-based tool to analyze user query intent
│   ├── answer_generator.py    # LLM to synthesize final answers
│   ├── query_invoice_repository.py # Data access layer for reading from DB
│   └── tools.py               # Pydantic models for retrieval tools
```

### 3.1. Ingestion (Write Path)

The ingestion flow is orchestrated by the `IngestionService` and proceeds as follows:

1. **Deduplication:** A hash of the input file is checked against the database to prevent re-processing.
2. **Parse:** The `InvoiceParser` uses LlamaParse to convert the PDF into structured Markdown, preserving as much layout information as possible.
3. **Extract:** The `InvoiceExtractor` takes the parsed pages and applies one of two strategies:
    - **Single-Shot:** For single-page invoices, a simple, optimized LLM call extracts all data at once.
    - **Sequential Chain:** For multi-page invoices, it iterates through each page, using the **Stateful Sequential Extraction** algorithm (see below) to maintain context.
4. **Enrich & Embed:** The extracted line items are enriched with metadata (e.g., invoice ID, vendor). A descriptive `search_text` field is created for each line item and converted into a vector embedding by the `GeminiEmbedder`.
5. **Save:** The `CommandInvoiceRepository` saves the final `InvoiceModel` and its associated `LineItemModel` documents (including their vectors) to the MongoDB database in a single transaction.

### 3.2. Retrieval (Read Path)

The retrieval flow is orchestrated by the `RetrievalService`:

1. **Route Query:** The user's natural language query is sent to the `QueryRouter`. This LLM-based component analyzes the query and identifies two key pieces of information:
    - **Structured Filters:** Specific criteria like dates, vendors, or page numbers.
    - **Semantic Intent:** The core meaning of the query (e.g., "all charges related to labor").
2. **Execute Query:** The `QueryInvoiceRepository` receives the router's output as structured tools (`SearchLineItemsTool` or `SearchInvoicesTool`). It embeds the semantic intent into a vector for similarity search when needed and constructs a MongoDB aggregation pipeline based on the structured criteria. The repository executes the hybrid search—combining metadata filtering with vector search in a single pipeline.
3. **Generate Answer:** The top-k retrieved line items and the original user query are passed to the `AnswerGenerator`. This final LLM call synthesizes a concise, human-readable answer that is explicitly grounded in the retrieved data. If the user requests raw data, this step is skipped.

## 4. Key Algorithms & Strategies

### 4.1. Stateful Sequential Extraction ("Rolling Context")

This is the core algorithm for handling complex, multi-page invoices. The `InvoiceExtractor` maintains a `PageState` object that is passed from one page to the next. This object tracks:

- `table_status`: Whether a table is currently being parsed and is expected to continue on the next page.
- `active_columns`: The headers of the current table, which are injected into the context for subsequent "headless" table rows on the next page.
- `active_section_title`: The current section of the invoice to provide better contextual understanding.

This stateful approach allows the system to correctly associate line items with their headers and context, even when they are spread across page breaks.

### 4.2. Hybrid Search & Synthesis

The retrieval path is designed to maximize both precision and relevance. By first using the `QueryRouter` to extract hard filters, it dramatically narrows the search space. The subsequent vector search then operates only on relevant documents, ensuring high-quality semantic matches. The final `AnswerGenerator` step ensures the user receives a helpful, conversational answer instead of just a raw data dump, improving the overall user experience.

## 5. Technology Stack

- **Orchestration & AI:** LlamaIndex, LangChain
- **LLMs:** Google Gemini 2.5 Flash / Pro (for extraction, routing, synthesis)
- **Parsing:** LlamaParse
- **Embeddings:** Google Gemini (`text-embedding-004`)
- **Data Schemas:** Pydantic (for both transient validation and data modeling)
- **Database:** MongoDB Atlas (for document storage and vector search)
- **Dependency Injection:** `wireup`
- **CLI:** Typer
