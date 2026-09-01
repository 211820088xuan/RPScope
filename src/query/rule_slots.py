"""T1+T2: 规则槽位抽取 — 词典匹配优先, 正则兜底。

优先级: 股票代码精确 > 词典最长匹配 > 正则 > LLM 兜底
歧义(多匹配) → 走澄清机制, 不自选。
"""
from __future__ import annotations
import re, sqlite3
from src.query.dict_match import CompanyMatcher, PersonMatcher, Match

_CODE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_EVENT_MAP = {"担保": "guarantee", "诉讼": "lawsuit", "质押": "pledge", "法律纠纷": "lawsuit"}
_ROLE_MAP = {
    "前十大股东": "holder", "十大股东": "holder", "股东": "holder",
    "实际控制人": "controller", "实控人": "controller",
    "董监高": "all", "高管": "all", "董事": "director", "监事": "director", "总经理": "director",
}

_matcher_cache: dict = {}


def _get_company_matcher(conn: sqlite3.Connection) -> CompanyMatcher:
    key = id(conn)
    if key not in _matcher_cache:
        _matcher_cache[key] = CompanyMatcher(conn)
    return _matcher_cache[key]


def _get_person_matcher(conn: sqlite3.Connection) -> PersonMatcher:
    key = "p" + str(id(conn))
    if key not in _matcher_cache:
        _matcher_cache[key] = PersonMatcher(conn)
    return _matcher_cache[key]


def _find_company(conn, text: str, context_code: str = "") -> dict | None:
    """用词典匹配找公司, 返回 {code, name, method, ambiguous, candidates} 或 None。"""
    cm = _get_company_matcher(conn)
    m = cm.match(text)
    if m:
        return {"code": m.stock_code, "name": m.text, "method": m.method,
                "ambiguous": m.ambiguous, "candidates": m.candidates}
    # 兜底: context_code
    if context_code:
        return {"code": context_code, "name": "", "method": "context_fallback",
                "ambiguous": False, "candidates": []}
    return None


def _find_all_companies(conn, text: str, context_code: str = "") -> list[dict]:
    """找 text 中所有公司, 用于 Q2/Q6。"""
    cm = _get_company_matcher(conn)
    matches = cm.all_matches(text)
    results = []
    for m in matches:
        results.append({"code": m.stock_code, "name": m.text, "method": m.method,
                        "ambiguous": m.ambiguous, "candidates": m.candidates})
    # 不足 2 个时用 context_code 补
    if len(results) < 2 and context_code:
        results.append({"code": context_code, "name": "", "method": "context_fallback",
                        "ambiguous": False, "candidates": []})
    return results


def _find_person(conn, text: str) -> dict | None:
    """用词典匹配找人名。"""
    pm = _get_person_matcher(conn)
    m = pm.match(text)
    if m:
        return {"entity_id": m.entity_id, "name": m.text, "method": m.method,
                "ambiguous": m.ambiguous, "candidates": m.candidates}
    return None


def _find_entity(conn, text: str) -> dict | None:
    """找人/机构: 先查人名词典, 再查公司词典。"""
    p = _find_person(conn, text)
    if p:
        return p
    c = _find_company(conn, text)
    if c:
        return {**c, "entity_id": 0}
    return None


def extract_q1(conn, question: str, context_code: str = "") -> dict | None:
    """Q1: 查公司关联方。槽位: company"""
    c = _find_company(conn, question, context_code)
    if c:
        slots = {"company": c["code"]}
        if c.get("ambiguous"):
            slots["_clarify"] = {"slot": "company", "input": c.get("name", c["code"]),
                                 "candidates": c["candidates"]}
        return slots
    return None


def extract_q2(conn, question: str, context_code: str = "") -> dict | None:
    """Q2: 两实体关系。槽位: entity_a, entity_b"""
    # 先找双公司
    companies = _find_all_companies(conn, question, context_code)
    if len(companies) >= 2:
        slots = {"entity_a": companies[0]["code"], "entity_b": companies[1]["code"]}
        clarifs = []
        for i, c in enumerate(companies[:2]):
            if c.get("ambiguous"):
                clarifs.append({"slot": "entity_" + chr(97+i), "input": c.get("name", ""),
                                "candidates": c["candidates"]})
        if clarifs:
            slots["_clarify"] = clarifs
        return slots
    # 找人+公司 或 人+人
    persons = []
    pm = _get_person_matcher(conn)
    # 逐字符偏移找两个人名
    text_norm = question
    for name in pm._sorted_names:
        if name in text_norm:
            persons.append(name)
            text_norm = text_norm.replace(name, " " * len(name), 1)  # 避免重复匹配
            if len(persons) >= 2:
                break
    if len(persons) >= 2:
        return {"entity_a": persons[0], "entity_b": persons[1]}
    if len(persons) == 1 and len(companies) >= 1:
        return {"entity_a": persons[0], "entity_b": companies[0]["code"]}
    if len(persons) == 1 and context_code:
        return {"entity_a": persons[0], "entity_b": context_code}
    if len(companies) == 1 and context_code and companies[0]["code"] != context_code:
        return {"entity_a": companies[0]["code"], "entity_b": context_code}
    return None


