"""normalize/name.py 单元测试 - 20+ case 覆盖全半角/空白/后缀剥离/基金管理人提取。"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.normalize.name import (
    fund_manager,
    fund_match_key,
    is_channel_name,
    normalize_name,
    normalize_person,
    org_match_key,
)


# ---- normalize_name ----
def test_fullwidth_digits_letters():
    assert normalize_name("１２３ＡＢＣ") == "123ABC"

def test_fullwidth_space_u3000():
    assert normalize_name("\u3000中国\u3000") == "中国"

def test_collapse_all_whitespace():
    assert normalize_name("  中国 工商 \n银行 \t") == "中国工商银行"

def test_fullwidth_hyphen_to_half():
    assert normalize_name("A－B") == "A-B"

def test_em_dash_to_half():
    assert normalize_name("A—B") == "A-B"   # U+2014
    assert normalize_name("A–B") == "A-B"   # U+2013

def test_empty_and_none():
    assert normalize_name("") == ""
    assert normalize_name(None) == ""

def test_cjk_unchanged():
    assert normalize_name("中国工商银行股份有限公司") == "中国工商银行股份有限公司"


# ---- org_match_key ----
def test_strip_gufen_youxiang():
    assert org_match_key("中国工商银行股份有限公司") == "中国工商银行"

def test_strip_youxiang():
    assert org_match_key("XX有限公司") == "XX"

def test_strip_youxianzeren():
    assert org_match_key("XX有限责任公司") == "XX"

def test_strip_jituan_youxiang_iterative():
    assert org_match_key("XXX集团有限公司") == "XXX"

def test_strip_jituan_only():
    assert org_match_key("XX集团") == "XX"

def test_no_suffix_unchanged():
    assert org_match_key("中国工商银行") == "中国工商银行"

def test_fullwidth_suffix_stripped():
    assert org_match_key("中国工商银行股份有限公司") == "中国工商银行"


# ---- fund_manager / fund_match_key ----
def test_fund_manager_nanfang():
    assert fund_manager("招商银行股份有限公司-南方中证1000交易型开放式指数证券投资基金") == "南方"

def test_fund_manager_huataibairui():
    assert fund_manager("中国工商银行股份有限公司-华泰柏瑞沪深300交易型开放式指数证券投资基金") == "华泰柏瑞"

def test_fund_manager_yifangda():
    assert fund_manager("中国农业银行股份有限公司-易方达基金管理有限公司") == "易方达"

def test_fund_manager_unknown_none():
    assert fund_manager("某未知基金-某某1号产品") is None

def test_fund_match_key_known_manager():
    assert fund_match_key("招商银行股份有限公司-南方中证1000交易型开放式指数证券投资基金") == "FUND:南方"

def test_fund_match_key_fallback_custodian():
    assert fund_match_key("某未知基金-某某1号产品") == "CUST:某未知基金"


# ---- normalize_person ----
def test_person_strip_spaces():
    assert normalize_person(" 张 伟 ") == "张伟"

def test_person_fullwidth():
    assert normalize_person("张伟") == "张伟"


# ---- is_channel_name ----
def test_is_channel_exact():
    exact = {"香港中央结算有限公司"}
    pats = [re.compile(p) for p in [".*ETF.*"]]
    assert is_channel_name("香港中央结算有限公司", exact, pats) is True

def test_is_channel_pattern_etf_chinese():
    exact: set[str] = set()
    pats = [re.compile(p) for p in [".*交易型开放式指数.*"]]
    assert is_channel_name("招商银行股份有限公司-南方中证1000交易型开放式指数证券投资基金", exact, pats) is True

def test_is_channel_false_real_holder():
    exact = {"香港中央结算有限公司"}
    pats = [re.compile(p) for p in [".*ETF.*"]]
    assert is_channel_name("比亚迪股份有限公司", exact, pats) is False
