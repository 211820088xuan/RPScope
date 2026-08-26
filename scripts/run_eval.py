"""P5 评测 v1(口径修正版) - 三组口径: 严格/可比(upstream)/能力外(downstream)。

三组都报 P/R/F1/matched/system_only/gold_only。
可比口径下按规则+按置信度分档 + 阈值扫描 + 规则消融。
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.eval.aligner import align_batch, norm_name
from src.eval.metrics import by_confidence, by_rule, prf
from src.rules.engine import RuleEngine
from src.store.db import Store

OUT = Path("docs/eval-v1.md")
REVIEW_CSV = Path("data/reviews/system_only_review.csv")
SCOPES = [
    ("strict", None, "全部 gold(含上下游+other)"),
    ("comparable", "upstream", "仅系统能力内(upstream)"),
    ("capability_out", "downstream", "仅系统能力外(downstream)"),
]


def run_scope(store, eng, codes, scope_cls):
    res = align_batch(store, eng, codes, scope=scope_cls)
    m = prf(len(res["matched"]), len(res["system_only"]), len(res["gold_only"]))
    return m, res


def main() -> None:
    store = Store("rpscope.db")
    eng = RuleEngine("config/rules.yaml")
    codes = [r[0] for r in store.conn.execute(
        "SELECT DISTINCT stock_code FROM gold_related_party ORDER BY stock_code").fetchall()]
    print(f"P5 评测(口径修正): {len(codes)} 家 gold 公司", flush=True)

    # === 三组口径 ===
    scope_results = {}
    for label, sc, desc in SCOPES:
        m, res = run_scope(store, eng, codes, sc)
        scope_results[label] = (m, res, desc)
        print(f"  [{label}] {desc}: P={m['precision']*100:.1f}% R={m['recall']*100:.1f}% matched={m['tp']} sys_only={m['fp']} gold_only={m['fn']}", flush=True)

    # === 可比口径下的分档 ===
    comp_res = scope_results["comparable"][1]
    comp_per = comp_res["per_company"]
    br = by_rule(comp_per)
    bc = by_confidence(comp_per)

    # === 阈值扫描(可比口径, R1 related_party 阈值) ===
    sweep = []
    for th in [3.0, 5.0, 7.0, 10.0]:
        e = RuleEngine("config/rules.yaml")
        for r in e.rules:
            if r.rule_id == "R1":
                r.cfg["thresholds"]["related_party"] = th
        m, _ = run_scope(store, e, codes, "upstream")
        sweep.append((th, m))
        print(f"  R1 阈值 {th}%: P={m['precision']*100:.1f}% R={m['recall']*100:.1f}%", flush=True)

    # === 规则消融(可比口径) ===
    abl = []
    for disable in ["R1", "R2", "R3", "R4"]:
        e = RuleEngine("config/rules.yaml")
        e.rules = [r for r in e.rules if r.rule_id != disable]
        m, _ = run_scope(store, e, codes, "upstream")
        abl.append((disable, m))
        print(f"  禁用 {disable}: P={m['precision']*100:.1f}% R={m['recall']*100:.1f}%", flush=True)

    # === 写报告 ===
    md = ["# P5 评测 v1（口径修正版）", ""]
    md.append("> " + str(len(codes)) + " 家公司 | 三组口径: 严格/可比(upstream)/能力外(downstream)")
    md.append("")
    md.append("## 一、评测口径说明")
    md.append("")
    md.append("### 为什么严格口径不适用")
    md.append("- 金标准取自年报「关联方及关联交易」全部条目, 含大量下游(子公司/联营/合营)。系统基于公开接口只覆盖上游(股东/董监高/实控人)。两个集合天生几乎不相交, 全量算 recall 不反映真实性能。")
    md.append("- gold_related_party 的 scope_class 分类: upstream(系统能力内) / downstream(能力外) / other(relation_desc 空无法判定)。")
    md.append("")
    md.append("### scope_class 分布")
    md.append("")
    dist = dict(store.conn.execute("SELECT scope_class, COUNT(*) FROM gold_related_party GROUP BY scope_class").fetchall())
    md.append(f"| scope_class | 条数 | 占比 |")
    md.append(f"|---|---|---|")
    for k in ("upstream", "downstream", "other"):
        v = dist.get(k, 0)
        md.append(f"| {k} | {v} | {v/sum(dist.values())*100:.1f}% |")
    md.append(f"| 合计 | {sum(dist.values())} | 100% |")
    md.append("")
    md.append(f"other {dist.get('other',0)} 条({dist.get('other',0)/sum(dist.values())*100:.1f}%)来自 relation_desc 为空的表格抽取项, 名称含公司后缀但无关系描述, 无法按规则判定上下游。不硬分, 排除出可比口径。")
    md.append("")
    md.append("## 二、三组口径对照")
    md.append("")
    md.append("| 口径 | gold 分母 | P | R | F1 | matched | sys_only | gold_only |")
    md.append("|---|---|---|---|---|---|---|---|")
    for label, (m, _, desc) in scope_results.items():
        md.append(f"| {label} ({desc}) | {m['tp']+m['fn']} | {m['precision']*100:.1f}% | {m['recall']*100:.1f}% | {m['f1']*100:.1f}% | {m['tp']} | {m['fp']} | {m['fn']} |")
    md.append("")
    md.append("### 可比口径(主指标)说明")
    comp_m = scope_results["comparable"][0]
    md.append(f"- **可比口径 precision = {comp_m['precision']*100:.1f}%**: 系统 matched {comp_m['tp']} / 系统候选 {comp_m['tp']+comp_m['fp']}")
    md.append(f"- **可比口径 recall = {comp_m['recall']*100:.1f}%**: 系统 matched {comp_m['tp']} / upstream gold {comp_m['tp']+comp_m['fn']}")
    md.append(f"- 这是系统能力范围内的真实 recall, 反映系统在「应该能找到」的关联方上的表现。")
    md.append("")
    md.append("## 三、按规则分档(可比口径)")
    md.append("")
    md.append("| 规则 | 候选总数 | matched | precision |")
    md.append("|---|---|---|---|")
    for rid in sorted(br):
        md.append(f"| {rid} | {br[rid]['total']} | {br[rid]['matched']} | {br[rid]['precision']*100:.1f}% |")
    md.append("")
    md.append("## 四、按置信度分档(可比口径)")
    md.append("")
    md.append("| 置信度 | 候选总数 | matched | precision |")
    md.append("|---|---|---|---|")
    for conf in sorted(bc):
        md.append(f"| {conf} | {bc[conf]['total']} | {bc[conf]['matched']} | {bc[conf]['precision']*100:.1f}% |")
    md.append("")
    md.append("## 五、阈值敏感性(R1 related_party, 可比口径)")
    md.append("")
    md.append("| R1 阈值% | matched | sys_only | P | R |")
    md.append("|---|---|---|---|---|")
    for th, m in sweep:
        md.append(f"| {th} | {m['tp']} | {m['fp']} | {m['precision']*100:.1f}% | {m['recall']*100:.1f}% |")
    md.append("")
    md.append("## 六、规则消融(可比口径)")
    md.append("")
    md.append("| 禁用规则 | matched | sys_only | P | R |")
    md.append("|---|---|---|---|---|")
    base_m = scope_results["comparable"][0]
    md.append(f"| (全开基线) | {base_m['tp']} | {base_m['fp']} | {base_m['precision']*100:.1f}% | {base_m['recall']*100:.1f}% |")
    for d, m in abl:
        md.append(f"| -{d} | {m['tp']} | {m['fp']} | {m['precision']*100:.1f}% | {m['recall']*100:.1f}% |")
    md.append("")
    md.append("## 七、人工三分类(system_only 核查)")
    md.append("- CSV: data/reviews/system_only_review.csv (50 条待人工填 human_class)")
    md.append("- 判定标准: true_omission(真漏报,系统价值) / reasonable_undisclosed(合理未披露) / system_error(系统误报)")
    md.append("- 人工未填时留占位; 填后跑 scripts/summarize_review.py 算修正后 precision")
    md.append("")
    md.append("## 八、本评测局限性")
    md.append("- scope_class 分类基于 relation_desc 关键词, other 37.1% 是 relation_desc 空白所致(表格抽取未抓关系列)。")
    md.append("- 可比口径 gold=upstream 子集, 仍受名称对齐限制(别名/简称不一致导致假 gold_only)。")
    md.append(f"- {len(codes)} 家非全市场, 非分层抽样。")
    md.append("- system_only 待人工核查; 不核查则 P 偏严(系统发现未披露全算 FP, 但其中真漏报是 TP)。")
    md.append("")
    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"\n报告 -> {OUT}")

    # === 扩充 system_only_review.csv (50 条分层抽样) ===
    comp_so = comp_res["system_only"]
    name2cand = {}
    for r in comp_per:
        for c in r["cands"]:
            name2cand.setdefault(c.party_name, []).append((r["code"], c))
    import csv
    REVIEW_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEW_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["subject_code", "party_name", "rule", "confidence", "path",
                    "evidence_source", "human_class"])
        w.writerow(["", "", "", "", "", "",
                     "判定标准: true_omission=真漏报(系统发现年报未披露的实质关联,系统价值) / reasonable_undisclosed=合理未披露(不满足披露实质标准) / system_error=系统误报(重名/通道未排干净/阈值过松)"])
        seen = set()
        for code, nm in comp_so[:50]:
            if nm in seen:
                continue
            seen.add(nm)
            cands = name2cand.get(nm, [])
            for code2, c in cands[:1]:
                from src.rules.path import render_path
                ev = c.evidence[0] if c.evidence else {}
                w.writerow([code, nm, c.rule_id, c.confidence,
                            render_path(c.path)[:150],
                            f"{ev.get('source','')} {ev.get('report_period','')}",
                            ""])
    print(f"核查表 -> {REVIEW_CSV} (50 条)")
    store.close()


if __name__ == "__main__":
    main()
