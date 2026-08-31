"""T1: 逐项查明覆盖规模数字的口径与差异来源。"""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.graph.store import load_graph

# === 1. 数据库层面的统计 ===
c = sqlite3.connect("rpscope.db"); c.row_factory = sqlite3.Row

print("=== 1. company 表行数(DB) ===")
db_co = c.execute("SELECT COUNT(*) FROM company").fetchone()[0]
print(f"  company 表总行数: {db_co}")

# 检查有多少 company 在 holding/position/actual_controller 中有记录
print("\n=== 2. 各表中出现的不同公司数 ===")
col_map = {"holding": "stock_code", "position": "stock_code", "actual_controller": "stock_code", "event": "subject_code"}
for tbl, col in col_map.items():
    try:
        n = c.execute(f"SELECT COUNT(DISTINCT {col}) FROM {tbl}").fetchone()[0]
        print(f"  {tbl}: {n} 家")
    except Exception as e:
        print(f"  {tbl}: error {e}")

# 图中公司节点数
print("\n=== 3. 图中节点数(当前 graph.pkl) ===")
G = load_graph()
g_co = sum(1 for n, d in G.nodes(data=True) if d.get("kind") == "company")
g_ent = G.number_of_nodes() - g_co
g_edge = G.number_of_edges()
print(f"  图中公司节点(C:): {g_co}")
print(f"  图中实体节点(E:, 非通道): {g_ent}")
print(f"  图中总节点: {G.number_of_nodes()}")
print(f"  图中边数: {g_edge}")

# 公司节点中, 多少在 holding 里有记录
g_companies = [n for n, d in G.nodes(data=True) if d.get("kind") == "company"]
in_holding = sum(1 for code in g_companies if c.execute("SELECT 1 FROM holding WHERE stock_code=? LIMIT 1", (code.replace("C:", ""),)).fetchone())
print(f"\n  图中公司节点在 holding 中有记录的: {in_holding}")

# === 4. 历史数字溯源 ===
print("\n=== 4. 历史数字溯源 ===")
print("  8022: P1 ingest 时 company 表行数(含 B股/三板/SH/SZ前缀gap-fill)")
print("       normalize_codes.py 删除了 2095 个 SH/SZ 前缀的重复 company 行")
print(f"  当前 company 表: {db_co}")
print(f"  65069 -> 61225: entity 表差异")
db_ent_total = c.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
db_ent_ch = c.execute("SELECT COUNT(*) FROM entity WHERE is_channel=1").fetchone()[0]
db_ent_nonch = db_ent_total - db_ent_ch
print(f"  entity 表总行数: {db_ent_total}")
print(f"  entity 通道: {db_ent_ch}")
print(f"  entity 非通道: {db_ent_nonch}")
print(f"  图中非通道实体: {g_ent}")
print(f"  差异(DB非通道 {db_ent_nonch} vs 图 {g_ent}): {db_ent_nonch - g_ent}")
print("  差异原因: 图只导入有边的实体(有 holding/position/controller 记录的); entity 表可能有孤立实体(无任何边)")

# === 5. 边数差异 ===
print("\n=== 5. 边数差异 ===")
db_holds = c.execute("SELECT COUNT(*) FROM holding WHERE entity_id NOT IN (SELECT entity_id FROM entity WHERE is_channel=1)").fetchone()[0]
db_serves = c.execute("SELECT COUNT(*) FROM position WHERE entity_id NOT IN (SELECT entity_id FROM entity WHERE is_channel=1)").fetchone()[0]
db_ctrl = c.execute("SELECT COUNT(*) FROM actual_controller WHERE entity_id NOT IN (SELECT entity_id FROM entity WHERE is_channel=1)").fetchone()[0]
db_total_edges = db_holds + db_serves + db_ctrl
print(f"  DB 中非通道边: HOLDS={db_holds} SERVES_AS={db_serves} CONTROLS={db_ctrl} 总={db_total_edges}")
print(f"  图中边: {g_edge}")
print(f"  差异: {db_total_edges - g_edge} (图用 MultiDiGraph, 同 (u,v) 多条边在图中各自算)")

# === 6. 旧的 8022 来源 ===
print("\n=== 6. 旧 8022 来源 ===")
print("  P1 progress.md 记录: 'company: 8022 (A股5549 + B股/三板/动态补建2473)'")
print("  normalize_codes.py 执行后: 删除 2095 个 SH/SZ 前缀重复行 -> 5927")
print(f"  验证: 8022 - 2095 = {8022-2095} (约等于 {db_co})")

c.close()
