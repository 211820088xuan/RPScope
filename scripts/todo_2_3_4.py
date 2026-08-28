"""#2 含LLM消歧完整准确率 + #3 other AI重分类 + #4 deepseek tiebreaker。"""
import sys, json, csv, time
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.llm.client import LLMClient

# ============================================================
# #2: 含LLM消歧完整准确率
# ============================================================
def t2():
    from src.disambiguate.resolver import resolve_pair
    from src.disambiguate.signals import Record, Stats
    filled = [json.loads(l) for l in Path("data/annotations/person_disambig_filled.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    client = LLMClient()  # glm-5.2
    print(f"#2: 含LLM消歧 (resolver+glm-5.2 vs model-gold qwen3.7-max)")
    tp = fp = tn = fn = 0
    llm_calls = 0
    for i, p in enumerate(filled):
        gold = p.get("same_person", False)
        ra = Record(stock_code=str(p["rec_a"].get("stock_code","")), title=p["rec_a"].get("title",""),
                    valid_from=p["rec_a"].get("valid_from",""), source=p["rec_a"].get("source",""))
        rb = Record(stock_code=str(p["rec_b"].get("stock_code","")), title=p["rec_b"].get("title",""),
                    valid_from=p["rec_b"].get("valid_from",""), source=p["rec_b"].get("source",""))
        stats = Stats(name_freq=0, name_company_count=2)
        v = resolve_pair(p["name"], ra, rb, stats, client)
        if v.used_llm: llm_calls += 1
        pred = v.same_person
        if gold and pred: tp += 1
        elif (not gold) and pred: fp += 1
        elif (not gold) and (not pred): tn += 1
        else: fn += 1
        if (i+1) % 10 == 0:
            n = i+1; acc = (tp+tn)/n
            print(f"  [{i+1}/{len(filled)}] acc={acc*100:.1f}% llm={llm_calls}", flush=True)
    n = len(filled)
    acc = (tp+tn)/n
    prec = tp/(tp+fp) if (tp+fp) else 0
    rec = tp/(tp+fn) if (tp+fn) else 0
    f1 = 2*prec*rec/(prec+rec) if (prec+rec) else 0
    print(f"\n  结果: n={n} acc={acc*100:.1f}% P={prec*100:.1f}% R={rec*100:.1f}% F1={f1*100:.1f}%")
    print(f"  TP={tp} FP={fp} TN={tn} FN={fn} LLM调用={llm_calls}/{n}({llm_calls/n*100:.0f}%)")
    print(f"  对照: rule-only=55.6% | 银标(调优后)=93.3% | 本次含LLM={acc*100:.1f}%")

# ============================================================
# #3: other 30条 AI重分类
# ============================================================
def t3():
    csv_path = Path("data/reviews/other_sample.csv")
    if not csv_path.exists():
        print("#3: 无 other_sample.csv"); return
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    # 已有的 qwen3.7-max 标注
    filled = {}
    fpath = Path("data/reviews/other_sample_filled.csv")
    if fpath.exists():
        for r in csv.DictReader(open(fpath, encoding="utf-8-sig")):
            if r.get("human_scope_class"): filled[r["party_name"]] = r["human_scope_class"]
    
    client = LLMClient(model="qwen3.7-max")
    print(f"#3: other 30条 AI重分类 (qwen3.7-max, 已完成{len(filled)})")
    results = []
    for i, r in enumerate(rows):
        if r["party_name"] in filled:
            r["human_scope_class"] = filled[r["party_name"]]
            results.append(r); continue
        prompt = f"""判断该关联方属于系统能力范围内还是外:
- upstream: 控股股东/实控人/5%以上股东/董监高/同一控制兄弟公司/关键管理人员
- downstream: 子公司/联营/合营/参股/分公司
- other: 无法判定

名称: {r['party_name']}
关系描述: {r['relation_desc']}
输出JSON: {{"scope":"upstream|downstream|other","reason":""}}"""
        try:
            obj = client.chat_json([{"role":"user","content":prompt}], schema_keys=["scope","reason"])
            r["human_scope_class"] = obj.get("scope","")
        except: r["human_scope_class"] = ""
        print(f"  [{i+1}/{len(rows)}] {r['party_name'][:15]} -> {r['human_scope_class']}", flush=True)
        time.sleep(2)
        results.append(r)
    out = Path("data/reviews/other_sample_filled.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader(); w.writerows(results)
    c = Counter(r["human_scope_class"] for r in results if r["human_scope_class"])
    print(f"  统计: {dict(c)}")

# ============================================================
# #4: 53条分歧 deepseek tiebreaker
# ============================================================
def t4():
    # 读两模型 T1 结果, 找分歧
    max_f = {r["party_name"]: r for r in csv.DictReader(open("data/reviews/system_only_review_filled.csv", encoding="utf-8-sig"))}
    plus_f = {r["party_name"]: r["human_class"] for r in csv.DictReader(open("data/reviews/system_only_review_qwenplus.csv", encoding="utf-8-sig")) if r.get("human_class")}
    disagreements = []
    for nm, r in max_f.items():
        pc = plus_f.get(nm, "")
        if r.get("human_class") and pc and r["human_class"] != pc:
            disagreements.append({"party_name": nm, "max_class": r["human_class"], "plus_class": pc,
                                   "subject_name": r.get("subject_name",""), "rule_id": r.get("rule_id",""),
                                   "path": r.get("path_readable",""), "evidence": r.get("evidence",""),
                                   "gold_parties": r.get("gold_parties_of_subject","")})
    # T3 消歧分歧
    max_t3 = {}
    if Path("data/annotations/person_disambig_filled.jsonl").exists():
        for l in Path("data/annotations/person_disambig_filled.jsonl").read_text(encoding="utf-8").splitlines():
            if l.strip():
                o = json.loads(l); max_t3[o["name"]] = o.get("same_person")
    plus_t3 = {}
    p3path = Path("data/annotations/person_disambig_qwenplus.jsonl")
    if p3path.exists():
        for l in p3path.read_text(encoding="utf-8").splitlines():
            if l.strip():
                o = json.loads(l); plus_t3[o["name"]] = o.get("same_person")
    t3_disagree = [(n, max_t3[n], plus_t3[n]) for n in max_t3 if n in plus_t3 and max_t3[n] != plus_t3[n]]
    
    total_dis = len(disagreements) + len(t3_disagree)
    print(f"#4: {len(disagreements)} T1分歧 + {len(t3_disagree)} T3分歧 = {total_dis} 条, 用deepseek-v4-flash-0731 tiebreaker")
    
    ds = LLMClient(model="deepseek-v4-flash-0731")
    
    # T1 分歧
    t1_resolved = []
    for d in disagreements:
        prompt = f"""你是独立裁判。判断该关联方候选属于哪类:
- true_omission: 按上市规则确实构成关联人且年报未列示
- reasonable_undisclosed: 关系存在但不满足披露实质标准
- system_error: 路径不成立(重名/通道/时点错配/名称对齐失败)

主体:{d['subject_name']} 关联方:{d['party_name']} 规则:{d['rule_id']}
路径:{d['path'][:100]}
证据:{d['evidence'][:100]}
该公司年报已披露upstream关联方:{d['gold_parties'][:100]}
输出JSON: {{"class":"","reason":""}}"""
        try:
            obj = ds.chat_json([{"role":"user","content":prompt}], schema_keys=["class","reason"])
            d["deepseek_class"] = obj.get("class","")
            d["deepseek_reason"] = obj.get("reason","")
        except:
            d["deepseek_class"] = ""; d["deepseek_reason"] = ""
        print(f"  T1: {d['party_name'][:12]} max={d['max_class'][:8]} plus={d['plus_class'][:8]} ds={d['deepseek_class']}", flush=True)
        t1_resolved.append(d)
        time.sleep(2)
    
    # T3 分歧
    t3_resolved = []
    for name, mv, pv in t3_disagree:
        prompt = f"判断同名'{name}'在两家不同公司是否同一人。A说{'同人' if mv else '不同人'}, B说{'同人' if pv else '不同人'}。保守判断。输出JSON: {{\"same_person\":true/false,\"reason\":\"\"}}"
        try:
            obj = ds.chat_json([{"role":"user","content":prompt}], schema_keys=["same_person","reason"])
            ds_judge = bool(obj.get("same_person", False))
        except:
            ds_judge = False
        print(f"  T3: {name[:10]} max={'T' if mv else 'F'} plus={'T' if pv else 'F'} ds={'T' if ds_judge else 'F'}", flush=True)
        t3_resolved.append({"name": name, "max": mv, "plus": pv, "deepseek": ds_judge})
        time.sleep(2)
    
    # 统计: 三模型多数表决
    t1_majority = 0; t1_no_majority = 0
    for d in t1_resolved:
        votes = [d["max_class"], d["plus_class"], d["deepseek_class"]]
        c = Counter(votes)
        top = c.most_common(1)[0]
        if top[1] >= 2: t1_majority += 1
        else: t1_no_majority += 1
    t3_majority = 0; t3_no_majority = 0
    for t in t3_resolved:
        votes = [t["max"], t["plus"], t["deepseek"]]
        c = Counter(votes)
        top = c.most_common(1)[0]
        if top[1] >= 2: t3_majority += 1
        else: t3_no_majority += 1
    print(f"\n  T1: 多数表决一致 {t1_majority}/{len(t1_resolved)}, 三方各不同 {t1_no_majority}")
    print(f"  T3: 多数表决一致 {t3_majority}/{len(t3_resolved)}, 三方各不同 {t3_no_majority}")
    
    # 保存
    out = Path("data/reviews/tiebreaker_results.json")
    out.write_text(json.dumps({"t1": t1_resolved, "t3": t3_resolved}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  结果 -> {out}")

if __name__ == "__main__":
    print("=== #2: 含LLM消歧 ==="); t2()
    print("\n=== #3: other AI重分类 ==="); t3()
    print("\n=== #4: deepseek tiebreaker ==="); t4()
    print("\n完成 #2 + #3 + #4")
