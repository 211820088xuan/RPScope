"""T3: 实体链接 — 把槽位中的实体文本链接到图节点。

公司: 股票代码直接匹配 → 简称精确匹配 → 全称匹配 → 归一化键匹配 → 模糊候选
自然人/机构: 复用 normalize_name + entity 表查询

三种结果:
  - 唯一命中 → 继续
  - 多个候选 → 返回澄清请求
  - 无命中 → 返回"未找到"+ 最接近候选
"""
from __future__ import annotations
import re
from src.normalize.name import normalize_name, org_match_key
from src.store.db import Store


def link_company(store: Store, text: str) -> dict:
    """把文本链接到公司节点。返回 {matched, code, name, method, candidates}。"""
    text = text.strip()
    # 1. 6位代码直接匹配
    if re.match(r"^\d{6}$", text):
        row = store.conn.execute(
            "SELECT stock_code, short_name FROM company WHERE stock_code=?", (text,)).fetchone()
        if row:
            return {"matched": True, "code": row["stock_code"], "name": row["short_name"],
                    "method": "exact_code", "candidates": []}

    # 2. 简称精确匹配
    rows = store.conn.execute(
        "SELECT stock_code, short_name FROM company WHERE short_name=?", (text,)).fetchall()
    if len(rows) == 1:
        return {"matched": True, "code": rows[0]["stock_code"], "name": rows[0]["short_name"],
                "method": "short_name_exact", "candidates": []}
    if len(rows) > 1:
        cands = [{"code": r["stock_code"], "name": r["short_name"]} for r in rows]
        return {"matched": False, "code": None, "name": None, "method": "short_name_ambiguous",
                "candidates": cands, "clarify": True}

    # 3. 全称匹配
    rows = store.conn.execute(
        "SELECT stock_code, short_name FROM company WHERE full_name=?", (text,)).fetchall()
    if len(rows) == 1:
        return {"matched": True, "code": rows[0]["stock_code"], "name": rows[0]["short_name"],
                "method": "full_name_exact", "candidates": []}

    # 4. 归一化键匹配
    key = normalize_name(text)
    rows = store.conn.execute(
        "SELECT stock_code, short_name FROM company WHERE short_name=? COLLATE NOCASE", (key,)).fetchall()
    if len(rows) == 1:
        return {"matched": True, "code": rows[0]["stock_code"], "name": rows[0]["short_name"],
                "method": "normalized", "candidates": []}

    # 5. 模糊候选 (LIKE)
    rows = store.conn.execute(
        "SELECT stock_code, short_name FROM company WHERE short_name LIKE ? LIMIT 5", (f"%{text}%",)).fetchall()
    if rows:
        cands = [{"code": r["stock_code"], "name": r["short_name"]} for r in rows]
        return {"matched": False, "code": None, "name": None, "method": "fuzzy",
                "candidates": cands, "clarify": len(cands) > 1}

    return {"matched": False, "code": None, "name": None, "method": "not_found",
            "candidates": [], "clarify": False}


