"""断言回查 — 反转检测逻辑: 提取疑似实体 → 不在词典/结构化结果即可疑。

T1: 从文本提取所有疑似实体(不依赖是否已知)
T2: 白名单 = 词典已知 + 本次结构化结果 + 通用词表
T3: 不在白名单的疑似实体 → 拦截

仍包含: 评价性/因果/投资倾向表述检查。
"""
from __future__ import annotations
import re, sqlite3, json
from src.normalize.name import normalize_name, org_match_key
from src.store.db import Store
from src.query.entity_extract import extract_all

_matcher_cache = None


def _get_matcher(conn: sqlite3.Connection):
    global _matcher_cache
    if _matcher_cache is None or _matcher_cache[0] is not conn:
        from src.query.dict_match import CompanyMatcher, PersonMatcher
        _matcher_cache = (conn, CompanyMatcher(conn), PersonMatcher(conn))
    return _matcher_cache[1], _matcher_cache[2]


def verify_company(store: Store, code: str) -> bool:
    return bool(store.conn.execute(
        "SELECT 1 FROM company WHERE stock_code=?", (code,)).fetchone())


def verify_relation(store: Store, code_a: str, code_b: str) -> bool:
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


def _build_whitelist(conn: sqlite3.Connection, structured_result: dict = None) -> set:
    """构建白名单: 词典已知实体 + 结构化结果中的实体 + 通用词。"""
    wl = set()
    # 词典已知(公司)
    cm, pm = _get_matcher(conn)
    for name in cm._by_name:
        wl.add(name)
        wl.add(normalize_name(name))
    # 词典已知(人名)
    for name in pm._by_name:
        wl.add(name)
        wl.add(normalize_name(name))
    # 结构化结果中的实体名
    if structured_result:
        _extract_result_entities(structured_result, wl)
    return wl


def _extract_result_entities(result: dict, wl: set):
    """从结构化结果中提取所有实体名/代码加入白名单。"""
    def _add_name(name):
        if name:
            wl.add(normalize_name(name))
            wl.add(name)
    # holders
    for h in result.get("holders", {}).get("a", []) + result.get("holders", {}).get("b", []):
        _add_name(h.get("display_name", ""))
    # controllers
    for c in result.get("controllers", {}).get("a", []) + result.get("controllers", {}).get("b", []):
        _add_name(c.get("display_name", ""))
    # related parties
    for p in result.get("related", {}).get("overlap", []):
        _add_name(p.get("name", ""))
    # directors
    for d in result.get("directors", {}).get("cross", []):
        _add_name(d)
    # parties (Q1 result)
    for p in result.get("parties", []):
        _add_name(p.get("name", ""))
    # holders (Q4 result)
    for h in result.get("roles", {}).get("holders", []):
        _add_name(h.get("display_name", ""))
    # events (Q5 result: list of dicts)
    for e in result.get("events", []):
        if isinstance(e, dict):
            _add_name(e.get("counterparty", ""))
    # events summary (Q8 compare result: a/b dicts)
    for key in ("a", "b"):
        ev = result.get("events", {})
        if isinstance(ev, dict):
            ev_dict = ev.get(key, {})
            if isinstance(ev_dict, dict):
                for et, info in ev_dict.items():
                    if isinstance(info, dict):
                        pass  # no entity names in event summary
    # codes
    for key in ("code_a", "code_b", "code"):
        if key in result:
            wl.add(result[key])
    # basic info
    for key in ("a", "b"):
        co = result.get("basic", {}).get(key, {})
        if co:
            _add_name(co.get("short_name", ""))
            _add_name(co.get("full_name", ""))


# 评价性/因果/投资倾向检查
_EVAL_PATTERNS = [
    re.compile(r"更稳健|更健康|风险更高|风险更大|风险较低|优于|劣于|更优|更差|更好|更安全|值得.*关注|建议.*关注"),
    re.compile(r"看好|看空|推荐|买入|卖出|增持|减持|超配|低配"),
    re.compile(r"因为.*所以|导致|表明|说明|意味着|由此可知|可以看出|这说明"),
]
_VIOLATION_LABELS = ["评价性表述", "投资倾向", "因果推断"]


def check_evaluative(text: str) -> list[dict]:
    violations = []
    for label, pattern in zip(_VIOLATION_LABELS, _EVAL_PATTERNS):
        for m in pattern.findall(text):
            violations.append({"type": label, "text": m[:50]})
    return violations


def _is_known_entity(store: Store, name: str, wl: set) -> bool:
    """检查实体是否已知: 白名单 → company 表 → entity 表(精确+长串LIKE)。"""
    if not name:
        return True
    cn = normalize_name(name)
    if cn in wl or name in wl:
        return True
    # company 表精确
    if store.conn.execute(
        "SELECT 1 FROM company WHERE short_name=? COLLATE NOCASE", (cn,)).fetchone():
        return True
    # entity 表精确
    for k in (org_match_key(name), cn):
        if k and store.conn.execute(
            "SELECT 1 FROM entity WHERE canonical_name=? COLLATE NOCASE", (k,)).fetchone():
            return True
    # 长串 LIKE (>=6字, 避免短串误匹配)
    if len(cn) >= 6:
        if store.conn.execute(
            "SELECT 1 FROM entity WHERE display_name LIKE ? AND is_channel=0 LIMIT 1",
            (f"%{cn}%",)).fetchone():
            return True
    return False


def verify_answer(store: Store, answer: str, structured_result: dict = None) -> dict:
    """T1+T3: 反转检测 — 提取疑似实体 → 不在DB/白名单即拦截。"""
    suspected = extract_all(answer)
    wl = _build_whitelist(store.conn, structured_result)

    violations = []

    # 公司名: 查 DB
    for company in suspected["companies"]:
        if not _is_known_entity(store, company, wl):
            violations.append({"type": "unknown_company", "text": company})

    # 人名: 查 DB
    for person in suspected["persons"]:
        if not _is_known_entity(store, person, wl):
            violations.append({"type": "unknown_person", "text": person})

    # 代码: 验证 company 表
    for code in suspected["codes"]:
        if not verify_company(store, code):
            violations.append({"type": "unknown_code", "text": code})

    # 评价性检查
    eval_violations = check_evaluative(answer)

    return {
        "passed": not violations and not eval_violations,
        "violations": violations,
        "eval_violations": eval_violations,
        "suspected": suspected,
    }
