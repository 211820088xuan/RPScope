"""断言回查 — 先减法再判断 + 数值/日期验证 + 评价性检查。

T1: 词典先减(已知实体移除) → 剩余从右向左取最短 → 归一化白名单比对
T3: 数值/日期/计数验证(与结构化结果比对)
T2(评价性): 更稳健/更差/看好/买入/因为所以 等越界表述
"""
from __future__ import annotations
import re, sqlite3, json
from src.normalize.name import normalize_name, org_match_key
from src.store.db import Store
from src.query.entity_extract import extract_suspected, extract_values_from_result

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
    """构建归一化白名单: 词典已知 + 结构化结果实体 + 通用词。"""
    wl = set()
    cm, pm = _get_matcher(conn)
    for name in cm._by_name:
        wl.add(name)
    for name in pm._by_name:
        wl.add(name)
    if structured_result:
        _extract_result_entities(structured_result, wl)
    return wl


def _extract_result_entities(result: dict, wl: set):
    def _add(name):
        if name:
            n = normalize_name(name)
            wl.add(n)
            wl.add(name)
    for key in ("a", "b"):
        for h in result.get("holders", {}).get(key, []):
            _add(h.get("display_name", ""))
        for c in result.get("controllers", {}).get(key, []):
            _add(c.get("display_name", ""))
    for p in result.get("related", {}).get("overlap", []):
        _add(p.get("name", ""))
    for d in result.get("directors", {}).get("cross", []):
        _add(d)
    for p in result.get("parties", []):
        _add(p.get("name", ""))
    for h in result.get("roles", {}).get("holders", []):
        _add(h.get("display_name", ""))
    for h in result.get("holders", []):
        if isinstance(h, dict):
            _add(h.get("display_name", ""))
    for e in result.get("events", []):
        if isinstance(e, dict):
            _add(e.get("counterparty", ""))
    for key in ("code_a", "code_b", "code"):
        if key in result:
            wl.add(result[key])
    for key in ("a", "b"):
        co = result.get("basic", {}).get(key, {})
        if co and isinstance(co, dict):
            _add(co.get("short_name", ""))
            _add(co.get("full_name", ""))


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


def _verify_values(answer_values: dict, result_values: dict) -> list[dict]:
    """T3: 数值/日期验证。摘要中的值须在结构化结果中存在(含容差)。"""
    violations = []

    # 百分比: 容差 0.1
    result_pcts = result_values.get("percentages", [])
    for val, _ in answer_values.get("percentages", []):
        if not any(abs(val - rv) < 0.1 for rv in result_pcts):
            violations.append({"type": "unknown_pct", "text": f"{val}%"})

    # 金额: 比数字部分(浮点, 容差0.01)
    result_amt_nums = []
    for v, u in result_values.get("amounts", []):
        try:
            result_amt_nums.append(float(v))
        except ValueError:
            pass
    for val, unit in answer_values.get("amounts", []):
        try:
            fv = float(val)
        except ValueError:
            violations.append({"type": "unknown_amount", "text": f"{val}{unit}"})
            continue
        if not any(abs(fv - rv) < 0.01 for rv in result_amt_nums):
            violations.append({"type": "unknown_amount", "text": f"{val}{unit}"})

    # 日期: 须在结构化结果中存在
    result_dates = set(result_values.get("dates", []))
    for date in answer_values.get("dates", []):
        if date not in result_dates:
            violations.append({"type": "unknown_date", "text": date})

    # 计数: 须在结构化结果中存在
    result_counts = set(result_values.get("counts", []))
    for val, _ in answer_values.get("counts", []):
        if val not in result_counts:
            violations.append({"type": "unknown_count", "text": str(val)})

    return violations


def verify_answer(store: Store, answer: str, structured_result: dict = None) -> dict:
    """回查: 先减法实体提取 + 数值验证 + 评价性检查。"""
    cm, pm = _get_matcher(store.conn)

    # Step 1: 词典最长匹配(已知实体)
    company_matches = cm.all_matches(answer)
    known_companies = [m.text for m in company_matches if m.stock_code]
    person_match = pm.match(answer)
    known_persons = [person_match.text] if person_match and not person_match.ambiguous else []

    # Step 2: 剩余文本提取疑似实体, 但不物理移除已知实体(替换不可靠)
    # 改为: 提取所有疑似实体 → 双向子串比对已知实体(疑似含已知 或 已知含疑似 → 跳过)
    suspected = extract_suspected(answer, store.conn)  # 不传 known_matches, 提取全部

    # Step 3: 白名单比对(归一化键 + 双向子串)
    wl = _build_whitelist(store.conn, structured_result)
    # 已知公司的归一化名集合
    known_norm = set()
    for m in company_matches:
        if m.stock_code:
            known_norm.add(normalize_name(m.text))
            # 也加入 company 表的 short_name 归一化
            co = store.conn.execute("SELECT short_name FROM company WHERE stock_code=?", (m.stock_code,)).fetchone()
            if co:
                known_norm.add(normalize_name(co["short_name"]))
                known_norm.add(normalize_name(m.text))

    violations = []
    for company in suspected["companies"]:
        cn = normalize_name(company)
        # 精确匹配白名单
        if cn in wl or company in wl:
            continue
        # 双向子串: 疑似含已知 或 已知含疑似 → 已知实体, 跳过
        if any(k in cn or cn in k for k in known_norm if k and len(k) >= 3):
            continue
        # 双向子串: 与白名单
        if any(k in cn or cn in k for k in wl if k and len(k) >= 3):
            continue
        # 查 DB
        found = False
        for k in (org_match_key(company), cn):
            if k and store.conn.execute(
                "SELECT 1 FROM entity WHERE canonical_name=? COLLATE NOCASE", (k,)).fetchone():
                found = True
                break
        if not found and len(cn) >= 6:
            if store.conn.execute(
                "SELECT 1 FROM entity WHERE display_name LIKE ? AND is_channel=0 LIMIT 1",
                (f"%{cn}%",)).fetchone():
                found = True
        if not found:
            violations.append({"type": "unknown_company", "text": company})

    # 人名: 只查已知 person 之外的(保守策略)
    for person in suspected.get("persons", []):
        violations.append({"type": "unknown_person", "text": person})

    # 代码
    for code in re.findall(r"(?<!\d)(\d{6})(?!\d)", answer):
        if not verify_company(store, code):
            violations.append({"type": "unknown_code", "text": code})

    # T3: 数值/日期验证
    if structured_result:
        answer_values = suspected.get("values", {})
        result_values = extract_values_from_result(structured_result)
        value_violations = _verify_values(answer_values, result_values)
        violations.extend(value_violations)

    # 评价性检查
    eval_violations = check_evaluative(answer)

    return {
        "passed": not violations and not eval_violations,
        "violations": violations,
        "eval_violations": eval_violations,
        "suspected": suspected,
    }
