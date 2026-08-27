"""#1 标记53条分歧 + #2 消歧model-gold准确率 + #3 other重分类recall影响。"""
import csv, json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ============================================================
# #1: 标记 T1 核查表两模型分歧
# ============================================================
def t1_flag_disagreements():
    qf = {r["party_name"]: r for r in csv.DictReader(open("data/reviews/system_only_review_filled.csv", encoding="utf-8-sig"))}
    pp = {r["party_name"]: r["human_class"] for r in csv.DictReader(open("data/reviews/system_only_review_qwenplus.csv", encoding="utf-8-sig")) if r.get("human_class")}
    # 写回 filled CSV 加 cross_check 列
    out = Path("data/reviews/system_only_review_final.csv")
    fields = list(qf[list(qf)[0]].keys()) + ["cross_check", "plus_class"]
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        agree = disagree = 0
        for nm, r in qf.items():
            pc = pp.get(nm, "")
            if r.get("human_class") and pc:
                if r["human_class"] == pc:
                    r["cross_check"] = "agree"; agree += 1
                else:
                    r["cross_check"] = "DISAGREE"; disagree += 1
            else:
                r["cross_check"] = ""
            r["plus_class"] = pc
            w.writerow(r)
    print(f"#1: {agree} 一致 + {disagree} 分歧 = {agree+disagree} 总计 -> {out}")
    # 列出分歧
    for nm, r in qf.items():
        pc = pp.get(nm, "")
        if r.get("human_class") and pc and r["human_class"] != pc:
            print(f"  分歧: {nm[:15]:17} max={r['human_class']:25} plus={pc}")

# ============================================================
# #2: 消歧 model-gold 准确率
# ============================================================
def t2_disambig_gold():
    # 用 qwen3.7-max 标的 person_disambig_filled.jsonl 作 "model-gold"
    # 与 resolver 的预测(银标)对照
    from src.disambiguate.resolver import resolve_pair
    from src.disambiguate.signals import Record, Stats
    from src.llm.client import LLMClient
    filled = [json.loads(l) for l in Path("data/annotations/person_disambig_filled.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    client = LLMClient()  # glm-5.2 (系统 LLM, 作 resolver 的 LLM 兜底)
    tp = fp = tn = fn = 0
    for p in filled:
        gold = p.get("same_person", False)
        ra = Record(stock_code=str(p["rec_a"].get("stock_code","")), title=p["rec_a"].get("title",""),
                    valid_from=p["rec_a"].get("valid_from",""), source=p["rec_a"].get("source",""))
        rb = Record(stock_code=str(p["rec_b"].get("stock_code","")), title=p["rec_b"].get("title",""),
                    valid_from=p["rec_b"].get("valid_from",""), source=p["rec_b"].get("source",""))
        # resolver 用 glm-5.2 (与银标一致), stats 简化
        stats = Stats(name_freq=0, name_company_count=2)
        v = resolve_pair(p["name"], ra, rb, stats, client)
        pred = v.same_person
        if gold and pred: tp += 1
        elif (not gold) and pred: fp += 1
        elif (not gold) and (not pred): tn += 1
        else: fn += 1
    n = len(filled)
    acc = (tp + tn) / n if n else 0
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    print(f"\n#2: 消歧 model-gold(qwen3.7-max标注) vs resolver(glm-5.2)")
    print(f"  n={n} acc={acc*100:.1f}% P={prec*100:.1f}% R={rec*100:.1f}%")
    print(f"  TP={tp} FP={fp} TN={tn} FN={fn}")
    print(f"  对照: 之前银标(调优后) 93.3%")

# ============================================================
# #3: other 重分类 recall 影响
# ============================================================
def t3_other_recall_impact():
    # T2: 30条other sample中 8条=upstream(27%)
    # 607条other * 27% = ~164条可能是upstream
    # 可比口径 gold = 558 upstream
    # 如果 +164 = 722 upstream, recall分母变大
    base_matched = 14; base_gold = 558
    base_recall = base_matched / base_gold
    est_upstream_in_other = int(607 * 8 / 30)
    new_gold = base_gold + est_upstream_in_other
    new_recall = base_matched / new_gold  # matched 不变(系统候选不变)
    print(f"\n#3: other 重分类 recall 影响")
    print(f"  T2样本: 30条中 8条=upstream(27%)")
    print(f"  607条other * 27% = ~{est_upstream_in_other}条可能实为upstream")
    print(f"  当前可比口径: gold={base_gold}, matched={base_matched}, recall={base_recall*100:.1f}%")
    print(f"  若+{est_upstream_in_other}: gold={new_gold}, recall={new_recall*100:.1f}%")
    print(f"  recall变化: {(new_recall-base_recall)*100:+.1f}pp (被低估)")

if __name__ == "__main__":
    print("=== #1: 53条分歧标记 ===")
    t1_flag_disagreements()
    print("\n=== #2: 消歧model-gold ===")
    t2_disambig_gold()
    print("\n=== #3: other重分类recall影响 ===")
    t3_other_recall_impact()
