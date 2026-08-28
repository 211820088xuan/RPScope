"""#1: 用 qwen3.7-max 标 200 对消歧(增量, 跳过已有的90)。"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.llm.client import LLMClient

pairs = [json.loads(l) for l in Path("data/annotations/person_disambig.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
print(f"标注集: {len(pairs)} 对")

fpath = Path("data/annotations/person_disambig_filled.jsonl")
filled = {}
if fpath.exists():
    for l in fpath.read_text(encoding="utf-8").splitlines():
        if l.strip():
            o = json.loads(l)
            filled[o["name"] + str(o.get("rec_a", {}).get("stock_code", ""))] = o
print(f"已标: {len(filled)}")

client = LLMClient(model="qwen3.7-max")
results = list(filled.values())
n_new = 0
for i, p in enumerate(pairs):
    key = p["name"] + str(p.get("rec_a", {}).get("stock_code", ""))
    if key in filled:
        continue
    ra, rb = p["rec_a"], p["rec_b"]
    prompt = (
        f"判断两条记录是否同一自然人。中国人名重名率高，保守判断。\n"
        f"姓名:{p['name']}\n"
        f"A:公司{ra.get('stock_code','')},职务={ra.get('title','')},日期={ra.get('valid_from','')}\n"
        f"B:公司{rb.get('stock_code','')},职务={rb.get('title','')},日期={rb.get('valid_from','')}\n"
        f'输出JSON: {{"same_person":true/false,"reason":""}}'
    )
    try:
        obj = client.chat_json([{"role": "user", "content": prompt}], schema_keys=["same_person", "reason"])
        p["same_person"] = bool(obj.get("same_person", False))
    except:
        p["same_person"] = False
    results.append(p)
    n_new += 1
    print(f"  [{len(filled)+n_new}/{len(pairs)}] {p['name'][:8]} -> {p['same_person']}", flush=True)
    time.sleep(3)
    if n_new % 10 == 0:
        with open(fpath, "a", encoding="utf-8") as f:
            for r in results[-10:]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

with open(fpath, "w", encoding="utf-8") as f:
    for r in results:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
same = sum(1 for r in results if r.get("same_person"))
print(f"\n总计: {len(results)} 对, 同一人 {same} ({same/len(results)*100:.0f}%)")
