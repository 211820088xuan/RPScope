"""T5: 多轮对话测试集 40 组。

每组 2-4 轮, 覆盖: 代词指代(含跨轮)、序数指代(含越界)、
名称片段、省略主语、显式覆盖、指代歧义、焦点栈空、长对话。
"""
import sys, requests, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.query.conversation import get_session, _sessions, _session_ts
from src.query.coreference import resolve
from src.query.rule_slots import rule_extract
from src.store.db import Store
import sqlite3

DB = "rpscope.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# 模拟多轮对话, 每组: [(question, context_code, expected_coref_type, expected_entity_or_clarify)]
GROUPS = [
    # === 代词指代 (10组) ===
    [("002594的关联方有哪些", "002594", "none", None),
     ("它的担保情况呢", "", "pronoun", "002594")],

    [("比亚迪的前十大股东", "002594", "none", None),
     ("它的实控人是谁", "", "pronoun", "002594")],

    [("300750的关联方", "300750", "none", None),
     ("这家公司的董监高", "", "pronoun", "300750")],

    [("600519的股东", "600519", "none", None),
     ("它的诉讼情况", "", "pronoun", "600519")],

    [("002594的关联方有哪些", "002594", "none", None),
     ("比亚迪的担保情况", "", "none", None),
     ("它的质押呢", "", "pronoun", "002594")],  # 跨轮: 第1轮提到002594, 第3轮"它"

    [("比亚迪的关联方", "002594", "none", None),
     ("该公司的实控人", "", "pronoun", "002594")],

    [("宁德时代的关联方", "300750", "none", None),
     ("其前十大股东", "", "pronoun", "300750")],

    [("002594的关联方", "002594", "none", None),
     ("它的关联方", "", "pronoun", "002594"),
     ("它的担保", "", "pronoun", "002594")],

    [("600036的关联方", "600036", "none", None),
     ("这只股的风险事件", "", "pronoun", "600036")],

    [("茅台的关联方", "600519", "none", None),
     ("它的质押情况", "", "pronoun", "600519")],

    # === 序数指代 (8组) ===
    [("002594的关联方有哪些", "002594", "none", None),
     ("第二个是怎么关联的", "", "ordinal", "result_1")],

    [("比亚迪的关联方", "002594", "none", None),
     ("第一个呢", "", "ordinal", "result_0")],

    [("300750的关联方", "300750", "none", None),
     ("最后那个呢", "", "ordinal", "result_last")],

    [("002594的关联方", "002594", "none", None),
     ("第三个", "", "ordinal", "result_2")],

    [("比亚迪的关联方", "002594", "none", None),
     ("前面那个公司", "", "ordinal", "result_0")],

    # 序数越界
    [("002594的关联方", "002594", "none", None),
     ("第十个呢", "", "ordinal_clarify", "clarify")],

    # 上一轮无结果列表
    [("王传福控制哪些公司", "002594", "none", None),
     ("第一个呢", "", "ordinal_clarify", "clarify")],

    [("比亚迪的实控人", "002594", "none", None),
     ("第二个", "", "ordinal_clarify", "clarify")],

    # === 名称片段 (4组) ===
    [("002594和300750的关联方重合", "002594", "none", None),
     ("宁德时代那个呢", "", "name_fragment", "300750")],

    [("002594和300750什么关系", "002594", "none", None),
     ("比亚迪的担保", "", "none", "002594")],

    # === 省略主语 (6组) ===
    [("002594的关联方", "002594", "none", None),
     ("关联方有哪些", "", "omission", "002594")],

    [("比亚迪的前十大股东", "002594", "none", None),
     ("担保情况", "", "omission", "002594")],

    [("300750的关联方", "300750", "none", None),
     ("实控人是谁", "", "omission", "300750")],

    [("600519的关联方", "600519", "none", None),
     ("董监高", "", "omission", "600519")],

    [("002594的关联方", "002594", "none", None),
     ("质押情况", "", "omission", "002594")],

    # 焦点栈空(首次就说省略句)
    [("关联方有哪些", "", "omission_clarify", "clarify")],

    # === 显式覆盖 (4组) ===
    [("002594的关联方", "002594", "none", None),
     ("那茅台呢", "", "override", "600519")],

    [("比亚迪的关联方", "002594", "none", None),
     ("那宁德时代呢", "", "override", "300750")],

    [("300750的关联方", "300750", "none", None),
     ("那招商银行呢", "", "override", "600036")],

    [("002594的关联方", "002594", "none", None),
     ("那五粮液呢", "", "override", "000858")],

    # === 指代歧义 (2组) ===
    [("002594和300750的关联方重合", "002594", "none", None),
     ("它", "", "pronoun_ambiguous", "ambiguous")],

    [("比亚迪和宁德时代什么关系", "002594", "none", None),
     ("它的关联方", "", "pronoun_ambiguous", "ambiguous")],

    # === 长对话(超栈容量) (4组) ===
    [("002594的关联方", "002594", "none", None),
     ("它的担保", "", "pronoun", "002594"),
     ("比亚迪的关联方", "", "none", None),
     ("那茅台呢", "", "override", "600519"),
     ("它的担保", "", "pronoun", "600519"),
     ("那002594呢", "", "override", "002594"),
     ("它的质押", "", "pronoun", "002594")],  # 7轮, 测试栈淘汰

    [("比亚迪的关联方", "002594", "none", None),
     ("那茅台的关联方", "", "override", "600519"),
     ("那宁德时代呢", "", "override", "300750"),
     ("那五粮液呢", "", "override", "000858"),
     ("它的担保", "", "pronoun", "000858")],  # 5轮

    [("002594的关联方", "002594", "none", None),
     ("那300750呢", "", "override", "300750"),
     ("那600519呢", "", "override", "600519"),
     ("那000858呢", "", "override", "000858"),
     ("它的关联方", "", "pronoun", "000858")],

    [("比亚迪的关联方", "002594", "none", None),
     ("它的担保", "", "pronoun", "002594"),
     ("那宁德时代呢", "", "override", "300750"),
     ("它的质押", "", "pronoun", "300750"),
     ("那茅台呢", "", "override", "600519")],

    # === 无指代(正常多轮) (2组) ===
    [("002594的关联方", "002594", "none", None),
     ("300750的担保情况", "300750", "none", None)],

    [("比亚迪的关联方", "002594", "none", None),
     ("宁德时代的实控人", "300750", "none", None),
     ("茅台的担保", "600519", "none", None)],
]

