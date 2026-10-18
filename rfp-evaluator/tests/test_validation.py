import json

from rfp_agent.validation_tool import validate_scorecard


def good_reply(criteria, score=7):
    return json.dumps({
        "supplier_name": "Acme",
        "criteria": [{"criterion_id": c["criterion_id"], "score": score, "max_score": c["max_score"],
                      "justification": "ok", "evidence": "quoted text"} for c in criteria],
        "risks": ["r1"], "overall_summary": "fine"})


def test_clean_reply_has_no_warnings(criteria):
    card = validate_scorecard(good_reply(criteria), "Acme", criteria)
    assert card.warnings == []
    assert [c.score for c in card.criteria] == [7] * len(criteria)


def test_invalid_json_imputes_all_zero(criteria):
    card = validate_scorecard("I think this supplier is great!", "Acme", criteria)
    assert not card.llm_output_valid_json
    assert all(c.score == 0 and c.imputed for c in card.criteria)
    assert any(w.startswith("V1") for w in card.warnings)


def test_markdown_fenced_json_is_accepted(criteria):
    card = validate_scorecard("Here you go:\n```json\n" + good_reply(criteria) + "\n```", "Acme", criteria)
    assert card.llm_output_valid_json and card.warnings == []


def test_out_of_range_scores_are_clipped(criteria):
    data = json.loads(good_reply(criteria))
    data["criteria"][0]["score"] = 15
    data["criteria"][1]["score"] = -3
    data["criteria"][0].pop("max_score")
    data["criteria"][1].pop("max_score")
    card = validate_scorecard(data, "Acme", criteria)
    assert card.criteria[0].score == 10 and card.criteria[1].score == 0
    assert sum(w.startswith("V7") for w in card.warnings) == 2


def test_non_numeric_and_string_scores(criteria):
    data = json.loads(good_reply(criteria))
    data["criteria"][0]["score"] = "eight"
    data["criteria"][1]["score"] = "6"
    data["criteria"][2]["score"] = None
    card = validate_scorecard(data, "Acme", criteria)
    assert card.criteria[0].score == 0 and card.criteria[1].score == 6 and card.criteria[2].score == 0
    assert sum(w.startswith("V5") for w in card.warnings) == 2


def test_rescale_different_max(criteria):
    data = json.loads(good_reply(criteria))
    data["criteria"][0].update(score=4, max_score=5)
    card = validate_scorecard(data, "Acme", criteria)
    assert card.criteria[0].score == 8
    assert any(w.startswith("V6") for w in card.warnings)


def test_missing_unknown_duplicate_criteria(criteria):
    data = json.loads(good_reply(criteria))
    dropped = data["criteria"].pop()                       # missing last criterion
    data["criteria"].append({"criterion_id": 999, "score": 9})   # unknown
    data["criteria"].append(dict(data["criteria"][0], score=1))  # duplicate of first
    card = validate_scorecard(data, "Acme", criteria)
    assert len(card.criteria) == len(criteria)
    last = card.criteria[-1]
    assert last.criterion_id == dropped["criterion_id"] and last.imputed and last.score == 0
    assert card.criteria[0].score == 7                     # first occurrence kept
    codes = {w[:2] for w in card.warnings}
    assert {"V3", "V4", "V8"} <= codes


def test_match_by_name_when_id_wrong(criteria):
    data = json.loads(good_reply(criteria))
    data["criteria"][0]["criterion_id"] = "abc"
    data["criteria"][0]["name"] = criteria[0]["name"].upper()
    card = validate_scorecard(data, "Acme", criteria)
    assert not card.criteria[0].imputed


def test_name_mismatch_and_missing_evidence(criteria):
    data = json.loads(good_reply(criteria))
    data["supplier_name"] = "Someone Else"
    data["criteria"][0]["evidence"] = ""
    data["risks"] = "single risk string"
    card = validate_scorecard(data, "Acme", criteria)
    assert card.supplier_name == "Acme"
    assert card.criteria[0].evidence_missing
    assert card.risks == ["single risk string"]
    codes = {w[:2] for w in card.warnings}
    assert {"V2", "V9"} <= codes
