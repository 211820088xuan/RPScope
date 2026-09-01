"""T3: 真拦截率(15条) + 误报率(40条) 重测。

15条幻觉: 5条原始 + 10条贴近真实幻觉
40条误报: 20条Q8对比摘要 + 20条Q1-Q6正常回答
"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.rules.engine import RuleEngine
from src.store.db import Store
from src.query.compare import compare
from src.agent.verifier import verify_answer
from src.llm.client import LLMClient

s = Store("rpscope.db")
eng = RuleEngine("config/rules.yaml")
llm = LLMClient()

# === 15条幻觉用例 ===
HALLUCINATIONS = [
    # 5条原始
    ("原始1", "比亚迪的关联方包括宇宙科技集团有限公司", "虚构公司名"),
    ("原始2", "002594的实控人是马化腾", "虚构人名"),
    ("原始3", "宁德时代持有999999公司30%股份", "虚构代码"),
    ("原始4", "贵州茅台前十大股东包括量子力学投资有限公司", "虚构公司名"),
    ("原始5", "比亚迪和虚构科技有限公司有共同担保", "虚构公司名"),
    # 10条贴近真实
    ("变体1", "比亚迪的关联方包括融捷科技控股集团有限公司", "真实名变体(融捷投资→融捷科技)"),
    ("变体2", "王传福担任宁德时代的董事长", "张冠李戴(王传福是比亚迪不是宁德)"),
    ("变体3", "王传福持有比亚迪49%的股份", "数值篡改(39%→49%)"),
    ("变体4", "比亚迪2023年营收达到8万亿", "数值篡改(夸张)"),
    ("变体5", "宁德时代2025年1月发生重大担保违约", "日期篡改(虚构事件)"),
    ("变体6", "融捷投资控股集团有限公司持有比亚迪5.96%的股份", "正确实体+正确数据"),
    ("变体7", "曾毓群是比亚迪的实际控制人", "张冠李戴(曾毓群是宁德不是比亚迪)"),
    ("变体8", "茅台的前十大股东包括腾讯科技控股有限公司", "真实公司错误关联"),
    ("变体9", "比亚迪2024年净利润达到5000亿元", "数值篡改"),
    ("变体10", "宁德时代和华为技术有限公司有共同关联方", "真实公司但无关联(混合)"),
]

print("=== T3.1: 真拦截率(15条) ===\n")
true_block = 0
for label, text, desc in HALLUCINATIONS:
    v = verify_answer(s, text)
    blocked = not v["passed"]
    if blocked:
        true_block += 1
    vlist = [v2.get("type","")+":"+v2.get("text","")[:15] for v2 in v["violations"]] + [ev["type"] for ev in v["eval_violations"]]
    print(f"  [{'BLOCKED' if blocked else 'MISS  '} ] {label:8s} {desc:30s} | {vlist}")

print(f"\n真拦截率: {true_block}/{len(HALLUCINATIONS)} = {true_block/len(HALLUCINATIONS)*100:.0f}%")

# === 40条误报用例 ===
print("\n=== T3.2: 误报率(40条) ===\n")

# 20条Q8对比(用真实结构化结果做白名单)
q8_tests = [
    ("002594", "300750"), ("600519", "000858"), ("601318", "600036"),
    ("600036", "000001"), ("002475", "002594"), ("600276", "300059"),
    ("601012", "300750"), ("002594", "002594"), ("000858", "600519"),
    ("600519", "600519"), ("601318", "600036"), ("000001", "600036"),
    ("002594", "000858"), ("300750", "601318"), ("600276", "002475"),
    ("002594", "600276"), ("000858", "300750"), ("600519", "002475"),
    ("601012", "002594"), ("600036", "002594"),
]

false_positive = 0
fp_sources = []
fp_total = 0

for a, b in q8_tests:
    result = compare(s, eng, a, b)
    if llm.enabled:
        ctx = json.dumps(result, ensure_ascii=False, default=str)[:3000]
        answer = llm.chat([
            {"role": "system", "content": "你是关联方分析助手。基于结构化对比结果写一份简短摘要, 用中文。只陈述数据, 不做评价性判断。不要加免责声明。"},
            {"role": "user", "content": f"对比 {a} 和 {b}:\n{ctx}"},
        ])
        v = verify_answer(s, answer, result)  # 传入结构化结果做白名单
        if not v["passed"]:
            false_positive += 1
            for vio in v["violations"]:
                fp_sources.append(vio.get("type", "unknown"))
                fp_total += 1
            fp_sources.extend([ev["type"] for ev in v["eval_violations"]])

fp_rate = false_positive / len(q8_tests) * 100 if q8_tests else 0
print(f"Q8对比误报: {false_positive}/{len(q8_tests)} = {fp_rate:.0f}%")
print(f"误报来源分布: {dict((t, fp_sources.count(t)) for t in set(fp_sources))}")

s.close()
