"""P8 问答评测指标 - 答案正确性/引用正确性/回查通过率/幻觉率。

names 型: 金名集出现在答案里算命中(recall-oriented, ≥min_match)
bool 型: agent related 判定 == 金 bool
manual: 跳过(无金答案)
"""
from __future__ import annotations

from src.normalize.name import normalize_name, org_match_key


def name_in_answer(name: str, answer: str) -> bool:
    """金名(归一化)是否出现在答案里。"""
    a = normalize_name(answer)
    for cand in (normalize_name(name), org_match_key(name), name):
        if cand and cand in a:
            return True
    return False


def grade(qa: dict, agent_result: dict) -> dict:
    """返回 {correct, cited, verify_passed, hallucination}。"""
    answer = agent_result.get("answer", "")
    gold = qa.get("gold", {})
    gtype = gold.get("type")
    correct = None
    cited = bool(agent_result.get("verify", {}))  # 有 verify 结构即视为有引用

    if gtype == "names":
        expected = gold.get("expected", [])
        min_match = gold.get("min_match", 1)
        hits = sum(1 for n in expected if name_in_answer(n, answer))
        correct = hits >= min_match
        cited = len(expected) > 0 and hits > 0  # 命中即算引用对
    elif gtype == "bool":
        expected = gold.get("expected")
        # 从答案推断 agent 的 related 判定
        ans_related = ("关联" in answer and "未发现" not in answer and "无关联" not in answer)
        correct = (ans_related == expected)
    elif gtype == "manual":
        correct = None  # 跳过

    vp = agent_result.get("verify", {}).get("passed", True)
    vio = agent_result.get("verify", {}).get("violations", [])
    return {"correct": correct, "cited": cited, "verify_passed": vp,
            "hallucination": (not vp) and bool(vio), "intent": qa["intent"], "gtype": gtype}


def aggregate(results: list[dict]) -> dict:
    graded = [r for r in results if r["correct"] is not None]
    n = len(graded)
    correct = sum(1 for r in graded if r["correct"])
    cited = sum(1 for r in results if r["cited"])
    vp = sum(1 for r in results if r["verify_passed"])
    hal = sum(1 for r in results if r["hallucination"])
    total = len(results)
    by_intent = {}
    for r in graded:
        by_intent.setdefault(r["intent"], {"n": 0, "correct": 0})
        by_intent[r["intent"]]["n"] += 1
        if r["correct"]:
            by_intent[r["intent"]]["correct"] += 1
    return {"n_graded": n, "accuracy": correct / n if n else 0,
            "citation_rate": cited / total if total else 0,
            "verify_pass_rate": vp / total if total else 0,
            "hallucination_rate": hal / total if total else 0,
            "by_intent": {k: {"n": v["n"], "acc": v["correct"] / v["n"] if v["n"] else 0}
                          for k, v in by_intent.items()}}
