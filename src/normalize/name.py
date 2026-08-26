"""名称规范化与机构归并 - P1.3

- 全半角统一（NFKC）+ 去所有空白 + 连字符归一
- 机构名后缀剥离生成匹配键（有限公司/股份有限公司/集团/...）
- 基金/资管产品名解析：提取管理人（南方/华夏/华泰柏瑞/...）
"""
from __future__ import annotations

import re
import unicodedata

# 公司后缀（长短不等地剥，按最长匹配逐轮剥离）
ORG_SUFFIXES = [
    "股份有限公司", "股份公司", "有限责任公司", "有限公司",
    "股份合作公司", "合伙企业", "集团", "总公司", "分公司", "公司",
]

# 基金管理人 starter list（持续扩充；P2 起配合人工维护）
FUND_MANAGERS = [
    "华夏", "南方", "易方达", "嘉实", "富国", "华泰柏瑞", "工银瑞信",
    "招商", "博时", "汇添富", "广发", "景顺长城", "兴全", "银华",
    "鹏华", "中欧", "交银", "国泰", "华安", "大成", "长信", "诺安",
    "融通", "万家", "前海开源", "国泰基金",
]

_DASH = re.compile(r"[\u2010-\u2015\u2212\uFF0D]")


def normalize_name(s: str | None) -> str:
    """全半角统一 + 去所有空白 + 连字符归一为 '-'。

    中文实体名/人名内部不应有空白，故全去。NFKC 把全角数字字母/空格转半角，
    但不影响 CJK 汉字本身（繁简不做，需 opencc，P2 视需要再加）。
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = _DASH.sub("-", s)
    s = re.sub(r"\s+", "", s)
    return s.strip()


def normalize_person(s: str | None) -> str:
    """人名归一：同 normalize_name，但不剥任何后缀。"""
    return normalize_name(s)


def org_match_key(s: str | None) -> str:
    """机构匹配键：normalize 后逐轮剥最长公司后缀，最多 3 轮。

    '中国工商银行股份有限公司' -> '中国工商银行'
    'XXX集团有限公司' -> 'XXX'
    """
    s = normalize_name(s)
    for _ in range(3):
        longest = None
        for suf in ORG_SUFFIXES:
            if s.endswith(suf) and len(s) > len(suf):
                if longest is None or len(suf) > len(longest):
                    longest = suf
        if longest is None:
            break
        s = s[: -len(longest)]
    return s


def fund_manager(s: str | None) -> str | None:
    """从基金/资管产品名提取管理人。

    常见格式：'托管银行股份有限公司-XX管理人XXX基金' 或 'XX基金－YY证券－ZZ1号计划'
    在非首段（首段通常是托管行）里找已知管理人前缀；未识别返回 None。
    """
    s = normalize_name(s)
    if not s:
        return None
    parts = re.split(r"[-]", s)
    for part in parts[1:]:
        for mgr in FUND_MANAGERS:
            if part.startswith(mgr):
                return mgr
    for mgr in FUND_MANAGERS:
        if s.startswith(mgr):
            return mgr
    return None


def fund_match_key(s: str | None) -> str:
    """基金/资管产品匹配键：识别到管理人则按管理人归并，否则回退到托管行 org_key。"""
    mgr = fund_manager(s)
    if mgr:
        return f"FUND:{mgr}"
    parts = re.split(r"[-]", normalize_name(s))
    base = org_match_key(parts[0]) if parts and parts[0] else org_match_key(s)
    return f"CUST:{base}"


def is_channel_name(name: str, exact: set[str], patterns: list[re.Pattern]) -> bool:
    """通道判定（复用 config 的 exact 名单 + 正则模式）。"""
    if not name:
        return False
    n = normalize_name(name)
    if n in {normalize_name(x) for x in exact}:
        return True
    # 对原名与归一名都试一次模式
    for cand in (name, n):
        if any(p.search(cand) for p in patterns):
            return True
    return False
