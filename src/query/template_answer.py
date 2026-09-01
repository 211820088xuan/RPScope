"""Q4/Q5 模板回答 — 跳过 LLM, 直接格式化结构化结果。

Q4(公司角色): 股东/董监高/实控人 → 直接格式化为文本
Q5(风险事件): 担保/诉讼/质押 → 直接格式化为时间线
"""
from __future__ import annotations


def format_q4(result: dict) -> str:
    """Q4: 公司角色 → 文本。"""
    code = result.get("code", "")
    roles = result.get("roles", {})
    lines = [f"股票代码 {code} 的角色信息："]

    holders = roles.get("holders", [])
    if holders:
        lines.append("\n前十大股东：")
        for i, h in enumerate(holders, 1):
            name = h.get("display_name", "")
            ratio = h.get("ratio")
            etype = h.get("entity_type", "")
            ch = " [通道]" if h.get("is_channel") else ""
            r = f" {ratio}%" if ratio is not None else ""
            lines.append(f"  {i}. {name}{r} ({etype}){ch}")

    controllers = roles.get("controllers", [])
    if controllers:
        lines.append("\n实际控制人：")
        for c in controllers:
            name = c.get("display_name", "")
            ratio = c.get("control_ratio")
            r = f" ({ratio}%)" if ratio is not None else ""
            lines.append(f"  {name}{r}")

    directors = roles.get("directors", [])
    if directors:
        lines.append("\n董监高：")
        for d in directors:
            name = d.get("display_name", "")
            title = d.get("title", "")
            lines.append(f"  {name} - {title}")

    if not holders and not controllers and not directors:
        lines.append("  无数据")

    return "\n".join(lines)


def format_q5(result: dict) -> str:
    """Q5: 风险事件 → 文本。"""
    code = result.get("code", "")
    events = result.get("events", [])
    n = result.get("n", len(events))

    if not events:
        return f"股票代码 {code} 暂无风险事件记录。"

    lines = [f"股票代码 {code} 共有 {n} 条风险事件：\n"]

    # 按类型分组统计
    by_type = {}
    for e in events:
        et = e.get("event_type", "unknown")
        if et not in by_type:
            by_type[et] = []
        by_type[et].append(e)

    type_names = {"guarantee": "担保", "lawsuit": "诉讼", "pledge": "质押", "related_txn": "关联交易"}

    for et, evs in by_type.items():
        name = type_names.get(et, et)
        total = sum(e.get("amount") or 0 for e in evs)
        lines.append(f"【{name}】{len(evs)} 笔", )
        if total > 0:
            lines.append(f"  金额合计: {total:,.0f} 元")
        for e in evs[:5]:
            date = e.get("event_date", "")
            summary = e.get("summary", "")[:50]
            cp = e.get("counterparty", "")
            cp_s = f" 对方: {cp}" if cp else ""
            lines.append(f"  {date} {summary}{cp_s}")
        if len(evs) > 5:
            lines.append(f"  ...还有 {len(evs)-5} 笔")

    return "\n".join(lines)


def can_template(intent: str) -> bool:
    """判断该意图是否可以用模板回答(跳过 LLM)。"""
    return intent in ("Q4", "Q5")


def format_result(intent: str, result: dict) -> str:
    """模板格式化结构化结果。"""
    if intent == "Q4":
        return format_q4(result)
    elif intent == "Q5":
        return format_q5(result)
    return ""