# 留出集 20 组
HOLDOUT = [
    # 代词
    [("600036的关联方", "600036", "none", None), ("它的质押", "", "pronoun", "600036")],
    [("招商银行的前十大股东", "600036", "none", None), ("该公司的实控人", "", "pronoun", "600036")],
    # 序数
    [("比亚迪的关联方", "002594", "none", None), ("第二个", "", "ordinal", "result_1")],
    [("002594的关联方", "002594", "none", None), ("最后那个呢", "", "ordinal", "result_last")],
    # 省略
    [("300750的关联方", "300750", "none", None), ("关联方有哪些", "", "omission", "300750")],
    [("茅台的股东", "600519", "none", None), ("担保呢", "", "omission", "600519")],
    # 显式覆盖
    [("002594的关联方", "002594", "none", None), ("那宁德时代呢", "", "override", "300750")],
    [("比亚迪的关联方", "002594", "none", None), ("那招商银行呢", "", "override", "600036")],
    # 焦点栈空
    [("担保情况", "", "omission_clarify", "clarify")],
    [("实控人是谁", "", "omission_clarify", "clarify")],
    # 序数越界
    [("比亚迪的关联方", "002594", "none", None), ("第十个", "", "ordinal_clarify", "clarify")],
    # 长对话
    [("002594的关联方", "002594", "none", None), ("它的担保", "", "pronoun", "002594"),
     ("那茅台呢", "", "override", "600519"), ("它的质押", "", "pronoun", "600519")],
    # 无指代
    [("比亚迪的关联方", "002594", "none", None), ("300750的担保", "300750", "none", None)],
    # 代词跨轮
    [("002594的关联方", "002594", "none", None), ("比亚迪的担保", "", "none", None),
     ("它的质押", "", "pronoun", "002594")],
    # 歧义
    [("002594和300750什么关系", "002594", "none", None), ("它的关联方", "", "pronoun_ambiguous", "ambiguous")],
    # 名称片段
    [("002594和300750的关联方重合", "002594", "none", None), ("宁德时代那个呢", "", "name_fragment", "300750")],
    # 省略连续
    [("002594的关联方", "002594", "none", None), ("担保情况", "", "omission", "002594"),
     ("质押呢", "", "omission", "002594")],
    # 代词+显式混合
    [("002594的关联方", "002594", "none", None), ("那它的担保呢", "", "pronoun", "002594")],
    # 序数+省略
    [("比亚迪的关联方", "002594", "none", None), ("第一个", "", "ordinal", "result_0"),
     ("担保情况", "", "omission", None)],  # 第1个指代解到 result_0, 第3轮省略应指代上一轮主体
    # 长对话超栈
    [("002594的关联方", "002594", "none", None), ("那300750呢", "", "override", "300750"),
     ("那600519呢", "", "override", "600519"), ("那000858呢", "", "override", "000858"),
     ("它的担保", "", "pronoun", "000858")],
]


