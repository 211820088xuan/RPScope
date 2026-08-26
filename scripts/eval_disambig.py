"""P2 消歧评测 - 准确率/混淆矩阵/按置信度分档。

两种模式:
  --gold   读 data/annotations/person_disambig.jsonl 的 same_person(人工标), 报真实指标
  --silver  无人工标时, 用 LLM 打银标, 报"LLM与规则的分歧率"(非金标准, 仅作 ballpark)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.disambiguate.resolver import resolve_pair
from src.disambiguate.signals import Record, Stats
from src.llm.client import LLMClient
from src.store.db import Store

ANN = Path("data/annotations/person_disambig.jsonl")


def eval_gold() -> None:
    if not ANN.exists():
        print(f"无标注集 {ANN}, 先跑 build_annotation_set.py 并人工填 same_person")
        return
    labeled = [json.loads(l) for l in ANN.read_text(encoding="utf-8").splitlines() if l.strip()]
    labeled = [p for p in labeled if p.get("same_person") != ""]
    if not labeled:
        print("标注集存在但 same_person 全空, 请人工标注后再评")
        return
    client = LLMClient()
    tp = fp = tn = fn = 0
    by_conf: dict[str, list] = {}
    for p in labeled:
        gold = str(p["same_person"]).lower() in ("true", "1", "yes")
        ra = Record(**{k: p["rec_a"].get(k, "") for k in ("stock_code", "title", "valid_from", "source")})
        rb = Record(**{k: p["rec_b"].get(k, "") for k in ("stock_code", "title", "valid_from", "source")})
        stats = Stats(name_freq=0, name_company_count=0)
        v = resolve_pair(p["name"], ra, rb, stats, client)
        pred = v.same_person
        if gold and pred: tp += 1
        elif (not gold) and pred: fp += 1
        elif (not gold) and (not pred): tn += 1
        else: fn += 1
        by_conf.setdefault(v.confidence, []).append(int(pred == gold))
    n = len(labeled)
    acc = (tp + tn) / n if n else 0
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    print(f"== Gold 评测 (n={n}) ==")
    print(f"准确率 {acc*100:.1f}% | precision {prec*100:.1f}% | recall {rec*100:.1f}%")
    print(f"混淆矩阵: TP={tp} FP={fp} TN={tn} FN={fn}")
    for conf, hits in sorted(by_conf.items()):
        print(f"  {conf} 档准确率 {sum(hits)/len(hits)*100:.1f}% (n={len(hits)})")
    print(f"LLM 兜底率: {sum(1 for p in labeled for _ in [0])} / 保守策略: 宁漏(FN={fn})不错(FP={fp})")


def eval_silver() -> None:
    """无 gold 时, LLM 打银标, 报规则与 LLM 的分歧(非准确率, 仅 ballpark)。"""
    if not ANN.exists():
        print(f"无标注集, 先跑 build_annotation_set.py")
        return
    pairs = [json.loads(l) for l in ANN.read_text(encoding="utf-8").splitlines() if l.strip()]
    client = LLMClient()
    agree = llm_same = rule_same = 0
    for p in pairs[:80]:
        ra = Record(**{k: p["rec_a"].get(k, "") for k in ("stock_code", "title", "valid_from", "source")})
        rb = Record(**{k: p["rec_b"].get(k, "") for k in ("stock_code", "title", "valid_from", "source")})
        stats = Stats(0, 0)
        v_rule = resolve_pair(p["name"], ra, rb, stats, None)  # 纯规则
        v_llm = resolve_pair(p["name"], ra, rb, stats, client)  # 规则+LLM
        if v_rule.same_person == v_llm.same_person: agree += 1
        if v_llm.same_person: llm_same += 1
        if v_rule.same_person: rule_same += 1
    n = min(80, len(pairs))
    print(f"== Silver ballpark (n={n}, 非金标准) ==")
    print(f"规则与'规则+LLM'一致率 {agree/n*100:.1f}% | 规则判同 {rule_same} | +LLM判同 {llm_same}")
    print("注: 这是 LLM 自评 ballpark, 非真实准确率; 真实指标需人工 gold(--gold)。")


if __name__ == "__main__":
    if "--gold" in sys.argv:
        eval_gold()
    else:
        eval_silver()
