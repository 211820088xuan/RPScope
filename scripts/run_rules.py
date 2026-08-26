"""P3 批量跑规则 - 在 Eval 集上跑 R1-R7, 出统计。

统计: 总候选数/各规则命中/置信度分布/单公司 P95 耗时。
无 LLM(铁律2)。阈值全从 config/rules.yaml 读。
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rules.engine import RuleEngine
from src.store.db import Store


def sample_eval(store: Store, n: int = 300) -> list[str]:
    """优先抽有 controller/position 记录的公司(规则才有产出), 不足补随机。"""
    with_ctrl = [r[0] for r in store.conn.execute(
        "SELECT DISTINCT stock_code FROM actual_controller").fetchall()]
    with_pos = [r[0] for r in store.conn.execute(
        "SELECT DISTINCT stock_code FROM position").fetchall()]
    pool = list(dict.fromkeys(with_ctrl + with_pos))  # 去重保序
    if len(pool) >= n:
        return pool[:n]
    # 不足则从全表补
    rest = [r[0] for r in store.conn.execute(
        "SELECT stock_code FROM company WHERE stock_code NOT IN (%s)"
        % ",".join("?" * len(pool)) if pool else "SELECT stock_code FROM company",
        pool if pool else []).fetchall()]
    return (pool + rest)[:n]


def main(n: int = 300) -> None:
    store = Store("rpscope.db")
    eng = RuleEngine("config/rules.yaml")
    codes = sample_eval(store, n)
    print(f"Eval 集 {len(codes)} 家 | 启用规则 {[r.rule_id for r in eng.rules]}", flush=True)

    total_cands = 0
    rule_hits = Counter()
    conf_dist = Counter()
    per_rule_conf: dict[str, Counter] = {}
    times: list[float] = []
    t0all = time.perf_counter()
    for i, code in enumerate(codes):
        cands, dt = eng.evaluate_timed(store, code)
        times.append(dt)
        total_cands += len(cands)
        for c in cands:
            # 多规则合并的 rule_id 形如 R1+R3; 同规则多期记录合并会重复, 用 set 去重
            for rid in set(c.rule_id.split("+")):
                rule_hits[rid] += 1
                per_rule_conf.setdefault(rid, Counter())[c.confidence] += 1
            conf_dist[c.confidence] += 1
        if (i + 1) % 50 == 0:
            times.sort()
            p95 = times[int(len(times) * 0.95)] if times else 0
            print(f"  [{i+1}/{len(codes)}] 累计候选 {total_cands} | 当前 P95 {p95*1000:.0f}ms", flush=True)

    times.sort()
    p50 = times[int(len(times) * 0.5)] * 1000
    p95 = times[int(len(times) * 0.95)] * 1000
    print(f"\n=== P3 规则引擎统计 (Eval {len(codes)} 家) ===", flush=True)
    print(f"总候选(合并后) {total_cands} | 平均 {total_cands/len(codes):.1f}/家")
    print(f"单公司耗时 P50={p50:.0f}ms P95={p95:.0f}ms " + ("[OK]<3s" if p95 < 3000 else "[WARN]>=3s"))
    print(f"\n各规则命中(含合并拆开):")
    for rid in sorted(rule_hits):
        c = per_rule_conf[rid]
        print(f"  {rid}: {rule_hits[rid]} | high={c.get('high',0)} medium={c.get('medium',0)} low={c.get('low',0)}")
    print(f"\n置信度分布: {dict(conf_dist)}")
    store.close()


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    main(n)
