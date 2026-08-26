"""P5 评测 v1 - 在 28 家 gold 集上跑规则, 三分类对齐, P/R + 分档 + system_only 抽样核查表。

产出 docs/eval-v1.md + data/reviews/system_only_review.csv。
"""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.eval.aligner import align_batch
from src.eval.metrics import by_confidence, by_rule, prf
from src.rules.engine import RuleEngine
from src.store.db import Store

OUT_MD = Path("docs/eval-v1.md")
REVIEW_CSV = Path("data/reviews/system_only_review.csv")


def main() -> None:
    store = Store("rpscope.db")
    eng = RuleEngine("config/rules.yaml")
    codes = [r[0] for r in store.conn.execute(
        "SELECT DISTINCT stock_code FROM gold_related_party ORDER BY stock_code").fetchall()]
    print(f"P5 评测: {len(codes)} 家 gold 公司", flush=True)

    t0 = time.perf_counter()
    res = align_batch(store, eng, codes)
    dt = time.perf_counter() - t0
    per = res["per_company"]
    matched = res["matched"]; gold_only = res["gold_only"]; system_only = res["system_only"]

    m = prf(len(matched), len(system_only), len(gold_only))
    print(f"matched={m['tp']} system_only(FP)={m['fp']} gold_only(FN)={m['fn']}", flush=True)
    print(f"P={m['precision']*100:.1f}% R={m['recall']*100:.1f}% F1={m['f1']*100:.1f}%", flush=True)
    print(f"耗时 {dt:.0f}s", flush=True)

    br = by_rule(per); bc = by_confidence(per)
    md = ["# P5 评测 v1（对照年报金标准）", ""]
    md.append(f"> {len(codes)} 家公司 | 规则 R1-R7 | 对齐口径: 归一化名称")
    md.append("")
    md.append("## 一、三分类与 P/R（严格口径）")
    md.append("")
    md.append("| 指标 | 值 |")
    md.append("|---|---|")
    md.append(f"| gold 关联方(去重名) | {m['tp']+m['fn']} |")
    md.append(f"| 系统候选(去重名) | {m['tp']+m['fp']} |")
    md.append(f"| matched | {m['tp']} |")
    md.append(f"| system_only(疑似 FP, 待核查) | {m['fp']} |")
    md.append(f"| gold_only(疑似 FN, 待核查) | {m['fn']} |")
    md.append(f"| **precision** | **{m['precision']*100:.1f}%** |")
    md.append(f"| **recall** | **{m['recall']*100:.1f}%** |")
    md.append(f"| F1 | {m['f1']*100:.1f}% |")
    md.append("")
    md.append("## 二、关键解读（诚实）")
    md.append("")
    md.append("- **recall 必然低**: 年报金标准含大量下游(子公司/联营/合营), 而规则系统基于公开接口只覆盖上游(股东/董监高/实控人)。下游本就不在系统能力范围, 属'合理未披露'而非真漏报。")
    md.append("- **system_only 是系统价值所在**: 系统发现的结构性候选(共同股东/共同实控人/连锁董事)年报未披露, 三类情况:①真漏报/隐瞒(系统价值) ②不满足披露实质标准 ③系统误报。须人工核查分开。")
    md.append("- precision 口径偏严: system_only 全算 FP, 但其中'真漏报'其实是 TP, 待核查修正。")
    md.append("")
    md.append("## 三、按规则分档")
    md.append("")
    md.append("| 规则 | 候选总数 | matched | precision |")
    md.append("|---|---|---|---|")
    for rid in sorted(br):
        md.append(f"| {rid} | {br[rid]['total']} | {br[rid]['matched']} | {br[rid]['precision']*100:.1f}% |")
    md.append("")
    md.append("## 四、按置信度分档")
    md.append("")
    md.append("| 置信度 | 候选总数 | matched | precision |")
    md.append("|---|---|---|---|")
    for conf in sorted(bc):
        md.append(f"| {conf} | {bc[conf]['total']} | {bc[conf]['matched']} | {bc[conf]['precision']*100:.1f}% |")
    md.append("")
    md.append("## 五、本评测局限性")
    md.append("- 名称对齐靠归一化匹配, 别名/简称不一致会导致假 gold_only(对齐失败而非真漏报)。")
    md.append("- 28 家非全市场, 非分层抽样, 偏向深市小代码公司, 非统计代表。")
    md.append("- system_only 待人工核查(下方 CSV); 不核查则 P 偏严。")
    md.append("")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n报告 -> {OUT_MD}")

    # system_only 抽样 50 条核查表
    REVIEW_CSV.parent.mkdir(parents=True, exist_ok=True)
    so = list(system_only)[:50]
    # 给每条补路径/规则/证据(从 per_company 找)
    name2cand = {}
    for r in per:
        for c in r["cands"]:
            name2cand.setdefault(c.party_name, []).append((r["code"], c))
    with open(REVIEW_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["subject_code", "party_name", "rule", "confidence", "path",
                    "分类(真漏报/合理未披露/系统误报)"])
        for code, nm in so:
            cands = name2cand.get(nm) or []
            for code2, c in cands[:1]:
                from src.rules.path import render_path
                w.writerow([code, nm, c.rule_id, c.confidence, render_path(c.path), ""])
    print(f"核查表 -> {REVIEW_CSV} ({len(so)} 条 system_only 待人工分类)")
    store.close()


if __name__ == "__main__":
    main()