def link_entity(store: Store, text: str) -> dict:
    """把文本链接到 entity 节点(人/机构)。返回 {matched, entity_id, name, method, candidates}。
    先查 company 表, 因为公司名在 entity 表可能有多个保险产品变体。"""
    text = text.strip()
    # 0. 先查 company 表, 如果匹配到唯一公司, 用其 short_name 在 entity 表找实体
    co = store.conn.execute(
        "SELECT stock_code, short_name FROM company WHERE short_name=? COLLATE NOCASE", (text,)).fetchall()
    if len(co) == 1:
        cname = co[0]["short_name"]
        # 精确匹配
        rows = store.conn.execute(
            "SELECT entity_id, display_name, entity_type FROM entity "
            "WHERE display_name=? COLLATE NOCASE AND is_channel=0", (cname,)).fetchall()
        if len(rows) >= 1:
            return {"matched": True, "entity_id": rows[0]["entity_id"], "name": rows[0]["display_name"],
                    "type": rows[0]["entity_type"], "method": "company_name->entity", "candidates": []}
        # 模糊匹配 + 选 holding 记录最多的实体(最可能是主体)
        rows = store.conn.execute(
            "SELECT e.entity_id, e.display_name, e.entity_type, "
            "(SELECT COUNT(*) FROM holding h WHERE h.entity_id=e.entity_id) AS hold_count "
            "FROM entity e WHERE e.display_name LIKE ? AND e.is_channel=0 "
            "ORDER BY hold_count DESC LIMIT 1", (f"{cname}%",)).fetchone()
        if rows and rows["hold_count"] > 0:
            return {"matched": True, "entity_id": rows["entity_id"], "name": rows["display_name"],
                    "type": rows["entity_type"], "method": "company_fuzzy+hold_count", "candidates": []}
    # 精确匹配 display_name
    rows = store.conn.execute(
        "SELECT entity_id, display_name, entity_type, canonical_name FROM entity "
        "WHERE display_name=? COLLATE NOCASE AND is_channel=0", (text,)).fetchall()
    if len(rows) == 1:
        return {"matched": True, "entity_id": rows[0]["entity_id"], "name": rows[0]["display_name"],
                "type": rows[0]["entity_type"], "method": "display_name_exact", "candidates": []}
    if len(rows) > 1:
        cands = [{"entity_id": r["entity_id"], "name": r["display_name"], "type": r["entity_type"]} for r in rows]
        return {"matched": False, "entity_id": None, "name": None, "method": "ambiguous",
                "candidates": cands, "clarify": True}

    # 归一化匹配
    key = normalize_name(text)
    org_key = org_match_key(text)
    for k in (key, org_key, text):
        if k:
            rows = store.conn.execute(
                "SELECT entity_id, display_name, entity_type FROM entity "
                "WHERE canonical_name=? COLLATE NOCASE AND is_channel=0", (k,)).fetchall()
            if len(rows) == 1:
                return {"matched": True, "entity_id": rows[0]["entity_id"], "name": rows[0]["display_name"],
                        "type": rows[0]["entity_type"], "method": "normalized", "candidates": []}

    # 模糊候选
    rows = store.conn.execute(
        "SELECT entity_id, display_name, entity_type FROM entity "
        "WHERE display_name LIKE ? AND is_channel=0 LIMIT 5", (f"%{text}%",)).fetchall()
    if rows:
        cands = [{"entity_id": r["entity_id"], "name": r["display_name"], "type": r["entity_type"]} for r in rows]
        return {"matched": False, "entity_id": None, "name": None, "method": "fuzzy",
                "candidates": cands, "clarify": len(cands) > 1}

    return {"matched": False, "entity_id": None, "name": None, "method": "not_found",
            "candidates": [], "clarify": False}


def link_slots(store: Store, intent: str, slots: dict) -> dict:
    """对槽位中的实体进行链接。返回 {slots, clarifications, errors}。"""
    linked = dict(slots)
    clarifications = []
    errors = []

    def _link_company_slot(key: str):
        if key in linked and isinstance(linked[key], str) and not re.match(r"^\d{6}$", str(linked[key])):
            r = link_company(store, linked[key])
            if r["matched"]:
                linked[key] = r["code"]
                linked[f"_{key}_name"] = r["name"]
                linked[f"_{key}_method"] = r["method"]
            elif r.get("clarify"):
                clarifications.append({"slot": key, "input": linked[key], "candidates": r["candidates"]})
            else:
                errors.append({"slot": key, "input": linked[key], "message": "未找到该公司"})

    def _link_entity_slot(key: str):
        if key in linked and isinstance(linked[key], str):
            r = link_entity(store, linked[key])
            if r["matched"]:
                linked[key] = {"entity_id": r["entity_id"], "name": r["name"], "type": r["type"]}
                linked[f"_{key}_method"] = r["method"]
            elif r.get("clarify"):
                clarifications.append({"slot": key, "input": linked[key], "candidates": r["candidates"]})
            else:
                errors.append({"slot": key, "input": linked[key], "message": "未找到该实体"})

    if intent in ("Q1", "Q4", "Q5"):
        _link_company_slot("company")
    elif intent == "Q2":
        _link_entity_slot("entity_a")
        _link_entity_slot("entity_b")
    elif intent == "Q3":
        _link_entity_slot("entity")
    elif intent == "Q6":
        _link_company_slot("company_a")
        _link_company_slot("company_b")

    return {"slots": linked, "clarifications": clarifications, "errors": errors}
