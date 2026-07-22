"""Resolve migration configuration from centralized application settings."""

from app.shared.config import Settings


def resolve_migration_database_url(settings: Settings | None = None) -> str:
    return (settings or Settings()).database_url
