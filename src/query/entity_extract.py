"""T1: 从自由文本提取疑似实体片段 — 不依赖是否已知。

反转检测逻辑: 提取所有疑似实体 → 不在词典/结构化结果中即可疑。

提取类型:
  疑似公司名: 以公司后缀结尾的连续中文片段(按句子分隔词切分)
  疑似人名: 2-4字中文, 出现在语境词附近
  疑似代码: 6位数字
  疑似数值: 百分比/金额/日期
"""
from __future__ import annotations
import re
from src.normalize.name import normalize_name

# 公司后缀
_COMPANY_SUFFIXES = [
    "股份有限公司", "股份公司", "有限责任公司", "有限公司",
    "合伙企业", "集团", "控股", "科技", "投资", "实业",
    "发展", "银行", "证券", "保险", "医药", "能源", "矿业",
]

# 句子分隔词(公司名边界检测用)
_DELIMITERS = re.compile(r"[，,。；;：:、\s（）()\"'""''\n]+|的|和|与|跟|及|包括|含有|其中|上述|前十大|股东|关联方|实控人|实际控制人|担任|任职|持有|控制|担保|诉讼|质押|风险事件|金额|比例|日期|报告期|数据来源")

# 人名语境词
_PERSON_CONTEXT = re.compile(r"(?:董事|监事|高管|总经理|总裁|董事长|实控人|实际控制人|持股|控制|担任|任职|担保人|质押人)")

# 百分比
_PCT = re.compile(r"(\d+(?:\.\d+)?%)")
# 金额
_AMOUNT = re.compile(r"(\d[\d,.]*\s*(?:万元|亿元|元|万|亿))")
# 日期
_DATE = re.compile(r"(\d{4}[-/年]\d{1,2}[-/月]\d{0,2}日?|\d{4}[-/]\d{1,2})")

# 通用词白名单(泛指/指代词, 不是实体)
_GENERIC_WORDS = {
    "该公司", "双方", "两家公司", "其中", "上述", "该股", "这只",
    "该公司", "本系统", "系统", "数据", "结果", "查询",
    "有限公司", "股份有限公司", "集团", "控股", "科技",
    "投资", "实业", "发展", "银行", "证券", "保险",
}


def extract_suspected_companies(text: str) -> list[str]:
    """提取疑似公司名: 按分隔词分割, 在每段中找公司后缀(不限于段尾)。"""
    results = []
    segments = _DELIMITERS.split(text)
    for seg in segments:
        seg = seg.strip()
        if len(seg) < 4:
            continue
        # 在段中找公司后缀(不限于段尾)
        for suffix in _COMPANY_SUFFIXES:
            idx = seg.find(suffix)
            if idx >= 0:
                # 截取从段首到后缀结尾
                candidate = seg[:idx + len(suffix)]
                if len(candidate) >= 4 and candidate not in _GENERIC_WORDS:
                    cn = normalize_name(candidate)
                    if cn not in _GENERIC_WORDS and candidate not in results:
                        results.append(candidate)
                break  # 一个段只取第一个后缀
    return results


def extract_suspected_persons(text: str) -> list[str]:
    """提取疑似人名: 极保守策略, 只提取高置信句式。

    仅匹配 "XXX担任董事/监事/高管" 和 "董事XXX" 句式。
    不匹配 "控制" (避免匹配"实际控制人"中的"控制")。
    """
    _BAD_ENDINGS = {"的", "是", "在", "了", "实际", "等", "中", "和", "其", "该"}
    results = []
    # "XXX担任/任职" 句式(不含"控制")
    for m in re.finditer(r"([\u4e00-\u9fff]{2,4})(?:担任|任职)", text):
        name = m.group(1)
        if any(name.endswith(bad) for bad in _BAD_ENDINGS):
            continue
        if name not in _GENERIC_WORDS and len(name) >= 2:
            results.append(name)
    return results


def extract_codes(text: str) -> list[str]:
    """6位代码。"""
    return re.findall(r"(?<!\d)(\d{6})(?!\d)", text)


def extract_values(text: str) -> list[str]:
    """百分比/金额/日期。"""
    return _PCT.findall(text) + _AMOUNT.findall(text) + _DATE.findall(text)


def extract_all(text: str) -> dict:
    """提取所有疑似实体。返回 {companies, persons, codes, values}。"""
    return {
        "companies": extract_suspected_companies(text),
        "persons": extract_suspected_persons(text),
        "codes": extract_codes(text),
        "values": extract_values(text),
    }
