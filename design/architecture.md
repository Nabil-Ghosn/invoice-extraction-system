# Invoice Extraction System Architecture

## Overview

The Invoice Extraction System is designed to handle complex multi-page invoices with sophisticated layouts, including headless tables and shifting schemas across pages. The system uses a stateful sequential extraction approach to maintain context across pages while leveraging AI for intelligent data extraction.

## System Components

### 1. Invoice Parser (`invoice_parser.py`)

- Uses LlamaParse to convert PDF documents to structured Markdown
- Handles document ingestion and pre-processing
- Manages concurrent parsing with rate limiting
- Preserves table structures and document layout

### 2. Invoice Extractor (`invoice_extractor.py`)

- Core extraction logic using Google Gemini 2.5 Flash
- Implements sequential rolling context strategy
- Manages state transitions between pages
- Handles both single-page and multi-page extraction strategies

### 3. Data Models (`extracted_schemas.py`)

- Pydantic models for structured data extraction
- Line item extraction with normalization
- Invoice context tracking
- Page state management

### 4. Prompts (`prompts.py`)

- Multi-page prompt for sequential processing
- Single-page prompt for optimized processing
- Parser system prompt for document structure preservation

### 5. Configuration (`env_settings.py`)

- Environment variable management
- API key configuration
- Database and logging configuration

## Processing Strategies

### Single-Shot Strategy

- Used for single-page invoices
- Optimized for speed and efficiency
- Direct extraction without state management

### Sequential Chain Strategy  

- Used for multi-page invoices
- Maintains rolling context between pages
- Handles headless tables and schema shifts
- State object passed between pages

## State Management

The system maintains state between pages using the `PageState` model:

- `table_status`: Tracks if tables continue to next page
- `active_columns`: Maintains column headers for headless tables
- `active_section_title`: Tracks current section context

## Technology Stack

- **LlamaParse**: Document ingestion and layout preservation
- **Google Gemini 2.5 Flash**: AI extraction with 1M token context
- **LlamaIndex**: Orchestration and Pydantic program integration
- **Pydantic**: Data validation and structured output
- **Wireup**: Dependency injection
- **MongoDB**: Data storage (planned)

## Data Flow

1. Document ingestion via LlamaParse
2. Sequential page processing with context passing
3. Structured data extraction using AI
4. Validation and normalization
5. Output as structured Pydantic models

```tree
src/
├── core/                  # SHARED KERNEL
│   ├── database.py        # MongoDB connection logic
│   ├── models.py          # Beanie/Pydantic Models (Invoice, LineItem)
│   ├── config.py          # Env vars (API Keys)
│   └── services/
│       └── embedder.py    # Shared Embedding Service (used by both)
│
├── ingestion/             # WRITE PATH (Heavy Lifting)
│   ├── parser.py          # LlamaParse wrapper
│   ├── extractor.py       # LLM Extraction Chain (The Rolling Context logic)
│   └── service.py         # Orchestrator (The Sequence Diagram logic)
│
├── retrieval/             # READ PATH (RAG & Search)
│   ├── query_analyzer.py  # Router (Is this a filter or semantic query?)
│   ├── engine.py          # Handles vector search + Mongo filtering
│   ├── generator.py       # Final Answer LLM (The Grounding logic)
│   └── service.py         # Facade for the CLI to call
│
└── main.py                # Entry point (CLI definition)
```

This architecture implements a **logical CQRS pattern** within a **modular monolith**, strictly decoupling the high-compute **ingestion (Write Path)** from the low-latency **retrieval (Read Path)**. 

A centralized **Shared Kernel** (`core`) manages domain entities, database configurations, and common utilities like embedding services to ensure consistency across both modules. This separation allows for optimized resource allocation while enforcing architectural integrity through unidirectional dependencies.