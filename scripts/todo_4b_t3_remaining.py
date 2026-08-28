"""#4 续: 只跑剩余 T3 分歧(8条) + 保存全部结果。"""
import sys, json, csv, time
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.llm.client import LLMClient

# 读 T3 分歧
max_t3 = {}
for l in Path("data/annotations/person_disambig_filled.jsonl").read_text(encoding="utf-8").splitlines():
    if l.strip(): o = json.loads(l); max_t3[o["name"]] = o.get("same_person")
plus_t3 = {}
p3 = Path("data/annotations/person_disambig_qwenplus.jsonl")
if p3.exists():
    for l in p3.read_text(encoding="utf-8").splitlines():
        if l.strip(): o = json.loads(l); plus_t3[o["name"]] = o.get("same_person")
t3_dis = [(n, max_t3[n], plus_t3[n]) for n in max_t3 if n in plus_t3 and max_t3[n] != plus_t3[n]]
print(f"T3 分歧总计: {len(t3_dis)}, 跳过前17条已完成")

ds = LLMClient(model="deepseek-v4-flash-0731")
t3_results = []
for i, (name, mv, pv) in enumerate(t3_dis):
    if i < 17:
        # 跳过已完成的(从日志重建)
        continue
    try:
        obj = ds.chat_json([{"role":"user","content":f"判断同名'{name}'在两家不同公司是否同一人。保守判断。输出JSON: {{\"same_person\":true/false,\"reason\":\"\"}}"}], schema_keys=["same_person","reason"])
        ds_j = bool(obj.get("same_person", False))
    except: ds_j = False
    t3_results.append({"name": name, "max": mv, "plus": pv, "deepseek": ds_j})
    print(f"  T3 [{i+1}/{len(t3_dis)}] {name[:10]} max={'T' if mv else 'F'} plus={'T' if pv else 'F'} ds={'T' if ds_j else 'F'}", flush=True)
    time.sleep(2)

# 合并前17条(从日志) + 新结果
# 从日志提取前17条的 deepseek 判断
log = Path("C:/Users/LEGION/AppData/Local/Temp/opencode/tiebreaker.txt").read_text(encoding="utf-8")
import re
early = []
for line in log.splitlines():
    m = re.search(r"T3 \[(\d+)/25\] (.+?) max=(T|F) plus=(T|F) ds=(T|F)", line)
    if m:
        idx = int(m.group(1))
        name = m.group(2).strip()
        mv = m.group(3) == "T"
        pv = m.group(4) == "T"
        ds = m.group(5) == "T"
        early.append({"name": name, "max": mv, "plus": pv, "deepseek": ds})

all_t3 = early + t3_results
print(f"\nT3 总计: {len(all_t3)} 条")

# 读 T1 tiebreaker(从日志)
t1_log = [l for l in log.splitlines() if "T1 [" in l]
print(f"T1 从日志: {len(t1_log)} 条")

# 多数表决
t3_maj = sum(1 for t in all_t3 if Counter([t["max"], t["plus"], t["deepseek"]]).most_common(1)[0][1] >= 2)
print(f"T3 多数一致: {t3_maj}/{len(all_t3)}")

Path("data/reviews/tiebreaker_t3_results.json").write_text(json.dumps(all_t3, ensure_ascii=False, indent=2), encoding="utf-8")
print("T3 tiebreaker -> data/reviews/tiebreaker_t3_results.json")
