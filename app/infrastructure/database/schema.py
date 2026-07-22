"""Non-destructive development schema initialization."""

from sqlalchemy.ext.asyncio import AsyncEngine

from app.infrastructure.database.base import Base
from app.infrastructure.database.models import LogEventRecord


async def create_database_schema(engine: AsyncEngine) -> None:
    """Create registered missing tables without dropping existing objects."""
    _ = LogEventRecord
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
