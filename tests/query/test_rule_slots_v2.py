"""T3+T4: 词典匹配改造后重测覆盖率/正确率 + 四类口径统计。

用与上轮相同的测试用例, 对照改造前后。
"""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.query.rule_slots import rule_extract

DB = "rpscope.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# 与上轮相同的 41 条测试用例
TESTS = [
    # Q1 关联方
    ("Q1", "002594的关联方有哪些", "002594", {"company": "002594"}, "标准代码"),
    ("Q1", "比亚迪的关联方", "002594", {"company": "002594"}, "简称(词典应匹配)"),
    ("Q1", "300750关联方", "300750", {"company": "300750"}, "纯代码无动词"),
    ("Q1", "茅台的关联方清单", "600519", {"company": "600519"}, "简称+清单"),
    ("Q1", "关联方有哪些", "002594", {"company": "002594"}, "省略主语+context"),
    ("Q1", "关联方", "600036", {"company": "600036"}, "极简+context"),
    ("Q1", "宁德时代的关联方", "", {"company": "300750"}, "简称无context"),
    ("Q1", "002594的关联方 只看高置信度的", "002594", {"company": "002594"}, "带过滤词"),
    ("Q1", "中国平安的关联方", "", {"company": "601318"}, "公司名不含后缀(词典应匹配)"),
    ("Q1", "中国平安保险的关联方", "", None, "公司名含保险(可能歧义)"),
    # Q2 关系路径
    ("Q2", "002594和300750什么关系", "002594", {"entity_a": "002594", "entity_b": "300750"}, "双代码"),
    ("Q2", "比亚迪和宁德时代有关联吗", "002594", {"entity_a": "002594", "entity_b": "300750"}, "双简称(应止于实体名)"),
    ("Q2", "600519和000858的关系路径", "600519", {"entity_a": "600519", "entity_b": "000858"}, "双代码"),
    ("Q2", "王传福和融捷投资什么关系", "002594", None, "人+机构"),
    ("Q2", "宁德时代和比亚迪什么关系", "300750", {"entity_a": "300750", "entity_b": "002594"}, "双简称反向"),
    # Q3 反向查询 — 人名匹配返回 entity_id(整数), 不再返回名字字符串
    ("Q3", "王传福控制哪些公司", "002594", "nonempty", "人名3字+控制"),
    ("Q3", "曾毓群控制的公司有哪些", "300750", "nonempty", "人名3字"),
    ("Q3", "李平在哪些公司任职", "002594", "nonempty", "人名2字+任职"),
    ("Q3", "融捷投资持有哪些上市公司", "002594", "nonempty", "机构+持有"),
    ("Q3", "王传福担任哪些公司的董事", "002594", "nonempty", "人名+担任"),
    ("Q3", "欧阳锋控制哪些公司", "", "nonempty", "4字人名"),
    ("Q3", "王传福控制哪些公司的董事", "002594", "nonempty", "人名+控制+董事粘连"),
    # Q4 公司角色
    ("Q4", "002594的前十大股东", "002594", {"company": "002594", "role_type": "holder"}, "代码+前十大股东"),
    ("Q4", "比亚迪的实际控制人是谁", "002594", {"company": "002594", "role_type": "controller"}, "简称+实控人"),
    ("Q4", "300750的董监高", "300750", {"company": "300750", "role_type": "all"}, "代码+董监高"),
    ("Q4", "茅台的股东", "600519", {"company": "600519", "role_type": "holder"}, "简称+股东"),
    ("Q4", "前十大股东", "002594", {"company": "002594", "role_type": "holder"}, "省略+context"),
    ("Q4", "比亚迪股东", "", {"company": "002594", "role_type": "holder"}, "公司名+股东无分隔"),
    ("Q4", "宁德时代实控人", "", {"company": "300750", "role_type": "controller"}, "公司名+实控人无分隔"),
    # Q5 风险事件
    ("Q5", "002594的担保情况", "002594", {"company": "002594", "event_types": ["guarantee"]}, "代码+担保"),
    ("Q5", "比亚迪的风险事件", "002594", {"company": "002594"}, "简称+风险事件无特定类型"),
    ("Q5", "300750的诉讼", "300750", {"company": "300750", "event_types": ["lawsuit"]}, "代码+诉讼"),
    ("Q5", "茅台有没有质押", "600519", {"company": "600519", "event_types": ["pledge"]}, "简称+质押"),
    ("Q5", "担保情况", "002594", {"company": "002594", "event_types": ["guarantee"]}, "省略+context+担保"),
    # Q6 关联方重合 — "茅台"注册名是"贵州茅台", 词典匹配需用注册名
    ("Q6", "002594和300750的关联方重合", "002594", {"company_a": "002594", "company_b": "300750"}, "双代码"),
    ("Q6", "比亚迪和宁德时代有哪些共同关联方", "002594", {"company_a": "002594", "company_b": "300750"}, "双简称"),
    ("Q6", "贵州茅台和五粮液的关联方交集", "600519", {"company_a": "600519", "company_b": "000858"}, "注册名简称"),
    # 补充
    ("Q1", "中国平安的关联方", "", {"company": "601318"}, "地名前缀中国(词典匹配)"),
    ("Q4", "招商银行的股东", "", {"company": "600036", "role_type": "holder"}, "地名+银行后缀"),
    ("Q1", "这个股的关联方", "002594", {"company": "002594"}, "这个股→context"),
    ("Q1", "关联方", "", None, "极简无context→应失败"),
]

