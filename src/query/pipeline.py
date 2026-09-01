"""T5: 改造 Agent 链路 — 自然语言图查询。

流程:
  规则意图分类
  ├─ 确定 → 槽位抽取(LLM) → 实体链接 → 模板执行 → 结果组装 → 回答生成(LLM) → 回查
  ├─ 不确定 → LLM 意图分类+槽位抽取(合并) → 同上
  └─ 模板外(Q7) → LLM 生成查询 → 三道校验 → 执行 → 结果组装 → 回答生成 → 回查
  └─ 校验失败 → 能力边界说明
  实体链接歧义 → 澄清请求(中断, 等待用户选择)
"""
from __future__ import annotations
import time
from typing import TypedDict
from langgraph.graph import END, START, StateGraph

from src.llm.client import LLMClient
from src.query.intent import classify as rule_classify
from src.query.slot_filling import extract_slots, classify_and_extract
from src.query.entity_link import link_slots
from src.query.templates import get_executor
from src.query.generate import generate_and_execute
from src.query.trace import Trace
from src.query.rule_slots import rule_extract
from src.rules.engine import RuleEngine
from src.store.db import Store
from src.agent.verifier import verify_answer


class NLQueryState(TypedDict):
    question: str
    context_code: str
    intent: str
    confidence: float
    uncertain: bool
    classification_source: str
    slots: dict
    linked_slots: dict
    clarifications: list
    errors: list
    result: dict
    answer: str
    used_llm: bool
    verify: dict
    elapsed_ms: float
    _trace: Trace
    _t0: float


_DEPS: dict = {}


def configure(store: Store, engine: RuleEngine, llm: LLMClient) -> None:
    _DEPS["store"] = store
    _DEPS["engine"] = engine
    _DEPS["llm"] = llm


# ---- 节点 ----

def classify_node(state: NLQueryState) -> dict:
    q = state["question"]
    trace = Trace(q)
    r = rule_classify(q)
    trace.intent = r["intent"]
    trace.confidence = r["confidence"]
    trace.uncertain = r["uncertain"]
    trace.classification_source = "rule" if not r["uncertain"] else "llm_pending"
    trace.add_event("classify", {"intent": r["intent"], "confidence": r["confidence"]})
    return {"intent": r["intent"], "confidence": r["confidence"], "uncertain": r["uncertain"],
            "classification_source": "rule" if not r["uncertain"] else "llm_pending",
            "_trace": trace, "_t0": time.perf_counter()}


def slot_fill_node(state: NLQueryState) -> dict:
    llm = _DEPS["llm"]
    trace = state["_trace"]
    intent = state["intent"]
    q = state["question"]

    if state["uncertain"]:
        # uncertain: 合并意图分类+槽位抽取为一次 LLM 调用
        r = classify_and_extract(q, llm)
        intent = r["intent"]
        trace.intent = intent
        trace.classification_source = "llm"
        trace.add_llm_call("classify_and_extract", (time.perf_counter() - state["_t0"]) * 1000)
        slots = r.get("slots", {})
        trace.slots = slots
        trace.add_event("slot_fill", {"slots": slots, "source": "llm"})
    else:
        # 确定: 先规则抽取, 失败才调 LLM
        r = rule_extract(intent, q, _DEPS["store"].conn, state.get("context_code", ""))
        if r:
            slots = r
            trace.add_event("slot_fill", {"slots": slots, "source": "rule"})
        else:
            # LLM 兜底
            r = extract_slots(q, intent, llm)
            trace.add_llm_call("extract_slots", (time.perf_counter() - state["_t0"]) * 1000)
            slots = r.get("slots", {})
            trace.add_event("slot_fill", {"slots": slots, "source": "llm_fallback"})

    # 如果 intent 是 Q4/Q5 且有 context_code 但 slots 里没有 company, 用 context_code
    if intent in ("Q1", "Q4", "Q5") and "company" not in slots and state.get("context_code"):
        slots["company"] = state["context_code"]
    if intent == "Q2" and "entity_b" not in slots and state.get("context_code"):
        slots.setdefault("entity_b", state["context_code"])

    trace.slots = slots
    return {"intent": intent, "slots": slots}


def entity_link_node(state: NLQueryState) -> dict:
    store = _DEPS["store"]
    trace = state["_trace"]
    r = link_slots(store, state["intent"], state["slots"])
    trace.entity_links = [{"slot": k, "method": v} for k, v in r["slots"].items() if k.startswith("_")]
    trace.add_event("entity_link", {"clarifications": r["clarifications"], "errors": r["errors"]})
    return {"linked_slots": r["slots"], "clarifications": r["clarifications"], "errors": r["errors"]}


