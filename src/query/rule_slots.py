"""T3: 规则槽位抽取 — 为 Q1-Q6 写模式匹配, 避免调 LLM。

规则抽取成功则不调 LLM, 失败才走 LLM 兜底。
"""
from __future__ import annotations
import re

# 6位股票代码
_CODE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
# 公司名: 中文+可能的有限公司/集团等后缀, 或已知简称
_COMPANY_NAME = re.compile(r"([\u4e00-\u9fa5]{2,8}(?:股份有限公司|有限公司|集团|控股|投资|银行|保险|医药|时代|绿能|精密))")
# 人名: 2-4字中文, 不含公司后缀
_PERSON_NAME = re.compile(r"([\u4e00-\u9fa5]{2,4})(?=控制|持有|担任|任职|在哪些)")
# 事件类型关键词
_EVENT_MAP = {"担保": "guarantee", "诉讼": "lawsuit", "质押": "pledge", "法律纠纷": "lawsuit"}
# 角色类型关键词
_ROLE_MAP = {
    "前十大股东": "holder", "十大股东": "holder", "股东": "holder",
    "实际控制人": "controller", "实控人": "controller",
    "董监高": "all", "高管": "all", "董事": "director", "监事": "director", "总经理": "director",
}
# 规则ID
_RULE_IDS = re.compile(r"R([1-7])")


def extract_q1(question: str, context_code: str = "") -> dict | None:
    """Q1: 查公司关联方。槽位: company"""
    code = _CODE.search(question)
    if code:
        return {"company": code.group(1)}
    name = _COMPANY_NAME.search(question)
    if name:
        return {"company": name.group(1)}
    if context_code:
        return {"company": context_code}
    return None


def extract_q2(question: str, context_code: str = "") -> dict | None:
    """Q2: 两实体关系。槽位: entity_a, entity_b"""
    codes = _CODE.findall(question)
    if len(codes) >= 2:
        return {"entity_a": codes[0], "entity_b": codes[1]}
    # 两个中文实体名
    m = re.search(r"([\u4e00-\u9fa5A-Za-z]{2,15})\s*(?:和|与|跟|及)\s*([\u4e00-\u9fa5A-Za-z]{2,15})", question)
    if m:
        slots = {"entity_a": m.group(1), "entity_b": m.group(2)}
        return slots
    if context_code:
        name = _COMPANY_NAME.search(question)
        if name:
            return {"entity_a": name.group(1), "entity_b": context_code}
    return None


def extract_q3(question: str, context_code: str = "") -> dict | None:
    """Q3: 反向查询。槽位: entity, relation_type?"""
    m = _PERSON_NAME.search(question)
    if m:
        entity = m.group(1)
    else:
        m2 = _COMPANY_NAME.search(question)
        if m2:
            entity = m2.group(1)
        else:
            return None
    slots = {"entity": entity}
    if "控制" in question:
        slots["relation_type"] = "control"
    elif "持股" in question or "持有" in question:
        slots["relation_type"] = "hold"
    elif "任职" in question or "担任" in question:
        slots["relation_type"] = "serve"
    return slots


def extract_q4(question: str, context_code: str = "") -> dict | None:
    """Q4: 公司角色。槽位: company, role_type"""
    code = _CODE.search(question)
    company = code.group(1) if code else None
    if not company:
        name = _COMPANY_NAME.search(question)
        company = name.group(1) if name else None
    if not company and context_code:
        company = context_code
    if not company:
        return None
    role = "all"
    for kw, rt in sorted(_ROLE_MAP.items(), key=lambda x: -len(x[0])):
        if kw in question:
            role = rt
            break
    return {"company": company, "role_type": role}


def extract_q5(question: str, context_code: str = "") -> dict | None:
    """Q5: 风险事件。槽位: company, event_types?"""
    code = _CODE.search(question)
    company = code.group(1) if code else None
    if not company:
        name = _COMPANY_NAME.search(question)
        company = name.group(1) if name else None
    if not company and context_code:
        company = context_code
    if not company:
        return None
    slots = {"company": company}
    event_types = []
    for kw, et in _EVENT_MAP.items():
        if kw in question:
            event_types.append(et)
    if event_types:
        slots["event_types"] = list(set(event_types))
    return slots


def extract_q6(question: str, context_code: str = "") -> dict | None:
    """Q6: 关联方重合。槽位: company_a, company_b"""
    codes = _CODE.findall(question)
    if len(codes) >= 2:
        return {"company_a": codes[0], "company_b": codes[1]}
    names = _COMPANY_NAME.findall(question)
    if len(names) >= 2:
        return {"company_a": names[0], "company_b": names[1]}
    if len(codes) == 1 and len(names) >= 1:
        return {"company_a": codes[0], "company_b": names[0]}
    if context_code and len(names) >= 1:
        return {"company_a": context_code, "company_b": names[0]}
    return None


_EXTRACTORS = {
    "Q1": extract_q1,
    "Q2": extract_q2,
    "Q3": extract_q3,
    "Q4": extract_q4,
    "Q5": extract_q5,
    "Q6": extract_q6,
}


def rule_extract(intent: str, question: str, context_code: str = "") -> dict | None:
    """规则槽位抽取。成功返回 slots, 失败返回 None(走 LLM 兜底)。"""
    fn = _EXTRACTORS.get(intent)
    if not fn:
        return None
    return fn(question, context_code)
