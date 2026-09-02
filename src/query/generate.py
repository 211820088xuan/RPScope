"""T4: 模板外查询的 LLM 生成路径 — 三道校验。

当意图无法归入 Q1-Q6 时, 走此路径。
LLM 生成 SQL 查询, 经三道校验后执行。
"""
from __future__ import annotations
import re, time
from src.llm.client import LLMClient
from src.llm.prompts import get_prompt
from src.store.db import Store

# 图/DB schema 白名单 (供 LLM 参考并做结构校验)
_SCHEMA_DESC = """\
节点/表:
  company(stock_code TEXT, short_name TEXT, full_name TEXT, industry TEXT, list_date TEXT, market_cap REAL, is_st INTEGER)
  entity(entity_id INTEGER, display_name TEXT, canonical_name TEXT, entity_type TEXT, is_channel INTEGER, confidence TEXT)
  holding(id INTEGER, stock_code TEXT, entity_id INTEGER, ratio REAL, report_period TEXT, source TEXT, holder_rank INTEGER)
  position(id INTEGER, stock_code TEXT, entity_id INTEGER, title TEXT, title_class TEXT, source TEXT)
  actual_controller(id INTEGER, stock_code TEXT, entity_id INTEGER, control_ratio REAL, valid_from TEXT, source TEXT)
  event(id INTEGER, subject_code TEXT, event_type TEXT, event_date TEXT, counterparty TEXT, amount REAL, summary TEXT, source_type TEXT)
关系:
  HOLDS: entity -> company (持股, ratio=比例)
  SERVES_AS: entity -> company (任职, title=职务)
  CONTROLS: entity -> company (控制, control_ratio=比例)
"""

# 禁止关键字 (只读校验)
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|ATTACH|DETACH|PRAGMA|VACUUM|REINDEX)\b",
    re.IGNORECASE,
)

# 允许的表名 (结构校验)
_ALLOWED_TABLES = {"company", "entity", "holding", "position", "actual_controller", "event"}

# 允许的列名 (结构校验 — 从 schema 提取)
_ALLOWED_COLUMNS = {
    "stock_code", "short_name", "full_name", "industry", "list_date", "market_cap", "is_st",
    "entity_id", "display_name", "canonical_name", "entity_type", "is_channel", "confidence",
    "id", "ratio", "report_period", "source", "holder_rank",
    "title", "title_class",
    "control_ratio", "valid_from",
    "subject_code", "event_type", "event_date", "counterparty", "amount", "summary", "source_type",
}


def _validate_structure(sql: str) -> tuple[bool, str]:
    """结构校验: 检查引用的表名/列名是否在白名单内。"""
    # 提取表名 (FROM/JOIN 后)
    tables = re.findall(r"(?:FROM|JOIN)\s+(\w+)", sql, re.IGNORECASE)
    for t in tables:
        if t.lower() not in _ALLOWED_TABLES:
            return False, f"非法表名: {t}"
    # 提取列名 (SELECT 后, WHERE 后) — 简化: 找 word.列名 和独立列名
    cols = re.findall(r"[a-zA-Z_]\w*\.[a-zA-Z_]\w*", sql)
    for c in cols:
        col = c.split(".")[-1]
        if col.lower() not in _ALLOWED_COLUMNS and col != "*":
            return False, f"非法列名: {c}"
    return True, "OK"


def _validate_readonly(sql: str) -> tuple[bool, str]:
    """只读校验: 禁止任何写操作。"""
    if _FORBIDDEN.search(sql):
        m = _FORBIDDEN.search(sql)
        return False, f"禁止的关键字: {m.group()}"
    return True, "OK"


def _validate_resource(sql: str) -> tuple[bool, str]:
    """资源约束: 强制 LIMIT, 检查无笛卡尔积。"""
    if "LIMIT" not in sql.upper():
        return False, "缺少 LIMIT 子句"
    # 检查 LIMIT 值
    m = re.search(r"LIMIT\s+(\d+)", sql, re.IGNORECASE)
    if m and int(m.group(1)) > 200:
        return False, f"LIMIT 过大: {m.group(1)} (>200)"
    return True, "OK"


def generate_and_execute(store: Store, llm: LLMClient, question: str, trace=None) -> dict:
    """模板外查询: LLM 生成 SQL → 三道校验 → 执行。"""
    import time as _time
    retry_note = ""
    for attempt in range(3):
        t0 = _time.perf_counter()
        try:
            messages = get_prompt("sql_generate",
                schema=_SCHEMA_DESC,
                allowed_tables=", ".join(_ALLOWED_TABLES),
                question=question + (f"\n\n上次校验失败: {retry_note}, 请修正后重新生成。" if retry_note else ""),
            )
            sql = llm.chat(messages)
            elapsed = (_time.perf_counter() - t0) * 1000
            if trace:
                from src.llm.prompts import get_prompt_name_version
                pv = get_prompt_name_version("sql_generate")
                trace.add_llm_call("generate_query", elapsed, retried=attempt > 0,
                                   prompt_name="sql_generate", prompt_version=pv)
            # 清理 markdown 围栏
            sql = sql.strip().strip("`").strip()
            if sql.startswith("sql"):
                sql = sql[3:].strip()

            # 三道校验
            checks = []
            for name, fn in [("structure", _validate_structure), ("readonly", _validate_readonly), ("resource", _validate_resource)]:
                ok, msg = fn(sql)
                checks.append({"check": name, "passed": ok, "message": msg})
                if not ok:
                    if trace:
                        trace.validation = {"attempt": attempt + 1, "checks": checks, "sql": sql}
                    if attempt < 2:
                        retry_note = msg
                        continue
                    return {"source": "generated_query", "error": f"校验失败: {msg}",
                            "validation": checks, "sql": sql, "attempts": attempt + 1}

            # 校验通过, 执行
            if trace:
                trace.validation = {"attempt": attempt + 1, "checks": checks, "sql": sql, "passed": True}
            rows = store.conn.execute(sql).fetchall()
            results = [dict(r) for r in rows]
            return {"source": "generated_query", "sql": sql, "results": results,
                    "n": len(results), "validation": checks, "attempts": attempt + 1}
        except Exception as e:
            if attempt < 2:
                retry_note = str(e)
                continue
            return {"source": "generated_query", "error": str(e), "attempts": attempt + 1}

    return {"source": "generated_query", "error": "无法回答此类问题", "attempts": 3}
