"""#4 deepseek tiebreaker for 53 disagreements."""
import sys, json, csv, time
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.llm.client import LLMClient

# T1 分歧
max_f = {r["party_name"]: r for r in csv.DictReader(open("data/reviews/system_only_review_filled.csv", encoding="utf-8-sig"))}
plus_f = {r["party_name"]: r["human_class"] for r in csv.DictReader(open("data/reviews/system_only_review_qwenplus.csv", encoding="utf-8-sig")) if r.get("human_class")}
disagreements = [r for nm, r in max_f.items() if r.get("human_class") and plus_f.get(nm, "") and r["human_class"] != plus_f.get(nm, "")]
print(f"T1 分歧: {len(disagreements)} 条")

# T3 分歧
max_t3 = {}
for l in Path("data/annotations/person_disambig_filled.jsonl").read_text(encoding="utf-8").splitlines():
    if l.strip(): o = json.loads(l); max_t3[o["name"]] = o.get("same_person")
plus_t3 = {}
p3 = Path("data/annotations/person_disambig_qwenplus.jsonl")
if p3.exists():
    for l in p3.read_text(encoding="utf-8").splitlines():
        if l.strip(): o = json.loads(l); plus_t3[o["name"]] = o.get("same_person")
t3_dis = [(n, max_t3[n], plus_t3[n]) for n in max_t3 if n in plus_t3 and max_t3[n] != plus_t3[n]]
print(f"T3 分歧: {len(t3_dis)} 条")

ds = LLMClient(model="deepseek-v4-flash-0731")
print(f"deepseek enabled={ds.enabled}")

t1_results = []
for i, r in enumerate(disagreements):
    prompt = f"判断该关联方候选属于哪类: true_omission(真漏报) / reasonable_undisclosed(合理未披露) / system_error(误报). 主体:{r.get('subject_name','')} 关联方:{r['party_name']} 规则:{r.get('rule_id','')} 路径:{r.get('path_readable','')[:80]}. 输出JSON: {{\"class\":\"\",\"reason\":\"\"}}"
    try:
        obj = ds.chat_json([{"role":"user","content":prompt}], schema_keys=["class","reason"])
        ds_cls = obj.get("class","")
    except: ds_cls = ""
    r["deepseek_class"] = ds_cls
    t1_results.append(r)
    print(f"  T1 [{i+1}/{len(disagreements)}] {r['party_name'][:12]} max={r['human_class'][:8]} plus={plus_f.get(r['party_name'],'')[:8]} ds={ds_cls[:8]}", flush=True)
    time.sleep(2)

t3_results = []
for i, (name, mv, pv) in enumerate(t3_dis):
    try:
        obj = ds.chat_json([{"role":"user","content":f"判断同名'{name}'在两家不同公司是否同一人。保守判断。输出JSON: {{\"same_person\":true/false,\"reason\":\"\"}}"}], schema_keys=["same_person","reason"])
        ds_j = bool(obj.get("same_person", False))
    except: ds_j = False
    t3_results.append({"name": name, "max": mv, "plus": pv, "deepseek": ds_j})
    print(f"  T3 [{i+1}/{len(t3_dis)}] {name[:10]} max={'T' if mv else 'F'} plus={'T' if pv else 'F'} ds={'T' if ds_j else 'F'}", flush=True)
    time.sleep(2)

# 多数表决
t1_maj = sum(1 for r in t1_results if Counter([r["human_class"], plus_f.get(r["party_name"],""), r.get("deepseek_class","")]).most_common(1)[0][1] >= 2)
t3_maj = sum(1 for t in t3_results if Counter([t["max"], t["plus"], t["deepseek"]]).most_common(1)[0][1] >= 2)
print(f"\nT1 多数一致: {t1_maj}/{len(t1_results)}")
print(f"T3 多数一致: {t3_maj}/{len(t3_results)}")

Path("data/reviews/tiebreaker_results.json").write_text(json.dumps({"t1": t1_results, "t3": t3_results}, ensure_ascii=False, indent=2), encoding="utf-8")
print("tiebreaker -> data/reviews/tiebreaker_results.json")