def extract_q3(conn, question: str, context_code: str = "") -> dict | None:
    """Q3: 反向查询。槽位: entity, relation_type?"""
    e = _find_entity(conn, question)
    if not e:
        return None
    slots = {"entity": e.get("entity_id") or e.get("name")}
    if e.get("ambiguous"):
        slots["_clarify"] = {"slot": "entity", "input": e.get("name", ""),
                             "candidates": e["candidates"]}
    if "控制" in question:
        slots["relation_type"] = "control"
    elif "持股" in question or "持有" in question:
        slots["relation_type"] = "hold"
    elif "任职" in question or "担任" in question:
        slots["relation_type"] = "serve"
    return slots


def extract_q4(conn, question: str, context_code: str = "") -> dict | None:
    """Q4: 公司角色。槽位: company, role_type"""
    c = _find_company(conn, question, context_code)
    if not c:
        return None
    slots = {"company": c["code"]}
    if c.get("ambiguous"):
        slots["_clarify"] = {"slot": "company", "input": c.get("name", ""),
                             "candidates": c["candidates"]}
    role = "all"
    for kw, rt in sorted(_ROLE_MAP.items(), key=lambda x: -len(x[0])):
        if kw in question:
            role = rt
            break
    slots["role_type"] = role
    return slots


def extract_q5(conn, question: str, context_code: str = "") -> dict | None:
    """Q5: 风险事件。槽位: company, event_types?"""
    c = _find_company(conn, question, context_code)
    if not c:
        return None
    slots = {"company": c["code"]}
    if c.get("ambiguous"):
        slots["_clarify"] = {"slot": "company", "input": c.get("name", ""),
                             "candidates": c["candidates"]}
    event_types = []
    for kw, et in _EVENT_MAP.items():
        if kw in question:
            event_types.append(et)
    if event_types:
        slots["event_types"] = list(set(event_types))
    return slots


def extract_q6(conn, question: str, context_code: str = "") -> dict | None:
    """Q6: 关联方重合。槽位: company_a, company_b"""
    companies = _find_all_companies(conn, question, context_code)
    if len(companies) >= 2:
        slots = {"company_a": companies[0]["code"], "company_b": companies[1]["code"]}
        clarifs = []
        for i, c in enumerate(companies[:2]):
            if c.get("ambiguous"):
                clarifs.append({"slot": "company_" + chr(97+i), "input": c.get("name", ""),
                                "candidates": c["candidates"]})
        if clarifs:
            slots["_clarify"] = clarifs
        return slots
    return None


def extract_q8(conn, question: str, context_code: str = "") -> dict | None:
    """Q8: 对比分析。槽位: company_a, company_b"""
    companies = _find_all_companies(conn, question, context_code)
    if len(companies) >= 2:
        slots = {"company_a": companies[0]["code"], "company_b": companies[1]["code"]}
        clarifs = []
        for i, c in enumerate(companies[:2]):
            if c.get("ambiguous"):
                clarifs.append({"slot": "company_" + chr(97+i), "input": c.get("name", ""),
                                "candidates": c["candidates"]})
        if clarifs:
            slots["_clarify"] = clarifs
        return slots
    return None


_EXTRACTORS = {
    "Q1": extract_q1,
    "Q2": extract_q2,
    "Q3": extract_q3,
    "Q4": extract_q4,
    "Q5": extract_q5,
    "Q6": extract_q6,
    "Q8": extract_q8,
}


def rule_extract(intent: str, question: str, conn: sqlite3.Connection, context_code: str = "") -> dict | None:
    """规则槽位抽取(词典匹配)。成功返回 slots, 失败返回 None(走 LLM 兜底)。
    注意: conn 参数是 sqlite3.Connection, 不是 Store 对象。"""
    fn = _EXTRACTORS.get(intent)
    if not fn:
        return None
    return fn(conn, question, context_code)
