"""P3 规则引擎测试 - 固定 fixture 图, 每规则命中/不命中/边界。

fixture 场景:
  C1(000001 subject) 的控制人=张三(也控 C2) -> R2 命中 C1-C2
  C1 被股东X公司 30% 持(同期也持 C5 30%) -> R3 low 命中 C1-C5; R1 high 命中 X
  C1 董事李四(也任 C3 董事, disambig=medium) -> R4 命中 C1-C3, 置信<=medium
  C1 董事长王五(持 C4 8%) -> R5 命中 C1-C4
  香港中央结算(is_channel=1) 持 C1 15% -> R1 排除
  独立董事赵六 任 C1+C6 -> R4 排除(independent_director)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from src.rules.engine import RuleEngine
from src.store.db import Store


@pytest.fixture
def store():
    s = Store(":memory:")
    # 公司
    for code, name in [("000001", "C1"), ("000002", "C2"), ("000003", "C3"),
                       ("000004", "C4"), ("000005", "C5"), ("000006", "C6")]:
        s.upsert_company(stock_code=code, short_name=name)
    # 实体
    eid_ctrl = s.get_or_create_entity(entity_type="person", canonical_name="张三", display_name="张三")
    eid_dir = s.get_or_create_entity(entity_type="person", canonical_name="李四", display_name="李四", confidence="medium")
    eid_kp = s.get_or_create_entity(entity_type="person", canonical_name="王五", display_name="王五", confidence="high")
    eid_hold = s.get_or_create_entity(entity_type="org", canonical_name="股东X公司", display_name="股东X公司")
    eid_channel = s.get_or_create_entity(entity_type="org", canonical_name="香港中央结算有限公司", display_name="香港中央结算有限公司", is_channel=True)
    eid_ind = s.get_or_create_entity(entity_type="person", canonical_name="赵六", display_name="赵六")
    eid_gov = s.get_or_create_entity(entity_type="org", canonical_name="国务院国资委", display_name="国务院国资委", is_channel=True)
    # 控制人: 张三控 C1 和 C2 (兄弟公司 R2)
    s.upsert_controller(stock_code="000001", entity_id=eid_ctrl, control_ratio=45, source="cninfo", valid_from="2020-01-01", valid_to=None)
    s.upsert_controller(stock_code="000002", entity_id=eid_ctrl, control_ratio=40, source="cninfo", valid_from="2020-01-01", valid_to=None)
    # 持股: 股东X持 C1 30% 和 C5 30% 同期(R3 low + R1 high)
    s.upsert_holding(entity_id=eid_hold, stock_code="000001", report_period="2025-12-31", shares=100, ratio=30, holder_rank=1, source="stock_gdfx_free_holding_detail_em", valid_from="2025-12-31")
    s.upsert_holding(entity_id=eid_hold, stock_code="000005", report_period="2025-12-31", shares=100, ratio=30, holder_rank=1, source="stock_gdfx_free_holding_detail_em", valid_from="2025-12-31")
    # 通道持 C1 15%(应排除)
    s.upsert_holding(entity_id=eid_channel, stock_code="000001", report_period="2025-12-31", shares=50, ratio=15, holder_rank=2, source="stock_gdfx_free_holding_detail_em", valid_from="2025-12-31")
    # 王五(董事长) 持 C4 8%(R5)
    s.upsert_holding(entity_id=eid_kp, stock_code="000004", report_period="2025-12-31", shares=10, ratio=8, holder_rank=3, source="stock_ggcg_em", valid_from="2025-12-31")
    # 任职: 李四任 C1+C3 董事(R4); 赵六任 C1+C6 独立董事(排除)
    s.upsert_position(entity_id=eid_dir, stock_code="000001", title="董事", title_class="director", source="inner_trade", valid_from="2024-01-01", valid_to=None)
    s.upsert_position(entity_id=eid_dir, stock_code="000003", title="董事", title_class="director", source="inner_trade", valid_from="2024-01-01", valid_to=None)
    s.upsert_position(entity_id=eid_ind, stock_code="000001", title="独立董事", title_class="independent_director", source="inner_trade", valid_from="2024-01-01", valid_to=None)
    s.upsert_position(entity_id=eid_ind, stock_code="000006", title="独立董事", title_class="independent_director", source="inner_trade", valid_from="2024-01-01", valid_to=None)
    s.upsert_position(entity_id=eid_kp, stock_code="000001", title="董事长", title_class="director", source="inner_trade", valid_from="2024-01-01", valid_to=None)
    s.commit()
    return s


@pytest.fixture
def engine():
    return RuleEngine("config/rules.yaml")


def find(cands, rule_id):
    return [c for c in cands if c.rule_id.startswith(rule_id)]


# ---- R1 ----
def test_r1_hit_high(store, engine):
    cs = engine.evaluate(store, "000001")
    r1 = [c for c in cs if "R1" in c.rule_id and c.party_name == "股东X公司"]
    assert r1 and r1[0].confidence == "high"  # 30%>=20 significant

def test_r1_channel_excluded(store, engine):
    cs = engine.evaluate(store, "000001")
    assert not any(c.party_name == "香港中央结算有限公司" for c in cs)

def test_r1_below_threshold_miss(store, engine):
    cs = engine.evaluate(store, "000004")  # C4 只被王五持 8%, 王五是 person, 8%>=5 -> R1 命中 high
    r1 = find(cs, "R1")
    assert any(c.party_name == "王五" for c in r1)


# ---- R2 ----
def test_r2_brother_hit(store, engine):
    cs = engine.evaluate(store, "000001")
    r2 = find(cs, "R2")
    assert any(c.party_id == "C:000002" for c in r2)

def test_r2_gov_controller_excluded(store, engine):
    # 给 C1 加政府控制人(应被忽略, 不产生 R2 兄弟)
    eid_gov = store.conn.execute("SELECT entity_id FROM entity WHERE canonical_name='国务院国资委'").fetchone()[0]
    store.upsert_controller(stock_code="000001", entity_id=eid_gov, control_ratio=99, source="cninfo", valid_from="2020-01-01", valid_to=None)
    store.commit()
    cs = engine.evaluate(store, "000001")
    # 政府 control 不应新增 R2 兄弟(张三那条仍在, 但不应因国资委新增)
    r2 = find(cs, "R2")
    assert all(c.party_id == "C:000002" for c in r2)


# ---- R3 ----
def test_r3_low_confidence(store, engine):
    cs = engine.evaluate(store, "000001")
    r3 = find(cs, "R3")
    assert any(c.party_id == "C:000005" and c.confidence == "low" for c in r3)

def test_r3_diff_period_miss(store, engine):
    # 把 C5 的持股改到不同报告期
    store.conn.execute("UPDATE holding SET report_period='2024-12-31' WHERE stock_code='000005'")
    store.commit()
    cs = engine.evaluate(store, "000001")
    r3 = find(cs, "R3")
    assert not any(c.party_id == "C:000005" for c in r3)


# ---- R4 ----
def test_r4_chain_hit(store, engine):
    cs = engine.evaluate(store, "000001")
    r4 = find(cs, "R4")
    assert any(c.party_id == "C:000003" for c in r4)

def test_r4_independent_excluded(store, engine):
    cs = engine.evaluate(store, "000001")
    r4 = find(cs, "R4")
    assert not any(c.party_id == "C:000006" for c in r4)  # 独董赵六不产生 R4

def test_r4_confidence_clamp(store, engine):
    cs = engine.evaluate(store, "000001")
    r4 = [c for c in cs if "R4" in c.rule_id and c.party_id == "C:000003"]
    assert r4 and r4[0].confidence == "medium"  # 李四 disambig=medium, R4 不得高于


# ---- R5 ----
def test_r5_keyperson_hit(store, engine):
    cs = engine.evaluate(store, "000001")
    r5 = find(cs, "R5")
    assert any(c.party_id == "C:000004" and c.confidence == "high" for c in r5)


# ---- R7 ----
def test_r7_empty_without_pair_table(store, engine):
    cs = engine.evaluate(store, "000001")
    r7 = find(cs, "R7")
    assert r7 == []  # 无 guarantee_pair 表, 诚实空


# ---- engine 集成 ----
def test_engine_merges_multi_rule(store, engine):
    cs = engine.evaluate(store, "000001")
    # 股东X 既 R1(直接持) 又 R3(共同持 C5) -> 出现在候选里
    assert len(cs) > 0
    # 每条都有 path 和 evidence
    for c in cs:
        assert c.path and c.evidence and c.confidence in ("high", "medium", "low")
