# Invoice Extraction System

An enterprise-grade RAG (Retrieval-Augmented Generation) pipeline designed to transform unstructured invoice PDFs into structured, queryable data. Unlike traditional OCR tools, this system utilizes **Vision LLMs** and **Context-Aware Parsing** to handle complex, multi-page invoices with varying layouts. It enables users to perform both precise structural filtering and fuzzy semantic searches using natural language.

## Key Features

* **📄 Scalable Ingestion:** Process massive invoices (50+ pages) with "Rolling Context" logic to handle headers spanning multiple page breaks.
* **🧠 Intelligent Extraction:** Converts raw PDFs into strict JSON schemas (Line Items & Metadata) using **LlamaParse** and **Gemini 1.5**.
* **🔍 Hybrid Retrieval Engine:** Unifies **Vector Search** (semantic understanding) with **Metadata Filtering** (exact matching) in a single MongoDB pipeline.
* **💬 Grounded Q&A:** Generates natural language answers strictly cited with sources `[Invoice: X, Page: Y]` to eliminate hallucinations.
* **🧩 Atomic Chunking:** Stores line items as individual records enriched with parent metadata for maximum retrieval precision.
* **🖥️ CLI Interface:** Simple command-line tools for ingestion, querying, and system evaluation.

---

## 🛠️ Technical Implementation

> 🏗️ **Architecture:** See [`design/architecture.md`](design/architecture.md) for system diagrams.
> 🧠 **Decisions:** See [`APPROACH.md`](APPROACH.md) for a deep dive into trade-offs.

### 1. Extraction Strategy: Rolling Context

We utilize a **Stateful Sequential Extraction** pipeline to handle multi-page invoices.

* **The Problem:** Standard OCR fails on "headless tables" (tables that span page breaks without repeating headers).
* **The Solution:** We maintain a `PageState` object across iterations. If Page 1 ends inside a table, Page 2 inherits those headers, ensuring data continuity.
* **Engine:** Powered by **LlamaParse** (layout-aware parsing) and **Gemini 2.5 Flash** (structural extraction).

### 2. Chunking Strategy: Atomic Line Items

Instead of arbitrary token windows, we chunk data by **semantic boundaries**.

* **Granularity:** Each extracted Line Item is treated as an atomic record.
* **Enrichment:** Every item is enriched with parent metadata (Invoice ID, Page #, Vendor). This ensures that a vector search for "Labor costs" can still be accurately filtered by "Page 3".

### 3. Storage & Retrieval: Hybrid Search

We use **MongoDB Atlas** as a unified operational and vector database.

* **Query Routing:** An LLM router first extracts hard filters (e.g., `date > 2023`) from the user's prompt.
* **Execution:** These filters are applied strictly **before** vector search runs. This "Hybrid" approach prevents hallucinations where the LLM might otherwise ignore metadata constraints.

### 4. AI Stack

* **LLM (Gemini 2.5 Flash):** Chosen for its **1M token context window**, allowing the model to reason across entire documents at low cost.
* **Embeddings (text-embedding-004):** Native integration optimized for retrieval tasks (768 dimensions).

### 5. Evaluation Strategy (Planned)

We have designed a validation framework based on a **"Golden Set"** methodology to ensure reliability:

* **Extraction Accuracy:** JSON-to-JSON comparison against manually labeled ground truth.
* **Retrieval Recall:** Automated tests to verify that specific line items appear in the top-$k$ results for semantic queries.
* **Hallucination Check:** An "LLM-as-a-Judge" pipeline to verify the final answer is strictly grounded in the retrieved context.

---

## Prerequisites

### System Requirements

* Python 3.12+
* pip or uv package manager

### External Services & APIs

* **Google API Key** for Gemini models (required for LLM functionality)
* **Llama Cloud API Key** for document parsing (required for processing PDF invoices)
* **MongoDB Atlas** account for vector search capabilities (or local MongoDB instance)

### MongoDB Vector Index Configuration

For vector search functionality, you need to create a vector index in MongoDB Atlas with the following configuration:

```json
{
  "fields": [
    {
      "numDimensions": 768,
      "path": "vector",
      "similarity": "cosine",
      "type": "vector"
    },
    {
      "path": "page_number",
      "type": "filter"
    },
    {
      "path": "total_amount",
      "type": "filter"
    },
    {
      "path": "invoice_id",
      "type": "filter"
    }
  ]
}
```

### Environment Setup

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Fill in your API keys in the `.env` file:
   * `GOOGLE_API_KEY`: Your Google API key for accessing Gemini models
   * `LLAMA_CLOUD_API_KEY`: Your Llama Cloud API key for document parsing
   * `DATABASE_URI`: MongoDB connection string (defaults to local instance)
   * `DATABASE_NAME`: Name of the database to use (defaults to `invoice_extraction_db`)

## Setup

1. Clone the repository
2. Install dependencies with `uv`:

   ```bash
   uv sync
   ```

3. Copy the environment file and fill in your API keys:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and add your Google API Key and Llama Cloud API Key.

## Usage

### Command Line Interface

The main script `main.py` supports two primary commands: `ingest` for processing invoice documents and `ask` for querying the ingested data.

#### Ingest Invoices

This command processes one or more invoice PDF files, extracts structured data, and stores them in the database.

Usage:

```bash
python main.py ingest <file_path1> [file_path2] ...
```

Example:

```bash
python main.py ingest invoice1.pdf invoice2.pdf
```

#### Ask Questions

This command allows you to query the ingested invoice data using natural language.

Usage:

```bash
python main.py ask "<query>" [--llm-generated]
```

Arguments:

* `<query>`: The natural language question you want to ask about your invoices (e.g., "What is the total amount for invoice #123?").
* `--llm-generated` (optional): If this flag is present, the system will use an LLM to generate a human-readable answer. If omitted, the system will return structured data (e.g., JSON) directly.

Examples:

* To get structured data for line items containing "consulting fees":

    ```bash
    python main.py ask "Show me all line items for consulting fees"
    ```

* To get a natural language answer about a specific invoice:

    ```bash
    python main.py ask "What was the total amount for the invoice from 'Acme Corp' on 2023-01-15?" --llm-generated
    ```
