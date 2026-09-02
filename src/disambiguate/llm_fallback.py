"""P2 LLM 兜底消歧 - 多信号无法判定时调一次 GLM。

走 src/llm/client.py 统一封装。保守策略: LLM 不确定也判不同人(宁漏不错)。
"""
from __future__ import annotations

from src.disambiguate.signals import Record
from src.llm.client import LLMClient
from src.llm.prompts import get_prompt


def llm_judge(name: str, rec_a: Record, rec_b: Record, client: LLMClient) -> tuple[bool, float, str]:
    """返回 (same_person, confidence, reason)。失败降级为不同人。"""
    messages = get_prompt("disambig",
        name=name,
        rec_a_stock_code=rec_a.stock_code, rec_a_title=rec_a.title,
        rec_a_valid_from=rec_a.valid_from, rec_a_source=rec_a.source,
        rec_b_stock_code=rec_b.stock_code, rec_b_title=rec_b.title,
        rec_b_valid_from=rec_b.valid_from, rec_b_source=rec_b.source,
    )
    try:
        obj = client.chat_json(
            messages,
            schema_keys=["same_person", "confidence", "reason"],
        )
        same = bool(obj.get("same_person", False))
        conf = float(obj.get("confidence", 0.5))
        reason = str(obj.get("reason", ""))
        return same, conf, reason
    except Exception as e:
        return False, 0.3, f"LLM降级判不同人: {type(e).__name__}: {e}"
