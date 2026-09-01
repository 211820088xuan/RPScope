"""T1 留出集: 40 条端到端测试 — 跑一次不调参。

含: 口语化/省略主语、多意图混合、纯代码/纯名称、
不存在实体、歧义实体、错别字。每类≥5条。
"""
import requests, time, sys

BASE = "http://127.0.0.1:8765"

HOLDOUT_E2E = [
    # 口语化/省略主语 (5条) — context_code 提供主语
    ("HO-01", "关联方有哪些", "002594", "Q1", 5),
    ("HO-02", "前十大股东", "300750", "Q4", 5),
    ("HO-03", "担保情况", "002594", "Q5", 5),
    ("HO-04", "实控人是谁", "600519", "Q4", 5),
    ("HO-05", "关联方", "600036", "Q1", 5),

    # 多意图混合 (5条) — 记录实际分类, 不预设期望正确
    ("HO-06", "比亚迪的关联方里有没有担保", "002594", "Q1", 5),
    ("HO-07", "002594的关联方和诉讼", "002594", "Q1", 5),
    ("HO-08", "比亚迪的股东和关联方", "002594", "Q4", 5),
    ("HO-09", "300750的关联方和质押", "300750", "Q1", 5),
    ("HO-10", "002594的实控人和担保", "002594", "Q4", 5),

    # 只给代码 (5条)
    ("HO-11", "002594关联方清单", "002594", "Q1", 5),
    ("HO-12", "600036的股东", "600036", "Q4", 5),
    ("HO-13", "000001的担保", "000001", "Q5", 5),
    ("HO-14", "002475关联方", "002475", "Q1", 5),
    ("HO-15", "600276的实控人", "600276", "Q4", 5),

    # 只给名称 (5条)
    ("HO-16", "立讯精密的关联方", "", "Q1", 5),
    ("HO-17", "恒瑞医药的股东", "", "Q4", 5),
    ("HO-18", "隆基绿能的担保", "", "Q5", 5),
    ("HO-19", "东方财富的关联方", "", "Q1", 5),
    ("HO-20", "立讯精密的前十大股东", "", "Q4", 5),

    # 不存在实体 (5条)
    ("HO-21", "999999的关联方", "", "Q1", 5),
    ("HO-22", "腾讯的关联方", "", "Q1", 5),
    ("HO-23", "张三控制哪些公司", "", "Q3", 5),
    ("HO-24", "999999的股东", "", "Q4", 5),
    ("HO-25", "李四在哪些公司任职", "", "Q3", 5),

    # 歧义实体 (5条)
    ("HO-26", "平安的关联方", "", "Q1", 5),
    ("HO-27", "平安的股东", "", "Q4", 5),
    ("HO-28", "万科的担保", "", "Q5", 5),
    ("HO-29", "平安控制哪些公司", "", "Q3", 5),
    ("HO-30", "万科和保利什么关系", "", "Q2", 5),

    # 错别字与变体 (5条)
    ("HO-31", "比亚迪的关联防", "002594", "Q1", 5),
    ("HO-32", "茅苔的关联方", "", "Q1", 5),
    ("HO-33", "比雅迪的担保", "", "Q5", 5),
    ("HO-34", "宁德时代的关连方", "300750", "Q1", 5),
    ("HO-35", "比亚迪的关连方", "002594", "Q1", 5),

    # 补充: 正常变体 (5条)
    ("HO-36", "002594有哪些关联人", "002594", "Q1", 5),
    ("HO-37", "比亚迪的关联交易", "002594", "Q1", 5),
    ("HO-38", "茅台和五粮液关联方重合", "600519", "Q6", 5),
    ("HO-39", "002594的质押情况", "002594", "Q5", 5),
    ("HO-40", "王传福持有哪些公司", "002594", "Q3", 5),
]


def run():
    passed = 0
    intent_match = 0
    fails = []
    for label, q, ctx, exp, min_len in HOLDOUT_E2E:
        try:
            t0 = time.time()
            r = requests.post(f"{BASE}/api/ask",
                              json={"question": q, "context_code": ctx, "nocache": True},
                              timeout=120)
            elapsed = time.time() - t0
            j = r.json()
            intent = j.get("intent", "")
            ans = j.get("answer", "")
            ans_len = len(ans)
            ok = intent == exp and ans_len >= min_len
            im = intent == exp
            if im:
                intent_match += 1
            if ok:
                passed += 1
            else:
                fails.append(f"  [{label}] exp={exp} got={intent} len={ans_len} | {q[:40]}")
            status = "PASS" if ok else "FAIL"
            print(f"  [{status}] {label:6s} intent={intent:3s}/{exp:3s} len={ans_len:5d} {elapsed:.1f}s | {q[:35]}")
        except Exception as e:
            fails.append(f"  [{label}] EXCEPTION: {str(e)[:60]} | {q[:40]}")
            print(f"  [FAIL] {label:6s} exception: {str(e)[:50]}")

    print(f"\n{'='*60}")
    print(f"端到端: {passed}/{len(HOLDOUT_E2E)} = {passed/len(HOLDOUT_E2E)*100:.0f}%")
    print(f"意图匹配: {intent_match}/{len(HOLDOUT_E2E)} = {intent_match/len(HOLDOUT_E2E)*100:.0f}%")
    if fails:
        print(f"\n失败 ({len(fails)}):")
        for f in fails:
            print(f)
    return passed


if __name__ == "__main__":
    run()
