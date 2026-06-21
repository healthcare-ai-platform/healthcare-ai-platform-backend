import os

import databases

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/healthcare",
)

db: databases.Database = databases.Database(DATABASE_URL)
