"""P7 意图分类准确率测试 - 自建 20 条(文档要 100, 此处小集 demo)。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.agent.intent import classify

CASES = [
    ("002594的前十大股东是谁", "fact_query"),
    ("300750的实控人是谁", "fact_query"),
    ("600519公司基本信息", "fact_query"),
    ("000858的高管有哪些", "fact_query"),
    ("002594的董事和监事", "fact_query"),
    ("002594的关联方有哪些", "related_party"),
    ("列出300750的关联关系", "related_party"),
    ("002594的关联交易", "related_party"),
    ("002594和300750是什么关系", "relation_explain"),
    ("600519与000858有关系吗", "relation_explain"),
    ("002594和300750关联吗", "relation_explain"),
    ("002594有哪些风险事件", "open_qa"),
    ("分析一下300750的关联方情况", "open_qa"),
    ("这家公司有没有隐藏关联方", "open_qa"),
    ("002594的诉讼情况严重吗", "open_qa"),
    ("002594实控人和大股东", "fact_query"),
    ("帮我找002594的关联方", "related_party"),
    ("002594和000001关联吗", "relation_explain"),
    ("300750最近有什么公告", "open_qa"),
    ("002594的十大股东和实控人", "fact_query"),
]


def main():
    correct = 0
    wrong = []
    for q, expected in CASES:
        got = classify(q)
        if got == expected:
            correct += 1
        else:
            wrong.append((q, expected, got))
    print(f"意图分类准确率 {correct}/{len(CASES)} = {correct/len(CASES)*100:.0f}%")
    for q, exp, got in wrong:
        print(f"  WRONG: '{q[:30]}' expected={exp} got={got}")


if __name__ == "__main__":
    main()
