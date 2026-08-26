"""P7 CLI - 问一个问题, 看意图路由 + 答案 + 回查 + 延迟。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.graph import run
from src.llm.client import LLMClient
from src.rules.engine import RuleEngine
from src.store.db import Store

DEMO = [
    "002594的前十大股东和实控人",               # fact_query (无LLM)
    "002594的关联方有哪些",                      # related_party (无LLM)
    "002594和300750是什么关系",                # relation_explain (无LLM)
    "002594有哪些风险事件",                     # open_qa (LLM)
]


def main() -> None:
    store = Store("rpscope.db")
    eng = RuleEngine("config/rules.yaml")
    llm = LLMClient()
    qs = sys.argv[1:] if len(sys.argv) > 1 else DEMO
    print(f"LLM enabled={llm.enabled}\n")
    for q in qs:
        r = run(store, eng, llm, q)
        print(f"Q: {q}")
        print(f"  [意图={r['intent']} LLM={r['used_llm']} 回查={'通过' if r['verify']['passed'] else '未通过'} {r['elapsed_ms']:.0f}ms]")
        print(f"  A: {r['answer'][:200]}{'...' if len(r['answer'])>200 else ''}")
        print()


if __name__ == "__main__":
    main()
