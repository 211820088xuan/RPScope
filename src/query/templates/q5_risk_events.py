"""Q5: 查某公司的风险事件。"""
from __future__ import annotations
from src.store.db import Store


def execute(store: Store, engine, slots: dict) -> dict:
    code = slots["company"]
    event_types = slots.get("event_types")
    date_range = slots.get("date_range")
    q = "SELECT event_type, event_date, counterparty, amount, summary, source_type " \
        "FROM event WHERE subject_code=?"
    params = [code]
    if event_types:
        placeholders = ",".join("?" * len(event_types))
        q += f" AND event_type IN ({placeholders})"
        params.extend(event_types)
    if date_range and len(date_range) == 2:
        q += " AND event_date >= ? AND event_date <= ?"
        params.extend(date_range)
    q += " ORDER BY event_date"
    events = [dict(r) for r in store.conn.execute(q, params).fetchall()]
    return {"template": "Q5", "code": code, "events": events, "n": len(events),
            "evidence_source": "sql"}
