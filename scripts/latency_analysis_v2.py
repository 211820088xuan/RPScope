"""T2: 延迟归因(绝对耗时) — 从 trace 拆解各阶段, 用事件时间差算阶段耗时。

之前错误: 用 cumulative timestamp 除以 total, 导致占比>100%。
修正: 用相邻 event 的 elapsed_ms 差值算各阶段绝对耗时。
"""
import json, glob, os, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

trace_dir = ".cache/traces"
files = glob.glob(os.path.join(trace_dir, "*.json"))

by_intent = defaultdict(lambda: {"stages": [], "totals": [], "llm_calls": [], "llm_retries": 0, "llm_count": 0})

for f in files:
    t = json.loads(Path(f).read_text(encoding="utf-8"))
    intent = t.get("intent", "")
    if not intent:
        continue
    total = t.get("total_elapsed_ms", 0)
    by_intent[intent]["totals"].append(total)

    # 从 events 用相邻时间差算各阶段
    events = t.get("events", [])
    prev_ts = 0
    stage_durations = {}
    for e in events:
        node = e.get("node", "")
        ts = e.get("elapsed_ms", 0)
        dur = max(0, ts - prev_ts)
        stage_durations[node] = dur
        prev_ts = ts

    # 补充: execute 阶段用 query_elapsed_ms
    if "query_elapsed_ms" in t:
        stage_durations["execute"] = t["query_elapsed_ms"]
    # verify 阶段 = total - 最后一个 event
    if events:
        stage_durations["verify"] = max(0, total - events[-1].get("elapsed_ms", 0))

    by_intent[intent]["stages"].append(stage_durations)

    # LLM 调用
    for call in t.get("llm_calls", []):
        by_intent[intent]["llm_calls"].append(call.get("elapsed_ms", 0))
        by_intent[intent]["llm_count"] += 1
        if call.get("retried"):
            by_intent[intent]["llm_retries"] += 1


def pct(arr, p):
    if not arr:
        return 0
    s = sorted(arr)
    idx = min(int(len(s) * p / 100), len(s) - 1)
    return s[idx]


def mean(arr):
    return sum(arr) / len(arr) if arr else 0


print("=== 延迟归因 (绝对耗时 ms) ===\n")
print(f"{'意图':4s} {'N':3s} {'分类P50':8s} {'槽位P50':8s} {'链接P50':8s} {'执行P50':8s} {'生成P50':8s} {'回查P50':8s} {'合计P50':8s} {'合计P95':8s}")
print("-" * 95)
for intent in sorted(by_intent):
    d = by_intent[intent]
    n = len(d["totals"])
    if n == 0:
        continue
    stages = d["stages"]
    print(f"{intent:4s} {n:3d} "
          f"{pct([s.get('classify',0) for s in stages],50):7.0f}  "
          f"{pct([s.get('slot_fill',0) for s in stages],50):7.0f}  "
          f"{pct([s.get('entity_link',0) for s in stages],50):7.0f}  "
          f"{pct([s.get('execute',0) for s in stages],50):7.0f}  "
          f"{pct([s.get('answer_generate',0) for s in stages],50):7.0f}  "
          f"{pct([s.get('verify',0) for s in stages],50):7.0f}  "
          f"{pct(d['totals'],50):7.0f}  "
          f"{pct(d['totals'],95):7.0f}")

print(f"\n=== LLM 调用统计 ===")
for intent in sorted(by_intent):
    d = by_intent[intent]
    if d["llm_calls"]:
        retry_rate = d["llm_retries"] / d["llm_count"] * 100 if d["llm_count"] else 0
        print(f"  {intent}: 调用={d['llm_count']} P50={pct(d['llm_calls'],50):.0f}ms P95={pct(d['llm_calls'],95):.0f}ms 重试率={retry_rate:.0f}%")

print(f"\n=== 分母错误诊断 ===")
print("之前错误原因: events 中的 elapsed_ms 是累计时间戳(从开始到该事件),")
print("用 slot_fill_elapsed / total 得到的是 '该事件时间点/总耗时', 不是 '该阶段耗时/总耗时'。")
print("例如 slot_fill 在 10s 时间点触发, total=15s, 10/15=67%(占比合理);")
print("但 answer_generate 在 14s 触发, 14/15=93%(占比合理);")
print("两者相加 67%+93%=160% > 100%, 因为分母是同一个 total, 分子是不同时间点。")
print("修正: 用相邻事件时间差算各阶段绝对耗时。")
