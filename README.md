# Invoice Extraction System

An enterprise-grade RAG (Retrieval-Augmented Generation) pipeline designed to transform unstructured invoice PDFs into structured, queryable data. Unlike traditional OCR tools, this system utilizes **Vision LLMs** and **Context-Aware Parsing** to handle complex, multi-page invoices (Level 2 complexity) with varying layouts. It enables users to perform both precise structural filtering and fuzzy semantic searches using natural language.

## Key Features

* **📄 Scalable Ingestion:** Process massive invoices (50+ pages) with "Rolling Context" logic to handle headers spanning multiple page breaks.
* **🧠 Intelligent Extraction:** Converts raw PDFs into strict JSON schemas (Line Items & Metadata) using **LlamaParse** and **Gemini 1.5**.
* **🔍 Hybrid Retrieval Engine:** Unifies **Vector Search** (semantic understanding) with **Metadata Filtering** (exact matching) in a single MongoDB pipeline.
* **💬 Grounded Q&A:** Generates natural language answers strictly cited with sources `[Invoice: X, Page: Y]` to eliminate hallucinations.
* **🧩 Atomic Chunking:** Stores line items as individual records enriched with parent metadata for maximum retrieval precision.
* **🖥️ CLI Interface:** Simple command-line tools for ingestion, querying, and system evaluation.

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

## Architecture Overview

The system is built on a **Logical Command Query Responsibility Segregation (CQRS)** pattern within a modular monolith. This design separates the application into two main pipelines:

* **Ingestion (Write Path):** A high-compute pipeline that parses PDFs, extracts data using a stateful "rolling context" LLM strategy, creates embeddings, and saves the structured data to MongoDB.
* **Retrieval (Read Path):** A low-latency RAG pipeline that uses an LLM to route natural language queries to appropriate search tools, which are then executed by a repository layer that combines vector search with metadata filtering in a single MongoDB pipeline and synthesizes grounded answers.

A **Shared Kernel** (`src/core`) provides common data models and services to both pipelines. For a detailed breakdown, please see [`design/architecture.md`](design/architecture.md).

To look more for Design decisions & trade-offs that are taken step by step through this project, please see [`APPROACH.md`](APPROACH.md)