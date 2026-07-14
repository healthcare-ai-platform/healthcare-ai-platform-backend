import asyncio
import os
import threading
from typing import Optional

import snowflake.connector

# dbt writes marts to <profile_schema>_<model_schema> by default (dbt's stock
# generate_schema_name behavior) — with profiles.yml's base schema "staging"
# and marts/+schema: marts, the real schema is STAGING_MARTS, not MARTS.
MARTS_SCHEMA = os.getenv("SNOWFLAKE_MARTS_SCHEMA", "STAGING_MARTS")

_lock = threading.Lock()
_conn: Optional[snowflake.connector.SnowflakeConnection] = None


def _connect() -> snowflake.connector.SnowflakeConnection:
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        database=os.getenv("SNOWFLAKE_DATABASE", "HEALTHCARE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        role=os.getenv("SNOWFLAKE_ROLE", "SYSADMIN"),
    )


def _get_connection() -> snowflake.connector.SnowflakeConnection:
    global _conn
    with _lock:
        if _conn is None or _conn.is_closed():
            _conn = _connect()
        return _conn


def _fetch_all_sync(sql: str, params: Optional[dict] = None) -> list[dict]:
    conn = _get_connection()
    cur = conn.cursor(snowflake.connector.DictCursor)
    try:
        cur.execute(sql, params or {})
        return cur.fetchall()
    finally:
        cur.close()


async def fetch_all(sql: str, params: Optional[dict] = None) -> list[dict]:
    """
    Query Snowflake's dbt marts (analytics/BI — dim_patients, fct_lab_results).
    The connector is synchronous, so this runs it off the event loop thread
    rather than blocking every other request while Snowflake responds.
    """
    return await asyncio.to_thread(_fetch_all_sync, sql, params)


def shutdown() -> None:
    global _conn
    with _lock:
        if _conn is not None and not _conn.is_closed():
            _conn.close()
        _conn = None
