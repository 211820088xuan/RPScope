"""用 deepseek-v4-flash-0731 独立填写三份材料, 再与 qwen3.7-max 结果交叉对比。

两模型一致=高置信; 不一致=需真正人工看。
"""
import csv, json, sys, time
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.llm.client import LLMClient

JUDGE2 = "qwen3.7-plus"
llm = LLMClient(model=JUDGE2)
print(f"第二裁判: {JUDGE2} enabled={llm.enabled}")

# 复用 model_review 的 prompt 逻辑, 写到 _deepseek 文件
def t1_cross():
    csv_path = Path("data/reviews/system_only_review.csv")
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    out = Path("data/reviews/system_only_review_qwenplus.csv")
    done = {}
    if out.exists():
        for r in csv.DictReader(open(out, encoding="utf-8-sig")):
            if r.get("human_class"): done[r["party_name"]] = r["human_class"]
    for i, r in enumerate(rows):
        if r["party_name"] in done:
            r["human_class"] = done[r["party_name"]]; continue
        prompt = f"""判断该关联方候选属于哪类:
- true_omission: 按上市规则确实构成关联人且年报未列示
- reasonable_undisclosed: 关系存在但不满足披露实质标准(比例低/独董/超12个月)
- system_error: 路径不成立(重名/通道/时点错配/名称对齐失败)

主体:{r['subject_name']}({r['subject_code']}) 关联方:{r['party_name']} 规则:{r['rule_id']} 置信度:{r['confidence']}
路径:{r['path_readable']}
证据:{r['evidence']}
该公司年报已披露upstream关联方:{r['gold_parties_of_subject']}
名称变体:{r['name_variants']}
输出JSON:{{"class":"","reason":""}}"""
        try:
            obj = llm.chat_json([{"role":"user","content":prompt}], schema_keys=["class","reason"])
            r["human_class"] = obj.get("class","")
        except: r["human_class"] = ""
        print(f"  [{i+1}/{len(rows)}] {r['party_name'][:12]} -> {r['human_class']}", flush=True)
        with open(out,"w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
        time.sleep(0.5)

def t3_cross():
    ann = Path("data/annotations/person_disambig.jsonl")
    pairs = [json.loads(l) for l in ann.read_text(encoding="utf-8").splitlines() if l.strip()]
    out = Path("data/annotations/person_disambig_qwenplus.jsonl")
    done = set()
    if out.exists():
        for l in out.read_text(encoding="utf-8").splitlines():
            if l.strip(): done.add(json.loads(l)["name"])
    for i, p in enumerate(pairs):
        if p["name"] in done: continue
        ra, rb = p["rec_a"], p["rec_b"]
        prompt = f"""判断两条记录是否同一自然人。中国人名重名率高。
姓名:{p['name']}
A:公司{ra.get('stock_code','')},职务={ra.get('title','')},日期={ra.get('valid_from','')}
B:公司{rb.get('stock_code','')},职务={rb.get('title','')},日期={rb.get('valid_from','')}
输出JSON:{{"same_person":true/false,"reason":""}}"""
        try:
            obj = llm.chat_json([{"role":"user","content":prompt}], schema_keys=["same_person","reason"])
            p["same_person"] = bool(obj.get("same_person",False))
        except: p["same_person"] = False
        print(f"  [{i+1}/{len(pairs)}] {p['name']} -> {p['same_person']}", flush=True)
        with open(out,"a",encoding="utf-8") as f: f.write(json.dumps(p,ensure_ascii=False)+"\n")
        time.sleep(0.5)

def compare():
    """交叉对比 qwen3.7-max vs deepseek。"""
    print("\n=== 交叉对比 ===")
    # T1
    qf = list(csv.DictReader(open("data/reviews/system_only_review_filled.csv",encoding="utf-8-sig")))
    df = {r["party_name"]:r["human_class"] for r in csv.DictReader(open("data/reviews/system_only_review_qwenplus.csv",encoding="utf-8-sig"))}
    agree=disagree=0; dis_items=[]
    for r in qf:
        q=r["human_class"]; d=df.get(r["party_name"],"")
        if q and d:
            if q==d: agree+=1
            else: disagree+=1; dis_items.append((r["party_name"][:15],q,d))
    print(f"T1 核查表: 一致 {agree}, 不一致 {disagree}")
    for nm,q,d in dis_items[:10]: print(f"  {nm}: qwen={q} ds={d}")
    # T3
    qp={json.loads(l)["name"]:json.loads(l).get("same_person") for l in open("data/annotations/person_disambig_filled.jsonl",encoding="utf-8") if l.strip()}
    dp={}
    if Path("data/annotations/person_disambig_qwenplus.jsonl").exists():
        dp={json.loads(l)["name"]:json.loads(l).get("same_person") for l in open("data/annotations/person_disambig_qwenplus.jsonl",encoding="utf-8") if l.strip()}
    a=d=0; dis3=[]
    for name in qp:
        if name in dp:
            if qp[name]==dp[name]: a+=1
            else: d+=1; dis3.append((name,qp[name],dp[name]))
    print(f"T3 消歧: 一致 {a}, 不一致 {d}")
    for nm,q,ds in dis3[:10]: print(f"  {nm}: qwen={q} ds={ds}")

if __name__=="__main__":
    print("=== T1(deepseek) ==="); t1_cross()
    print("\n=== T3(deepseek) ==="); t3_cross()
    compare()
