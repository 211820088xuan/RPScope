"""P7 断言回查 - 验证 Agent 答案里的实体/数值/关系是否在图谱+事实源真实存在。

确定性(无 LLM)。回查不通过的结论丢弃/标[未验证]。
这是项目核心防幻觉设计(铁律2 的延伸: LLM 碰不到判定, 回查碰得到)。
"""
from __future__ import annotations

import re

from src.normalize.name import normalize_name, org_match_key
from src.store.db import Store


def verify_entity(store: Store, name: str) -> bool:
    """名称是否在 entity 表存在(归一化匹配)。"""
    if not name:
        return False
    for k in (org_match_key(name), normalize_name(name), name):
        if k and store.conn.execute(
            "SELECT 1 FROM entity WHERE canonical_name=? COLLATE NOCASE", (k,)).fetchone():
            return True
    return False


def verify_company(store: Store, code: str) -> bool:
    return bool(store.conn.execute(
        "SELECT 1 FROM company WHERE stock_code=?", (code,)).fetchone())


def verify_relation(store: Store, code_a: str, code_b: str) -> bool:
    """A-B 是否在图谱有关联路径(通过规则引擎验证, 复用 P3)。
    这里简化: 查 actual_controller 共同(兄弟) 或 共同股东, 真实复用应由 graph.py 调 engine。"""
    # 共同实控人
    ca = [r[0] for r in store.conn.execute(
        "SELECT entity_id FROM actual_controller WHERE stock_code=?", (code_a,)).fetchall()]
    cb = [r[0] for r in store.conn.execute(
        "SELECT entity_id FROM actual_controller WHERE stock_code=?", (code_b,)).fetchall()]
    if set(ca) & set(cb):
        return True
    # 共同非通道股东
    ha = [r[0] for r in store.conn.execute(
        "SELECT entity_id FROM holding WHERE stock_code=? AND entity_id IN "
        "(SELECT entity_id FROM entity WHERE is_channel=0)", (code_a,)).fetchall()]
    hb = [r[0] for r in store.conn.execute(
        "SELECT entity_id FROM holding WHERE stock_code=? AND entity_id IN "
        "(SELECT entity_id FROM entity WHERE is_channel=0)", (code_b,)).fetchall()]
    return bool(set(ha) & set(hb))


def extract_entities_from_text(text: str) -> list[str]:
    """从答案文本里抽公司名(含公司后缀) + 6位代码。"""
    codes = re.findall(r"\b\d{6}\b", text)
    names = re.findall(r"([\u4e00-\u9fa5A-Za-z()（）]{2,30}(?:有限公司|股份有限公司|集团|企业))", text)
    return codes + names


def verify_answer(store: Store, answer: str) -> dict:
    """回查答案里提到的公司代码/名称是否真实存在。"""
    ents = extract_entities_from_text(answer)
    violations = []
    for e in ents:
        if e.isdigit() and len(e) == 6:
            if not verify_company(store, e):
                violations.append(e)
        else:
            if not verify_entity(store, e):
                violations.append(e)
    return {"passed": not violations, "violations": violations, "checked": ents}
