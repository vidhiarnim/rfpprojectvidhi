import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rfp_agent import database as db  # noqa: E402


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    db.init_db(c)
    yield c
    c.close()


@pytest.fixture
def criteria(conn):
    return db.get_active_criteria(conn)
