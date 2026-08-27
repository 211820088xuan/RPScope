"""T1+T2+T3 核查材料准备 - 不填 human_class, 只组装判断所需信息。

T1: 补全 28 条核查表(CSV+MD) + data/reviews/README.md
T2: other 607条诊断 + docs/scope-class-review.md + other_sample.csv
T3: person_disambig_sheet.md(90对, 不展示预测) + eval_disambig --gold 说明
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.eval.aligner import align_batch, norm_name
from src.normalize.name import normalize_name, org_match_key
from src.rules.engine import RuleEngine
from src.rules.path import render_path
from src.store.db import Store

# ============================================================
# T1: 补全核查表
# ============================================================
def t1_enrich_review(store, eng):
    codes = [r[0] for r in store.conn.execute(
        "SELECT DISTINCT stock_code FROM gold_related_party ORDER BY stock_code").fetchall()]
    res = align_batch(store, eng, codes, scope="upstream")

    # 收集所有 system_only 候选(去重 by name, 保留完整 candidate 对象)
    seen = set()
    items = []
    for r in res["per_company"]:
        for c in r["cands"]:
            nm = norm_name(c.party_name)
            if nm in r["matched"] or nm in seen:
                continue
            seen.add(nm)
            # subject info
            sco = store.conn.execute("SELECT short_name FROM company WHERE stock_code=?", (r["code"],)).fetchone()
            sname = sco["short_name"] if sco else r["code"]
            # gold parties of this subject (upstream scope)
            gold_list = [x[0] for x in store.conn.execute(
                "SELECT party_name FROM gold_related_party WHERE stock_code=? AND scope_class='upstream'",
                (r["code"],)).fetchall()]
            # name variants
            variants = []
            if c.party_id.startswith("E:"):
                eid = c.party_id[2:]
                ent = store.conn.execute("SELECT raw_names, display_name, canonical_name FROM entity WHERE entity_id=?", (eid,)).fetchone()
                if ent and ent["raw_names"]:
                    variants = json.loads(ent["raw_names"])
                if ent and ent["display_name"] and ent["display_name"] not in variants:
                    variants.append(ent["display_name"])
            elif c.party_id.startswith("C:"):
                co = store.conn.execute("SELECT short_name, full_name FROM company WHERE stock_code=?", (c.party_id[2:],)).fetchone()
                if co:
                    variants = [co["short_name"]] + ([co["full_name"]] if co["full_name"] else [])
            # evidence format
            ev_strs = []
            for e in c.evidence[:3]:
                ev_strs.append(f"{e.get('table','?')}#{e.get('pk','?')} src={e.get('source','?')} period={e.get('report_period','?')}")
            # path
            path_str = render_path(c.path)
            items.append({
                "subject_code": r["code"], "subject_name": sname,
                "party_name": c.party_name, "rule_id": c.rule_id,
                "path_readable": path_str,
                "evidence": " | ".join(ev_strs),
                "report_period": c.as_of_date or "",
                "confidence": c.confidence, "score": c.score,
                "gold_parties_of_subject": ", ".join(gold_list[:15]),
                "name_variants": ", ".join(variants[:5]),
                "human_class": "", "human_note": "",
            })

    # 排序: R2 最前, 然后按 rule_id, 组内 confidence 降序
    rule_order = {"R2": 0, "R1": 1, "R4": 2, "R5": 3, "R3": 4, "R6": 5, "R7": 6}
    conf_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda x: (rule_order.get(x["rule_id"].split("+")[0], 99), conf_order.get(x["confidence"], 9), -x["score"]))

    # CSV
    csv_path = Path("data/reviews/system_only_review.csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["subject_code","subject_name","party_name","rule_id",
                                           "path_readable","evidence","report_period","confidence","score",
                                           "gold_parties_of_subject","name_variants","human_class","human_note"])
        w.writeheader()
        for item in items:
            w.writerow(item)

    # Markdown
    md_path = Path("data/reviews/review_sheet.md")
    md = ["# 关联方核查表（可比口径 system_only）", "",
          f"> {len(items)} 条候选, 按 rule_id 分组(R2最前), 组内 confidence 降序",
          "> human_class 和 human_note 留空, 供人工填写", ""]
    cur_rule = ""
    for i, item in enumerate(items, 1):
        rid = item["rule_id"].split("+")[0]
        if rid != cur_rule:
            cur_rule = rid
            md.append(f"\n---\n## 规则 {cur_rule}\n")
        md.append(f"### {i}. {item['party_name']}")
        md.append(f"- **主体**: {item['subject_name']}({item['subject_code']})")
        md.append(f"- **规则**: {item['rule_id']} | **置信度**: {item['confidence']} | **score**: {item['score']}")
        md.append(f"- **路径**: {item['path_readable']}")
        md.append(f"- **证据**: {item['evidence']}")
        md.append(f"- **时点**: {item['report_period'] or '未指定'}")
        md.append(f"- **该公司年报已披露的 upstream 关联方**: {item['gold_parties_of_subject'] or '(无)'}")
        md.append(f"- **名称变体**: {item['name_variants'] or '(无)'}")
        md.append(f"- **human_class**: ______ | **human_note**: ______")
        md.append("")
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"T1: CSV -> {csv_path} ({len(items)} 条), MD -> {md_path}")

    # README
    readme = Path("data/reviews/README.md")
    readme.write_text("""# 人工核查判定口径

