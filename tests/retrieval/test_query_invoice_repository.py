import asyncio
from datetime import date
import os
from pymongo import AsyncMongoClient
import pytest
import pytest_asyncio
from beanie import init_beanie

# Import your models
from src.core.models import InvoiceModel, LineItemModel, ProcessingStatus
from src.retrieval.query_invoice_repository import BeanieQueryInvoiceRepository
from src.retrieval.tools import SearchInvoicesTool, SearchLineItemsTool

# READ FROM ENV
TEST_DATABASE_URI = os.getenv("TEST_DATABASE_URI")
TEST_DATABASE_NAME = os.getenv("TEST_DATABASE_NAME")
VECTOR_SIZE = 768


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_repository():
    """
    1. Connects to Atlas.
    2. Initializes Beanie.
    3. CLEANS the collections before each test to ensure isolation.
    4. Returns the Repository instance.
    """
    if not TEST_DATABASE_URI:
        pytest.skip("ATLAS_URI not set. Skipping Integration tests.")
    if not TEST_DATABASE_NAME or not TEST_DATABASE_URI:
        raise
    client = AsyncMongoClient(TEST_DATABASE_URI)
    db = client[TEST_DATABASE_NAME]

    await init_beanie(database=db, document_models=[InvoiceModel, LineItemModel])

    # --- CLEAN SLATE ---
    await LineItemModel.delete_all()
    await InvoiceModel.delete_all()

    # Import here to avoid early import issues if not using dependency injection container
    repo = BeanieQueryInvoiceRepository()

    yield repo

    # --- TEARDOWN (Optional: Clean up after test) ---
    await LineItemModel.delete_all()
    await InvoiceModel.delete_all()