def run_groups(groups, label):
    correct = 0
    total = 0
    errors = []
    clarifies = 0
    correct_clarifies = 0
    by_type = {}

    for gi, group in enumerate(groups):
        sid = f"{label}_{gi}"
        conv = get_session(sid)

        for ti, (q, ctx, exp_type, exp_entity) in enumerate(group):
            total += 1
            # 模拟: 分类 + 槽位抽取(检测是否有实体)
            test_slots = rule_extract("Q1", q, conn, ctx)
            has_entity = test_slots is not None and bool(test_slots.get("company"))

            # 如果有实体但不是Q1, 仍检查指代
            if not has_entity:
                test_slots = rule_extract("Q4", q, conn, ctx)
                has_entity = test_slots is not None and bool(test_slots.get("company"))

            coref = resolve(q, conv, has_entity, conn)
            ctype = "none"
            cresolved = False
            if coref.get("resolved"):
                ctype = coref.get("source", "")
                cresolved = True
            elif coref.get("clarify"):
                ctype = "clarify"
                cresolved = False
            elif coref.get("no_coreference"):
                ctype = "none"

            # 判定
            if exp_type == "none":
                ok = ctype == "none"
            elif exp_type == "pronoun":
                ok = cresolved and "stack" in ctype
            elif exp_type == "ordinal":
                ok = cresolved and "ordinal" in ctype
            elif exp_type == "ordinal_clarify":
                ok = not cresolved and coref.get("clarify")
                if ok:
                    clarifies += 1
                    correct_clarifies += 1
            elif exp_type == "omission":
                ok = cresolved and "omission" in ctype
            elif exp_type == "omission_clarify":
                ok = not cresolved and coref.get("clarify")
                if ok:
                    clarifies += 1
                    correct_clarifies += 1
            elif exp_type == "override":
                # 显式覆盖: 问句含新实体, 规则槽位应抽取到, 指代不应触发
                ok = ctype == "none" and has_entity
            elif exp_type == "name_fragment":
                ok = cresolved and "name_fragment" in ctype
            elif exp_type == "pronoun_ambiguous":
                # 歧义: 要么澄清, 要么解到任一(算错因为不确定)
                ok = not cresolved and coref.get("clarify")
                if ok:
                    clarifies += 1
                    correct_clarifies += 1
            else:
                ok = False

            # 错误消解(最危险): 解到了错误实体且未澄清
            error_resolution = False
            if cresolved and not ok and exp_type not in ("none", "override", "ordinal_clarify", "omission_clarify", "pronoun_ambiguous"):
                error_resolution = True
                errors.append(f"  组{gi}轮{ti}: exp={exp_type} got={ctype} entity={coref.get('entity',{}).get('name','')} | {q[:30]}")

            if ok:
                correct += 1

            by_type.setdefault(exp_type, {"total":0, "ok":0})
            by_type[exp_type]["total"] += 1
            if ok:
                by_type[exp_type]["ok"] += 1

            # 模拟焦点栈更新(简化: 只存用户提及的公司)
            if has_entity and test_slots and test_slots.get("company"):
                code = test_slots["company"]
                conv.record_turn(question=q, intent="Q1", slots={"company": code},
                                linked_entities=[{"stock_code": code, "name": code}],
                                result_entities=[{"name": f"关联方{i}", "stock_code": f"00000{i}"} for i in range(5)])
            elif cresolved and coref.get("entity"):
                e = coref["entity"]
                conv.record_turn(question=q, intent="Q1", slots={"company": e.get("stock_code","")},
                                linked_entities=[{"stock_code": e.get("stock_code",""), "name": e.get("name","")}],
                                result_entities=[{"name": f"关联方{i}", "stock_code": f"00000{i}"} for i in range(5)])
            else:
                conv.record_turn(question=q, intent="Q1", slots={}, linked_entities=[], result_entities=[])

    print(f"\n=== {label} ===")
    print(f"总计: {correct}/{total} = {correct/total*100:.0f}%")
    print(f"澄清触发: {clarifies}, 正确澄清: {correct_clarifies}")
    print(f"错误消解(最危险): {len(errors)}")
    if errors:
        print("错误消解详情:")
        for e in errors:
            print(e)
    print(f"\n按类型:")
    for t in sorted(by_type):
        d = by_type[t]
        print(f"  {t:25s}: {d['ok']}/{d['total']}")
    return len(errors)


# 运行
print("=== 多轮对话测试 ===")
e1 = run_groups(GROUPS, "测试集(40组)")
print()
e2 = run_groups(HOLDOUT, "留出集(20组)")

print(f"\n{'='*60}")
print(f"测试集错误消解率: {e1}")
print(f"留出集错误消解率: {e2}")
conn.close()
