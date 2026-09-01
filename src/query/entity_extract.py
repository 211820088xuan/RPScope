"""实体提取 — 先减法再判断。

Step 1: 词典最长匹配, 命中的实体从文本中移除(已知实体不是幻觉)
Step 2: 剩余文本找公司后缀, 从右向左取最短边界(遇到分隔词即停)
Step 3: 白名单比对用归一化键
Step 4: 仍未命中才标记可疑

+ 数值/日期/计数验证(无中文分词问题, 正则可靠)
"""
from __future__ import annotations
import re
import sqlite3
from src.normalize.name import normalize_name, org_match_key

_COMPANY_SUFFIXES = [
    "股份有限公司", "股份公司", "有限责任公司", "有限公司",
    "合伙企业", "集团", "控股", "科技", "投资", "实业",
    "发展", "银行", "证券", "保险", "医药", "能源", "矿业",
]

# 从右向左回溯时的停止词(遇到即停, 不纳入候选)
_STOP_WORDS = re.compile(r"的|是|包括|含有|和|与|跟|及|为|在|了|有|由|从|对|向|被|将|把|给|到|这|那|该|本|其|某|一")

# 非实体字符(标点/空格/换行)
_NON_ENTITY = re.compile(r"[，,。；;：:、\s（）()\"'""''\n\r]+")

# 通用泛指词
_GENERIC = {
    "该公司", "双方", "两家公司", "其中", "上述", "该股", "这只",
    "本系统", "系统", "数据", "结果", "查询", "以上", "如下",
    "有限公司", "股份有限公司", "集团", "控股", "科技",
    "投资", "实业", "发展", "银行", "证券", "保险",
}

# 数值/日期/计数正则
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_AMOUNT = re.compile(r"(\d[\d,.]*)\s*(万元|亿元|元|万|亿)")
_DATE = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月]?(\d{0,2})日?")
_COUNT = re.compile(r"(\d+)\s*(?:家|条|个|项|笔|起)")


def extract_suspected(text: str, conn: sqlite3.Connection = None,
                      known_matches: list = None) -> dict:
    """提取疑似实体(先减法) + 数值/日期。

    known_matches: 词典已匹配的实体列表(从调用方传入, 避免重复匹配)
    """
    # === Step 1: 词典匹配的已知实体从文本中移除 ===
    remaining = text
    if known_matches:
        for m in known_matches:
            remaining = remaining.replace(m, " " * len(m))

    # === Step 2: 剩余文本找公司后缀, 从右向左取最短 ===
    suspected_companies = []
    for suffix in _COMPANY_SUFFIXES:
        for m in re.finditer(re.escape(suffix), remaining):
            # 从后缀开始向左回溯, 遇到停止词/非实体字符即停
            start = m.start()
            for i in range(m.start() - 1, max(m.start() - 20, -1), -1):
                substr = remaining[i:m.start()]
                if _STOP_WORDS.search(substr) or _NON_ENTITY.search(substr):
                    start = i + 1
                    break
                start = i
            candidate = remaining[start:m.end()].strip()
            # 过滤: >=4字, 不在通用词表, 不重复
            cn = normalize_name(candidate)
            if len(candidate) >= 4 and cn not in _GENERIC and candidate not in suspected_companies:
                suspected_companies.append(candidate)

    # === 数值/日期/计数 ===
    pcts = [(float(v), "%") for v in _PCT.findall(text)]
    amounts = [(v, u) for v, u in _AMOUNT.findall(text)]
    dates = [f"{y}-{m.zfill(2)}-{d.zfill(2)}" if d else f"{y}-{m.zfill(2)}"
             for y, m, d in _DATE.findall(text)]
    counts = [(int(v), "count") for v in _COUNT.findall(text)]

    return {
        "companies": suspected_companies,
        "values": {
            "percentages": pcts,
            "amounts": amounts,
            "dates": dates,
            "counts": counts,
        },
    }


def extract_values_from_result(result: dict) -> dict:
    """从结构化结果中提取所有数值/日期, 供比对。
    除了正则, 还从已知字段直接提取(control_ratio/ratio/amount等)。"""
    import json
    text = json.dumps(result, ensure_ascii=False, default=str)

    # 正则提取
    pcts = [float(v) for v in _PCT.findall(text)]
    amounts = [(v, u) for v, u in _AMOUNT.findall(text)]
    dates = [f"{y}-{m.zfill(2)}-{d.zfill(2)}" if d else f"{y}-{m.zfill(2)}"
             for y, m, d in _DATE.findall(text)]

    # 直接从字段提取(比正则更全)
    # Q4/Q8 holders 的 ratio
    for key in ("a", "b"):
        for h in result.get("holders", {}).get(key, []):
            if isinstance(h, dict) and h.get("ratio") is not None:
                pcts.append(float(h["ratio"]))
    # Q8 controllers 的 control_ratio
    for key in ("a", "b"):
        for c in result.get("controllers", {}).get(key, []):
            if isinstance(c, dict) and c.get("control_ratio") is not None:
                pcts.append(float(c["control_ratio"]))
    # Q4 holders
    for h in result.get("holders", []):
        if isinstance(h, dict) and h.get("ratio") is not None:
            pcts.append(float(h["ratio"]))
    # Q8 basic market_cap
    for key in ("a", "b"):
        co = result.get("basic", {}).get(key, {})
        if isinstance(co, dict) and co.get("market_cap") is not None:
            pcts.append(float(co["market_cap"]))
    # events amount
    for key in ("a", "b"):
        ev = result.get("events", {}).get(key, {})
        if isinstance(ev, dict):
            for et, info in ev.items():
                if isinstance(info, dict) and info.get("total_amount"):
                    amounts.append((str(info["total_amount"]), "元"))

    # 计数: 列表长度 + 结构化结果中的 count 字段
    counts = []
    for key in ("parties", "results", "events", "holders"):
        val = result.get(key)
        if isinstance(val, list):
            counts.append(len(val))
    for key in ("a", "b"):
        holders = result.get("holders", {}).get(key, [])
        if isinstance(holders, list):
            counts.append(len(holders))
        dirs = result.get("directors", {})
        if isinstance(dirs, dict):
            if key == "a":
                counts.append(dirs.get("n_a", 0))
            else:
                counts.append(dirs.get("n_b", 0))
            counts.append(dirs.get("cross_count", 0))
    related = result.get("related", {})
    if isinstance(related, dict):
        counts.append(related.get("n_a", 0))
        counts.append(related.get("n_b", 0))
        counts.append(related.get("n_overlap", 0))
    events = result.get("events", {})
    if isinstance(events, dict):
        for key in ("a", "b"):
            ev = events.get(key, {})
            if isinstance(ev, dict):
                for et, info in ev.items():
                    if isinstance(info, dict):
                        counts.append(info.get("count", 0))
    if isinstance(events, list):
        counts.append(len(events))

    # 也从 JSON 中提取所有原始数字(作为金额/计数的候选)
    all_nums = re.findall(r"\d+(?:\.\d+)?", text)
    for num in all_nums:
        amounts.append((num, ""))  # 无单位的数字也作为候选
        counts.append(int(float(num)) if "." not in num else int(float(num)))

    return {"percentages": pcts, "amounts": amounts, "dates": dates, "counts": counts}
