"""End-to-end tests with the offline provider (no network, fully deterministic)."""
import copy
from datetime import date, timedelta

import pytest

from rfp_agent import database as db
from rfp_agent.document_tool import DocumentError, extract_text
from rfp_agent.evaluation_agent import EvaluationAgent, FaultInjectingProvider, OfflineDemoProvider
from rfp_agent.orchestrator import Orchestrator, SupplierSubmission, validate_inputs
from rfp_agent.ranking_tool import SupplierInput, rank_suppliers
from rfp_agent.samples import SAMPLE_DIR, SAMPLE_SUPPLIERS


def submissions():
    return [SupplierSubmission(s["supplier_name"], s["submission_date"], s["experience_rating"], s["file"],
                               (SAMPLE_DIR / s["file"]).read_bytes()) for s in SAMPLE_SUPPLIERS]


def strip_volatile(result):
    r = copy.deepcopy(result)
    for k in ("rfp_run_id", "created_at", "trace"):
        r.pop(k)
    for s in r["suppliers"]:
        s["llm_call"].pop("elapsed_s")
    return r


def test_sample_pdfs_extract():
    for s in SAMPLE_SUPPLIERS:
        doc = extract_text((SAMPLE_DIR / s["file"]).read_bytes(), s["file"])
        assert doc.chars > 1000 and doc.pages >= 1


def test_bad_documents_rejected():
    with pytest.raises(DocumentError):
        extract_text(b"", "empty.pdf")
    with pytest.raises(DocumentError):
        extract_text(b"hello world, not a pdf", "fake.pdf")


def test_input_validation_messages():
    subs = submissions()[:2]
    subs[1].supplier_name = subs[0].supplier_name.lower()
    subs[0].experience_rating = 9
    subs[0].submission_date = date.today() + timedelta(days=3)
    errs = validate_inputs(subs)
    assert any("Duplicate" in e for e in errs)
    assert any("experience rating" in e for e in errs)
    assert any("future" in e for e in errs)
    assert validate_inputs(subs[:1])  # fewer than 2 suppliers


def test_full_run_persists_and_is_reproducible(conn):
    agent = EvaluationAgent(OfflineDemoProvider())
    r1 = Orchestrator(conn, agent).run(submissions())
    r2 = Orchestrator(conn, agent).run(list(reversed(submissions())))
    assert strip_volatile(r1)["suppliers"] == strip_volatile(r2)["suppliers"]
    assert [s["final_rank"] for s in r1["suppliers"]] == [1, 2, 3, 4, 5]

    stored = db.get_run(conn, r1["rfp_run_id"])
    assert stored["rfp_run_id"] == r1["rfp_run_id"]
    rows = db.get_supplier_rows(conn, r1["rfp_run_id"])
    assert len(rows) == 5 and all(r["status"] == "EVALUATED" for r in rows)
    assert {r["final_rank"] for r in rows} == {1, 2, 3, 4, 5}
    runs = db.list_runs(conn)
    assert all(r["status"] == "COMPLETED" for r in runs)


def test_rerank_from_stored_scorecards_matches(conn):
    """Success condition: validated scorecards always reproduce the same ordering."""
    r = Orchestrator(conn, EvaluationAgent(OfflineDemoProvider())).run(submissions())
    again = rank_suppliers(r["criteria"], [
        SupplierInput(s["supplier_name"], date.fromisoformat(s["submission_date"]), s["experience_rating"],
                      {c["criterion_id"]: c["score"] for c in s["criteria"]}) for s in r["suppliers"]])
    assert [(s["supplier_name"], s["ppi"], s["absolute_score"]) for s in again["suppliers"]] == \
           [(s["supplier_name"], s["ppi"], s["absolute_score"]) for s in r["suppliers"]]


def test_fault_injection_is_normalised(conn):
    prov = FaultInjectingProvider(OfflineDemoProvider(), {"NexaWorks"})
    r = Orchestrator(conn, EvaluationAgent(prov)).run(submissions())
    nexa = next(s for s in r["suppliers"] if s["supplier_name"] == "NexaWorks")
    codes = {w[:2] for w in nexa["validation_warnings"]}
    assert {"V2", "V3", "V5", "V7", "V8", "V9"} <= codes
    assert all(0 <= c["score"] <= c["max_score"] for c in nexa["criteria"])
    assert nexa["criteria"][-1]["imputed"]


def test_criteria_changes_flow_into_next_run(conn):
    crit = db.get_all_criteria(conn)
    crit[4]["is_active"] = 0                     # drop Support & Experience
    crit[0]["weight"] = 40                       # Technical 30 -> 40 keeps total 100
    db.save_criteria(conn, crit)
    r = Orchestrator(conn, EvaluationAgent(OfflineDemoProvider())).run(submissions())
    assert len(r["criteria"]) == 4
    assert all(len(s["criteria"]) == 4 for s in r["suppliers"])


def test_invalid_criteria_rejected(conn):
    crit = db.get_all_criteria(conn)
    crit[0]["weight"] = 50
    with pytest.raises(ValueError):
        db.save_criteria(conn, crit)


def test_failed_llm_marks_run_failed(conn):
    class Broken:
        name, model = "broken", "none"

        def generate(self, *a, **k):
            raise ConnectionError("network down")

    with pytest.raises(Exception):
        Orchestrator(conn, EvaluationAgent(Broken(), max_retries=0, backoff_s=0)).run(submissions()[:2])
    assert db.list_runs(conn)[0]["status"] == "FAILED"
