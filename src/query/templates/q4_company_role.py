"""Q4: 查某公司的股东/董监高/实控人。"""
from __future__ import annotations
from src.store.db import Store


def execute(store: Store, engine, slots: dict) -> dict:
    code = slots["company"]
    role = slots.get("role_type", "all")
    top_n = slots.get("top_n", 10)
    results = {}
    if role in ("holder", "all"):
        holders = [dict(r) for r in store.conn.execute(
            "SELECT e.display_name, e.entity_type, e.is_channel, "
            "MAX(h.ratio) AS ratio FROM holding h "
            "JOIN entity e ON h.entity_id=e.entity_id "
            "WHERE h.stock_code=? GROUP BY e.display_name, e.entity_type, e.is_channel "
            "ORDER BY MIN(h.id) LIMIT ?", (code, top_n)).fetchall()]
        results["holders"] = holders
    if role in ("controller", "all"):
        ctrl = [dict(r) for r in store.conn.execute(
            "SELECT ac.control_ratio, e.display_name, e.entity_type "
            "FROM actual_controller ac JOIN entity e ON ac.entity_id=e.entity_id "
            "WHERE ac.stock_code=? AND e.is_channel=0", (code,)).fetchall()]
        results["controllers"] = ctrl
    if role in ("director", "all"):
        directors = [dict(r) for r in store.conn.execute(
            "SELECT e.display_name, p.title, p.title_class "
            "FROM position p JOIN entity e ON p.entity_id=e.entity_id "
            "WHERE p.stock_code=?", (code,)).fetchall()]
        results["directors"] = directors
    return {"template": "Q4", "code": code, "roles": results,
            "evidence_source": "sql"}
