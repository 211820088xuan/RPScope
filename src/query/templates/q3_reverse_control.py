"""Q3: 反向查询 — 某人/机构控制或持股哪些公司。"""
from __future__ import annotations
from src.store.db import Store


def execute(store: Store, engine, slots: dict) -> dict:
    entity = slots["entity"]
    rel_type = slots.get("relation_type")
    min_ratio = slots.get("min_ratio")
    as_of = slots.get("as_of")
    eid = entity.get("entity_id")
    ename = entity.get("name", "")
    results = []
    if not rel_type or rel_type == "control":
        rows = store.conn.execute(
            "SELECT ac.stock_code, ac.control_ratio, e.display_name AS controller_name, "
            "c.short_name FROM actual_controller ac "
            "JOIN entity e ON ac.entity_id=e.entity_id "
            "JOIN company c ON ac.stock_code=c.stock_code "
            "WHERE ac.entity_id=? AND e.is_channel=0", (eid,)).fetchall()
        for r in rows:
            results.append({"stock_code": r["stock_code"], "short_name": r["short_name"],
                            "relation": "control", "ratio": r["control_ratio"]})
    if not rel_type or rel_type == "hold":
        rows = store.conn.execute(
            "SELECT h.stock_code, MAX(h.ratio) AS ratio, c.short_name "
            "FROM holding h JOIN company c ON h.stock_code=c.stock_code "
            "WHERE h.entity_id=? GROUP BY h.stock_code, c.short_name "
            "ORDER BY MAX(h.ratio) DESC", (eid,)).fetchall()
        for r in rows:
            if min_ratio and (r["ratio"] or 0) < min_ratio:
                continue
            results.append({"stock_code": r["stock_code"], "short_name": r["short_name"],
                            "relation": "hold", "ratio": r["ratio"]})
    if not rel_type or rel_type == "serve":
        rows = store.conn.execute(
            "SELECT p.stock_code, p.title, c.short_name "
            "FROM position p JOIN company c ON p.stock_code=c.stock_code "
            "WHERE p.entity_id=?", (eid,)).fetchall()
        for r in rows:
            results.append({"stock_code": r["stock_code"], "short_name": r["short_name"],
                            "relation": "serve", "title": r["title"]})
    return {"template": "Q3", "entity": ename, "results": results, "n": len(results),
            "evidence_source": "sql"}
