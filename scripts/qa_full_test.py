"""NL2GraphQuery 端到端测试 60 条, 覆盖 7 类意图 + 歧义 + 无结果 + 模板外。"""
import requests, time, sys

BASE = "http://127.0.0.1:8765"

# 60 条测试: (label, question, context_code, expected_intent, min_answer_len)
TESTS = [
    # === Q1 关联方 (12条) ===
    ("Q1-01", "002594的关联方有哪些", "002594", "Q1", 10),
    ("Q1-02", "比亚迪的关联方", "002594", "Q1", 10),
    ("Q1-03", "300750关联方", "300750", "Q1", 10),
    ("Q1-04", "茅台的关联方清单", "600519", "Q1", 10),
    ("Q1-05", "600036的关联方", "600036", "Q1", 10),
    ("Q1-06", "002594的关联方 只看高置信度的", "002594", "Q1", 10),
    ("Q1-07", "茅台R2规则的关联方", "600519", "Q1", 5),
    ("Q1-08", "600036的关联方 截至2024年底", "600036", "Q1", 5),
    ("Q1-09", "宁德时代的关联方", "", "Q1", 10),
    ("Q1-10", "五粮液的关联方有哪些", "", "Q1", 10),
    ("Q1-11", "中国平安关联方", "", "Q1", 10),
    ("Q1-12", "招商银行的关联方清单", "", "Q1", 10),

    # === Q2 关系路径 (10条) ===
    ("Q2-01", "002594和300750什么关系", "002594", "Q2", 10),
    ("Q2-02", "比亚迪和宁德时代有关联吗", "002594", "Q2", 10),
    ("Q2-03", "600519和000858的关系路径", "600519", "Q2", 10),
    ("Q2-04", "比亚迪与宁德时代什么关系", "002594", "Q2", 10),
    ("Q2-05", "002594跟300750有关联吗", "002594", "Q2", 10),
    ("Q2-06", "600036和000001什么关系", "600036", "Q2", 10),
    ("Q2-07", "中国平安和招商银行有关联吗", "601318", "Q2", 10),
    ("Q2-08", "茅台和五粮液的关系", "600519", "Q2", 10),
    ("Q2-09", "宁德时代和比亚迪什么关系", "300750", "Q2", 10),
    ("Q2-10", "300750与002594的关联", "300750", "Q2", 10),

    # === Q3 反向查询 (10条) ===
    ("Q3-01", "王传福控制哪些公司", "002594", "Q3", 5),
    ("Q3-02", "融捷投资持有哪些上市公司", "002594", "Q3", 5),
    ("Q3-03", "曾毓群控制的公司有哪些", "300750", "Q3", 5),
    ("Q3-04", "中国平安持股超过5%的公司", "601318", "Q3", 5),
    ("Q3-05", "李振国在哪些公司任职", "601012", "Q3", 5),
    ("Q3-06", "王传福担任哪些公司的董事", "002594", "Q3", 5),
    ("Q3-07", "吕向阳控制哪些上市公司", "002594", "Q3", 5),
    ("Q3-08", "夏佐全在哪些公司有任职", "002594", "Q3", 5),
    ("Q3-09", "曾毓群控制了哪些公司", "300750", "Q3", 5),
    ("Q3-10", "王传福在哪几家公司任职", "002594", "Q3", 5),

    # === Q4 公司角色 (10条) ===
    ("Q4-01", "002594的前十大股东", "002594", "Q4", 10),
    ("Q4-02", "比亚迪的实际控制人是谁", "002594", "Q4", 10),
    ("Q4-03", "300750的董监高", "300750", "Q4", 10),
    ("Q4-04", "茅台的股东", "600519", "Q4", 10),
    ("Q4-05", "600036的实控人", "600036", "Q4", 10),
    ("Q4-06", "比亚迪的董事有哪些", "002594", "Q4", 10),
    ("Q4-07", "300750的监事", "300750", "Q4", 10),
    ("Q4-08", "茅台的总经理是谁", "600519", "Q4", 10),
    ("Q4-09", "比亚迪的十大股东", "002594", "Q4", 10),
    ("Q4-10", "宁德时代的实际控制人", "300750", "Q4", 10),

    # === Q5 风险事件 (8条) ===
    ("Q5-01", "002594的担保情况", "002594", "Q5", 10),
    ("Q5-02", "比亚迪的风险事件", "002594", "Q5", 10),
    ("Q5-03", "300750的诉讼", "300750", "Q5", 5),
    ("Q5-04", "茅台有没有质押", "600519", "Q5", 5),
    ("Q5-05", "600036近三年的担保", "600036", "Q5", 5),
    ("Q5-06", "比亚迪的担保", "002594", "Q5", 10),
    ("Q5-07", "002594有哪些诉讼", "002594", "Q5", 5),
    ("Q5-08", "宁德时代的质押情况", "300750", "Q5", 5),

    # === Q6 关联方重合 (6条) ===
    ("Q6-01", "002594和300750的关联方重合", "002594", "Q6", 5),
    ("Q6-02", "比亚迪和宁德时代有哪些共同关联方", "002594", "Q6", 5),
    ("Q6-03", "茅台和五粮液的关联方交集", "600519", "Q6", 5),
    ("Q6-04", "600036和000001的关联方重叠", "600036", "Q6", 5),
    ("Q6-05", "中国平安和招商银行关联方重合度", "601318", "Q6", 5),
    ("Q6-06", "比亚迪和宁德时代关联方交集", "002594", "Q6", 5),

    # === Q7 模板外 (4条) ===
    ("Q7-01", "这个股的后续增长情况", "002594", "Q7", 50),
    ("Q7-02", "比亚迪的财务状况怎么样", "002594", "Q7", 50),
    ("Q7-03", "002594值得买吗", "002594", "Q7", 50),
    ("Q7-04", "比亚迪的竞争对手有哪些", "002594", "Q7", 50),
]


