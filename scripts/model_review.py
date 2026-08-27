"""用 qwen3.7-max(独立模型) 填写三份核查材料。

与系统 LLM(glm-5.2) 不同家族, 作半独立裁判。
结果标注"模型标注(qwen3.7-max)", 非人工金标准。
增量写盘, 可中断续跑。
"""
import csv, json, sys, time
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.llm.client import LLMClient
from src.store.db import Store

JUDGE = "qwen3.7-max"
llm = LLMClient(model=JUDGE)
print(f"裁判模型: {JUDGE} enabled={llm.enabled}")

# ============================================================
# T1: 28 条核查表 human_class
# ============================================================
def t1():
    csv_path = Path("data/reviews/system_only_review.csv")
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    out_path = Path("data/reviews/system_only_review_filled.csv")
    done = {}
    if out_path.exists():
        for r in csv.DictReader(open(out_path, encoding="utf-8-sig")):
            if r.get("human_class"):
                done[r["party_name"]] = r["human_class"]
    print(f"T1: {len(rows)} 条, 已完成 {len(done)}")
    for i, r in enumerate(rows):
        if r["party_name"] in done:
            r["human_class"] = done[r["party_name"]]; continue
        prompt = f"""你是关联方核查员。基于以下信息判断该候选属于哪类:

判定标准:
- true_omission: 按上市规则确实构成关联人(同一实控人兄弟公司/董监高兼任等), 且该公司年报关联方章节未列示
- reasonable_undisclosed: 关系存在但不满足披露实质标准(控制比例低/独立董事/超出12个月窗口/纯供应链)
- system_error: 路径不成立(实控人识别错/人名重名/通道未排/时点错配/名称对齐失败)

候选信息:
- 主体: {r['subject_name']}({r['subject_code']})
- 关联方: {r['party_name']}
- 规则: {r['rule_id']}
- 置信度: {r['confidence']}
- 路径: {r['path_readable']}
- 证据: {r['evidence']}
- 该公司年报已披露的upstream关联方: {r['gold_parties_of_subject']}
- 名称变体: {r['name_variants']}

输出JSON: {{"class":"true_omission|reasonable_undisclosed|system_error","reason":"一句话"}}"""
        try:
            obj = llm.chat_json([{"role":"user","content":prompt}], schema_keys=["class","reason"])
            r["human_class"] = obj.get("class","")
            r["human_note"] = obj.get("reason","")
        except Exception as e:
            r["human_class"] = ""; r["human_note"] = f"error:{e}"
        print(f"  [{i+1}/{len(rows)}] {r['party_name'][:15]} -> {r['human_class']}", flush=True)
        # 增量写
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader(); w.writerows(rows)
        time.sleep(1)
    c = Counter(r["human_class"] for r in rows if r["human_class"])
    print(f"  统计: {dict(c)}")


# ============================================================
# T2: 30 条 other_sample human_scope_class
# ============================================================
def t2():
    csv_path = Path("data/reviews/other_sample.csv")
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    done = {}
    out_path = Path("data/reviews/other_sample_filled.csv")
    if out_path.exists():
        for r in csv.DictReader(open(out_path, encoding="utf-8-sig")):
            if r.get("human_scope_class"):
                done[r["party_name"]] = r["human_scope_class"]
    print(f"T2: {len(rows)} 条, 已完成 {len(done)}")
    for i, r in enumerate(rows):
        if r["party_name"] in done:
            r["human_scope_class"] = done[r["party_name"]]; continue
        prompt = f"""判断该关联方属于系统能力范围内还是外:
- upstream: 控股股东/实控人/5%以上股东/董监高/同一控制下的兄弟公司/关键管理人员
- downstream: 子公司/联营/合营/参股/分公司
- other: 无法从名称和描述判定

名称: {r['party_name']}
关系描述: {r['relation_desc']}

输出JSON: {{"scope":"upstream|downstream|other","reason":"一句话"}}"""
        try:
            obj = llm.chat_json([{"role":"user","content":prompt}], schema_keys=["scope","reason"])
            r["human_scope_class"] = obj.get("scope","")
        except Exception as e:
            r["human_scope_class"] = ""
        print(f"  [{i+1}/{len(rows)}] {r['party_name'][:15]} -> {r['human_scope_class']}", flush=True)
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader(); w.writerows(rows)
        time.sleep(1)
    c = Counter(r["human_scope_class"] for r in rows if r["human_scope_class"])
    print(f"  统计: {dict(c)}")

# ============================================================
# T3: 90 对消歧 same_person
# ============================================================
def t3():
    ann_path = Path("data/annotations/person_disambig.jsonl")
    if not ann_path.exists():
        print("T3: 无标注集"); return
    pairs = [json.loads(l) for l in ann_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    out_path = Path("data/annotations/person_disambig_filled.jsonl")
    done = set()
    if out_path.exists():
        for l in out_path.read_text(encoding="utf-8").splitlines():
            if l.strip():
                o = json.loads(l); done.add(o["name"]+str(o.get("rec_a",{}).get("stock_code","")))
    print(f"T3: {len(pairs)} 对, 已完成 {len(done)}")
    results = []
    for i, p in enumerate(pairs):
        key = p["name"]+str(p.get("rec_a",{}).get("stock_code",""))
        if key in done:
            continue
        ra, rb = p["rec_a"], p["rec_b"]
        prompt = f"""判断两条记录是否为同一自然人。中国人名重名率高, 保守判断。

姓名: {p['name']}
记录A: 公司{ra.get('stock_code','')}, 职务={ra.get('title','')}, 日期={ra.get('valid_from','')}, 来源={ra.get('source','')}
记录B: 公司{rb.get('stock_code','')}, 职务={rb.get('title','')}, 日期={rb.get('valid_from','')}, 来源={rb.get('source','')}

输出JSON: {{"same_person":true/false,"reason":"一句话"}}"""
        try:
            obj = llm.chat_json([{"role":"user","content":prompt}], schema_keys=["same_person","reason"])
            p["same_person"] = bool(obj.get("same_person", False))
            p["judge_reason"] = obj.get("reason","")
        except Exception as e:
            p["same_person"] = False; p["judge_reason"] = f"error:{e}"
        print(f"  [{i+1}/{len(pairs)}] {p['name']} -> {p['same_person']}", flush=True)
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(p, ensure_ascii=False)+"\n")
        time.sleep(1)
    # 统计
    all_p = [json.loads(l) for l in out_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    same = sum(1 for p in all_p if p.get("same_person"))
    print(f"  统计: 同一人 {same}/{len(all_p)}")

if __name__ == "__main__":
    print("=== T1: 核查表 ==="); t1()
    print("\n=== T2: other分类 ==="); t2()
    print("\n=== T3: 消歧 ==="); t3()
    print("\n完成(模型标注 qwen3.7-max, 非人工金标准)")
