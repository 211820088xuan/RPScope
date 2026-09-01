"""T1: 对话状态与焦点栈 — 显式维护可被指代的实体。

不存 messages 列表, 而存结构化的轮次记录 + 焦点实体栈。
焦点更新规则是确定性代码, 不由 LLM 决定。
"""
from __future__ import annotations
import time, json
from dataclasses import dataclass, field, asdict
from typing import Any

_MAX_TURNS = 3  # 焦点栈保留最近 3 轮


@dataclass
class FocusEntity:
    """可被指代的实体。"""
    entity_id: int = 0
    stock_code: str = ""
    name: str = ""
    entity_type: str = ""  # company / person / org
    source: str = ""  # user_mention / query_subject / result_item
    turn: int = 0
    result_index: int = -1  # 若来自结果列表, 记录序号(0-based)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TurnRecord:
    """一轮对话的记录。"""
    turn: int
    question: str
    intent: str
    slots: dict
    linked_entities: list[dict]  # 本轮链接到的实体
    result_entities: list[dict]  # 本轮返回结果中的实体(供序数指代)
    # each: {entity_id, stock_code, name, type}
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class ConversationState:
    """会话状态, 按 session_id 隔离。"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.chat_history: list[TurnRecord] = []
        self.focus_stack: list[FocusEntity] = []
        self.turn = 0

    def begin_turn(self) -> int:
        self.turn += 1
        return self.turn

    def record_turn(self, question: str, intent: str, slots: dict,
                    linked_entities: list[dict], result_entities: list[dict],
                    elapsed_ms: float = 0.0):
        """记录一轮, 更新焦点栈。确定性规则, 不调 LLM。"""
        turn = self.begin_turn()
        rec = TurnRecord(turn=turn, question=question, intent=intent,
                         slots={k: v for k, v in slots.items() if not k.startswith("_")},
                         linked_entities=linked_entities,
                         result_entities=result_entities,
                         elapsed_ms=elapsed_ms)
        self.chat_history.append(rec)

        # 焦点更新规则(确定性):
        # 1. 用户显式提及的实体(从 slots)入栈, 优先级最高
        for le in linked_entities:
            fe = FocusEntity(
                entity_id=le.get("entity_id", 0),
                stock_code=le.get("stock_code", le.get("code", "")),
                name=le.get("name", ""),
                entity_type=le.get("type", le.get("entity_type", "")),
                source="user_mention",
                turn=turn,
                result_index=-1,
            )
            self.focus_stack.insert(0, fe)  # 栈顶

        # 2. 上一轮的查询主体保留在栈中(已在 step 1 入栈)

        # 3. 结果列表整体入栈(供序数指代)
        for i, re_entity in enumerate(result_entities):
            fe = FocusEntity(
                entity_id=re_entity.get("entity_id", 0),
                stock_code=re_entity.get("stock_code", re_entity.get("code", "")),
                name=re_entity.get("name", ""),
                entity_type=re_entity.get("type", ""),
                source="result_item",
                turn=turn,
                result_index=i,
            )
            self.focus_stack.append(fe)

        # 4. 容量限制: 只保留最近 _MAX_TURNS 轮
        min_turn = turn - _MAX_TURNS
        self.focus_stack = [f for f in self.focus_stack if f.turn >= min_turn]
        self.chat_history = [r for r in self.chat_history if r.turn >= min_turn]

    def get_last_turn(self) -> TurnRecord | None:
        return self.chat_history[-1] if self.chat_history else None

    def get_focus_top(self) -> FocusEntity | None:
        """焦点栈栈顶(最近显式提及的实体)。"""
        for f in self.focus_stack:
            if f.source == "user_mention":
                return f
        return self.focus_stack[0] if self.focus_stack else None

    def get_last_results(self) -> list[dict] | None:
        """上一轮的结果列表(供序数指代)。"""
        last = self.get_last_turn()
        return last.result_entities if last and last.result_entities else None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "turn": self.turn,
            "chat_history": [r.to_dict() for r in self.chat_history],
            "focus_stack": [f.to_dict() for f in self.focus_stack],
        }


# 会话存储(内存 + TTL, 接口允许换持久化)
_sessions: dict[str, ConversationState] = {}
_session_ts: dict[str, float] = {}
_TTL = 1800  # 30 分钟


def get_session(session_id: str) -> ConversationState:
    """获取或创建会话状态。"""
    now = time.time()
    # 清理过期会话
    expired = [sid for sid, ts in _session_ts.items() if now - ts > _TTL]
    for sid in expired:
        _sessions.pop(sid, None)
        _session_ts.pop(sid, None)

    if session_id not in _sessions:
        _sessions[session_id] = ConversationState(session_id)
    _session_ts[session_id] = now
    return _sessions[session_id]