# 四类口径
CAT_HIT_OK = 0       # 规则命中且正确
CAT_HIT_WRONG = 0     # 规则命中但抽错(真静默错误)
CAT_MISS_OK = 0       # 规则未命中, 兜底成功
CAT_MISS_FAIL = 0     # 规则未命中, 兜底失败

by_intent = {}
silent_errors = []

for intent, q, ctx, expected, note in TESTS:
    by_intent.setdefault(intent, {"total": 0, "hit_ok": 0, "hit_wrong": 0, "miss_ok": 0, "miss_fail": 0})
    by_intent[intent]["total"] += 1

    result = rule_extract(intent, q, conn, ctx)

    if result is None:
        # 规则未命中
        if expected is None:
            CAT_MISS_FAIL += 1
            by_intent[intent]["miss_fail"] += 1
            status = "MISS_FAIL(expected)"
        else:
            # 期望成功但未抽取 → 看是否有 context 兜底
            if ctx:
                CAT_MISS_OK += 1
                by_intent[intent]["miss_ok"] += 1
                status = "MISS_OK(context)"
            else:
                CAT_MISS_FAIL += 1
                by_intent[intent]["miss_fail"] += 1
                status = "MISS_FAIL"
    elif expected is None:
        # 规则抽取了但预期失败
        CAT_HIT_OK += 1
        by_intent[intent]["hit_ok"] += 1
        status = "HIT_OK(unexpected)"
    else:
        # 规则抽取了, 检查正确性
        # 去掉 _clarify 等内部字段
        clean = {k: v for k, v in result.items() if not k.startswith("_")}
        if expected == "nonempty":
            # 只检查槽位非空
            ok = bool(clean.get("entity"))
        else:
            ok = True
            for k, v in expected.items():
                if clean.get(k) != v:
                    ok = False
                    silent_errors.append(f"  [{intent}] {note}: slot '{k}' expected='{v}' got='{clean.get(k)}' | {q}")
                    break
        if ok:
            CAT_HIT_OK += 1
            by_intent[intent]["hit_ok"] += 1
            status = "HIT_OK"
        else:
            CAT_HIT_WRONG += 1
            by_intent[intent]["hit_wrong"] += 1
            status = "HIT_WRONG"

    print(f"  [{status:20s}] {intent:3s} {note:30s} | {q[:35]}")

total = len(TESTS)
print(f"\n{'='*70}")
print(f"总计: {total} 条")
print(f"\n=== 四类口径 ===")
print(f"  规则命中且正确:  {CAT_HIT_OK}/{total} = {CAT_HIT_OK/total*100:.0f}%")
print(f"  规则命中但抽错:  {CAT_HIT_WRONG}/{total} = {CAT_HIT_WRONG/total*100:.0f}%")
print(f"  规则未命中兜底成功: {CAT_MISS_OK}/{total} = {CAT_MISS_OK/total*100:.0f}%")
print(f"  规则未命中兜底失败: {CAT_MISS_FAIL}/{total} = {CAT_MISS_FAIL/total*100:.0f}%")
print(f"\n覆盖率(命中): {(CAT_HIT_OK+CAT_HIT_WRONG)}/{total} = {(CAT_HIT_OK+CAT_HIT_WRONG)/total*100:.0f}%")
print(f"正确率(命中分母): {CAT_HIT_OK}/{(CAT_HIT_OK+CAT_HIT_WRONG)} = {CAT_HIT_OK/(CAT_HIT_OK+CAT_HIT_WRONG)*100:.0f}%" if (CAT_HIT_OK+CAT_HIT_WRONG) > 0 else "N/A")

print(f"\n=== 按意图 ===")
for intent in sorted(by_intent):
    d = by_intent[intent]
    print(f"  {intent}: hit_ok={d['hit_ok']} hit_wrong={d['hit_wrong']} miss_ok={d['miss_ok']} miss_fail={d['miss_fail']}")

if silent_errors:
    print(f"\n静默错误 ({len(silent_errors)}):")
    for e in silent_errors:
        print(e)
else:
    print(f"\n静默错误: 0")

conn.close()
