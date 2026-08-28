"""保存 #4 tiebreaker 全部结果(T1从日志 + T3从日志)。"""
import re, json
from pathlib import Path

log = Path("C:/Users/LEGION/AppData/Local/Temp/opencode/tiebreaker.txt").read_text(encoding="utf-8", errors="replace")

t1_results = []
t3_results = []
for line in log.splitlines():
    m = re.search(r"T1 \[(\d+)/(\d+)\] (.+?) max=(\w+) plus=(\w+) ds=(\w+)", line)
    if m:
        t1_results.append({"party_name": m.group(3).strip(), "max_class": m.group(4), "plus_class": m.group(5), "deepseek_class": m.group(6)})
    m2 = re.search(r"T3 \[(\d+)/(\d+)\] (.+?) max=(T|F) plus=(T|F) ds=(T|F)", line)
    if m2:
        t3_results.append({"name": m2.group(3).strip(), "max": m2.group(4)=="T", "plus": m2.group(5)=="T", "deepseek": m2.group(6)=="T"})

# 多数表决
from collections import Counter
t1_maj = sum(1 for r in t1_results if Counter([r["max_class"], r["plus_class"], r["deepseek_class"]]).most_common(1)[0][1] >= 2)
t3_maj = sum(1 for t in t3_results if Counter([t["max"], t["plus"], t["deepseek"]]).most_common(1)[0][1] >= 2)

print(f"T1: {len(t1_results)} 条, 多数一致 {t1_maj}")
print(f"T3: {len(t3_results)} 条, 多数一致 {t3_maj}")
print(f"总计: {len(t1_results)+len(t3_results)} 条分歧全部用3模型裁判完毕")

Path("data/reviews/tiebreaker_results.json").write_text(
    json.dumps({"t1": t1_results, "t3": t3_results, "t1_majority": t1_maj, "t3_majority": t3_maj}, ensure_ascii=False, indent=2),
    encoding="utf-8")
print("-> data/reviews/tiebreaker_results.json")
