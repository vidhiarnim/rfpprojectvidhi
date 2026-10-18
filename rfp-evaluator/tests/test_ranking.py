import random
from datetime import date

import pytest

from rfp_agent.ranking_tool import SupplierInput, rank_suppliers

CRIT = [
    {"criterion_id": 1, "name": "Tech", "weight": 30, "max_score": 10},
    {"criterion_id": 2, "name": "Plan", "weight": 20, "max_score": 10},
    {"criterion_id": 3, "name": "Price", "weight": 20, "max_score": 10},
    {"criterion_id": 4, "name": "Security", "weight": 20, "max_score": 10},
    {"criterion_id": 5, "name": "Support", "weight": 10, "max_score": 10},
]


def sup(name, scores, d="2026-09-20", exp=3.0):
    return SupplierInput(name, date.fromisoformat(d), exp, dict(zip(range(1, 6), scores)))


def by_name(result):
    return {s["supplier_name"]: s for s in result["suppliers"]}


def test_absolute_score_formula():
    r = rank_suppliers(CRIT, [sup("A", [8, 6, 5, 9, 7]), sup("B", [10, 10, 10, 10, 10])])
    # 8/10*30 + 6/10*20 + 5/10*20 + 9/10*20 + 7/10*10 = 24+12+10+18+7 = 71
    assert by_name(r)["A"]["absolute_score"] == 71.0
    assert by_name(r)["B"]["absolute_score"] == 100.0


def test_benchmark_gap_relative_and_ppi():
    r = rank_suppliers(CRIT, [sup("A", [8, 6, 5, 9, 7]), sup("B", [4, 8, 10, 3, 7])])
    a = by_name(r)["A"]
    tech = a["criteria"][0]
    assert tech["benchmark"] == 8 and tech["gap"] == 0 and tech["relative_pct"] == 100
    plan = a["criteria"][1]
    assert plan["benchmark"] == 8 and plan["gap"] == -2 and plan["relative_pct"] == 75
    # PPI A = (100*30 + 75*20 + 50*20 + 100*20 + 100*10)/100 = 85
    assert a["ppi"] == 85.0
    # PPI B = (50*30 + 100*20 + 100*20 + 33.333*20 + 100*10)/100 = 71.67
    assert by_name(r)["B"]["ppi"] == pytest.approx(71.67, abs=0.01)
    assert [s["supplier_name"] for s in r["suppliers"]] == ["A", "B"]


def test_zero_benchmark_is_safe():
    r = rank_suppliers(CRIT, [sup("A", [5, 0, 5, 5, 5]), sup("B", [6, 0, 4, 4, 4])])
    plan = by_name(r)["A"]["criteria"][1]
    assert plan["benchmark"] == 0 and plan["relative_pct"] == 0
    assert any(b["benchmark_zero"] for b in r["benchmarks"])


def test_gaps_never_positive():
    r = rank_suppliers(CRIT, [sup("A", [8, 6, 5, 9, 7]), sup("B", [4, 8, 10, 3, 7]), sup("C", [1, 2, 3, 4, 5])])
    assert all(c["gap"] <= 0 for s in r["suppliers"] for c in s["criteria"])


def test_tie_break_submission_date():
    r = rank_suppliers(CRIT, [sup("Late", [7] * 5, "2026-09-25"), sup("Early", [7] * 5, "2026-09-21")])
    assert [s["supplier_name"] for s in r["suppliers"]] == ["Early", "Late"]
    assert "Rule 2" in r["suppliers"][1]["tie_break_explanation"]
    assert r["ties_resolved"]


def test_tie_break_experience():
    r = rank_suppliers(CRIT, [sup("Low", [7] * 5, exp=2), sup("High", [7] * 5, exp=4.5)])
    assert [s["supplier_name"] for s in r["suppliers"]] == ["High", "Low"]
    assert "Rule 3" in r["suppliers"][1]["tie_break_explanation"]


def test_tie_break_name_ascending():
    r = rank_suppliers(CRIT, [sup("zeta", [7] * 5), sup("Alpha", [7] * 5), sup("beta", [7] * 5)])
    assert [s["supplier_name"] for s in r["suppliers"]] == ["Alpha", "beta", "zeta"]
    assert [s["final_rank"] for s in r["suppliers"]] == [1, 2, 3]
    assert "Rule 4" in r["suppliers"][2]["tie_break_explanation"]


def test_ppi_beats_every_other_rule():
    r = rank_suppliers(CRIT, [sup("Aaa", [5] * 5, "2026-01-01", 5), sup("Zzz", [6] * 5, "2026-12-01", 0)])
    assert r["suppliers"][0]["supplier_name"] == "Zzz"


def test_order_independent_and_repeatable():
    base = [sup("A", [8, 6, 5, 9, 7]), sup("B", [4, 8, 10, 3, 7]), sup("C", [8, 6, 5, 9, 7], exp=4),
            sup("D", [7, 7, 7, 7, 7], "2026-09-01"), sup("E", [7, 7, 7, 7, 7], "2026-09-01")]
    expected = rank_suppliers(CRIT, base)
    for seed in range(20):
        shuffled = base[:]
        random.Random(seed).shuffle(shuffled)
        assert rank_suppliers(CRIT, shuffled) == expected


def test_weights_not_100_are_normalised():
    crit = [dict(c, weight=c["weight"] / 2) for c in CRIT]   # total 50
    r = rank_suppliers(crit, [sup("A", [10] * 5), sup("B", [5] * 5)])
    assert by_name(r)["A"]["absolute_score"] == 100.0
    assert r["notes"]


def test_duplicate_names_rejected():
    with pytest.raises(ValueError):
        rank_suppliers(CRIT, [sup("A", [1] * 5), sup("a", [2] * 5)])
