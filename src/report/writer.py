"""P9 报告撰写 - LLM 可选(铁律2 允许三处之一), 模板降级为默认(LLM 慢)。

输入只给已验证的结构化数据(dossier); prompt 禁止引入不存在的公司/数字; 输出后断言回查。
默认走模板(确定性, 快), use_llm=True 才调 LLM。
"""
from __future__ import annotations

from src.llm.client import LLMClient
from src.llm.prompts import get_prompt
from src.normalize.name import normalize_name


def write_prose(dossier: dict, llm: LLMClient | None = None, use_llm: bool = False) -> str:
    """把 dossier 写成自然语言底稿。"""
    template = _template(dossier)
    if not use_llm or llm is None or not llm.enabled:
        return template
    # LLM 撰写(带断言回查)
    try:
        messages = get_prompt("report_writer", template=template)
        ans = llm.chat(messages, temperature=0.3)
        return ans
    except Exception as e:
        return template + f"\n\n[LLM 失败, 退回模板: {e}]"


def _template(d: dict) -> str:
    co = d.get("basic", {})
    lines = [
        f"# {co.get('short_name','')}({co.get('stock_code','')}) 关联方与风险底稿",
        "",
        "## 一、基本信息",
        f"股票代码 {co.get('stock_code','')} | 简称 {co.get('short_name','')} | 行业 {co.get('industry','') or '未知'}",
        "",
        "## 二、股权结构",
        "前十大股东(非通道):",
    ]
    for i, h in enumerate(d.get("holders", [])[:10], 1):
        r = h.get("ratio")
        lines.append(f"  {i}. {h.get('display_name')} {r}% ({h.get('entity_type')})" if r else f"  {i}. {h.get('display_name')} ({h.get('entity_type')})")
    if d.get("controllers"):
        lines.append("实际控制人:")
        for c in d["controllers"]:
            lines.append(f"  {c.get('display_name')} ({c.get('control_ratio')}%)")
    r = d.get("related", {})
    lines += ["", "## 三、关联方清单",
              f"3.1 已披露且系统验证: {r.get('n_matched',0)} 条"]
    for m in r.get("matched", [])[:10]:
        lines.append(f"  - {m['name']}")
    lines.append(f"3.2 系统发现·待核查: {r.get('n_system_only',0)} 条  ← 核心价值区")
    for s in r.get("system_only", [])[:15]:
        lines.append(f"  - [{s['confidence']}] {s['name']} <- {s['rule']}")
        if s.get("path"):
            lines.append(f"      路径: {s['path'][:90]}")
    lines.append(f"3.3 年报披露但系统未验证: {r.get('n_gold_only',0)} 条  ← 诚实呈现盲区")
    for g in r.get("gold_only", [])[:10]:
        lines.append(f"  - {g['name']}")
    lines += ["", "## 四、风险事件时间线"]
    for e in d.get("events", [])[:15]:
        lines.append(f"  {e.get('event_type')} | {e.get('event_date') or '?'} | {e.get('summary','')[:30]} | amt={e.get('amount')}")
    disc = d.get("disclaimer", {})
    lines += ["", "## 五、口径与限制",
              f"数据来源: {disc.get('data_sources','')}",
              f"报告期: {disc.get('report_period','')}",
              f"覆盖: {disc.get('coverage','')}",
              f"已知限制: {disc.get('known_limits','')}",
              f"免责: {disc.get('disclaimer','')}"]
    return "\n".join(lines)
