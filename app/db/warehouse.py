import os

import databases

REDSHIFT_URL = os.getenv(
    "REDSHIFT_URL",
    "postgresql+asyncpg://warehouse:warehouse@localhost:5433/warehouse",
)

warehouse: databases.Database = databases.Database(REDSHIFT_URL)
