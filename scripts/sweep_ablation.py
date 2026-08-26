"""P5 阈值扫描 + 规则消融 - 确定性, 不依赖人工。

阈值扫描: R1 related_party 阈值 3->10%, 看 P/R/matched 变化。
消融: 逐条禁用 R1/R2/R3/R4, 看候选数与 matched 变化。
结果追加到 docs/eval-v1.md。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.eval.aligner import align_batch
from src.eval.metrics import prf
from src.rules.engine import RuleEngine
from src.store.db import Store

OUT = Path("docs/eval-v1.md")


def run_align(eng: RuleEngine, store: Store, codes: list[str]) -> dict:
    res = align_batch(store, eng, codes)
    m = prf(len(res["matched"]), len(res["system_only"]), len(res["gold_only"]))
    return {"matched": m["tp"], "sys": m["fp"], "gold": m["fn"],
            "P": m["precision"], "R": m["recall"], "F1": m["f1"]}


def main() -> None:
    store = Store("rpscope.db")
    codes = [r[0] for r in store.conn.execute(
        "SELECT DISTINCT stock_code FROM gold_related_party").fetchall()]
    print(f"扫描/消融: {len(codes)} 家", flush=True)

    # --- 阈值扫描: R1 related_party ---
    sweep = []
    for th in [3.0, 5.0, 7.0, 10.0]:
        eng = RuleEngine("config/rules.yaml")
        for r in eng.rules:
            if r.rule_id == "R1":
                r.cfg["thresholds"]["related_party"] = th
        m = run_align(eng, store, codes)
        sweep.append((th, m))
        print(f"  R1 阈值 {th}%: matched={m['matched']} sys={m['sys']} P={m['P']*100:.1f}% R={m['R']*100:.1f}%", flush=True)

    # --- 消融: 逐条禁用 ---
    abl = []
    for disable in ["R1", "R2", "R3", "R4"]:
        eng = RuleEngine("config/rules.yaml")
        eng.rules = [r for r in eng.rules if r.rule_id != disable]
        m = run_align(eng, store, codes)
        abl.append((disable, m))
        print(f"  禁用 {disable}: matched={m['matched']} sys={m['sys']} P={m['P']*100:.1f}% R={m['R']*100:.1f}%", flush=True)

    # 追加到 eval-v1.md
    md = ["", "## 六、阈值敏感性（R1 related_party 阈值）", ""]
    md.append("| R1 阈值% | matched | system_only | precision | recall |")
    md.append("|---|---|---|---|---|")
    for th, m in sweep:
        md.append(f"| {th} | {m['matched']} | {m['sys']} | {m['P']*100:.1f}% | {m['R']*100:.1f}% |")
    md.append("")
    md.append("## 七、规则消融（逐条禁用）")
    md.append("| 禁用规则 | matched | system_only | precision | recall |")
    md.append("|---|---|---|---|---|")
    # 全开基线
    eng = RuleEngine("config/rules.yaml")
    base = run_align(eng, store, codes)
    md.append(f"| (全开基线) | {base['matched']} | {base['sys']} | {base['P']*100:.1f}% | {base['R']*100:.1f}% |")
    for d, m in abl:
        md.append(f"| -{d} | {m['matched']} | {m['sys']} | {m['P']*100:.1f}% | {m['R']*100:.1f}% |")
    md.append("")
    with open(OUT, "a", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\n结果追加 -> {OUT}")
    store.close()


if __name__ == "__main__":
    main()
