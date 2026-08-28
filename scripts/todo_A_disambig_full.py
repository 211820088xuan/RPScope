"""A: 消歧完整准确率 - 续跑剩余50/90对, 增量保存。"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.disambiguate.resolver import resolve_pair
from src.disambiguate.signals import Record, Stats
from src.llm.client import LLMClient
from src.normalize.name import normalize_name, org_match_key

filled = [json.loads(l) for l in Path("data/annotations/person_disambig_filled.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
client = LLMClient()  # glm-5.2

# 增量结果文件
out_path = Path("data/annotations/disambig_acc_results.jsonl")
done = set()
if out_path.exists():
    for l in out_path.read_text(encoding="utf-8").splitlines():
        if l.strip():
            o = json.loads(l)
            done.add(o["name"] + str(o.get("rec_a",{}).get("stock_code","")))

print(f"A: 消歧完整准确率 (已完成 {len(done)}/{len(filled)})")
tp = fp = tn = fn = 0
llm_calls = 0
results = []
for i, p in enumerate(filled):
    key = p["name"] + str(p.get("rec_a",{}).get("stock_code",""))
    if key in done:
        # 读已有结果
        for l in out_path.read_text(encoding="utf-8").splitlines():
            if l.strip():
                o = json.loads(l)
                if o["name"]+str(o.get("rec_a",{}).get("stock_code","")) == key:
                    gold = o.get("gold", False)
                    pred = o.get("pred", False)
                    if o.get("used_llm"): llm_calls += 1
                    if gold and pred: tp += 1
                    elif (not gold) and pred: fp += 1
                    elif (not gold) and (not pred): tn += 1
                    else: fn += 1
                    results.append(o)
                    break
        continue

    gold = p.get("same_person", False)
    ra = Record(stock_code=str(p["rec_a"].get("stock_code","")), title=p["rec_a"].get("title",""),
                valid_from=p["rec_a"].get("valid_from",""), source=p["rec_a"].get("source",""))
    rb = Record(stock_code=str(p["rec_b"].get("stock_code","")), title=p["rec_b"].get("title",""),
                valid_from=p["rec_b"].get("valid_from",""), source=p["rec_b"].get("source",""))
    stats = Stats(name_freq=0, name_company_count=2)
    v = resolve_pair(p["name"], ra, rb, stats, client)
    pred = v.same_person
    if v.used_llm: llm_calls += 1
    if gold and pred: tp += 1
    elif (not gold) and pred: fp += 1
    elif (not gold) and (not pred): tn += 1
    else: fn += 1

    result = {"name": p["name"], "rec_a": p["rec_a"], "gold": gold, "pred": pred,
              "used_llm": v.used_llm, "score": v.score, "confidence": v.confidence}
    results.append(result)
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    n = i + 1
    acc = (tp + tn) / n if n else 0
    print(f"  [{n}/{len(filled)}] {p['name'][:8]} gold={gold} pred={pred} llm={v.used_llm} acc={acc*100:.1f}%", flush=True)
    time.sleep(1)

n = len(results)
acc = (tp + tn) / n if n else 0
prec = tp / (tp + fp) if (tp + fp) else 0
rec = tp / (tp + fn) if (tp + fn) else 0
f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
print(f"\n=== A: 消歧完整准确率 (n={n}) ===")
print(f"  accuracy={acc*100:.1f}% P={prec*100:.1f}% R={rec*100:.1f}% F1={f1*100:.1f}%")
print(f"  TP={tp} FP={fp} TN={tn} FN={fn} LLM={llm_calls}/{n}({llm_calls/n*100:.0f}%)")
print(f"  对照: rule-only=55.6% | 银标(调优后)=93.3%")
