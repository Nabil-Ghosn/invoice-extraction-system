import asyncio

from wireup import AsyncContainer
from src.cli.router import CliDispatcher
from src.core.config import initialize_services


async def main() -> None:
    """The main entry point for the application."""
    container: AsyncContainer = await initialize_services()

    cli_dispatcher: CliDispatcher = await container.get(CliDispatcher)
    await cli_dispatcher.dispatch()


if __name__ == "__main__":
    asyncio.run(main())
