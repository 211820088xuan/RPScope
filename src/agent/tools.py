"""P7 Agent 工具 - 包装规则引擎/事件/直接 SQL 为可调用工具。

每个工具返回结构化结果 + 供 verifier 回查的 evidence。
"""
from __future__ import annotations

from src.rules.engine import RuleEngine
from src.rules.path import render_path
from src.store.db import Store


def tool_fact(store: Store, code: str) -> dict:
    """事实查询: 公司基本信息 + 前十大股东 + 实控人(直接 SQL, <500ms)。"""
    co = store.conn.execute("SELECT * FROM company WHERE stock_code=?", (code,)).fetchone()
    holders = [dict(r) for r in store.conn.execute(
        "SELECT h.ratio, h.holder_rank, e.display_name, e.entity_type, e.is_channel "
        "FROM holding h JOIN entity e ON h.entity_id=e.entity_id "
        "WHERE h.stock_code=? ORDER BY h.holder_rank LIMIT 10", (code,)).fetchall()]
    ctrl = [dict(r) for r in store.conn.execute(
        "SELECT ac.control_ratio, e.display_name FROM actual_controller ac "
        "JOIN entity e ON ac.entity_id=e.entity_id WHERE ac.stock_code=? AND e.is_channel=0",
        (code,)).fetchall()]
    return {"intent": "fact_query", "company": dict(co) if co else None,
            "holders": holders, "controllers": ctrl}


def tool_related_party(store: Store, engine: RuleEngine, code: str, as_of: str | None = None) -> dict:
    """关联方查询: 规则引擎 R1-R7(<3s)。"""
    cands = engine.evaluate(store, code, as_of)
    return {"intent": "related_party", "code": code,
            "parties": [{"name": c.party_name, "rule": c.rule_id, "confidence": c.confidence,
                         "path": render_path(c.path), "score": c.score} for c in cands],
            "n": len(cands), "raw_cands": cands}


def tool_relation_explain(store: Store, engine: RuleEngine, code_a: str, code_b: str) -> dict:
    """A和B什么关系: 定向路径查询(<2s)。查 B 是否在 A 的关联方候选里。"""
    cands = engine.evaluate(store, code_a)
    target = f"C:{code_b}"
    hit = [c for c in cands if c.party_id == target]
    return {"intent": "relation_explain", "code_a": code_a, "code_b": code_b,
            "related": bool(hit), "path": render_path(hit[0].path) if hit else "",
            "rule": hit[0].rule_id if hit else "", "confidence": hit[0].confidence if hit else ""}


def tool_events(store: Store, code: str) -> dict:
    """事件时间线挂载。"""
    evs = [dict(r) for r in store.get_events(code)]
    return {"intent": "events", "events": evs, "n": len(evs)}