## 三个取值的判定标准

### true_omission（真漏报 = 系统价值）
按上市规则确实构成关联人（同一实控人下的兄弟公司、董监高兼任的公司等），且经核对该公司年报关联方章节确实未列示该关联方。

### reasonable_undisclosed（合理未披露）
关系客观存在但不满足披露的实质标准：
- 控制比例过低（如虽有共同股东但持股很低、无实际影响）
- 任职为独立董事（独董兼职普遍，上市规则中独董关联认定另有口径）
- 关系已超出 12 个月窗口（如去年离任的董事）
- 纯供应链关系（准则第36号第六条第(二)项明确不构成关联方）

### system_error（系统误报）
路径本身不成立：
- 实控人识别错误
- 人名重名未消歧（不同人被当成同一人）
- 通道类股东未排除干净
- 时点错配（用不同报告期的数据交叉）
- 名称对齐失败（gold 里有该公司但用了不同名称）

## 填写方式
1. 打开 review_sheet.md 或 CSV
2. 逐条查看路径、证据、该公司年报已披露的关联方列表
3. 判断该候选属于上述哪一类
4. 在 human_class 填入: true_omission / reasonable_undisclosed / system_error
5. 在 human_note 简写理由（可选）

## 注意
- gold_parties_of_subject 列出了该公司年报已披露的 upstream 关联方名称。如果候选名称在该列表中（或名称变体匹配），可能是名称对齐失败而非真漏报——核对 name_variants。
- 如果候选的路径/证据有明显数据质量问题（如时点错配、通道未排），直接判 system_error。
""", encoding="utf-8")
    print(f"    README -> {readme}")


# ============================================================
# T2: other 诊断
# ============================================================
def t2_diagnose_other(store):
    rows = store.conn.execute(
        "SELECT id, stock_code, party_name, relation_desc, source_page FROM gold_related_party WHERE scope_class='other'").fetchall()
    # relation_desc 分布
    desc_counts = Counter()
    for r in rows:
        d = (r["relation_desc"] or "").strip()
        desc_counts[d if d else "(空)"] += 1
    top50 = desc_counts.most_common(50)

    # 诊断
    md = ["# scope_class other 诊断（607 条, 37.1%）", ""]
    md.append(f"> 总计 {len(rows)} 条, relation_desc 去重后 {len(desc_counts)} 种取值")
    md.append(f"> 空白 relation_desc: {desc_counts.get('(空)', 0)} 条")
    md.append("")
    md.append("## Top 50 relation_desc 取值分布")
    md.append("")
    md.append("| 频次 | relation_desc | 诊断(为何没被分类) |")
    md.append("|---|---|---|")
    for desc, cnt in top50:
        if desc == "(空)":
            diag = "relation_desc 为空(表格抽取未抓关系列)"
        elif "其他" in desc:
            diag = "描述模糊('其他'不明确上下游)"
        elif "公司" in desc and "控制" not in desc and "股东" not in desc and "子" not in desc:
            diag = "关键词未覆盖(描述含'公司'但不匹配 upstream/downstream 关键词)"
        else:
            diag = "关键词表未覆盖或描述模糊"
        md.append(f"| {cnt} | {desc[:60]} | {diag} |")
    md.append("")
    md.append("## 诊断总结")
    md.append("")
    md.append(f"- **主因**: {desc_counts.get('(空)', 0)} 条 relation_desc 为空({desc_counts.get('(空)', 0)/len(rows)*100:.0f}%), 来自表格抽取(只抓了名称列未抓关系列)")
    md.append(f"- **次要**: 部分描述模糊('其他')或关键词未覆盖的边缘写法")
    md.append(f"- **结论**: other 主要是数据质量问题(relation_desc 缺失), 非规则覆盖不足。不排除其中混有上游关系——但无法从名称推断, 需人工判断。")
    md.append(f"- **影响**: 可比口径 gold=558(upstream), 若 other 中有部分实为 upstream, 则 recall 被低估。但当前不自行扩充关键词, 先出诊断待人工确认。")
    Path("docs/scope-class-review.md").write_text("\n".join(md), encoding="utf-8")
    print(f"T2: scope-class-review.md -> docs/scope-class-review.md")

    # other_sample.csv (30条分层抽样)
    # 按 relation_desc 类型分层
    by_type = {}
    for r in rows:
        d = (r["relation_desc"] or "").strip()
        key = d[:20] if d else "(空)"
        by_type.setdefault(key, []).append(r)
    sample = []
    import random; random.seed(42)
    for key, items in by_type.items():
        n = max(1, min(len(items), 30 // len(by_type) + 1))
        sample.extend(random.sample(items, min(n, len(items))))
        if len(sample) >= 30: break
    sample = sample[:30]
    csv_path = Path("data/reviews/other_sample.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stock_code", "party_name", "relation_desc", "source_page", "human_scope_class"])
        for r in sample:
            w.writerow([r["stock_code"], r["party_name"], r["relation_desc"] or "(空)", r["source_page"], ""])
    print(f"    other_sample.csv -> {csv_path} ({len(sample)} 条)")


# ============================================================
# T3: 消歧标注集
# ============================================================
def t3_disambig_sheet():
    ann_path = Path("data/annotations/person_disambig.jsonl")
    if not ann_path.exists():
        print("T3: 无 person_disambig.jsonl, 跳过"); return
    pairs = [json.loads(l) for l in ann_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    store = Store("rpscope.db")

    md = ["# 人名消歧人工标注集", "",
          f"> {len(pairs)} 对同名候选。以下信息供人工判断是否同一人。",
          "> **不展示系统预测或银标标签, 避免锚定人工判断。**", ""]

    for i, p in enumerate(pairs, 1):
        name = p["name"]
        ra, rb = p["rec_a"], p["rec_b"]
        # 公司信息
        def co_info(code):
            code = str(code).zfill(6)
            r = store.conn.execute("SELECT short_name, industry FROM company WHERE stock_code=?", (code,)).fetchone()
            return (r["short_name"], r["industry"]) if r else ("?", "?")
        ca = co_info(ra.get("stock_code"))
        cb = co_info(rb.get("stock_code"))
        # 姓名频次
        freq = store.conn.execute(
            "SELECT COUNT(DISTINCT stock_code) FROM position WHERE entity_id IN "
            "(SELECT entity_id FROM entity WHERE canonical_name=?)", (name,)).fetchone()[0]
        # 持股记录
        holds_a = store.conn.execute(
            "SELECT COUNT(*) FROM holding WHERE entity_id IN (SELECT entity_id FROM entity WHERE canonical_name=?) AND stock_code=?",
            (name, str(ra.get("stock_code","")).zfill(6))).fetchone()[0]
        holds_b = store.conn.execute(
            "SELECT COUNT(*) FROM holding WHERE entity_id IN (SELECT entity_id FROM entity WHERE canonical_name=?) AND stock_code=?",
            (name, str(rb.get("stock_code","")).zfill(6))).fetchone()[0]

        md.append(f"---")
        md.append(f"## 第 {i} 对: {name}")
        md.append(f"")
        md.append(f"| | 记录 A | 记录 B |")
        md.append(f"|---|---|---|")
        md.append(f"| 公司 | {ca[0]}({ra.get('stock_code','')}) | {cb[0]}({rb.get('stock_code','')}) |")
        md.append(f"| 行业 | {ca[1] or '未知'} | {cb[1] or '未知'} |")
        md.append(f"| 职务 | {ra.get('title','')} | {rb.get('title','')} |")
        md.append(f"| 日期 | {ra.get('valid_from','')} | {rb.get('valid_from','')} |")
        md.append(f"| 持股记录 | {'有' if holds_a else '无'} | {'有' if holds_b else '无'} |")
        md.append(f"")
        md.append(f"- 姓名在全库出现频次: {freq} 家公司")
        md.append(f"- **判断**: 是同一人 / 不是同一人 / 无法判定")
        md.append(f"")

    md_path = Path("data/annotations/person_disambig_sheet.md")
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"T3: person_disambig_sheet.md -> {md_path} ({len(pairs)} 对)")

    # eval_disambig --gold 使用说明
    md2 = ["# 人名消歧评测使用说明", "",
           "## 人工标注", "1. 打开 `data/annotations/person_disambig_sheet.md`",
           "2. 逐对判断是否同一人, 在 person_disambig.jsonl 的每条 same_person 字段填 true/false",
           "3. 标注原则: 保守(信息不足判不同人)", "",
           "## 跑真金标准准确率", "```", "py scripts/eval_disambig.py --gold", "```",
           "输出: 准确率/precision/recall/混淆矩阵/按置信度分档", "",
           "## 与银标 93.3% 对照",
           "- 银标(qwen3.7-max 裁判) 93.3% 是独立模型判定, 非人工金标准",
           "- 人工金标准完成后, 与银标逐条对照, 算银标相对人工的准确率",
           "- 若人工 vs 银标差异大, 说明银标存在系统性偏差(如对常见名过度保守)", ""]
    Path("data/annotations/eval_gold_instructions.md").write_text("\n".join(md2), encoding="utf-8")
    print(f"    eval_gold_instructions.md -> data/annotations/")


# ============================================================
# main
# ============================================================
if __name__ == "__main__":
    store = Store("rpscope.db")
    eng = RuleEngine("config/rules.yaml")
    print("=== T1: 补全核查表 ===")
    t1_enrich_review(store, eng)
    print("\n=== T2: other 诊断 ===")
    t2_diagnose_other(store)
    print("\n=== T3: 消歧标注集 ===")
    t3_disambig_sheet()
    store.close()
    print("\n=== 人工填写时间估算 ===")
    print("核查表 28 条: 约 1-2 小时(每条约 3-5 分钟, 需查年报)")
    print("other_sample 30 条: 约 1 小时(判断 scope_class)")
    print("消歧标注 90 对: 约 1.5-2 小时(每对约 1 分钟)")
    print("总计: 约 4-5 小时")
