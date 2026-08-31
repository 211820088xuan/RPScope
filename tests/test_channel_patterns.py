"""T1.3: 正则测试用例 - 用 Top50 真实控制人名称断言命中/不命中。"""
import re, yaml
from pathlib import Path
import pytest

cfg = yaml.safe_load(Path("config/rules.yaml").read_text(encoding="utf-8"))["channel_exclusion"]
exact = set(cfg.get("exact", []))
pats = [re.compile(p) for p in cfg.get("patterns", [])]

def is_excluded(name):
    for x in exact:
        if name == x:
            return True
    for p in pats:
        if p.search(name):
            return True
    return False

# 应该被排除(政府机构)
@pytest.mark.parametrize("name", [
    "国务院国有资产监督管理委员会",
    "深圳市国有资产监督管理局",  # 局 ≠ 委员会, 之前漏排
    "河南省财政厅",
    "广州市人民政府",
    "中国证券监督管理委员会",
    "国务院",
    "中央汇金资产管理有限责任公司",  # exact
])
def test_should_exclude_gov(name):
    assert is_excluded(name), f"政府机构未被排除: {name}"

# 不应该被排除(国企集团/经营主体)
@pytest.mark.parametrize("name", [
    "中国电子信息产业集团有限公司",
    "国家开发投资集团有限公司",
    "深圳市投资控股有限公司",  # 地方国企投资平台, 非政府监管机构
    "招商局集团有限公司",
    "华润集团有限公司",
    "王传福",  # 自然人
])
def test_should_keep_soe(name):
    assert not is_excluded(name), f"国企集团被误排: {name}"
