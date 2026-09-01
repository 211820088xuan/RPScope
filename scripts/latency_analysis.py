"""T3: 延迟归因 — 从 trace 文件拆解各阶段耗时。"""
import json, glob, os
from collections import defaultdict
from pathlib import Path

trace_dir = ".cache/traces"
files = glob.glob(os.path.join(trace_dir, "*.json"))

by_intent = defaultdict(lambda: {"classify": [], "slot_fill": [], "entity_link": [], "execute": [], "answer_gen": [], "verify": [], "total": [], "llm_calls": []})

for f in files:
    t = json.loads(Path(f).read_text(encoding="utf-8"))
    intent = t.get("intent", "")
    if not intent:
        continue
    by_intent[intent]["total"].append(t.get("total_elapsed_ms", 0))

    # 从 events 拆解各阶段
    events = t.get("events", [])
    for e in events:
        node = e.get("node", "")
        elapsed = e.get("elapsed_ms", 0)
        if node == "classify":
            by_intent[intent]["classify"].append(elapsed)
        elif node == "slot_fill":
            prev = events[max(0, events.index(e)-1)].get("elapsed_ms", 0) if events.index(e) > 0 else 0
            by_intent[intent]["slot_fill"].append(elapsed - prev)
        elif node == "entity_link":
            prev = events[events.index(e)-1].get("elapsed_ms", 0) if events.index(e) > 0 else 0
            by_intent[intent]["entity_link"].append(elapsed - prev)
        elif node == "execute":
            by_intent[intent]["execute"].append(t.get("query_elapsed_ms", 0))
        elif node == "answer_generate":
            by_intent[intent]["answer_gen"].append(elapsed)
        elif node == "verify":
            by_intent[intent]["verify"].append(elapsed)

    # LLM 调用
    for call in t.get("llm_calls", []):
        by_intent[intent]["llm_calls"].append(call.get("elapsed_ms", 0))


def pct(arr, p):
    if not arr:
        return 0
    s = sorted(arr)
    idx = min(int(len(s) * p / 100), len(s) - 1)
    return s[idx]


print("=== 延迟归因 (ms) ===")
print(f"{'意图':4s} {'N':3s} {'分类 P50':8s} {'槽位 P50':8s} {'链接 P50':8s} {'执行 P50':8s} {'生成 P50':8s} {'总计 P50':8s} {'总计 P95':8s}")
print("-" * 80)
for intent in sorted(by_intent):
    d = by_intent[intent]
    n = len(d["total"])
    if n == 0:
        continue
    print(f"{intent:4s} {n:3d} {pct(d['classify'],50):7.0f}  {pct(d['slot_fill'],50):7.0f}  {pct(d['entity_link'],50):7.0f}  {pct(d['execute'],50):7.0f}  {pct(d['answer_gen'],50):7.0f}  {pct(d['total'],50):7.0f}  {pct(d['total'],95):7.0f}")

print(f"\n=== LLM 调用耗时 ===")
for intent in sorted(by_intent):
    d = by_intent[intent]
    if d["llm_calls"]:
        print(f"  {intent}: P50={pct(d['llm_calls'],50):.0f}ms P95={pct(d['llm_calls'],95):.0f}ms n={len(d['llm_calls'])}")

print(f"\n=== 占比分析 (按意图 P50) ===")
for intent in sorted(by_intent):
    d = by_intent[intent]
    total = pct(d["total"], 50)
    if total == 0:
        continue
    classify = pct(d["classify"], 50)
    slot = pct(d["slot_fill"], 50)
    link = pct(d["entity_link"], 50)
    execute = pct(d["execute"], 50)
    answer = pct(d["answer_gen"], 50)
    # verify is negligible
    print(f"  {intent}: 分类={classify/total*100:.0f}% 槽位={slot/total*100:.0f}% 链接={link/total*100:.0f}% 执行={execute/total*100:.0f}% 生成={answer/total*100:.0f}%")
