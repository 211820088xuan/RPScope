"""T2: 意图分类测试。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.query.intent import classify
from tests.query.test_intent_data import TESTS


def test_intent_classification():
    correct = 0
    by_intent = {}
    for t in TESTS:
        exp = t["expected"]
        got = classify(t["question"])["intent"]
        if exp not in by_intent:
            by_intent[exp] = {"total": 0, "correct": 0}
        by_intent[exp]["total"] += 1
        if got == exp:
            by_intent[exp]["correct"] += 1
            correct += 1

    total = len(TESTS)
    print(f"\n=== 意图分类测试结果 ===")
    print(f"总计: {correct}/{total} = {correct/total*100:.0f}%")
    print(f"\n按意图:")
    for intent in ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"]:
        s = by_intent.get(intent, {"total": 0, "correct": 0})
        pct = s["correct"]/s["total"]*100 if s["total"] else 0
        print(f"  {intent}: {s['correct']}/{s['total']} = {pct:.0f}%")

    # 列出错误
    errors = [t for t in TESTS if classify(t["question"])["intent"] != t["expected"]]
    if errors:
        print(f"\n错误 ({len(errors)} 条):")
        for e in errors:
            got = classify(e["question"])
            print(f"  {e['question']:40s} expected={e['expected']} got={got['intent']} note={e['note']}")

    assert correct >= 80, f"规则覆盖率应≥80%, 实际{correct/total*100:.0f}%"