# We mark these tests as async
@pytest.mark.asyncio
class TestBeanieRepositoryIntegration:
    async def test_search_invoices_metadata_filtering(self, db_repository):
        """
        Verifies that _build_invoice_pipeline works correctly with Mongo.
        """
        # 1. ARRANGE: Insert Dummy Data
        inv1 = await InvoiceModel(
            filename="google_bill.pdf",
            file_hash="hash1",
            status=ProcessingStatus.COMPLETED,
            invoice_number="INV-001",
            sender_name="Google",
            invoice_date=date(2023, 10, 1),
            total_amount=100.00,
        ).insert()

        inv2 = await InvoiceModel(
            filename="aws_bill.pdf",
            file_hash="hash2",
            status=ProcessingStatus.COMPLETED,
            invoice_number="INV-002",
            sender_name="AWS",
            invoice_date=date(2023, 10, 5),
            total_amount=200.00,
        ).insert()

        # 2. ACT: Search for Google invoices
        criteria = SearchInvoicesTool(sender_name="Google")
        results = await db_repository.search_invoices(criteria)

        # 3. ASSERT
        assert len(results) == 1
        assert results[0].invoice_number == "INV-001"
        assert results[0].sender_name == "Google"

    async def test_search_line_items_aggregation_and_lookup(self, db_repository):
        """
        Verifies:
        1. Filtering by Amount (Logic)
        2. The $lookup join with Invoices (Integration)
        """
        # 1. ARRANGE
        invoice = await InvoiceModel(
            filename="hardware.pdf",
            file_hash="hash_hw",
            status=ProcessingStatus.COMPLETED,
            invoice_number="HW-999",
            sender_name="Nvidia",
            invoice_date=date(2023, 11, 15),
        ).insert()

        # Item 1: Expensive
        await LineItemModel(
            invoice_id=invoice.id,
            page_number=1,
            description="RTX 4090",
            section="Hardware",
            total_amount=1500.0,
            search_text="gpu",
            vector=[0.0] * VECTOR_SIZE,  # Dummy vector
            quantity=None,
            unit_price=None,
        ).insert()

        # Item 2: Cheap
        await LineItemModel(
            invoice_id=invoice.id,
            page_number=1,
            description="HDMI Cable",
            section="Cables",
            total_amount=20.0,
            search_text="cable",
            vector=[0.0] * VECTOR_SIZE,
            quantity=None,
            unit_price=None,
        ).insert()

        # 2. ACT: Search for items > $1000
        criteria = SearchLineItemsTool(min_amount=1000.0)
        # Pass None for embedding to trigger Path B (Structured Search)
        results = await db_repository.search_line_items(criteria, embedding=None)

        # 3. ASSERT
        assert len(results) == 1
        item = results[0]
        assert item.description == "RTX 4090"

        # Test the $lookup projection (fields from the InvoiceModel)
        assert item.invoice_number == "HW-999"
        assert item.sender_name == "Nvidia"

    async def test_search_line_items_context_filtering(self, db_repository):
        """
        Verifies the 'Pre-Filter Strategy' (_resolve_invoice_ids).
        We filter items based on the PARENT invoice's date.
        """
        # 1. ARRANGE
        # Old Invoice
        inv_old = await InvoiceModel(
            filename="old.pdf",
            file_hash="h1",
            status=ProcessingStatus.COMPLETED,
            invoice_date=date(2020, 1, 1),
        ).insert()
        await LineItemModel(
            invoice_id=inv_old.id,
            page_number=1,
            description="Old Item",
            section="A",
            total_amount=10,
            search_text="old",
            vector=[],
            quantity=None,
            unit_price=None,
        ).insert()

        # New Invoice
        inv_new = await InvoiceModel(
            filename="new.pdf",
            file_hash="h2",
            status=ProcessingStatus.COMPLETED,
            invoice_date=date(2023, 1, 1),
        ).insert()
        await LineItemModel(
            invoice_id=inv_new.id,
            page_number=1,
            description="New Item",
            section="A",
            total_amount=10,
            search_text="new",
            vector=[],
            quantity=None,
            unit_price=None,
        ).insert()

        # 2. ACT: Filter for invoices after 2022
        criteria = SearchLineItemsTool(invoice_date_start="2022-01-01")
        results = await db_repository.search_line_items(criteria, embedding=None)

        # 3. ASSERT
        assert len(results) == 1
        assert results[0].description == "New Item"

    async def test_atlas_vector_search(self, db_repository):
        """
        Verifies the $vectorSearch pipeline.

        WARNING: Atlas Vector Search is eventually consistent.
        Newly inserted documents might take a few seconds to be indexed.
        This test might be flaky without a sleep.
        """
        # 1. ARRANGE
        invoice = await InvoiceModel(
            filename="vec.pdf", file_hash="vec", status=ProcessingStatus.COMPLETED
        ).insert()

        # Let's assume 3 dimensions for simplicity in this example
        # In reality, match your embedding model (e.g., VECTOR_SIZE for OpenAI)
        target_vector: list[float] = [1.0] * VECTOR_SIZE
        noise_vector: list[float] = [0.0] * VECTOR_SIZE

        await LineItemModel(
            invoice_id=invoice.id,
            page_number=1,
            description="Target Item",
            section="A",
            total_amount=10,
            search_text="t",
            vector=target_vector,
            quantity=None,
            unit_price=None,
        ).insert()

        await LineItemModel(
            invoice_id=invoice.id,
            page_number=1,
            description="Noise Item",
            section="A",
            total_amount=10,
            search_text="n",
            vector=noise_vector,
            quantity=None,
            unit_price=None,
        ).insert()

        # Wait for Atlas Indexing (Simulated)
        # In a real CI env, you might need a retry loop or explicit wait
        await asyncio.sleep(2)

        # 2. ACT
        criteria = SearchLineItemsTool(query_text="Find target", limit=1)
        # Search using the target vector
        results = await db_repository.search_line_items(
            criteria, embedding=target_vector
        )

        # 3. ASSERT
        # Note: If this fails, check if 'vector_index' exists in Atlas
        if not results:
            pytest.xfail("Vector index might be lagging or missing in Atlas")

        assert results[0].description == "Target Item"
        # Check that score is projected
        assert hasattr(results[0], "score")
