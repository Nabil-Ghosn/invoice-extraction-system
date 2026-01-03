# ---------------------------------------------------------
# PROMPT 1: The Multi-Page Prompt for Sequential Rolling Context Strategy
# ---------------------------------------------------------
MULTI_PAGE_PROMPT_TEMPLATE = """
You are an expert Invoice Parsing AI. You are processing **Page {current_page_num}** of a multi-page invoice.

### PREVIOUS PAGE CONTEXT (The State of the Document)
The previous page left the document in this state:
```json
{previous_state}
```

### INSTRUCTIONS
1. **Analyze Layout & Continuity:**
   - Check the JSON `previous_state` above.
   - If `table_status` was 'table_open_headless' and this page starts with numbers/text but NO headers, you MUST map them to the `active_columns` list.
   - If this page starts a *new* table, extract the new column headers.

2. **Extract Global Metadata:**
   - Scan for Invoice Number, Date, or Vendor Name on this page. If found, extract them into `invoice_context`.

3. **Extract Line Items:**
   - Extract every row found on this page into `line_items`.
   - Normalize `quantity`, `unit_price`, and `total` to numbers.

4. **Set Next Page State (Crucial):**
   - Look at the *bottom* of this page. Does the table cut off? 
   - If the table continues, set `table_status` to 'table_open_headless'.
   - If the table finishes, set `table_status` to 'no_table'.

### INPUT TEXT (Page {current_page_num})
{page_text}
"""

# ---------------------------------------------------------
# PROMPT 2: The Single-Page Prompt
# ---------------------------------------------------------
SINGLE_PAGE_PROMPT_TEMPLATE = """
You are an expert Invoice Parsing AI. You are processing a **Single Page Invoice**.

### INSTRUCTIONS
1. **Extract Global Metadata:**
   - Find Invoice Number, Date, Vendor Name, and Totals.

2. **Extract Line Items:**
   - Identify the main data table.
   - Extract every row into `line_items`.
   - Ignore headers or footers when creating item rows.

3. **State Management:**
   - Since this is a single page, `next_page_state` should always be set to "no_table" with empty columns.

### INPUT TEXT
{page_text}
"""

PARSER_INVOICE_PROMPT = """
This document is an invoice. Preserve all tables exactly as they appear.
Reconstruct rows and columns faithfully. Do not merge or infer values.
Return clean markdown with clear table boundaries.
"""
