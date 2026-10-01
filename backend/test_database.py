"""Opt-in smoke test for a developer-configured database."""

import os

import pytest
from sqlalchemy import text

from backend.database.connection import DATABASE_URL, get_engine


@pytest.mark.skipif(
    os.getenv("RUN_DATABASE_TESTS") != "1" or not DATABASE_URL,
    reason="Set RUN_DATABASE_TESTS=1 with a configured development database to run.",
)
def test_database_connection():
    engine = get_engine()
    assert engine is not None
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar() == 1