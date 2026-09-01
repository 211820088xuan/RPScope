"""T1: 护栏三道校验的直接单元测试。

直接调用 _validate_structure / _validate_readonly / _validate_resource，
手工构造非法 SQL 字符串，不经过 LLM。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.query.generate import _validate_structure, _validate_readonly, _validate_resource


# ========== 结构校验 ==========

def test_structure_valid():
    assert _validate_structure("SELECT * FROM company LIMIT 10") == (True, "OK")
    assert _validate_structure("SELECT stock_code, short_name FROM company WHERE stock_code='002594' LIMIT 10") == (True, "OK")
    assert _validate_structure("SELECT e.display_name FROM entity e JOIN holding h ON e.entity_id=h.entity_id LIMIT 10") == (True, "OK")

def test_structure_nonexistent_table():
    ok, msg = _validate_structure("SELECT * FROM evil_table LIMIT 10")
    assert not ok and "evil_table" in msg, f"应拒绝非法表名, got: {msg}"

def test_structure_nonexistent_column():
    ok, msg = _validate_structure("SELECT e.password FROM entity e LIMIT 10")
    assert not ok and "password" in msg, f"应拒绝非法列名, got: {msg}"

def test_structure_typo_table():
    ok, msg = _validate_structure("SELECT * FROM companyy LIMIT 10")
    assert not ok and "companyy" in msg, f"应拒绝拼写近似的表名, got: {msg}"

def test_structure_comment_bypass():
    """注释里藏恶意 SQL"""
    ok, msg = _validate_structure("SELECT * FROM company -- DROP TABLE entity\n LIMIT 10")
    # 注释里的 DROP 应被 readonly 校验拦截, 结构校验应通过(无非法表名)
    assert ok, f"注释内的文本不应影响结构校验, got: {msg}"

def test_structure_block_comment_bypass():
    ok, msg = _validate_structure("SELECT * FROM company /* DELETE FROM entity */ LIMIT 10")
    assert ok, f"块注释不应影响结构校验, got: {msg}"

def test_structure_case_variants():
    ok, msg = _validate_structure("select * from COMPANY limit 10")
    assert ok, f"大小写不应影响表名校验, got: {msg}"

def test_structure_multi_statement():
    """多语句: 第二条引用非法表"""
    ok, msg = _validate_structure("SELECT * FROM company LIMIT 10; SELECT * FROM evil_table LIMIT 10")
    # 当前的 regex 只找 FROM/JOIN 后的表名, 会捕获到 evil_table
    assert not ok, f"多语句中的非法表名应被拒绝, got: {msg}"

def test_structure_subquery_nonexistent():
    ok, msg = _validate_structure("SELECT * FROM company WHERE stock_code IN (SELECT stock_code FROM evil_table) LIMIT 10")
    assert not ok and "evil_table" in msg, f"子查询中的非法表名应被拒绝, got: {msg}"


# ========== 只读校验 ==========

def test_readonly_delete():
    ok, msg = _validate_readonly("DELETE FROM company")
    assert not ok and "DELETE" in msg.upper(), f"应拒绝 DELETE, got: {msg}"

def test_readonly_update():
    ok, msg = _validate_readonly("UPDATE company SET short_name='hacked' WHERE stock_code='002594'")
    assert not ok and "UPDATE" in msg.upper(), f"应拒绝 UPDATE, got: {msg}"

def test_readonly_insert():
    ok, msg = _validate_readonly("INSERT INTO company VALUES ('999999', 'hacked')")
    assert not ok, f"应拒绝 INSERT, got: {msg}"

def test_readonly_drop():
    ok, msg = _validate_readonly("DROP TABLE company")
    assert not ok, f"应拒绝 DROP, got: {msg}"

def test_readonly_create():
    ok, msg = _validate_readonly("CREATE TABLE hacked (id TEXT)")
    assert not ok, f"应拒绝 CREATE, got: {msg}"

def test_readonly_alter():
    ok, msg = _validate_readonly("ALTER TABLE company ADD COLUMN password TEXT")
    assert not ok, f"应拒绝 ALTER, got: {msg}"

def test_readonly_pragma():
    ok, msg = _validate_readonly("PRAGMA database_list")
    assert not ok, f"应拒绝 PRAGMA, got: {msg}"

def test_readonly_attach():
    ok, msg = _validate_readonly("ATTACH DATABASE 'evil.db' AS evil")
    assert not ok, f"应拒绝 ATTACH, got: {msg}"

def test_readonly_case_variants():
    ok, msg = _validate_readonly("delete from company")
    assert not ok, f"应拒绝小写 delete, got: {msg}"

def test_readonly_mixed_case():
    ok, msg = _validate_readonly("Drop Table company")
    assert not ok, f"应拒绝混合大小写 Drop, got: {msg}"

def test_readonly_whitespace_bypass():
    ok, msg = _validate_readonly("DELETE  FROM  company")
    assert not ok, f"应拒绝多余空格的 DELETE, got: {msg}"

def test_readonly_valid_select():
    assert _validate_readonly("SELECT * FROM company LIMIT 10") == (True, "OK")


# ========== 资源约束校验 ==========

def test_resource_no_limit():
    ok, msg = _validate_resource("SELECT * FROM company")
    assert not ok and "LIMIT" in msg, f"应拒绝无 LIMIT, got: {msg}"

def test_resource_limit_too_large():
    ok, msg = _validate_resource("SELECT * FROM company LIMIT 999999")
    assert not ok and "999999" in msg, f"应拒绝过大 LIMIT, got: {msg}"

def test_resource_limit_ok():
    assert _validate_resource("SELECT * FROM company LIMIT 10") == (True, "OK")

def test_resource_limit_200():
    """边界值: LIMIT 200 应通过"""
    assert _validate_resource("SELECT * FROM company LIMIT 200") == (True, "OK")

def test_resource_limit_201():
    """边界值: LIMIT 201 应拒绝"""
    ok, msg = _validate_resource("SELECT * FROM company LIMIT 201")
    assert not ok, f"应拒绝 LIMIT 201, got: {msg}"


# ========== 组合校验 ==========

def test_combined_safe_query():
    sql = "SELECT stock_code, short_name, industry FROM company WHERE industry IS NOT NULL LIMIT 50"
    for name, fn in [("structure", _validate_structure), ("readonly", _validate_readonly), ("resource", _validate_resource)]:
        ok, msg = fn(sql)
        assert ok, f"{name} 校验应通过: {msg}"
