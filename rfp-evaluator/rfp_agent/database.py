"""SQLite persistence layer.

Tables (superset of the minimum design in the brief):

evaluation_criteria(criterion_id, name, description, weight, max_score, is_active, updated_at)
rfp_runs(rfp_run_id, created_at, status, completed_at, llm_provider, llm_model,
         criteria_snapshot, run_json, error_message)
supplier_results(id, rfp_run_id, supplier_name, source_file, submission_date,
                 experience_rating, status, absolute_score, ppi, final_rank, result_json)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "rfp_evaluation.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluation_criteria (
    criterion_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,
    description  TEXT    NOT NULL DEFAULT '',
    weight       REAL    NOT NULL CHECK (weight >= 0 AND weight <= 100),
    max_score    REAL    NOT NULL DEFAULT 10 CHECK (max_score > 0),
    is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    updated_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS rfp_runs (
    rfp_run_id        TEXT PRIMARY KEY,
    created_at        TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('CREATED','RUNNING','COMPLETED','FAILED')),
    completed_at      TEXT,
    llm_provider      TEXT,
    llm_model         TEXT,
    criteria_snapshot TEXT,
    run_json          TEXT,
    error_message     TEXT
);

CREATE TABLE IF NOT EXISTS supplier_results (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    rfp_run_id        TEXT NOT NULL REFERENCES rfp_runs(rfp_run_id) ON DELETE CASCADE,
    supplier_name     TEXT NOT NULL,
    source_file       TEXT,
    submission_date   TEXT NOT NULL,
    experience_rating REAL NOT NULL,
    status            TEXT NOT NULL DEFAULT 'PENDING',
    absolute_score    REAL,
    ppi               REAL,
    final_rank        INTEGER,
    result_json       TEXT,
    UNIQUE (rfp_run_id, supplier_name)
);

CREATE INDEX IF NOT EXISTS idx_supplier_results_run ON supplier_results(rfp_run_id);
"""

SEED_CRITERIA = [
    ("Technical Capability", "Architecture, integrations, scalability, technical fit", 30, 10),
    ("Implementation Plan", "Timeline, milestones, staffing, risk plan", 20, 10),
    ("Commercial Value", "Pricing clarity, total cost, assumptions", 20, 10),
    ("Security & Compliance", "Controls, certifications, privacy, auditability", 20, 10),
    ("Support & Experience", "Support model, similar projects, references", 10, 10),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection, seed: bool = True) -> None:
    conn.executescript(SCHEMA)
    if seed:
        (count,) = conn.execute("SELECT COUNT(*) FROM evaluation_criteria").fetchone()
        if count == 0:
            seed_criteria(conn)
    conn.commit()


def seed_criteria(conn: sqlite3.Connection, reset: bool = False) -> None:
    if reset:
        conn.execute("DELETE FROM evaluation_criteria")
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'evaluation_criteria'")
    conn.executemany(
        "INSERT INTO evaluation_criteria (name, description, weight, max_score, is_active, updated_at) "
        "VALUES (?, ?, ?, ?, 1, ?)",
        [(n, d, w, m, _now()) for n, d, w, m in SEED_CRITERIA],
    )
    conn.commit()


