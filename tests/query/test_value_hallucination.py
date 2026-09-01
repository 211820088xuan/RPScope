"""#2: 补传 structured_result 的幻觉测试 — 数值篡改应转为拦截。

构造真实结构化结果 + 注入篡改数值的摘要, 验证回查拦截。
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.rules.engine import RuleEngine
from src.store.db import Store
from src.query.compare import compare
from src.agent.verifier import verify_answer

s = Store("rpscope.db")
eng = RuleEngine("config/rules.yaml")

# 构造真实结构化结果
result_002594 = compare(s, eng, "002594", "300750")
result_q4 = {"code": "002594", "roles": {
    "holders": [{"display_name": "融捷投资控股集团有限公司", "ratio": 5.96},
                {"display_name": "王传福", "ratio": None}],
    "controllers": [{"display_name": "王传福", "control_ratio": 39.28}]}}
result_q5 = {"code": "002594", "events": [
    {"event_type": "guarantee", "event_date": "2018-06-30", "amount": 63864300, "summary": "12笔担保"}]}

# 幻觉用例: (text, structured_result, expected_block, desc)
TESTS = [
    # 数值篡改(有 structured_result, 应拦截)
    ("王传福持有比亚迪49%的股份", result_q4, True, "持股39%→49%"),
    ("比亚迪2023年营收达到8万亿元", result_002594, True, "数值夸张"),
    ("宁德时代2025年1月发生重大担保违约", result_q5, True, "日期篡改"),
    ("比亚迪2024年净利润达到5000亿元", result_002594, True, "数值篡改"),
    # 正确数值(应通过)
    ("王传福持有比亚迪39.28%的股份", result_q4, False, "正确数值"),
    ("融捷投资控股集团有限公司持有比亚迪5.96%的股份", result_q4, False, "正确数值"),
    ("002594有12笔担保,金额63864300元", result_q5, False, "正确数值"),
]

print("=== #2: 数值篡改拦截验证(传 structured_result) ===\n")
blocked = 0
total = len(TESTS)
for text, result, exp_block, desc in TESTS:
    v = verify_answer(s, text, result)
    got_block = not v["passed"]
    ok = got_block == exp_block
    vlist = [v2.get("type","")+":"+str(v2.get("text",""))[:20] for v2 in v["violations"]]
    if got_block == exp_block:
        blocked += 1
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] exp={'block' if exp_block else 'pass':5s} got={'block' if got_block else 'pass':5s} | {desc:20s} | {vlist}")

print(f"\n通过率: {blocked}/{total} = {blocked/total*100:.0f}%")

# 之前 4 条数值篡改全部漏过, 现在应全部拦截
print(f"\n数值篡改拦截: {sum(1 for t in TESTS[:4] if not verify_answer(s, t[0], t[1])['passed'])}/4")

s.close()
