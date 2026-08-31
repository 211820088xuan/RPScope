"""Q6: 两家公司的关联方重合。"""
from __future__ import annotations
from src.rules.engine import RuleEngine
from src.store.db import Store


def execute(store: Store, engine: RuleEngine, slots: dict) -> dict:
    code_a = slots["company_a"]
    code_b = slots["company_b"]
    as_of = slots.get("as_of")
    cands_a = engine.evaluate(store, code_a, as_of)
    cands_b = engine.evaluate(store, code_b, as_of)
    names_a = {c.party_name for c in cands_a}
    names_b = {c.party_name for c in cands_b}
    overlap = names_a & names_b
    overlap_detail = []
    for name in overlap:
        ca = next(c for c in cands_a if c.party_name == name)
        cb = next(c for c in cands_b if c.party_name == name)
        overlap_detail.append({"name": name, "rule_a": ca.rule_id, "rule_b": cb.rule_id,
                               "confidence": ca.confidence})
    return {"template": "Q6", "code_a": code_a, "code_b": code_b,
            "overlap": overlap_detail, "n_a": len(names_a), "n_b": len(names_b),
            "n_overlap": len(overlap), "evidence_source": "rules_engine"}
