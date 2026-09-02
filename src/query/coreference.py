"""T2: 指代消解 — 规则优先, LLM 兜底, 不确定必须澄清。

指代类型:
  代词指代   「它的担保对象呢」     → 焦点栈栈顶
  序数指代   「第三个是怎么关联的」  → 上一轮结果列表第 N 项
  名称片段   「宁德时代那个呢」     → 上一轮结果中名称匹配项
  省略主语   「关联方有哪些」(无实体) → 焦点栈栈顶
  显式覆盖   「那茅台呢」           → 新实体, 替换焦点

消解失败必须澄清, 不得猜测。
"""
from __future__ import annotations
import re, yaml
from pathlib import Path
from src.query.conversation import ConversationState, FocusEntity
from src.normalize.name import normalize_name
from src.llm.prompts import get_prompt

_CFG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "coreference_keywords.yaml"
_CFG: dict | None = None


def _load_cfg() -> dict:
    global _CFG
    if _CFG is None:
        _CFG = yaml.safe_load(_CFG_PATH.read_text(encoding="utf-8"))
    return _CFG


# 代词检测
def _has_pronoun(question: str) -> str | None:
    """检测问句是否含代词, 返回匹配到的代词或 None。"""
    cfg = _load_cfg()
    for p in cfg["pronouns"]:
        if p in question:
            return p
    return None


# 序数检测
def _extract_ordinal(question: str) -> int | None:
    """提取序数词, 返回 0-based 索引或 None。支持任意'第N个'。"""
    cfg = _load_cfg()
    # 先匹配配置中的已知序数词(按长度降序)
    for kw, idx in sorted(cfg["ordinals"].items(), key=lambda x: -len(x[0])):
        if kw in question:
            return idx
    # 通配: 第N个/第N (中文数字)
    cn_map = {"一":0,"二":1,"三":2,"四":3,"五":4,"六":5,"七":6,"八":7,"九":8,"十":9}
    m = re.search(r"第([一二三四五六七八九十])个?", question)
    if m:
        return cn_map.get(m.group(1), None)
    # 阿拉伯数字
    m = re.search(r"第(\d+)个?", question)
    if m:
        return int(m.group(1)) - 1
    return None


# 省略主语检测
def _is_omission(question: str, has_entity: bool) -> bool:
    """问句无实体但含查询关键词时, 触发省略主语指代。"""
    if has_entity:
        return False
    cfg = _load_cfg()
    return any(kw in question for kw in cfg["omission_indicators"])


# 显式覆盖检测
def _is_override(question: str) -> bool:
    cfg = _load_cfg()
    return any(kw in question for kw in cfg["override_indicators"])


