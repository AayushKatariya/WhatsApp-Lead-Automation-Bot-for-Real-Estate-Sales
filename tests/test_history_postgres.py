"""History against a real PostgreSQL, using the dashboard's own schema.

Skipped unless TEST_DATABASE_URL is set. No Docker needed; the dashboard's dev database works:
    cd dashboard && npx pglite-server --max-connections=5        (leave it running)
    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres python -m pytest -q tests/test_history_postgres.py
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from history import History  # noqa: E402

URL = os.environ.get("TEST_DATABASE_URL", "")
SCHEMA = Path(__file__).resolve().parent.parent / "dashboard" / "db" / "schema.sql"
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def db():
    import psycopg

    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS contacts, messages, events, team")
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
        yield conn


def test_history_round_trip(db):
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(URL, min_size=0, max_size=2, open=True)
    h = History(pool=pool)
    site = {"site_id": "GV", "name": "Green Valley Residency"}
    msg = {"id": "wamid.in1", "from": "919812345678", "type": "text", "text": {"body": "Price?"}}

    h.incoming("919812345678", "Priya", msg)
    h.incoming("919812345678", "", msg)  # Meta resent it: still one row, and the name is kept
    h.outgoing("919812345678", "text", {"body": "Our team will call you"}, "wamid.out1")
    h.status({"id": "wamid.out1", "status": "read"})
    h.status({"id": "wamid.out1", "status": "delivered"})  # arrived late: must not undo "read"
    h.event("919812345678", "Priya", site, "price_request", "Asked for price details")
    pool.close()

    assert db.execute("SELECT name FROM contacts").fetchall() == [("Priya",)]
    rows = db.execute("SELECT direction, kind, body, status, payload->'text'->>'body' FROM messages ORDER BY id").fetchall()
    assert rows == [("in", "text", "Price?", "received", "Price?"),
                    ("out", "text", "Our team will call you", "read", None)]
    assert db.execute("SELECT site_id, site_name, event FROM events").fetchall() == \
        [("GV", "Green Valley Residency", "price_request")]
