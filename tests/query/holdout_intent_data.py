"""T1 留出集: 40 条意图分类测试, 独立于原测试集。

含: 口语化/省略主语、多意图混合、只给代码/只给名称、
不存在实体、歧义实体、错别字与简称变体。每类≥5条。
"""

HOLDOUT_INTENT = [
    # 口语化/省略主语 (7条)
    {"question": "关联方有哪些", "expected": "Q1", "note": "省略主语"},
    {"question": "前十大股东", "expected": "Q4", "note": "省略主语"},
    {"question": "担保情况", "expected": "Q5", "note": "省略主语"},
    {"question": "关联方", "expected": "Q1", "note": "极简"},
    {"question": "实控人是谁", "expected": "Q4", "note": "省略主语"},
    {"question": "有哪些诉讼", "expected": "Q5", "note": "省略主语"},
    {"question": "关联方重合", "expected": "Q6", "note": "省略主语+两公司"},

    # 多意图混合 (7条)
    {"question": "比亚迪的关联方里有没有担保", "expected": "Q1", "note": "关联方+担保混合→Q1优先"},
    {"question": "002594的关联方和诉讼", "expected": "Q1", "note": "关联方+诉讼混合"},
    {"question": "比亚迪的股东和关联方", "expected": "Q4", "note": "股东+关联方→Q4优先"},
    {"question": "002594的实控人和担保", "expected": "Q4", "note": "实控人+担保→Q4优先"},
    {"question": "300750的关联方和质押", "expected": "Q1", "note": "关联方+质押混合"},
    {"question": "比亚迪关联方和前十大股东", "expected": "Q1", "note": "关联方+股东混合"},
    {"question": "002594的董监高和担保", "expected": "Q4", "note": "董监高+担保→Q4优先"},

    # 只给代码不给名称 (5条)
    {"question": "002594关联方清单", "expected": "Q1", "note": "纯代码"},
    {"question": "600036的股东", "expected": "Q4", "note": "纯代码"},
    {"question": "000001的担保", "expected": "Q5", "note": "纯代码"},
    {"question": "300750和002594什么关系", "expected": "Q2", "note": "纯代码双实体"},
    {"question": "002475关联方", "expected": "Q1", "note": "纯代码"},

    # 只给名称不给代码 (5条)
    {"question": "立讯精密的关联方", "expected": "Q1", "note": "简称无代码"},
    {"question": "恒瑞医药的股东", "expected": "Q4", "note": "简称无代码"},
    {"question": "隆基绿能的担保", "expected": "Q5", "note": "简称无代码"},
    {"question": "东方财富和招商银行什么关系", "expected": "Q2", "note": "双简称"},
    {"question": "立讯精密的前十大股东", "expected": "Q4", "note": "简称无代码"},

    # 不存在的公司/人名 (6条)
    {"question": "999999的关联方", "expected": "Q1", "note": "不存在的代码"},
    {"question": "腾讯的关联方", "expected": "Q1", "note": "非A股公司"},
    {"question": "张三控制哪些公司", "expected": "Q3", "note": "不存在的人名"},
    {"question": "阿里巴巴的关联方", "expected": "Q1", "note": "非A股公司"},
    {"question": "999999的股东", "expected": "Q4", "note": "不存在代码"},
    {"question": "李四在哪些公司任职", "expected": "Q3", "note": "不存在的人名"},

    # 歧义实体(应触发澄清, 但意图分类应正确) (5条)
    {"question": "平安的关联方", "expected": "Q1", "note": "歧义简称"},
    {"question": "平安的股东", "expected": "Q4", "note": "歧义简称"},
    {"question": "万科的担保", "expected": "Q5", "note": "可能歧义"},
    {"question": "平安控制哪些公司", "expected": "Q3", "note": "歧义简称"},
    {"question": "万科和保利什么关系", "expected": "Q2", "note": "两个简称"},

    # 错别字与简称变体 (5条)
    {"question": "比亚迪的关联防", "expected": "Q1", "note": "错别字 防→方"},
    {"question": "宁德时代的股东", "expected": "Q4", "note": "正常"},
    {"question": "茅苔的关联方", "expected": "Q1", "note": "错别字 苔→台"},
    {"question": "比雅迪的担保", "expected": "Q5", "note": "错别字 雅→亚"},
    {"question": "宁德时代的关连方", "expected": "Q1", "note": "变体 关连→关联"},
]
