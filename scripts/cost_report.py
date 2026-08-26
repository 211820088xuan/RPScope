"""P10 成本报告 - 跑一组 LLM 调用, 汇总 token/耗时/成本/优化降幅 -> docs/cost-report.md。

成本估算: DashScope glm-5.2 定价(参考 0.5元/百万 input, 1元/百万 output, 实际以官方为准)。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.client import LLMClient, metrics
from src.serve.cache import QueryCache
from src.serve.observability import snapshot as trace_snapshot

OUT = Path("docs/cost-report.md")

# 典型单次底稿涉及的 LLM 调用(消歧兜底 0 调用 + open_qa 答案 1 调用 + 金标准抽取 1 调用)
SAMPLE_PROMPTS = [
    ("消歧兜底(典型)", "判断两条董监高记录是否同一人: 张伟@002594董事 vs 张伟@300750董事, 输出JSON same_person/confidence/reason"),
    ("open_qa答案", "基于结构化数据回答: 002594有哪些风险事件"),
    ("金标准抽取", "从年报关联方章节文本抽取关联方名称JSON"),
]


def main() -> None:
    llm = LLMClient()
    cache = QueryCache()
    print(f"LLM enabled={llm.enabled}", flush=True)
    rows = []
    for label, prompt in SAMPLE_PROMPTS:
        if not llm.enabled:
            rows.append((label, 0, 0, 0.0, "LLM禁用"))
            continue
        # 跑 2 次(第2次走 cache? 此处 client 无缓存, 演示结构)
        t0 = __import__("time").perf_counter()
        try:
            llm.chat([{"role": "user", "content": prompt}])
            dt = __import__("time").perf_counter() - t0
            m = metrics()
            rows.append((label, m["prompt_tokens"], m["completion_tokens"], dt, ""))
        except Exception as e:
            rows.append((label, 0, 0, 0.0, f"{type(e).__name__}"))

    m = metrics()
    in_tok = sum(r[1] for r in rows); out_tok = sum(r[2] for r in rows)
    cost_in = in_tok / 1e6 * 0.5; cost_out = out_tok / 1e6 * 1.0  # 元
    total_cost = cost_in + cost_out
    traces = trace_snapshot()

    md = ["# P10 成本报告", ""]
    md.append("> 定价参考: DashScope glm-5.2 约 0.5元/百万 input, 1元/百万 output(以官方为准)")
    md.append("")
    md.append("## 单次底稿的 LLM 调用构成")
    md.append("")
    md.append("| 环节 | input tok | output tok | 耗时s | 备注 |")
    md.append("|---|---|---|---|---|")
    for label, it, ot, dt, note in rows:
        md.append(f"| {label} | {it} | {ot} | {dt:.2f} | {note} |")
    md.append("")
    md.append("## 成本汇总")
    md.append("")
    md.append(f"- input tokens: {in_tok} -> 约 {cost_in:.4f} 元")
    md.append(f"- output tokens: {out_tok} -> 约 {cost_out:.4f} 元")
    md.append(f"- **单次底稿估算成本: {total_cost:.4f} 元**")
    md.append(f"- 总调用 {m['calls']} 次, 错误 {m['errors']}, JSON修复 {m['json_repairs']}, 降级 {m['fallbacks']}")
    md.append("")
    md.append("## 优化手段与降幅")
    md.append("")
    md.append("| 手段 | 做法 | 可量化指标 |")
    md.append("|---|---|---|")
    md.append("| 规则优先 | 判定 100% 走规则, 单次底稿判定环节 LLM=0 | 判定 LLM 调用数=0 |")
    md.append("| 意图路由 | 简单问题不进多跳(P8: 简单题 0.05s/题 vs 全LLM 10s/题) | 速度 200x |")
    md.append("| 消歧分级 | 多信号能定的不调 LLM(P2: 兜底率 66.7% 实测集, 全图谱更低) | LLM 兜底率 |")
    md.append("| 语义缓存 | 相似问题命中(此版结构就绪) | 缓存命中率 |")
    md.append("| 结构化输出 | JSON mode, 避长文本重试 | JSON 一次成功率 |")
    md.append("| 模板降级 | LLM 不可用走模板(P10降级已验证) | RPSCOPE_LLM_ENABLED=false 仍产出底稿 |")
    md.append("")
    md.append("## 链路追踪(本次调用)")
    md.append("")
    for t in traces[:8]:
        md.append(f"- {t.get('name')}: {t.get('elapsed_ms',0):.0f}ms" + (f" tokens={t.get('tokens')}" if t.get('tokens') else ""))
    md.append("")
    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"成本报告 -> {OUT}")
    print(f"总 input={in_tok} output={out_tok} 成本≈{total_cost:.4f}元")


if __name__ == "__main__":
    main()
