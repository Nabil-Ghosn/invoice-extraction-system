# Invoice Extraction System

A sophisticated invoice parsing and extraction system that leverages AI to extract structured data from complex multi-page invoices.

## Features

- Multi-page invoice processing with sequential rolling context
- Support for complex invoice layouts with headless tables and shifting schemas
- Integration with Google Gemini 2.5 Flash for intelligent extraction
- LlamaParse for high-quality document parsing
- Stateful extraction pipeline to maintain context across pages
- Comprehensive data validation with Pydantic models

## Prerequisites

- Python 3.12+
- Google API Key for Gemini models
- Llama Cloud API Key for document parsing
- MongoDB (for data storage)

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

Process one or more invoice files:

```bash
python main.py <invoice_file_path1> [invoice_file_path2] ...
```

Example:

```bash
python main.py invoice1.pdf invoice2.pdf
```

### Test Suite

Run the test suite to process sample invoices:

```bash
python -m tests.test_invoice_processing
```

The test suite processes sample invoices from the `tests/data/` directory and saves results to `tests/results/`.

## Architecture

The system uses a stateful sequential extraction approach:

1. **Document Ingestion**: LlamaParse converts PDFs to structured Markdown
2. **Sequential Processing**: Pages are processed in order with rolling context
3. **State Management**: Page N's output includes state for Page N+1
4. **Data Extraction**: Structured data is extracted using Pydantic models

For more details on the architecture and design decisions, see `APPROACH.md`.

## Project Structure

- `src/`: Core source code
  - `invoice_parser.py`: Document parsing with LlamaParse
  - `invoice_extractor.py`: AI extraction logic
  - `extracted_schemas.py`: Data models for extracted information
  - `prompts.py`: LLM prompts for extraction
  - `env_settings.py`: Environment configuration
- `tests/`: Test suite and sample data
- `design/`: Architecture documentation
