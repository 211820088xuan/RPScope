"""P7 Agent - LangGraph StateGraph 编排(意图路由 + 工具执行 + 断言回查)。

节点: classify -> route(条件) -> {fact|related|relation|open} -> verify -> END
简单意图(事实/关联方/关系)不调 LLM; 仅 open_qa 用 LLM 撰写(report writer, 铁律2 允许)。
"""
from __future__ import annotations

import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from src.agent.intent import classify, extract_codes
from src.agent.tools import tool_events, tool_fact, tool_related_party, tool_relation_explain
from src.agent.verifier import verify_answer
from src.llm.client import LLMClient
from src.rules.engine import RuleEngine
from src.store.db import Store


class AgentState(TypedDict):
    question: str
    intent: str
    codes: list[str]
    code: str
    answer: str
    used_llm: bool
    verify: dict
    elapsed_ms: float
    _t0: float
    _ctx: dict  # 中间结构化数据


# ---- 格式化 ----
def _fmt_fact(r: dict) -> str:
    co = r.get("company") or {}
    lines = [f"公司: {co.get('short_name','')}({co.get('stock_code','')}) 行业={co.get('industry','') or '未知'}"]
    hs = r.get("holders", [])
    if hs:
        lines.append("前十大股东:")
        for h in hs[:10]:
            tag = "[通道]" if h.get("is_channel") else ""
            ratio = h.get("ratio")
            ratio_s = f"{ratio}%" if ratio is not None else "未披露"
            lines.append(f"  {h.get('holder_rank')}. {h.get('display_name')} {ratio_s}{tag}")
    cs = r.get("controllers", [])
    if cs:
        lines.append("实际控制人:")
        for c in cs:
            lines.append(f"  {c.get('display_name')} ({c.get('control_ratio')}%)")
    return "\n".join(lines) or "无数据"


def _fmt_related(r: dict) -> str:
    lines = [f"关联方候选 {r.get('n',0)} 条(规则引擎):"]
    for p in (r.get("parties") or [])[:15]:
        lines.append(f"  [{p.get('confidence')}] {p.get('name')} <- {p.get('rule')}")
        if p.get("path"):
            lines.append(f"      路径: {p['path'][:80]}")
    return "\n".join(lines)


def _fmt_relation(r: dict) -> str:
    if r.get("related"):
        return (f"{r['code_a']} 与 {r['code_b']} 关联: 规则 {r.get('rule')} "
                f"({r.get('confidence')})\n路径: {r.get('path')}")
    return f"{r['code_a']} 与 {r['code_b']} 未发现关联路径(基于已入库数据)"


# ---- 依赖注入(图编译时绑定) ----
_DEPS: dict = {}


def configure(store: Store, engine: RuleEngine, llm: LLMClient) -> None:
    _DEPS["store"] = store
    _DEPS["engine"] = engine
    _DEPS["llm"] = llm


# ---- 节点 ----
def classify_node(state: AgentState) -> dict:
    q = state["question"]
    codes = extract_codes(q)
    code = (codes or [state.get("code", "")])[0]
    return {"intent": classify(q), "codes": codes, "code": code, "_t0": time.perf_counter()}


def fact_node(state: AgentState) -> dict:
    r = tool_fact(_DEPS["store"], state["code"])
    return {"answer": _fmt_fact(r), "used_llm": False, "_ctx": r}


def related_node(state: AgentState) -> dict:
    r = tool_related_party(_DEPS["store"], _DEPS["engine"], state["code"])
    ev = tool_events(_DEPS["store"], state["code"])
    return {"answer": _fmt_related(r) + f"\n\n事件时间线 {ev.get('n',0)} 条",
            "used_llm": False, "_ctx": {**r, "events": ev}}


def relation_node(state: AgentState) -> dict:
    codes = state["codes"]
    r = tool_relation_explain(_DEPS["store"], _DEPS["engine"], codes[0], codes[1])
    return {"answer": _fmt_relation(r), "used_llm": False, "_ctx": r}


def open_node(state: AgentState) -> dict:
    llm = _DEPS["llm"]
    code = state["code"]
    parts = []
    if code:
        parts.append(_fmt_fact(tool_fact(_DEPS["store"], code)))
        parts.append(_fmt_related(tool_related_party(_DEPS["store"], _DEPS["engine"], code)))
        ev = tool_events(_DEPS["store"], code)
        parts.append(f"风险事件: {ev.get('n',0)} 条")
        for e in (ev.get("events") or [])[:5]:
            parts.append(f"  {e.get('event_date','')} {e.get('event_type','')} {(e.get('summary','') or '')[:40]}")
    ctx = "\n".join(parts) or "无可用结构化数据"
    answer = ctx
    used = False
    if llm.enabled:
        used = True
        try:
            answer = llm.chat([
                {"role": "system", "content": f"你是关联方与风险分析助手。用户正在查看股票 {code}，以下是系统从公开数据中提取的结构化数据。你可以结合这些数据和你的知识回答用户问题。涉及具体公司名/持股比例/事件时，以结构化数据为准。"},
                {"role": "user", "content": f"问题: {state['question']}\n\n结构化数据:\n{ctx}\n\n请用中文回答。"},
            ])
        except Exception as e:
            used = False
            answer = f"[LLM 失败, 退回结构化] {ctx}\n\n(LLM错误: {e})"
    v = verify_answer(_DEPS["store"], answer)
    if not v["passed"]:
        answer += f"\n\n[回查警告: 未在事实源找到: {v['violations']}]"
    return {"answer": answer, "used_llm": used, "verify": v, "_ctx": {"ctx": ctx}}


def finish_node(state: AgentState) -> dict:
    elapsed = (time.perf_counter() - state.get("_t0", time.perf_counter())) * 1000
    v = state.get("verify") or {"passed": True, "violations": []}
    return {"elapsed_ms": elapsed, "verify": v}


def route(state: AgentState) -> str:
    intent = state["intent"]
    code = state.get("code", "")
    if intent == "fact_query" and code:
        return "fact"
    if intent == "related_party" and code:
        return "related"
    if intent == "relation_explain" and len(state.get("codes", [])) >= 2:
        return "relation"
    return "open"


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("classify", classify_node)
    g.add_node("fact", fact_node)
    g.add_node("related", related_node)
    g.add_node("relation", relation_node)
    g.add_node("open", open_node)
    g.add_node("finish", finish_node)
    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", route, {"fact": "fact", "related": "related",
                                                "relation": "relation", "open": "open"})
    for n in ("fact", "related", "relation", "open"):
        g.add_edge(n, "finish")
    g.add_edge("finish", END)
    return g.compile()


_APP = None


def run(store: Store, engine: RuleEngine, llm: LLMClient, question: str, context_code: str = "") -> dict:
    global _APP
    if _APP is None:
        configure(store, engine, llm)
        _APP = build_graph()
    elif _DEPS.get("store") is not store:
        configure(store, engine, llm)
    codes = extract_codes(question)
    code = (codes or [context_code])[0] if (codes or context_code) else ""
    out = _APP.invoke({"question": question, "code": code, "codes": codes or ([context_code] if context_code else []), "answer": "",
                       "used_llm": False, "verify": {}, "elapsed_ms": 0.0, "_t0": 0.0, "_ctx": {}})
    return {"intent": out.get("intent", ""), "answer": out.get("answer", ""),
            "used_llm": out.get("used_llm", False), "code": out.get("code", ""),
            "verify": out.get("verify", {}), "elapsed_ms": out.get("elapsed_ms", 0.0)}