def run():
    passed = 0
    intent_ok = 0
    fail_details = []
    by_intent = {}

    total = len(TESTS)
    print(f"Running {total} tests...\n")

    for i, (label, q, ctx, exp, min_len) in enumerate(TESTS):
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
            verify = j.get("verify", {})
            clarif = j.get("clarifications", [])

            # Check
            intent_match = intent == exp
            ans_ok = ans_len >= min_len
            ok = intent_match and ans_ok

            if intent_match:
                intent_ok += 1
            if ok:
                passed += 1
            else:
                v_str = "ok" if verify.get("passed") else f"viol={len(verify.get('violations', []))}"
                fail_details.append(f"  [{label}] exp={exp} got={intent} len={ans_len} min={min_len} {v_str} | {q[:40]}")

            by_intent.setdefault(exp, {"total": 0, "pass": 0})
            by_intent[exp]["total"] += 1
            if ok:
                by_intent[exp]["pass"] += 1

            status = "PASS" if ok else "FAIL"
            print(f"  [{status}] {label:8s} intent={intent:3s}/{exp:3s} len={ans_len:5d} {elapsed:.1f}s | {q[:35]}")

        except Exception as e:
            fail_details.append(f"  [{label}] EXCEPTION: {str(e)[:80]} | {q[:40]}")
            by_intent.setdefault(exp, {"total": 0, "pass": 0})
            by_intent[exp]["total"] += 1
            print(f"  [FAIL] {label:8s} exception: {str(e)[:60]}")

    # AI Report test
    print("\n--- AI Report ---")
    try:
        t0 = time.time()
        r = requests.get(f"{BASE}/api/report/002594/prose", timeout=120)
        elapsed = time.time() - t0
        j = r.json()
        ok_llm = j.get("used_llm", False)
        fallback = "退回模板" in j.get("prose", "")
        has_fin = any(k in j.get("prose", "") for k in ["财务", "营收", "估值"])
        prose_len = len(j.get("prose", ""))
        report_ok = ok_llm and not fallback and has_fin and prose_len > 1000
        if report_ok:
            passed += 1
        total += 1
        status = "PASS" if report_ok else "FAIL"
        print(f"  [{status}] AI-Report llm={ok_llm} fallback={fallback} fin={has_fin} len={prose_len} {elapsed:.1f}s")
        if not report_ok:
            fail_details.append(f"  [AI-Report] llm={ok_llm} fallback={fallback} fin={has_fin} len={prose_len}")
    except Exception as e:
        total += 1
        fail_details.append(f"  [AI-Report] EXCEPTION: {str(e)[:80]}")
        print(f"  [FAIL] AI-Report exception: {str(e)[:60]}")

    # Summary
    print(f"\n{'='*60}")
    print(f"TOTAL: {passed}/{total} = {passed/total*100:.0f}%")
    print(f"Intent match: {intent_ok}/{len(TESTS)} = {intent_ok/len(TESTS)*100:.0f}%")
    print(f"\nBy intent:")
    for k in sorted(by_intent):
        s = by_intent[k]
        pct = s["pass"]/s["total"]*100
        print(f"  {k}: {s['pass']}/{s['total']} = {pct:.0f}%")
    if fail_details:
        print(f"\nFailures ({len(fail_details)}):")
        for f in fail_details:
            print(f)

    return passed == total


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
