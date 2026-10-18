"""Orchestrator Agent: drives the ten-step workflow and records a trace.

Setup -> Input -> Batch -> Evaluate -> Validate -> Score -> Benchmark -> Rank -> Persist -> Present

The orchestrator decides *which tool runs when*; it never scores anything
itself. The LLM (Evaluation Agent) only judges proposal content; arithmetic,
benchmarks, tie-breaks and ranks come from the deterministic Ranking Tool.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable

from . import __version__
from . import database as db
from .document_tool import DocumentError, ExtractedDocument, extract_text
from .evaluation_agent import EvaluationAgent
from .ranking_tool import SupplierInput, rank_suppliers
from .validation_tool import validate_scorecard

MIN_SUPPLIERS = 2
EXPERIENCE_RANGE = (0.0, 5.0)


@dataclass
class SupplierSubmission:
    supplier_name: str
    submission_date: date
    experience_rating: float
    file_name: str
    pdf_bytes: bytes


def new_run_id() -> str:
    return f"RFP-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6].upper()}"


def validate_inputs(submissions: list[SupplierSubmission], today: date | None = None) -> list[str]:
    """Business validation of the batch before anything is written or any LLM is called."""
    today = today or date.today()
    errors: list[str] = []
    if len(submissions) < MIN_SUPPLIERS:
        errors.append(f"Upload at least {MIN_SUPPLIERS} supplier PDFs - peer benchmarking needs peers.")
    seen: dict[str, str] = {}
    for s in submissions:
        name = (s.supplier_name or "").strip()
        label = name or s.file_name
        if not name:
            errors.append(f"{s.file_name}: supplier name is required.")
        elif name.casefold() in seen:
            errors.append(f"Duplicate supplier name '{name}' ({seen[name.casefold()]} and {s.file_name}).")
        else:
            seen[name.casefold()] = s.file_name
        if not isinstance(s.submission_date, date):
            errors.append(f"{label}: submission date is required.")
        elif s.submission_date > today:
            errors.append(f"{label}: submission date {s.submission_date} is in the future.")
        try:
            rating = float(s.experience_rating)
            if not EXPERIENCE_RANGE[0] <= rating <= EXPERIENCE_RANGE[1]:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"{label}: experience rating must be between {EXPERIENCE_RANGE[0]:g} and "
                          f"{EXPERIENCE_RANGE[1]:g}.")
    return errors


class Orchestrator:
    def __init__(self, conn: sqlite3.Connection, agent: EvaluationAgent,
                 progress: Callable[[str, float], None] | None = None):
        self.conn = conn
        self.agent = agent
        self.progress = progress or (lambda msg, frac: None)
        self.trace: list[dict[str, Any]] = []

    def _log(self, step: str, tool: str, detail: str, t0: float | None = None) -> None:
        entry = {"step": step, "tool": tool, "detail": detail,
                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if t0 is not None:
            entry["seconds"] = round(time.perf_counter() - t0, 2)
        self.trace.append(entry)

    def run(self, submissions: list[SupplierSubmission]) -> dict[str, Any]:
        errors = validate_inputs(submissions)
        if errors:
            raise ValueError("Input validation failed:\n- " + "\n- ".join(errors))

        # Step 2b: extract all documents up-front so an unreadable PDF fails the batch early
        docs: dict[str, ExtractedDocument] = {}
        for s in submissions:
            t0 = time.perf_counter()
            docs[s.supplier_name] = extract_text(s.pdf_bytes, s.file_name)   # may raise DocumentError
            d = docs[s.supplier_name]
            self._log("2 Input", "Document Tool", f"{s.file_name}: {d.pages} pages, {d.chars} chars via "
                      f"{d.extractor}{' (truncated)' if d.truncated else ''}", t0)

        # Step 3: batch + run id + supplier entries
        run_id = new_run_id()
        db.create_run(self.conn, run_id, self.agent.provider.name, self.agent.provider.model)
        db.add_supplier_entries(self.conn, run_id, [
            {"supplier_name": s.supplier_name, "source_file": s.file_name,
             "submission_date": s.submission_date.isoformat(), "experience_rating": s.experience_rating}
            for s in submissions])
        self._log("3 Batch", "Orchestrator", f"Created {run_id} with {len(submissions)} supplier entries")

        try:
            # Step 4: reload LATEST active criteria at evaluation time
            criteria = db.get_active_criteria(self.conn)
            crit_errors = db.validate_criteria([{**c, "is_active": 1} for c in criteria])
            if crit_errors:
                raise ValueError("Criteria invalid: " + "; ".join(crit_errors))
            db.set_run_status(self.conn, run_id, "RUNNING", criteria_snapshot=criteria)
            self._log("4 Evaluate", "SQLite", f"Reloaded {len(criteria)} active criteria "
                      f"({', '.join(c['name'] + ' ' + format(c['weight'], 'g') + '%' for c in criteria)})")

            scorecards, run_warnings, llm_meta = {}, [], {}
            n = len(submissions)
            for i, s in enumerate(submissions):
                self.progress(f"Evaluating {s.supplier_name} ({i + 1}/{n})", i / (n + 1))
                db.set_supplier_status(self.conn, run_id, s.supplier_name, "EVALUATING")
                res = self.agent.evaluate(s.supplier_name, criteria, docs[s.supplier_name].text)
                self._log("4 Evaluate", "Evaluation Agent",
                          f"{s.supplier_name}: {res.attempts} call(s), {res.elapsed_s}s"
                          f"{', self-repaired JSON' if res.repaired else ''}")
                # Step 5: validate / normalise
                card = validate_scorecard(res.raw_text, s.supplier_name, criteria)
                scorecards[s.supplier_name] = card
                llm_meta[s.supplier_name] = {"attempts": res.attempts, "repaired": res.repaired,
                                             "elapsed_s": res.elapsed_s, "raw_reply_chars": len(res.raw_text)}
                run_warnings += [f"{s.supplier_name}: {w}" for w in card.warnings]
                self._log("5 Validate", "Validation Tool",
                          f"{s.supplier_name}: {len(card.warnings)} warning(s)"
                          f"{'' if card.llm_output_valid_json else ' - invalid JSON'}")
                db.set_supplier_status(self.conn, run_id, s.supplier_name, "VALIDATED")

            # Steps 6-8: deterministic scoring, benchmark, PPI, tie-break, rank
            self.progress("Scoring, benchmarking and ranking", n / (n + 1))
            t0 = time.perf_counter()
            ranking = rank_suppliers(criteria, [
                SupplierInput(s.supplier_name, s.submission_date, float(s.experience_rating),
                              {c.criterion_id: c.score for c in scorecards[s.supplier_name].criteria})
                for s in submissions])
            self._log("6-8 Score/Benchmark/Rank", "Ranking Tool",
                      f"Ranked {n} suppliers; {len(ranking['ties_resolved'])} PPI tie(s) resolved", t0)

            meta = {s.supplier_name: s for s in submissions}
            suppliers_out = []
            for r in ranking["suppliers"]:
                card = scorecards[r["supplier_name"]]
                by_id = {c.criterion_id: c for c in card.criteria}
                for d in r["criteria"]:
                    c = by_id[d["criterion_id"]]
                    d.update(justification=c.justification, evidence=c.evidence, imputed=c.imputed,
                             evidence_missing=c.evidence_missing)
                doc = docs[r["supplier_name"]]
                suppliers_out.append({
                    "final_rank": r["final_rank"], "supplier_name": r["supplier_name"],
                    "submission_date": r["submission_date"], "experience_rating": r["experience_rating"],
                    "absolute_score": r["absolute_score"], "ppi": r["ppi"], "ppi_sort_value": r["ppi_sort_value"],
                    "tie_break_explanation": r["tie_break_explanation"],
                    "criteria": r["criteria"], "risks": card.risks, "overall_summary": card.overall_summary,
                    "validation_warnings": card.warnings, "llm_output_valid_json": card.llm_output_valid_json,
                    "llm_call": llm_meta[r["supplier_name"]],
                    "source_document": {"file_name": meta[r["supplier_name"]].file_name, "pages": doc.pages,
                                        "chars": doc.chars, "sha256": doc.sha256, "truncated": doc.truncated},
                })

            result = {
                "rfp_run_id": run_id,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": "COMPLETED",
                "app_version": __version__,
                "llm": {"provider": self.agent.provider.name, "model": self.agent.provider.model,
                        "temperature": 0},
                "criteria": criteria,
                "formulas": {
                    "absolute_score": "sum((score / max_score) * weight)",
                    "benchmark": "max(score) for the criterion across all suppliers in the run",
                    "gap": "score - benchmark",
                    "relative_pct": "score / benchmark * 100 (0 when benchmark is 0)",
                    "ppi": "sum(relative_pct * weight) / sum(weight)",
                },
                "tie_break_rules": ranking["tie_break_rules"],
                "ties_resolved": ranking["ties_resolved"],
                "benchmarks": ranking["benchmarks"],
                "suppliers": suppliers_out,
                "warnings": run_warnings + ranking["notes"],
                "trace": self.trace,
            }
            # Step 9: persist everything under one RFP_RUN_ID
            t0 = time.perf_counter()
            self._log("9 Persist", "SQLite", f"Saved {n} supplier results and run JSON for {run_id}")
            db.save_run_results(self.conn, result)
            self.progress("Done", 1.0)
            return result
        except Exception as exc:
            db.set_run_status(self.conn, run_id, "FAILED", error_message=str(exc))
            self._log("FAILED", "Orchestrator", str(exc))
            raise


__all__ = ["Orchestrator", "SupplierSubmission", "validate_inputs", "DocumentError", "new_run_id"]
