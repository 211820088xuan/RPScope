"""调优后重评 - 复用已存 silver_gold(qwen3.7-max 裁判不变), 只重算系统侧预测。

省去慢吞吞的 qwen3.7-max 重调, 仅 glm-5.2 中段调用。对比调优前后准确率。
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

SILVER = Path("data/annotations/silver_eval.jsonl")


def main() -> None:
    rows = [json.loads(l) for l in SILVER.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"复用 {len(rows)} 条 silver_gold, 重算调优后系统预测", flush=True)
    print("调优: HIGH_SAME 0.70/LOW_DIFF 0.40 + 权重正信号+0.05 + LLM prompt 客观化", flush=True)

    client = LLMClient()  # glm-5.2
    store = Store("rpscope.db")

    tp = fp = tn = fn = 0
    by_conf: dict[str, list] = {}
    llm = 0
    for i, r in enumerate(rows):
        gold = r["silver_gold"]
        ra = Record(**{k: r["rec_a"].get(k, "") for k in ("stock_code", "title", "valid_from", "source")})
        rb = Record(**{k: r["rec_b"].get(k, "") for k in ("stock_code", "title", "valid_from", "source")})
        # 查 n_co (与原评测一致)
        canon = r.get("name")
        row = store.conn.execute(
            "SELECT entity_id FROM entity WHERE entity_type='person' AND canonical_name=?", (canon,)).fetchone()
        n_co = 0
        if row:
            n_co = store.conn.execute(
                "SELECT COUNT(DISTINCT stock_code) FROM ("
                "  SELECT stock_code FROM position WHERE entity_id=? UNION SELECT stock_code FROM holding WHERE entity_id=?)",
                (row[0], row[0])).fetchone()[0]
        stats = Stats(name_freq=0, name_company_count=n_co)
        v = resolve_pair(r["name"], ra, rb, stats, client)
        pred = v.same_person
        if v.used_llm:
            llm += 1
        if gold and pred: tp += 1
        elif (not gold) and pred: fp += 1
        elif (not gold) and (not pred): tn += 1
        else: fn += 1
        by_conf.setdefault(v.confidence, []).append(int(pred == gold))
        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(rows)}] acc={(tp+tn)/(i+1)*100:.1f}% llm={llm}", flush=True)

    n = len(rows)
    acc = (tp + tn) / n
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    print(f"\n=== 调优后银标结果 (n={n}, 裁判 silver_gold 复用) ===", flush=True)
    print(f"准确率 {acc*100:.1f}% (调优前 82.2%) | precision {prec*100:.1f}% | recall {rec*100:.1f}%")
    print(f"混淆 TP={tp} FP={fp} TN={tn} FN={fn} | LLM触发 {llm}/{n} ({llm/n*100:.1f}%)")
    for c, h in sorted(by_conf.items()):
        print(f"  {c}档 {sum(h)/len(h)*100:.1f}% (n={len(h)})")
    delta = acc - 0.822
    print(f"\n准确率变化: {'+' if delta>=0 else ''}{delta*100:.1f}pp vs 调优前 82.2%")


if __name__ == "__main__":
    main()