def resolve(question: str, state: ConversationState, has_entity: bool,
            conn=None) -> dict:
    """指代消解主入口。

    返回:
      {resolved: True, entity: {stock_code/entity_id, name, type}, source: str, pronoun: str}
      {resolved: False, clarify: str, candidates: list}
    """
    pronoun = _has_pronoun(question)
    ordinal = _extract_ordinal(question)
    omission = _is_omission(question, has_entity)
    override = _is_override(question)

    # --- 代词指代 ---
    if pronoun:
        # 检查焦点栈中有几个不同的 user_mention 实体
        user_mentions = [f for f in state.focus_stack if f.source == "user_mention"]
        unique_codes = set(f.stock_code or str(f.entity_id) for f in user_mentions if f.stock_code or f.entity_id)
        if len(unique_codes) > 1:
            # 多个实体 → 歧义, 必须澄清
            return {"resolved": False,
                    "clarify": f"上一轮提到了多个实体({', '.join(f.name for f in user_mentions[:3])}), 请问「{pronoun}」指哪一个？",
                    "candidates": [{"name": f.name, "stock_code": f.stock_code} for f in user_mentions[:5]]}
        focus = state.get_focus_top()
        if focus:
            return {"resolved": True,
                    "entity": {"stock_code": focus.stock_code, "entity_id": focus.entity_id,
                               "name": focus.name, "type": focus.entity_type},
                    "source": "pronoun_stack_top", "pronoun": pronoun}
        return {"resolved": False, "clarify": "请问您想查询哪家公司？当前没有可指代的实体。",
                "candidates": []}

    # --- 序数指代 ---
    if ordinal is not None:
        last_results = state.get_last_results()
        if not last_results:
            return {"resolved": False,
                    "clarify": "上一轮没有返回结果列表, 无法使用序数指代。",
                    "candidates": []}
        # 负索引(最后)
        if ordinal < 0:
            ordinal = len(last_results) + ordinal
        if ordinal < 0 or ordinal >= len(last_results):
            return {"resolved": False,
                    "clarify": f"上一轮结果只有 {len(last_results)} 项, 没有第 {ordinal+1} 项。",
                    "candidates": [{"name": r.get("name", ""), "stock_code": r.get("stock_code", "")}
                                   for r in last_results]}
        target = last_results[ordinal]
        return {"resolved": True,
                "entity": {"stock_code": target.get("stock_code", ""),
                           "entity_id": target.get("entity_id", 0),
                           "name": target.get("name", ""), "type": target.get("type", "")},
                "source": "ordinal", "pronoun": f"第{ordinal+1}项"}

    # --- 省略主语 ---
    if omission:
        focus = state.get_focus_top()
        if focus:
            return {"resolved": True,
                    "entity": {"stock_code": focus.stock_code, "entity_id": focus.entity_id,
                               "name": focus.name, "type": focus.entity_type},
                    "source": "omission_stack_top", "pronoun": "(省略主语)"}
        return {"resolved": False, "clarify": "请问您想查询哪家公司？",
                "candidates": []}

    # --- 名称片段指代 ---
    # 在上一轮结果中匹配名称片段
    last_results = state.get_last_results()
    last_turn = state.get_last_turn()
    if last_results and last_turn:
        # 提取问句中可能的公司/人名片段
        from src.query.dict_match import CompanyMatcher, PersonMatcher
        if conn:
            cm = CompanyMatcher(conn)
            pm = PersonMatcher(conn)
            for matcher, etype in [(cm, "company"), (pm, "person")]:
                m = matcher.match(question)
                if m:
                    # 在上一轮结果中找匹配
                    matched = [r for r in last_results
                               if normalize_name(r.get("name", "")) == normalize_name(m.text)
                               or normalize_name(m.text) in normalize_name(r.get("name", ""))]
                    if len(matched) == 1:
                        return {"resolved": True,
                                "entity": {"stock_code": matched[0].get("stock_code", ""),
                                           "entity_id": matched[0].get("entity_id", 0),
                                           "name": matched[0].get("name", ""),
                                           "type": matched[0].get("type", "")},
                                "source": "name_fragment", "pronoun": m.text}
                    if len(matched) > 1:
                        return {"resolved": False,
                                "clarify": f"「{m.text}」在上一轮结果中有多条匹配, 请选择:",
                                "candidates": [{"name": r.get("name", ""),
                                                "stock_code": r.get("stock_code", "")}
                                               for r in matched]}

    # --- 显式覆盖 ---
    # 如果问句含新实体(已在 has_entity 中检测), 不需要指代消解
    # override 不做特殊处理, 正常走槽位抽取

    # 无指代
    return {"resolved": False, "no_coreference": True}


def resolve_with_llm_fallback(question: str, state: ConversationState,
                              has_entity: bool, llm, conn=None) -> dict:
    """规则消解失败时, LLM 兜底(只输出 entity_id 或序号)。"""
    result = resolve(question, state, has_entity, conn)
    if result.get("resolved") or result.get("no_coreference") or result.get("clarify"):
        return result

    # LLM 兜底: 给 LLM 上下文, 让它判断指代目标
    focus_top = state.get_focus_top()
    last_results = state.get_last_results()
    ctx = f"焦点栈顶: {focus_top.name if focus_top else '空'}\n"
    if last_results:
        ctx += f"上一轮结果: {json.dumps([r.get('name','') for r in last_results[:5]], ensure_ascii=False)}"
    try:
        ans = llm.chat_json(get_prompt("coreference", ctx=ctx, question=question))
        if ans.get("uncertain"):
            return {"resolved": False, "clarify": "无法确定指代目标, 请明确指出您想查询哪家公司。",
                    "candidates": []}
        if "result_index" in ans:
            idx = int(ans["result_index"])
            if last_results and 0 <= idx < len(last_results):
                target = last_results[idx]
                return {"resolved": True,
                        "entity": {"stock_code": target.get("stock_code", ""),
                                   "entity_id": target.get("entity_id", 0),
                                   "name": target.get("name", ""), "type": target.get("type", "")},
                        "source": "llm_ordinal", "pronoun": "(LLM判断)"}
        if "entity_name" in ans:
            name = ans["entity_name"]
            # 在焦点栈中找
            for f in state.focus_stack:
                if normalize_name(f.name) == normalize_name(name):
                    return {"resolved": True,
                            "entity": {"stock_code": f.stock_code, "entity_id": f.entity_id,
                                       "name": f.name, "type": f.entity_type},
                            "source": "llm_stack", "pronoun": name}
        return {"resolved": False, "clarify": f"未找到「{name}」相关的实体。",
                "candidates": []}
    except Exception:
        return {"resolved": False, "clarify": "无法确定指代目标, 请明确指出您想查询哪家公司。",
                "candidates": []}


import json