# --------------------------------------------------------------------------- criteria
def get_all_criteria(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM evaluation_criteria ORDER BY criterion_id").fetchall()
    return [dict(r) for r in rows]


def get_active_criteria(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT criterion_id, name, description, weight, max_score FROM evaluation_criteria "
        "WHERE is_active = 1 ORDER BY criterion_id"
    ).fetchall()
    return [dict(r) for r in rows]


def validate_criteria(criteria: list[dict[str, Any]]) -> list[str]:
    """Return a list of human-readable errors; empty list means valid."""
    errors: list[str] = []
    active = [c for c in criteria if int(c.get("is_active", 1)) == 1]
    if not active:
        errors.append("At least one criterion must be active.")
    names = [str(c.get("name") or "").strip() for c in criteria]
    if any(not n for n in names):
        errors.append("Every criterion needs a name.")
    lowered = [n.lower() for n in names if n]
    if len(lowered) != len(set(lowered)):
        errors.append("Criterion names must be unique.")
    for c in criteria:
        try:
            w, m = float(c.get("weight")), float(c.get("max_score"))
        except (TypeError, ValueError):
            errors.append(f"'{c.get('name')}': weight and max score must be numbers.")
            continue
        if not 0 <= w <= 100:
            errors.append(f"'{c.get('name')}': weight must be between 0 and 100.")
        if m <= 0:
            errors.append(f"'{c.get('name')}': max score must be greater than 0.")
    total = sum(float(c.get("weight") or 0) for c in active)
    if active and abs(total - 100.0) > 0.01:
        errors.append(f"Active criteria weights must total 100% (currently {total:g}%).")
    return errors


def save_criteria(conn: sqlite3.Connection, criteria: list[dict[str, Any]]) -> None:
    """Upsert the full criteria list (rows without criterion_id are inserted).

    Criteria are never hard-deleted so past runs stay traceable; remove a
    criterion by setting is_active = 0.
    """
    errors = validate_criteria(criteria)
    if errors:
        raise ValueError("; ".join(errors))
    with conn:
        for c in criteria:
            values = (str(c["name"]).strip(), str(c.get("description") or "").strip(),
                      float(c["weight"]), float(c["max_score"]), int(c.get("is_active", 1)), _now())
            cid = c.get("criterion_id")
            if cid is None or (isinstance(cid, float) and cid != cid):  # None or NaN
                conn.execute(
                    "INSERT INTO evaluation_criteria (name, description, weight, max_score, is_active, "
                    "updated_at) VALUES (?, ?, ?, ?, ?, ?)", values)
            else:
                conn.execute(
                    "UPDATE evaluation_criteria SET name=?, description=?, weight=?, max_score=?, "
                    "is_active=?, updated_at=? WHERE criterion_id=?", values + (int(cid),))


# --------------------------------------------------------------------------- runs
def create_run(conn: sqlite3.Connection, rfp_run_id: str, llm_provider: str, llm_model: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO rfp_runs (rfp_run_id, created_at, status, llm_provider, llm_model) "
            "VALUES (?, ?, 'CREATED', ?, ?)", (rfp_run_id, _now(), llm_provider, llm_model))


def add_supplier_entries(conn: sqlite3.Connection, rfp_run_id: str, suppliers: list[dict[str, Any]]) -> None:
    with conn:
        conn.executemany(
            "INSERT INTO supplier_results (rfp_run_id, supplier_name, source_file, submission_date, "
            "experience_rating, status) VALUES (?, ?, ?, ?, ?, 'PENDING')",
            [(rfp_run_id, s["supplier_name"], s.get("source_file"), str(s["submission_date"]),
              float(s["experience_rating"])) for s in suppliers])


def set_run_status(conn: sqlite3.Connection, rfp_run_id: str, status: str,
                   criteria_snapshot: list[dict] | None = None, error_message: str | None = None) -> None:
    with conn:
        if criteria_snapshot is not None:
            conn.execute("UPDATE rfp_runs SET criteria_snapshot=? WHERE rfp_run_id=?",
                         (json.dumps(criteria_snapshot), rfp_run_id))
        conn.execute(
            "UPDATE rfp_runs SET status=?, error_message=COALESCE(?, error_message), "
            "completed_at=CASE WHEN ? IN ('COMPLETED','FAILED') THEN ? ELSE completed_at END "
            "WHERE rfp_run_id=?", (status, error_message, status, _now(), rfp_run_id))


def set_supplier_status(conn: sqlite3.Connection, rfp_run_id: str, supplier_name: str, status: str) -> None:
    with conn:
        conn.execute("UPDATE supplier_results SET status=? WHERE rfp_run_id=? AND supplier_name=?",
                     (status, rfp_run_id, supplier_name))


def save_run_results(conn: sqlite3.Connection, run_result: dict[str, Any]) -> None:
    """Write every supplier result and the full run JSON in one transaction."""
    run_id = run_result["rfp_run_id"]
    with conn:
        for s in run_result["suppliers"]:
            conn.execute(
                "UPDATE supplier_results SET status='EVALUATED', absolute_score=?, ppi=?, final_rank=?, "
                "result_json=? WHERE rfp_run_id=? AND supplier_name=?",
                (s["absolute_score"], s["ppi"], s["final_rank"], json.dumps(s, ensure_ascii=False),
                 run_id, s["supplier_name"]))
        conn.execute(
            "UPDATE rfp_runs SET status='COMPLETED', completed_at=?, run_json=? WHERE rfp_run_id=?",
            (_now(), json.dumps(run_result, ensure_ascii=False), run_id))


def list_runs(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT r.rfp_run_id, r.created_at, r.status, r.llm_provider, r.llm_model, r.error_message, "
        "COUNT(s.id) AS suppliers FROM rfp_runs r LEFT JOIN supplier_results s "
        "ON s.rfp_run_id = r.rfp_run_id GROUP BY r.rfp_run_id ORDER BY r.created_at DESC LIMIT ?",
        (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_run(conn: sqlite3.Connection, rfp_run_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT run_json FROM rfp_runs WHERE rfp_run_id=?", (rfp_run_id,)).fetchone()
    if row is None or row["run_json"] is None:
        return None
    return json.loads(row["run_json"])


def get_supplier_rows(conn: sqlite3.Connection, rfp_run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT rfp_run_id, supplier_name, submission_date, experience_rating, status, absolute_score, "
        "ppi, final_rank FROM supplier_results WHERE rfp_run_id=? ORDER BY final_rank IS NULL, final_rank",
        (rfp_run_id,)).fetchall()
    return [dict(r) for r in rows]
