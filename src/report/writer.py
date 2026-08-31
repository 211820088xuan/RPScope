"""P9 报告撰写 - LLM 可选(铁律2 允许三处之一), 模板降级为默认(LLM 慢)。

输入只给已验证的结构化数据(dossier); prompt 禁止引入不存在的公司/数字; 输出后断言回查。
默认走模板(确定性, 快), use_llm=True 才调 LLM。
"""
from __future__ import annotations

from src.llm.client import LLMClient
from src.normalize.name import normalize_name


def write_prose(dossier: dict, llm: LLMClient | None = None, use_llm: bool = False) -> str:
    """把 dossier 写成自然语言底稿。"""
    template = _template(dossier)
    if not use_llm or llm is None or not llm.enabled:
        return template
    # LLM 撰写(带断言回查)
    try:
        ans = llm.chat([
            {"role": "system", "content": "你是关联方底稿撰写员。基于给定的结构化数据写一份全面的关联方与风险底稿。内容包括：公司概况、股权结构分析（控制权分布、实控人背景）、关联方清单分析（已验证/系统发现待核查/年报未验证各自的含义和数量）、风险事件分析（担保/诉讼/质押的风险提示）、口径与限制说明。只基于给定的结构化数据, 不引入数据里没有的具体公司名/数字/日期。"},
            {"role": "user", "content": f"基于以下结构化数据写一份关联方与风险底稿(中文, markdown格式):\n{template}"},
        ], temperature=0.3)
        # 断言回查: 答案里的公司名(含后缀)须在 template 出现
        import re
        _GENERIC = {"联营企业","关联企业","子公司","分公司","母公司","合资企业","合伙企业","相关企业","其他企业","所属企业"}
        names = re.findall(r"[\u4e00-\u9fa5A-Za-z()（）]{2,30}(?:有限公司|股份有限公司|集团|企业)", ans)
        violations = [n for n in set(names) if n not in _GENERIC and normalize_name(n) not in normalize_name(template)]
        if violations:
            return template + f"\n\n[撰写回查: LLM 引入了未给定实体 {violations}, 退回模板]"
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
