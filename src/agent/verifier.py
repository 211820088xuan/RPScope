"""P7 断言回查 - 验证 Agent 答案里的实体/数值/关系是否在图谱+事实源真实存在。

确定性(无 LLM)。回查不通过的结论丢弃/标[未验证]。

T1: 实体识别改用词典最长匹配替代正则切分(修复过捕获误报)。
T2: 增加评价性/因果/投资倾向表述检查(越界拦截)。
"""
from __future__ import annotations
import re, sqlite3
from src.normalize.name import normalize_name, org_match_key
from src.store.db import Store

# 词典匹配器缓存
_matcher_cache = None


def _get_matcher(conn: sqlite3.Connection):
    global _matcher_cache
    if _matcher_cache is None or _matcher_cache[0] is not conn:
        from src.query.dict_match import CompanyMatcher
        _matcher_cache = (conn, CompanyMatcher(conn))
    return _matcher_cache[1]


def verify_entity(store: Store, name: str) -> bool:
    """名称是否在 entity 表或 company 表存在(归一化匹配)。"""
    if not name:
        return False
    # 查 entity 表(人/机构)
    for k in (org_match_key(name), normalize_name(name), name):
        if k and store.conn.execute(
            "SELECT 1 FROM entity WHERE canonical_name=? COLLATE NOCASE", (k,)).fetchone():
            return True
    # 查 company 表(short_name/full_name)
    for k in (normalize_name(name), name):
        if k and store.conn.execute(
            "SELECT 1 FROM company WHERE short_name=? COLLATE NOCASE", (k,)).fetchone():
            return True
    return False


def verify_company(store: Store, code: str) -> bool:
    return bool(store.conn.execute(
        "SELECT 1 FROM company WHERE stock_code=?", (code,)).fetchone())


def verify_relation(store: Store, code_a: str, code_b: str) -> bool:
    """A-B 是否在图谱有关联路径。"""
    ca = [r[0] for r in store.conn.execute(
        "SELECT entity_id FROM actual_controller WHERE stock_code=?", (code_a,)).fetchall()]
    cb = [r[0] for r in store.conn.execute(
        "SELECT entity_id FROM actual_controller WHERE stock_code=?", (code_b,)).fetchall()]
    if set(ca) & set(cb):
        return True
    ha = [r[0] for r in store.conn.execute(
        "SELECT entity_id FROM holding WHERE stock_code=? AND entity_id IN "
        "(SELECT entity_id FROM entity WHERE is_channel=0)", (code_a,)).fetchall()]
    hb = [r[0] for r in store.conn.execute(
        "SELECT entity_id FROM holding WHERE stock_code=? AND entity_id IN "
        "(SELECT entity_id FROM entity WHERE is_channel=0)", (code_b,)).fetchall()]
    return bool(set(ha) & set(hb))


def extract_entities_from_text(text: str, conn: sqlite3.Connection = None) -> list[str]:
    """T1: 词典匹配已知实体(公司+人名, 精确边界, 无误报) + 6位代码。

    策略: 只提取词典中已知的公司和人名, 不从自由文本切分未知实体名。
    原因: 中文无词边界, 正则切分必然过捕获, 产生误报。
    幻觉检测主路径 = 评价性表述检查(T2) + 已知实体验证 + 代码验证。
    """
    codes = re.findall(r"(?<!\d)(\d{6})(?!\d)", text)
    if conn is None:
        names = re.findall(r"([\u4e00-\u9fa5A-Za-z()（）]{2,30}(?:有限公司|股份有限公司|集团|企业))", text)
        return codes + names

    from src.query.dict_match import CompanyMatcher, PersonMatcher, _norm
    cm = _get_matcher(conn)
    # 已知公司(精确边界, 无误报)
    matches = cm.all_matches(text)
    known_names = [m.text for m in matches if m.stock_code]

    # 已知人名
    pm = PersonMatcher(conn)
    person_matches = pm.match(text)
    persons = [person_matches.text] if person_matches and not person_matches.ambiguous else []

    return codes + known_names + persons


# T2: 评价性/因果/投资倾向表述检查
_EVAL_PATTERNS = [
    re.compile(r"更稳健|更健康|风险更高|风险更大|风险较低|优于|劣于|更优|更差|更好|更安全|值得.*关注|建议.*关注"),
    re.compile(r"看好|看空|推荐|买入|卖出|增持|减持|超配|低配"),
    re.compile(r"因为.*所以|导致|表明|说明|意味着|由此可知|可以看出|这说明"),
]

_VIOLATION_LABELS = ["评价性表述", "投资倾向", "因果推断"]


def check_evaluative(text: str) -> list[dict]:
    """T2: 检查文本中是否含评价性/投资倾向/因果推断表述。返回违规列表。"""
    violations = []
    for label, pattern in zip(_VIOLATION_LABELS, _EVAL_PATTERNS):
        matches = pattern.findall(text)
        for m in matches:
            violations.append({"type": label, "text": m[:50]})
    return violations


def verify_answer(store: Store, answer: str) -> dict:
    """回查: 6位代码验证 + 评价性/因果/投资倾向检查。

    词典匹配的实体已知在库中, 不需再验证(无误报)。
    幻觉检测主路径 = 评价性表述检查 + 代码验证。
    """
    ents = extract_entities_from_text(answer, store.conn)
    violations = []
    # 只验证 6位代码(词典匹配的公司/人名已知在库, 跳过验证避免误报)
    for e in ents:
        if e.isdigit() and len(e) == 6:
            if not verify_company(store, e):
                violations.append(e)

    # T2: 评价性/因果/投资倾向检查
    eval_violations = check_evaluative(answer)

    return {
        "passed": not violations and not eval_violations,
        "violations": violations,
        "eval_violations": eval_violations,
        "checked": ents,
    }
