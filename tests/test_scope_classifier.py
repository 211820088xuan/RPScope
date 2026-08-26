"""scope_classifier 单元测试 - 每类>=5真实样例(从库取)。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from src.eval.scope_classifier import classify


# upstream 样例(真实 relation_desc)
@pytest.mark.parametrize("name,desc", [
    ("王传福", "公司第一大股东、董事长"),
    ("吕向阳", "持有5%以上股份的股东"),
    ("曾毓群", "实际控制人"),
    ("厦门瑞庭投资有限公司", "控股股东"),
    ("深圳市创新投资集团有限公司", "同一控股股东"),
])
def test_upstream(name, desc):
    assert classify(name, desc) == "upstream"


# downstream 样例
@pytest.mark.parametrize("name,desc", [
    ("成都电服交投能源科技有限公司", "合营企业"),
    ("Autoflightx Inc", "联营企业"),
    ("福田时代新能源科技有限公司", "合营企业"),
    ("一汽集团子公司", "一汽集团子公司"),
    ("XX公司", "本公司母公司的控股子公司"),
])
def test_downstream(name, desc):
    assert classify(name, desc) == "downstream"


# other 样例(relation_desc 空, party_name 无关键词)
@pytest.mark.parametrize("name,desc", [
    ("某基金有限公司", ""),
    ("ABC Holdings Ltd", ""),
    ("XX投资合伙企业", ""),
    ("某未知机构", ""),
    ("PT.QMB New Energy Materials", ""),
])
def test_other(name, desc):
    assert classify(name, desc) == "other"


# 兜底: relation_desc 空 + party_name 含"子公司"
def test_name_fallback_downstream():
    assert classify("XX部分子公司", "") == "downstream"

# 兜底: relation_desc 空 + 短人名
def test_name_fallback_upstream_person():
    assert classify("张伟", "") == "upstream"

# downstream 优先于 upstream(desc 含两个关键词)
def test_downstream_priority():
    assert classify("XX", "控股股东的子公司") == "downstream"
