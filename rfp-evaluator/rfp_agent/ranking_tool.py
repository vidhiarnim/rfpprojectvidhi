"""Ranking Tool: deterministic scoring, peer benchmarking, PPI and tie-breaks.

Pure Python, no LLM, no I/O. Given the same validated scorecards, criteria and
supplier metadata it always returns the same numbers and the same order,
regardless of the order suppliers are passed in.

Formulas (w_c = criterion weight in %, active weights total 100)
------------------------------------------------------------------
absolute_score      = sum_c (score_c / max_c) * w_c                          (0-100)
benchmark_c         = max over suppliers of score_c
gap_c               = score_c - benchmark_c                                  (<= 0)
relative_pct_c      = score_c / benchmark_c * 100;  0 when benchmark_c == 0
PPI                 = sum_c relative_pct_c * w_c / sum_c w_c                 (0-100)

Tie-break order (stable sort, then sequential ranks 1..n)
---------------------------------------------------------
1) higher PPI  2) earlier submission date  3) higher experience rating
4) supplier name ascending (case-insensitive, then exact as final guard)
PPI is compared after rounding to PPI_DECIMALS to avoid float noise.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

PPI_DECIMALS = 4
DISPLAY_DECIMALS = 2

TIE_BREAK_RULES = [
    "1) Higher Peer Performance Index (PPI) ranks first",
    "2) If PPI is tied, the earlier submission date ranks first",
    "3) If still tied, the higher historical experience rating ranks first",
    "4) If still tied, supplier name in ascending (A-Z) order",
]


@dataclass(frozen=True)
class SupplierInput:
    supplier_name: str
    submission_date: date
    experience_rating: float
    scores: dict[int, float]              # criterion_id -> validated score


def _to_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _sort_key(s: dict[str, Any]) -> tuple:
    return (-round(s["_ppi_raw"], PPI_DECIMALS), _to_date(s["submission_date"]),
            -float(s["experience_rating"]), s["supplier_name"].casefold(), s["supplier_name"])


def _decider(a: dict[str, Any], b: dict[str, Any]) -> str:
    """Explain why supplier a is ranked directly above supplier b."""
    pa, pb = round(a["_ppi_raw"], PPI_DECIMALS), round(b["_ppi_raw"], PPI_DECIMALS)
    if pa != pb:
        return f"Rule 1 - higher PPI ({a['ppi']:.2f} vs {b['ppi']:.2f})"
    da, db = _to_date(a["submission_date"]), _to_date(b["submission_date"])
    if da != db:
        return f"PPI tied at {a['ppi']:.2f}; Rule 2 - earlier submission date ({da} vs {db})"
    if float(a["experience_rating"]) != float(b["experience_rating"]):
        return (f"PPI and submission date tied; Rule 3 - higher experience rating "
                f"({a['experience_rating']:g} vs {b['experience_rating']:g})")
    return "PPI, submission date and experience rating tied; Rule 4 - supplier name A-Z"


def rank_suppliers(criteria: list[dict[str, Any]], suppliers: list[SupplierInput]) -> dict[str, Any]:
    if not criteria:
        raise ValueError("No active criteria supplied to the ranking tool.")
    if not suppliers:
        raise ValueError("No suppliers supplied to the ranking tool.")
    names = [s.supplier_name for s in suppliers]
    if len({n.casefold() for n in names}) != len(names):
        raise ValueError("Supplier names must be unique within a run.")

    total_w = sum(float(c["weight"]) for c in criteria)
    if total_w <= 0:
        raise ValueError("Active criteria weights must be positive.")
    weight_note = None
    if abs(total_w - 100) > 0.01:
        weight_note = f"Active weights total {total_w:g}%; weights normalised to 100%."

    # 1) Benchmarks: highest validated score per criterion across all suppliers
    benchmarks: dict[int, dict[str, Any]] = {}
    for c in criteria:
        cid = int(c["criterion_id"])
        best = max(float(s.scores.get(cid, 0.0)) for s in suppliers)
        leaders = sorted(s.supplier_name for s in suppliers if float(s.scores.get(cid, 0.0)) == best)
        benchmarks[cid] = {"criterion_id": cid, "name": c["name"], "benchmark_score": best,
                           "max_score": float(c["max_score"]), "leaders": leaders,
                           "benchmark_zero": best == 0}

    # 2) Per-supplier metrics
    rows: list[dict[str, Any]] = []
    for s in suppliers:
        abs_score, ppi_num, details = 0.0, 0.0, []
        for c in criteria:
            cid, w, mx = int(c["criterion_id"]), float(c["weight"]) / total_w * 100, float(c["max_score"])
            sc = float(s.scores.get(cid, 0.0))
            bm = benchmarks[cid]["benchmark_score"]
            weighted = sc / mx * w
            rel = (sc / bm * 100) if bm > 0 else 0.0
            abs_score += weighted
            ppi_num += rel * w
            details.append({
                "criterion_id": cid, "name": c["name"], "weight": round(w, 4), "max_score": mx,
                "score": sc, "benchmark": bm, "gap": round(sc - bm, DISPLAY_DECIMALS),
                "relative_pct": round(rel, DISPLAY_DECIMALS),
                "weighted_points": round(weighted, DISPLAY_DECIMALS),
                "is_benchmark_leader": bm > 0 and sc == bm,
            })
        ppi_raw = ppi_num / 100
        rows.append({
            "supplier_name": s.supplier_name,
            "submission_date": _to_date(s.submission_date).isoformat(),
            "experience_rating": float(s.experience_rating),
            "absolute_score": round(abs_score, DISPLAY_DECIMALS),
            "ppi": round(ppi_raw, DISPLAY_DECIMALS),
            "_ppi_raw": ppi_raw,
            "criteria": details,
        })

    # 3) Deterministic stable sort and sequential ranks
    rows.sort(key=_sort_key)
    for i, r in enumerate(rows):
        r["final_rank"] = i + 1
        if i == 0:
            r["tie_break_explanation"] = "Ranked 1st - highest PPI after tie-break rules."
            if len(rows) > 1:
                r["tie_break_explanation"] = f"Ranked 1st; above {rows[1]['supplier_name']}: {_decider(r, rows[1])}."
        else:
            r["tie_break_explanation"] = (f"Ranked {i + 1}; below {rows[i - 1]['supplier_name']}: "
                                          f"{_decider(rows[i - 1], r)}.")

    ties = []
    for a, b in zip(rows, rows[1:]):
        if round(a["_ppi_raw"], PPI_DECIMALS) == round(b["_ppi_raw"], PPI_DECIMALS):
            ties.append(f"{a['supplier_name']} and {b['supplier_name']} tied on PPI "
                        f"({a['ppi']:.2f}); resolved by: {_decider(a, b)}")
    for r in rows:
        r["ppi_sort_value"] = round(r.pop("_ppi_raw"), PPI_DECIMALS)

    return {
        "benchmarks": list(benchmarks.values()),
        "suppliers": rows,
        "tie_break_rules": TIE_BREAK_RULES,
        "ties_resolved": ties,
        "notes": [n for n in [weight_note] if n],
    }
