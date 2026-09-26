#!/usr/bin/env python3
"""
Lightweight, idempotent schema helpers for existing databases.

`Base.metadata.create_all()` only creates tables that do not exist yet – it never
alters an existing one. New nullable columns therefore need an explicit, guarded
ALTER that is safe to run on every startup.

New tables (product_groups, product_group_members, report_subscribers,
subscriber_product_groups) are handled by create_all and need nothing here.
"""
import logging

from sqlalchemy import inspect, text

from models.engine.database import db

logger = logging.getLogger(__name__)


def ensure_column(table: str, column: str, ddl_type: str) -> bool:
    """Add `column` to `table` when it is missing. Returns True if it was added."""
    inspector = inspect(db.engine)
    if table not in inspector.get_table_names():
        logger.debug("ensure_column: table %s does not exist yet, skipping", table)
        return False

    existing = {col['name'] for col in inspector.get_columns(table)}
    if column in existing:
        return False

    with db.engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
    logger.info("Added column %s.%s (%s)", table, column, ddl_type)
    return True


def run_startup_migrations() -> None:
    """Bring an existing database up to date with the current models."""
    try:
        # Must run after create_all so product_groups exists for the reference.
        ensure_column('expenses', 'product_group_id', 'INTEGER REFERENCES product_groups(id)')
    except Exception:
        logger.exception("Startup migrations failed; continuing with current schema")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_startup_migrations()
    print("Startup migrations complete.")
