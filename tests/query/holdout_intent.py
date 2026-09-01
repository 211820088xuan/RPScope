"""T1 留出集: 意图分类测试 — 跑一次, 不调参。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.query.intent import classify
from tests.query.holdout_intent_data import HOLDOUT_INTENT


def run_holdout():
    correct = 0
    by_type = {}
    errors = []
    for t in HOLDOUT_INTENT:
        got = classify(t["question"])["intent"]
        exp = t["expected"]
        ok = got == exp
        if ok:
            correct += 1
        else:
            errors.append(f"  {t['question']:35s} exp={exp} got={got} note={t['note']}")

        cat = t["note"].split("→")[0].strip()[:10]
        by_type.setdefault(cat, {"total": 0, "ok": 0})
        by_type[cat]["total"] += 1
        if ok:
            by_type[cat]["ok"] += 1

    total = len(HOLDOUT_INTENT)
    print(f"=== 留出集意图分类 ===")
    print(f"准确率: {correct}/{total} = {correct/total*100:.0f}%")
    print(f"\n按类型:")
    for k, v in sorted(by_type.items()):
        print(f"  {k:12s}: {v['ok']}/{v['total']}")
    if errors:
        print(f"\n错误 ({len(errors)}):")
        for e in errors:
            print(e)
    return correct == total


if __name__ == "__main__":
    run_holdout()
