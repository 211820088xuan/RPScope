"""P3 证据组装 - 每条证据回溯到 SQLite 具体行(表+主键+来源接口+报告期)。"""
from __future__ import annotations


def make_evidence(table: str, pk: int, source: str, report_period: str | None = None,
                  raw: dict | None = None) -> dict:
    return {"table": table, "pk": pk, "source": source,
            "report_period": report_period, "raw": raw or {}}


def entity_name(store, entity_id: int | None) -> str:
    if not entity_id:
        return ""
    r = store.conn.execute(
        "SELECT display_name, canonical_name FROM entity WHERE entity_id=?", (entity_id,)).fetchone()
    if not r:
        return ""
    return r["display_name"] or r["canonical_name"] or ""