def execute_node(state: NLQueryState) -> dict:
    store = _DEPS["store"]
    engine = _DEPS["engine"]
    llm = _DEPS["llm"]
    trace = state["_trace"]
    intent = state["intent"]
    slots = state["linked_slots"]

    if intent == "Q7":
        # 模板外: LLM 生成查询
        t0 = time.perf_counter()
        result = generate_and_execute(store, llm, state["question"], trace)
        elapsed = (time.perf_counter() - t0) * 1000
        trace.query_elapsed_ms = elapsed
        trace.generated_query = result.get("sql")
        trace.add_event("execute", {"source": "generated_query", "n": result.get("n", 0), "elapsed_ms": elapsed})
    else:
        # 模板执行
        executor = get_executor(intent)
        t0 = time.perf_counter()
        result = executor(store, engine, slots)
        elapsed = (time.perf_counter() - t0) * 1000
        trace.query_elapsed_ms = elapsed
        trace.template_id = intent
        trace.query_params = {k: v for k, v in slots.items() if not k.startswith("_")}
        trace.query_result_count = result.get("n", len(result))
        trace.add_event("execute", {"template": intent, "n": trace.query_result_count, "elapsed_ms": elapsed})

    return {"result": result}


def clarify_node(state: NLQueryState) -> dict:
    """实体链接歧义 → 返回澄清请求。"""
    clars = state["clarifications"]
    lines = ["以下实体有多种匹配, 请选择:"]
    for c in clars:
        lines.append(f"\n「{c['input']}」的候选:")
        for i, cand in enumerate(c["candidates"], 1):
            label = cand.get("name", cand.get("code", ""))
            lines.append(f"  {i}. {label}")
    answer = "\n".join(lines)
    state["_trace"].answer = answer
    state["_trace"].add_event("clarify", {"clarifications": clars})
    return {"answer": answer, "used_llm": False}


def answer_generate_node(state: NLQueryState) -> dict:
    llm = _DEPS["llm"]
    trace = state["_trace"]
    result = state["result"]
    intent = state["intent"]
    q = state["question"]

    # 把结构化结果格式化为文本上下文
    import json
    ctx = json.dumps(result, ensure_ascii=False, default=str)[:3000]

    if not llm.enabled:
        answer = ctx
    else:
        try:
            code = state.get("linked_slots", {}).get("company", state.get("context_code", ""))
            answer = llm.chat([
                {"role": "system", "content": f"你是关联方分析助手。用户正在查看股票 {code}。基于以下结构化查询结果回答用户问题, 用中文。财务和行业分析可以基于你的知识。不要加免责声明。"},
                {"role": "user", "content": f"问题: {q}\n\n查询结果:\n{ctx}"},
            ])
        except Exception as e:
            answer = f"[LLM 失败] {ctx}\n\n(LLM错误: {e})"

    trace.answer = answer
    trace.add_event("answer_generate", {"answer_length": len(answer)})
    return {"answer": answer, "used_llm": llm.enabled}


def verify_node(state: NLQueryState) -> dict:
    store = _DEPS["store"]
    trace = state["_trace"]
    v = verify_answer(store, state["answer"])
    trace.verify_result = v
    trace.add_event("verify", {"passed": v["passed"], "violations": v.get("violations", [])})
    return {"verify": v}


def finish_node(state: NLQueryState) -> dict:
    elapsed = (time.perf_counter() - state.get("_t0", time.perf_counter())) * 1000
    trace = state["_trace"]
    trace.save()
    return {"elapsed_ms": elapsed}


# ---- 路由 ----

def route_after_link(state: NLQueryState) -> str:
    if state.get("clarifications"):
        return "clarify"
    if state.get("errors"):
        return "answer_generate"
    return "execute"


def route_after_classify(state: NLQueryState) -> str:
    # uncertain 时走 LLM 合并路径; 否则走规则确定路径
    return "slot_fill"  # slot_fill 内部判断是否 uncertain


# ---- 图构建 ----

def build_graph():
    g = StateGraph(NLQueryState)
    g.add_node("classify", classify_node)
    g.add_node("slot_fill", slot_fill_node)
    g.add_node("entity_link", entity_link_node)
    g.add_node("clarify", clarify_node)
    g.add_node("execute", execute_node)
    g.add_node("answer_generate", answer_generate_node)
    g.add_node("verify", verify_node)
    g.add_node("finish", finish_node)

    g.add_edge(START, "classify")
    g.add_edge("classify", "slot_fill")
    g.add_edge("slot_fill", "entity_link")
    g.add_conditional_edges("entity_link", route_after_link,
                            {"clarify": "clarify", "answer_generate": "answer_generate", "execute": "execute"})
    g.add_edge("clarify", "finish")
    g.add_edge("execute", "answer_generate")
    g.add_edge("answer_generate", "verify")
    g.add_edge("verify", "finish")
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

    out = _APP.invoke({
        "question": question, "context_code": context_code,
        "intent": "", "confidence": 0.0, "uncertain": False, "classification_source": "",
        "slots": {}, "linked_slots": {}, "clarifications": [], "errors": [],
        "result": {}, "answer": "", "used_llm": False, "verify": {},
        "elapsed_ms": 0.0, "_trace": None, "_t0": time.perf_counter(),
    })
    return {
        "intent": out.get("intent", ""),
        "answer": out.get("answer", ""),
        "used_llm": out.get("used_llm", False),
        "verify": out.get("verify", {}),
        "elapsed_ms": out.get("elapsed_ms", 0.0),
        "clarifications": out.get("clarifications", []),
    }
