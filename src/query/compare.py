"""T4+T5: 对比分析 — 确定性查询 + LLM 仅措辞。

5 个维度: 基本信息/股权结构/关联方/董监高/风险事件。
全部走确定性代码, LLM 只写摘要。
"""
from __future__ import annotations
import json
from src.rules.engine import RuleEngine
from src.rules.path import render_path
from src.store.db import Store


def compare(store: Store, engine: RuleEngine, code_a: str, code_b: str) -> dict:
    """两家公司全面对比。确定性, 无 LLM。"""
    a = code_a.zfill(6)
    b = code_b.zfill(6)

    # 1. 基本信息
    co_a = dict(store.conn.execute("SELECT * FROM company WHERE stock_code=?", (a,)).fetchone() or {})
    co_b = dict(store.conn.execute("SELECT * FROM company WHERE stock_code=?", (b,)).fetchone() or {})

    # 2. 股权结构
    holders_a = [dict(r) for r in store.conn.execute(
        "SELECT e.display_name, e.entity_type, e.is_channel, MAX(h.ratio) AS ratio "
        "FROM holding h JOIN entity e ON h.entity_id=e.entity_id "
        "WHERE h.stock_code=? GROUP BY e.display_name, e.entity_type, e.is_channel "
        "ORDER BY MIN(h.id) LIMIT 10", (a,)).fetchall()]
    holders_b = [dict(r) for r in store.conn.execute(
        "SELECT e.display_name, e.entity_type, e.is_channel, MAX(h.ratio) AS ratio "
        "FROM holding h JOIN entity e ON h.entity_id=e.entity_id "
        "WHERE h.stock_code=? GROUP BY e.display_name, e.entity_type, e.is_channel "
        "ORDER BY MIN(h.id) LIMIT 10", (b,)).fetchall()]
    ctrl_a = [dict(r) for r in store.conn.execute(
        "SELECT ac.control_ratio, e.display_name FROM actual_controller ac "
        "JOIN entity e ON ac.entity_id=e.entity_id WHERE ac.stock_code=? AND e.is_channel=0", (a,)).fetchall()]
    ctrl_b = [dict(r) for r in store.conn.execute(
        "SELECT ac.control_ratio, e.display_name FROM actual_controller ac "
        "JOIN entity e ON ac.entity_id=e.entity_id WHERE ac.stock_code=? AND e.is_channel=0", (b,)).fetchall()]

    # 3. 关联方 + 重合
    cands_a = engine.evaluate(store, a)
    cands_b = engine.evaluate(store, b)
    names_a = {c.party_name for c in cands_a}
    names_b = {c.party_name for c in cands_b}
    overlap = names_a & names_b
    overlap_detail = []
    for name in sorted(overlap):
        ca = next(c for c in cands_a if c.party_name == name)
        cb = next(c for c in cands_b if c.party_name == name)
        overlap_detail.append({"name": name, "rule_a": ca.rule_id, "rule_b": cb.rule_id,
                               "confidence": ca.confidence, "path": render_path(ca.path)})

    # 4. 董监高
    dirs_a = [dict(r) for r in store.conn.execute(
        "SELECT e.display_name, p.title FROM position p JOIN entity e ON p.entity_id=e.entity_id "
        "WHERE p.stock_code=?", (a,)).fetchall()]
    dirs_b = [dict(r) for r in store.conn.execute(
        "SELECT e.display_name, p.title FROM position p JOIN entity e ON p.entity_id=e.entity_id "
        "WHERE p.stock_code=?", (b,)).fetchall()]
    dir_names_a = {d["display_name"] for d in dirs_a}
    dir_names_b = {d["display_name"] for d in dirs_b}
    cross_dirs = dir_names_a & dir_names_b

    # 5. 风险事件
    events_a = [dict(r) for r in store.conn.execute(
        "SELECT event_type, event_date, counterparty, amount, summary FROM event WHERE subject_code=? ORDER BY event_date", (a,)).fetchall()]
    events_b = [dict(r) for r in store.conn.execute(
        "SELECT event_type, event_date, counterparty, amount, summary FROM event WHERE subject_code=? ORDER BY event_date", (b,)).fetchall()]
    # 按类型统计
    ev_summary_a = {}
    for e in events_a:
        et = e.get("event_type", "unknown")
        ev_summary_a.setdefault(et, {"count": 0, "total_amount": 0})
        ev_summary_a[et]["count"] += 1
        ev_summary_a[et]["total_amount"] += e.get("amount") or 0
    ev_summary_b = {}
    for e in events_b:
        et = e.get("event_type", "unknown")
        ev_summary_b.setdefault(et, {"count": 0, "total_amount": 0})
        ev_summary_b[et]["count"] += 1
        ev_summary_b[et]["total_amount"] += e.get("amount") or 0

    return {
        "template": "compare",
        "code_a": a, "code_b": b,
        "basic": {"a": co_a, "b": co_b},
        "holders": {"a": holders_a, "b": holders_b},
        "controllers": {"a": ctrl_a, "b": ctrl_b},
        "related": {
            "n_a": len(cands_a), "n_b": len(cands_b),
            "n_overlap": len(overlap), "overlap": overlap_detail,
        },
        "directors": {"n_a": len(dirs_a), "n_b": len(dirs_b),
                      "cross_count": len(cross_dirs), "cross": list(cross_dirs)[:10]},
        "events": {"a": ev_summary_a, "b": ev_summary_b,
                   "n_a": len(events_a), "n_b": len(events_b)},
        "evidence_source": "deterministic",
    }
