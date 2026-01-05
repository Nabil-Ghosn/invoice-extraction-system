import logging
from typing import Annotated, Any

import wireup
from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

import src
from src.core.env_settings import EnvironmentSettings
from src.core.models import InvoiceModel, LineItemModel


def configure_logging(
    log_level: str,
) -> None:
    """Configure application-wide logging."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def initialize_services() -> wireup.AsyncContainer:
    """
    Load environment settings, initialize the database, and set up the dependency injection container.

    :return: An initialized dependency injection container.
    """
    environment_config: EnvironmentSettings = EnvironmentSettings.load()
    configure_logging(environment_config.LOG_LEVEL)

    container: wireup.AsyncContainer = wireup.create_async_container(
        parameters=environment_config.model_dump(), service_modules=[src]
    )

    client: AsyncMongoClient[Any] = AsyncMongoClient(environment_config.DATABASE_URI)
    database: AsyncDatabase[Any] = client[environment_config.DATABASE_NAME]
    await init_beanie(database=database, document_models=[InvoiceModel, LineItemModel])

    return container
