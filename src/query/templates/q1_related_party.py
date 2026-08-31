"""Q1: 查某公司的关联方 — 复用规则引擎 R1-R7。"""
from __future__ import annotations
from src.rules.engine import RuleEngine
from src.rules.path import render_path
from src.store.db import Store


def execute(store: Store, engine: RuleEngine, slots: dict) -> dict:
    code = slots["company"]
    rule_ids = slots.get("rule_ids")
    min_conf = slots.get("min_confidence")
    as_of = slots.get("as_of")
    cands = engine.evaluate(store, code, as_of)
    if rule_ids:
        cands = [c for c in cands if c.rule_id in rule_ids]
    if min_conf:
        order = {"high": 0, "medium": 1, "low": 2}
        threshold = order.get(min_conf, 2)
        cands = [c for c in cands if order.get(c.confidence, 2) <= threshold]
    parties = [{"name": c.party_name, "rule": c.rule_id, "confidence": c.confidence,
                "path": render_path(c.path), "score": c.score} for c in cands]
    return {"template": "Q1", "code": code, "parties": parties, "n": len(parties),
            "evidence_source": "rules_engine"}
