from app.api.utils.common import common_logger


class _Database:
    """Stub — replace with a real databases.Database or SQLAlchemy async session."""

    async def execute(self, query: str, values: dict | None = None) -> None:
        # TODO: wire up a real async DB connection (e.g. `databases` library or asyncpg)
        common_logger(f"[DB STUB] execute called — not persisted. query={query!r}", level="warning")


db = _Database()
