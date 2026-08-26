"""P2 LLM 兜底消歧 - 多信号无法判定时调一次 GLM。

走 src/llm/client.py 统一封装。保守策略: LLM 不确定也判不同人(宁漏不错)。
"""
from __future__ import annotations

from src.disambiguate.signals import Record
from src.llm.client import LLMClient


def llm_judge(name: str, rec_a: Record, rec_b: Record, client: LLMClient) -> tuple[bool, float, str]:
    """返回 (same_person, confidence, reason)。失败降级为不同人。"""
    prompt = (
        "你是实体消歧助手。判断两条董监高/持股变动记录是否为同一自然人。\n"
        "中国人名重名率极高; 同名不等于同人。依据公司行业、时段、职务综合判断。\n"
        "客观判断, 不预设倾向: 证据指向同人就判同, 证据指向不同人就判不同, 仅在真无任何线索时才判不同。\n\n"
        f"姓名: {name}\n"
        f"记录A: 公司{rec_a.stock_code}, 职务={rec_a.title}, 日期={rec_a.valid_from}, 来源={rec_a.source}\n"
        f"记录B: 公司{rec_b.stock_code}, 职务={rec_b.title}, 日期={rec_b.valid_from}, 来源={rec_b.source}\n\n"
        "输出 JSON: {\"same_person\": bool, \"confidence\": 0..1, \"reason\": \"...\"}"
    )
    try:
        obj = client.chat_json(
            [{"role": "user", "content": prompt}],
            schema_keys=["same_person", "confidence", "reason"],
        )
        same = bool(obj.get("same_person", False))
        conf = float(obj.get("confidence", 0.5))
        reason = str(obj.get("reason", ""))
        return same, conf, reason
    except Exception as e:
        return False, 0.3, f"LLM降级判不同人: {type(e).__name__}: {e}"
