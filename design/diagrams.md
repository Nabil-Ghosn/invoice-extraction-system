# Diagrams

## 1. The Structural View (The "What")

### **A. Component Diagram (High-Level Architecture)**

* **Why:** This is your "System Map." It shows how your code interacts with the outside world. It proves you understand the boundaries between your application logic and external dependencies.
* **What it shows:**
  * **Client:** CLI / Script.
  * **Orchestrator:** `IngestionService`, `RAGService`.
  * **External Interfaces:** `LlamaParse API`, `Gemini LLM`, `Google Vertex AI` (Embeddings).
  * **Data Stores:** `MongoDB Atlas` (storing both Metadata and Vectors).
* **Architectural Value:** Demonstrates **Separation of Concerns**.

### **B. Class Diagram (Data Modeling)**

* **Why:** This is critical because we have **two distinct data worlds**:
    1. **Extraction World:** Transient Pydantic models (`InvoicePage`, `PageState`) used strictly for LLM validation.
    2. **Persistence World:** Database models (`InvoiceModel`, `LineItemModel`) used for storage and retrieval.
* **What it shows:**
  * The 1-to-many relationship between `Invoice` and `LineItems`.
  * The fields used for filtering (`invoice_date`, `vendor`) vs. fields used for embedding (`search_text`).
* **Architectural Value:** Demonstrates **Schema Design** and ODM (Object-Document Mapper) strategy.

---

## 2. The Interaction View (The "How")

### **C. Sequence Diagram (Data Flow)**

* **Why:** This is the most important diagram for explaining the "Pipeline."
* **Recommended Flows:**
    1. **Ingestion:** `Upload -> Parse -> Extract -> Enrich -> Embed -> Store`.
    2. **Retrieval (RAG):** `User Query -> Metadata Extraction -> Hybrid Search (Filter + Vector) -> Context Synthesis -> LLM Answer`.
* **Architectural Value:** Shows how you handle **latency** and **dependencies** (e.g., "We must wait for extraction before we can embed").

---

## 3. The Behavioral View (The "Logic")

### **D. State Machine Diagram (The "Algorithm")**

* **Why:** This is your "Senior" differentiator. The prompt explicitly mentions "Level 2 — Line items distributed across pages." This is the hardest part of the logic.
* **What it shows:** The **Rolling Context Strategy**.
  * **State 1:** `No_Table_Active` (Standard text processing).
  * **Transition:** Detect table start -> Move to State 2.
  * **State 2:** `Table_Active_With_Headers`.
  * **Transition:** End of Page -> Save Headers -> Move to Page N+1.
  * **State 3:** `Table_Continuing_Headless` (Inject saved headers).
* **Architectural Value:** It proves you aren't just sending PDFs to GPT-4 and hoping for the best; you have a **deterministic algorithm** for handling complex layouts.

---

## Summary of Recommendation

If you only have time for two, do **A (Component)** and **C (Sequence)**.
If you want to ace the "Complexity" requirement, add **D (State Machine)**.
