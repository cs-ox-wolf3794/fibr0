"""Thin Postgres access. The pipeline is the only writer; the web app only reads."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


@contextmanager
def connect(database_url: str) -> Iterator[psycopg.Connection]:
    """Open a connection with dict rows. Commits on clean exit, rolls back on error."""
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        yield conn
