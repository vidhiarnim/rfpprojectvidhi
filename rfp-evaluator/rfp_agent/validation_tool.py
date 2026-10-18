"""Validation Tool: turn a raw LLM reply into a trusted, complete scorecard.

Every problem is fixed with a documented, deterministic rule and recorded as a
warning, so the downstream Ranking Tool always receives exactly one numeric
score in [0, max_score] for every active criterion.

Normalisation rules
-------------------
V1  Reply is not parseable JSON           -> every criterion imputed as 0 (warning)
V2  supplier_name differs from input      -> input name kept (warning)
V3  criterion_id missing/unknown          -> matched by criterion name if possible, else dropped
V4  duplicate criterion_id                -> first occurrence kept
V5  score not numeric / NaN / missing     -> 0
V6  LLM used a different max_score scale  -> score rescaled to the database max_score
V7  score outside [0, max_score]          -> clipped to the range
V8  active criterion missing from reply   -> imputed score 0, flagged ``imputed``
V9  empty evidence                        -> evidence "" kept, flagged ``evidence_missing``
V10 risks / summary wrong type            -> coerced to list[str] / str
Scores are rounded to 2 decimals after normalisation.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CriterionScore(BaseModel):
    criterion_id: int
    name: str
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    justification: str = ""
    evidence: str = ""
    imputed: bool = False
    evidence_missing: bool = False

    @field_validator("score")
    @classmethod
    def _rounded(cls, v: float) -> float:
        return round(v, 2)


class ValidatedScorecard(BaseModel):
    supplier_name: str
    criteria: list[CriterionScore]
    risks: list[str] = []
    overall_summary: str = ""
    warnings: list[str] = []
    llm_output_valid_json: bool = True


def _parse(raw: str | dict) -> dict | None:
    if isinstance(raw, dict):
        return raw
    text = re.sub(r"^```(?:json)?|```$", "", str(raw).strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None if math.isnan(value) or math.isinf(value) else float(value)
    if isinstance(value, str):
        m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*(?:/\s*(\d+(?:\.\d+)?))?\s*", value)
        if m:
            return float(m.group(1))
    return None


def validate_scorecard(raw: str | dict, supplier_name: str, criteria: list[dict[str, Any]]) -> ValidatedScorecard:
    warnings: list[str] = []
    by_id = {int(c["criterion_id"]): c for c in criteria}
    by_name = {c["name"].strip().lower(): int(c["criterion_id"]) for c in criteria}

    data = _parse(raw)
    valid_json = data is not None
    if data is None:
        warnings.append("V1: LLM reply was not valid JSON; all criteria imputed as 0.")
        data = {}

    returned_name = str(data.get("supplier_name") or "").strip()
    if valid_json and returned_name and returned_name.lower() != supplier_name.lower():
        warnings.append(f"V2: LLM returned supplier_name '{returned_name}'; using '{supplier_name}'.")

    items = data.get("criteria")
    if valid_json and not isinstance(items, list):
        warnings.append("V1: 'criteria' is missing or not a list; all criteria imputed as 0.")
        items = []
    items = items or []

    accepted: dict[int, CriterionScore] = {}
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            warnings.append(f"V3: criteria[{idx}] is not an object; ignored.")
            continue
        cid = _to_number(item.get("criterion_id"))
        cid = int(cid) if cid is not None and cid == int(cid) else None
        if cid not in by_id:
            name_key = str(item.get("name") or item.get("criterion") or "").strip().lower()
            if name_key in by_name:
                cid = by_name[name_key]
                warnings.append(f"V3: criteria[{idx}] matched by name to criterion {cid}.")
            else:
                warnings.append(f"V3: criteria[{idx}] has unknown criterion_id "
                                f"'{item.get('criterion_id')}'; ignored.")
                continue
        crit = by_id[cid]
        label = f"criterion {cid} ({crit['name']})"
        if cid in accepted:
            warnings.append(f"V4: duplicate result for {label}; first occurrence kept.")
            continue

        db_max = float(crit["max_score"])
        score = _to_number(item.get("score"))
        if score is None:
            warnings.append(f"V5: {label} score '{item.get('score')}' is not numeric; set to 0.")
            score = 0.0
        llm_max = _to_number(item.get("max_score"))
        if llm_max and llm_max > 0 and abs(llm_max - db_max) > 1e-9 and 0 <= score <= llm_max:
            new = score / llm_max * db_max
            warnings.append(f"V6: {label} scored on a 0-{llm_max:g} scale; rescaled {score:g} -> {new:.2f}.")
            score = new
        if score < 0 or score > db_max:
            clipped = min(max(score, 0.0), db_max)
            warnings.append(f"V7: {label} score {score:g} outside 0-{db_max:g}; clipped to {clipped:g}.")
            score = clipped

        evidence = str(item.get("evidence") or "").strip()
        ev_missing = not evidence
        if ev_missing:
            warnings.append(f"V9: {label} has no supporting evidence quote.")
        accepted[cid] = CriterionScore(
            criterion_id=cid, name=crit["name"], score=score, max_score=db_max,
            justification=str(item.get("justification") or "").strip() or "No justification provided.",
            evidence=evidence, evidence_missing=ev_missing)

    final: list[CriterionScore] = []
    for cid, crit in by_id.items():
        if cid in accepted:
            final.append(accepted[cid])
        else:
            if valid_json:
                warnings.append(f"V8: criterion {cid} ({crit['name']}) missing from LLM output; imputed 0.")
            final.append(CriterionScore(
                criterion_id=cid, name=crit["name"], score=0.0, max_score=float(crit["max_score"]),
                justification="Not evaluated - criterion missing from LLM output (imputed 0).",
                evidence="", imputed=True, evidence_missing=True))

    risks = data.get("risks", [])
    if isinstance(risks, str):
        risks = [risks]
    if not isinstance(risks, list):
        warnings.append("V10: 'risks' was not a list; ignored.")
        risks = []
    summary = data.get("overall_summary", "")
    if not isinstance(summary, str):
        warnings.append("V10: 'overall_summary' was not text; converted.")
        summary = json.dumps(summary)

    return ValidatedScorecard(supplier_name=supplier_name, criteria=final,
                              risks=[str(r) for r in risks if str(r).strip()],
                              overall_summary=summary.strip(), warnings=warnings,
                              llm_output_valid_json=valid_json)
