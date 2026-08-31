"""Q7: 模板外查询 — 走 generate.py 的 LLM 生成路径。"""
from __future__ import annotations


def execute(store, engine, slots: dict) -> dict:
    return {"template": "Q7", "note": "此意图走 LLM 生成路径, 不在此执行",
            "evidence_source": "generated_query"}
