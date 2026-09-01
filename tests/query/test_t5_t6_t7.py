"""T5+T6+T7: 词典命中率重测 + 口语简称 + pronoun 用例重写 + 序数自动化。"""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.query.dict_match import CompanyMatcher
from src.query.conversation import get_session
from src.query.coreference import resolve, _extract_ordinal

conn = sqlite3.connect("rpscope.db")
conn.row_factory = sqlite3.Row
cm = CompanyMatcher(conn)

# T5: 30 条口语化简称
COLLOQUIAL = [
    ("五粮液", "000858"), ("万科", "ambiguous"),  # 万科A/B 撞车
    ("茅台", "600519"), ("贵州茅台", "600519"),
    ("平安", "NO_MATCH"), ("中国平安", "601318"),
    ("宁德", "NO_MATCH"), ("宁德时代", "300750"),
    ("比亚迪", "002594"), ("招商银行", "600036"),
    ("招行", "NO_MATCH"), ("恒瑞医药", "600276"),
    ("立讯精密", "002475"), ("隆基绿能", "601012"),
    ("东方财富", "300059"), ("中国平安", "601318"),
    ("盐田港", "000088"), ("金融街", "000402"),
    ("新希望", "000876"), ("中关村", "000931"),
    ("深振业A", "000006"), ("深振业a", "000006"),
    ("南玻A", "ambiguous"),  # 可能撞车
    ("万科A", "000002"), ("万科B", "NO_MATCH"),  # B 股可能不在
    ("深赛格", "000058"), ("农产品", "000061"),
    ("柳工", "000528"), ("英力特", "000635"),
    ("罗牛山", "000735"),
]

print("=== T5: 30 条口语简称命中率 ===")
hit = 0
for name, expected in COLLOQUIAL:
    m = cm.match(name)
    if expected == "NO_MATCH":
        ok = m is None
    elif expected == "ambiguous":
        ok = m is not None and m.ambiguous
    elif m and m.stock_code == expected:
        ok = True
    elif m and not m.ambiguous:
        ok = False  # matched wrong code
    else:
        ok = m is not None and m.ambiguous
    if ok:
        hit += 1
    code = m.stock_code if m else "None"
    amb = m.ambiguous if m else False
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name:12s} -> {code:8s} amb={amb} | exp={expected}")

print(f"\n命中率: {hit}/{len(COLLOQUIAL)} = {hit/len(COLLOQUIAL)*100:.0f}%")

# T6: pronoun_ambiguous 用例重写(真实存 2 个实体)
print("\n=== T6: pronoun_ambiguous 重写 ===")
conv = get_session("t6_pronoun")
# 正确存入 2 个 user_mention 实体
conv.record_turn(
    question="002594和300750的关联方重合", intent="Q6",
    slots={"company_a": "002594", "company_b": "300750"},
    linked_entities=[
        {"stock_code": "002594", "name": "比亚迪"},
        {"stock_code": "300750", "name": "宁德时代"},
    ],
    result_entities=[{"name": "共同关联方1", "stock_code": "000001"},
                    {"name": "共同关联方2", "stock_code": "000002"}])

# 测试代词指代(应触发澄清)
for q in ["它的担保", "这家公司呢", "它的关联方"]:
    r = resolve(q, conv, False, conn)
    resolved = r.get("resolved", False)
    clarify = r.get("clarify", "")
    candidates = len(r.get("candidates", []))
    ok = not resolved and bool(clarify) and candidates >= 2
    print(f"  [{'PASS' if ok else 'FAIL'}] {q:15s} resolved={resolved} clarify={clarify[:40]} cands={candidates}")

# T7: 序数通配自动化
print("\n=== T7: 序数通配自动化 ===")
conv2 = get_session("t7_ordinal")
conv2.record_turn(question="002594的关联方", intent="Q1",
    slots={"company": "002594"},
    linked_entities=[{"stock_code": "002594", "name": "比亚迪"}],
    result_entities=[{"name": f"关联方{i}", "stock_code": f"00000{i}"} for i in range(5)])

# 第一~第五(应成功)
for i, cn in enumerate(["第一个", "第二个", "第三个", "第四个", "第五个"]):
    r = resolve(cn, conv2, False, conn)
    ok = r.get("resolved") and r["entity"].get("name") == f"关联方{i}"
    print(f"  [{'PASS' if ok else 'FAIL'}] {cn:8s} -> {r.get('entity',{}).get('name','None')}")

# 阿拉伯数字
r = resolve("第2个", conv2, False, conn)
ok = r.get("resolved") and r["entity"].get("name") == "关联方1"
print(f"  [{'PASS' if ok else 'FAIL'}] 第2个(阿拉伯) -> {r.get('entity',{}).get('name','None')}")

# 最后一个
r = resolve("最后那个", conv2, False, conn)
ok = r.get("resolved") and r["entity"].get("name") == "关联方4"
print(f"  [{'PASS' if ok else 'FAIL'}] 最后那个 -> {r.get('entity',{}).get('name','None')}")

# 越界(应澄清)
r = resolve("第十个", conv2, False, conn)
ok = not r.get("resolved") and bool(r.get("clarify"))
print(f"  [{'PASS' if ok else 'FAIL'}] 第十个(越界) -> clarify={r.get('clarify','')[:40]}")

# 上一轮无结果列表
conv3 = get_session("t7_no_results")
conv3.record_turn(question="王传福控制哪些公司", intent="Q3",
    slots={"entity": "王传福"},
    linked_entities=[{"stock_code": "002594", "name": "王传福"}],
    result_entities=[])  # 无结果列表
r = resolve("第一个", conv3, False, conn)
ok = not r.get("resolved") and bool(r.get("clarify"))
print(f"  [{'PASS' if ok else 'FAIL'}] 无结果列表时序数 -> clarify={r.get('clarify','')[:40]}")

conn.close()
