"""T3: 规则槽位抽取覆盖率 + 正确率 + 静默错误检测。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.query.rule_slots import rule_extract

# 测试用例: (intent, question, context_code, expected_slots, note)
# expected_slots=None 表示预期抽取失败(走 LLM 兜底)
TESTS = [
    # Q1 关联方
    ("Q1", "002594的关联方有哪些", "002594", {"company": "002594"}, "标准代码"),
    ("Q1", "比亚迪的关联方", "002594", {"company": "比亚迪"}, "简称"),
    ("Q1", "300750关联方", "300750", {"company": "300750"}, "纯代码无动词"),
    ("Q1", "茅台的关联方清单", "600519", {"company": "茅台"}, "简称+清单"),
    ("Q1", "关联方有哪些", "002594", {"company": "002594"}, "省略主语+context"),
    ("Q1", "关联方", "600036", {"company": "600036"}, "极简+context"),
    ("Q1", "宁德时代的关联方", "", {"company": "宁德时代"}, "简称无context"),
    ("Q1", "002594的关联方 只看高置信度的", "002594", {"company": "002594"}, "带过滤词"),
    # Q1 静默错误风险: 公司名含数字
    ("Q1", "中国平安的关联方", "", {"company": "中国平安"}, "公司名不含有限公司后缀"),
    ("Q1", "中国平安保险的关联方", "", {"company": "中国平安保险"}, "公司名含保险后缀"),

    # Q2 关系路径
    ("Q2", "002594和300750什么关系", "002594", {"entity_a": "002594", "entity_b": "300750"}, "双代码"),
    ("Q2", "比亚迪和宁德时代有关联吗", "002594", {"entity_a": "比亚迪", "entity_b": "宁德时代"}, "双简称"),
    ("Q2", "600519和000858的关系路径", "600519", {"entity_a": "600519", "entity_b": "000858"}, "双代码"),
    ("Q2", "王传福和融捷投资什么关系", "002594", {"entity_a": "王传福", "entity_b": "融捷投资"}, "人+机构"),
    ("Q2", "宁德时代和比亚迪什么关系", "300750", {"entity_a": "宁德时代", "entity_b": "比亚迪"}, "双简称反向"),

    # Q3 反向查询
    ("Q3", "王传福控制哪些公司", "002594", {"entity": "王传福", "relation_type": "control"}, "人名3字+控制"),
    ("Q3", "曾毓群控制的公司有哪些", "300750", {"entity": "曾毓群", "relation_type": "control"}, "人名3字"),
    ("Q3", "李平在哪些公司任职", "002594", {"entity": "李平", "relation_type": "serve"}, "人名2字+任职"),
    ("Q3", "融捷投资持有哪些上市公司", "002594", {"entity": "融捷投资", "relation_type": "hold"}, "机构+持有"),
    ("Q3", "王传福担任哪些公司的董事", "002594", {"entity": "王传福", "relation_type": "serve"}, "人名+担任"),
    # 静默错误风险: 4字人名
    ("Q3", "欧阳锋控制哪些公司", "", {"entity": "欧阳锋", "relation_type": "control"}, "4字人名"),
    # 静默错误风险: 人名与角色词粘连
    ("Q3", "王传福控制哪些公司的董事", "002594", {"entity": "王传福", "relation_type": "control"}, "人名+控制+董事粘连"),

    # Q4 公司角色
    ("Q4", "002594的前十大股东", "002594", {"company": "002594", "role_type": "holder"}, "代码+前十大股东"),
    ("Q4", "比亚迪的实际控制人是谁", "002594", {"company": "比亚迪", "role_type": "controller"}, "简称+实控人"),
    ("Q4", "300750的董监高", "300750", {"company": "300750", "role_type": "all"}, "代码+董监高"),
    ("Q4", "茅台的股东", "600519", {"company": "茅台", "role_type": "holder"}, "简称+股东"),
    ("Q4", "前十大股东", "002594", {"company": "002594", "role_type": "holder"}, "省略+context"),
    # 静默错误风险: 公司名与角色词粘连
    ("Q4", "比亚迪股东", "", {"company": "比亚迪", "role_type": "holder"}, "公司名+股东无分隔"),
    ("Q4", "宁德时代实控人", "", {"company": "宁德时代", "role_type": "controller"}, "公司名+实控人无分隔"),

    # Q5 风险事件
    ("Q5", "002594的担保情况", "002594", {"company": "002594", "event_types": ["guarantee"]}, "代码+担保"),
    ("Q5", "比亚迪的风险事件", "002594", {"company": "比亚迪"}, "简称+风险事件无特定类型"),
    ("Q5", "300750的诉讼", "300750", {"company": "300750", "event_types": ["lawsuit"]}, "代码+诉讼"),
    ("Q5", "茅台有没有质押", "600519", {"company": "茅台", "event_types": ["pledge"]}, "简称+质押"),
    ("Q5", "担保情况", "002594", {"company": "002594", "event_types": ["guarantee"]}, "省略+context+担保"),

    # Q6 关联方重合
    ("Q6", "002594和300750的关联方重合", "002594", {"company_a": "002594", "company_b": "300750"}, "双代码"),
    ("Q6", "比亚迪和宁德时代有哪些共同关联方", "002594", {"company_a": "比亚迪", "company_b": "宁德时代"}, "双简称"),
    ("Q6", "茅台和五粮液的关联方交集", "600519", {"company_a": "茅台", "company_b": "五粮液"}, "双简称"),

    # 补充: 公司名含地名前缀
    ("Q1", "中国平安的关联方", "", {"company": "中国平安"}, "地名前缀中国"),
    ("Q4", "招商银行的股东", "", {"company": "招商银行", "role_type": "holder"}, "地名前缀招商+银行后缀"),

    # 补充: 应抽取失败(走LLM兜底)
    ("Q1", "这个股的关联方", "002594", {"company": "002594"}, "这个股→context"),
    ("Q1", "关联方", "", None, "极简无context→应失败"),
]


def run():
    by_intent = {}
    total = len(TESTS)
    coverage_ok = 0  # 抽取成功
    correct = 0      # 抽取正确
    silent_errors = []  # 静默错误

    for intent, q, ctx, expected, note in TESTS:
        by_intent.setdefault(intent, {"total": 0, "covered": 0, "correct": 0})

        result = rule_extract(intent, q, ctx)
        by_intent[intent]["total"] += 1

        if expected is None:
            # 预期失败
            if result is None:
                coverage_ok += 1
                by_intent[intent]["covered"] += 1
                correct += 1
                by_intent[intent]["correct"] += 1
                status = "OK(fail)"
            else:
                status = "UNEXPECTED_PASS"
                coverage_ok += 1
                by_intent[intent]["covered"] += 1
        elif result is None:
            # 预期成功但抽取失败
            status = "MISS(fallback)"
        else:
            coverage_ok += 1
            by_intent[intent]["covered"] += 1
            # 检查正确性
            ok = True
            for k, v in expected.items():
                if result.get(k) != v:
                    ok = False
                    silent_errors.append(f"  [{intent}] {note}: slot '{k}' expected='{v}' got='{result.get(k)}' | {q}")
                    break
            if ok:
                correct += 1
                by_intent[intent]["correct"] += 1
                status = "OK"
            else:
                status = "SILENT_ERROR"

        print(f"  [{status:15s}] {intent:3s} {note:25s} | {q[:30]}")

    print(f"\n{'='*70}")
    print(f"总计: {total} 条")
    print(f"覆盖率: {coverage_ok}/{total} = {coverage_ok/total*100:.0f}%")
    print(f"正确率: {correct}/{coverage_ok} = {correct/coverage_ok*100:.0f}% (覆盖率分母)")
    print(f"正确率: {correct}/{total} = {correct/total*100:.0f}% (总分母)")
    print(f"\n按意图:")
    for intent in sorted(by_intent):
        d = by_intent[intent]
        cov = d["covered"]/d["total"]*100 if d["total"] else 0
        acc = d["correct"]/d["covered"]*100 if d["covered"] else 0
        print(f"  {intent}: 覆盖 {d['covered']}/{d['total']}={cov:.0f}% 正确 {d['correct']}/{d['covered']}={acc:.0f}%")

    if silent_errors:
        print(f"\n静默错误 ({len(silent_errors)}):")
        for e in silent_errors:
            print(e)
    else:
        print(f"\n静默错误: 0")

    return len(silent_errors) == 0


if __name__ == "__main__":
    run()
