"""LLM 打通测试 - 验证 DashScope GLM 端点 + key + response_format 可用，再写业务逻辑。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.client import ENABLED, LLMClient, metrics


def main() -> None:
    print(f"LLM enabled={ENABLED} model={__import__('src.llm.client', fromlist=['MODEL']).MODEL}")
    if not ENABLED:
        print("未启用，退出")
        return
    c = LLMClient()
    # 1. 普通对话
    try:
        ans = c.chat([{"role": "user", "content": "用一个词回答：A 股是哪个国家的股市？"}])
        print(f"[plain] {ans}")
    except Exception as e:
        print(f"[plain] FAIL {type(e).__name__}: {e}")
        return
    # 2. JSON 模式
    try:
        obj = c.chat_json(
            [{"role": "user", "content": '输出 JSON：{"same_person": true, "reason": "..."} 判断"张伟"和"张伟"是否可能是同一人，给出占位判断。'}],
            schema_keys=["same_person", "reason"],
        )
        print(f"[json ] {obj}")
    except Exception as e:
        print(f"[json ] FAIL {type(e).__name__}: {e}")
    print("metrics:", metrics())


if __name__ == "__main__":
    main()
