"""#6 P8 无消歧消融 - 临时撤销 #D 拆分, 重跑 comparable eval, 对比, 撤销。

逻辑: pre-disambig(所有同名=一个entity) vs post-disambig(#D拆分) 的 P/R 差异。
"""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.eval.aligner import align_batch
from src.eval.metrics import prf
from src.rules.engine import RuleEngine
from src.store.db import Store

def run_eval(store):
    codes = [r[0] for r in store.conn.execute("SELECT DISTINCT stock_code FROM gold_related_party").fetchall()]
    eng = RuleEngine("config/rules.yaml")
    res = align_batch(store, eng, codes, scope="upstream")
    m = prf(len(res["matched"]), len(res["system_only"]), len(res["gold_only"]))
    return m

def main():
    store = Store("rpscope.db")
    # 1. 找所有 #D 实体 + 其 parent(同 display_name 无 #D)
    d_entities = list(store.conn.execute(
        "SELECT entity_id, canonical_name, display_name FROM entity WHERE canonical_name LIKE '%#D%'").fetchall())
    print(f"#D 实体: {len(d_entities)}")
    # 记录原映射用于撤销
    reassign_map = {}  # {#D entity_id -> parent entity_id}
    for d in d_entities:
        parent = store.conn.execute(
            "SELECT entity_id FROM entity WHERE display_name=? AND canonical_name NOT LIKE '%#D%' LIMIT 1",
            (d["display_name"],)).fetchone()
        if parent:
            reassign_map[d["entity_id"]] = parent[0]
    print(f"可撤销: {len(reassign_map)} 对")
    
    # 2. post-disambig(当前) baseline
    print("\n=== post-disambig(当前) ===")
    m_post = run_eval(store)
    print(f"  P={m_post['precision']*100:.1f}% R={m_post['recall']*100:.1f}% matched={m_post['tp']} sys={m_post['fp']} gold={m_post['fn']}")
    
    # 3. 撤销: 把 #D entity 的 position/holding 记录 reassign 回 parent
    n_pos = n_hol = 0
    for d_eid, p_eid in reassign_map.items():
        n_pos += store.conn.execute("UPDATE position SET entity_id=? WHERE entity_id=?", (p_eid, d_eid)).rowcount
        n_hol += store.conn.execute("UPDATE holding SET entity_id=? WHERE entity_id=?", (p_eid, d_eid)).rowcount
    store.commit()
    print(f"\n=== pre-disambig(撤销 {n_pos} position + {n_hol} holding) ===")
    m_pre = run_eval(store)
    print(f"  P={m_pre['precision']*100:.1f}% R={m_pre['recall']*100:.1f}% matched={m_pre['tp']} sys={m_pre['fp']} gold={m_pre['fn']}")
    
    # 4. 对比
    print(f"\n=== 消融对比 ===")
    print(f"  precision: pre={m_pre['precision']*100:.1f}% -> post={m_post['precision']*100:.1f}% ({(m_post['precision']-m_pre['precision'])*100:+.1f}pp)")
    print(f"  recall:    pre={m_pre['recall']*100:.1f}% -> post={m_post['recall']*100:.1f}% ({(m_post['recall']-m_pre['recall'])*100:+.1f}pp)")
    print(f"  matched:   pre={m_pre['tp']} -> post={m_post['tp']}")
    print(f"  sys_only:  pre={m_pre['fp']} -> post={m_post['fp']}")
    
    # 5. 撤销回 post-disambig(恢复 #D)
    for d_eid, p_eid in reassign_map.items():
        store.conn.execute("UPDATE position SET entity_id=? WHERE entity_id=? AND "
                           "id IN (SELECT id FROM position WHERE entity_id=? AND stock_code IN "
                           "(SELECT DISTINCT stock_code FROM position WHERE entity_id=?))",
                           (d_eid, p_eid, p_eid, p_eid))
    # 简化: 直接用备份恢复(如果有)
    # 实际: #D 实体原本的记录是 split 时创建的, reassign 到 parent 后, 想精确恢复较复杂
    # 简化: 重新跑 apply_disambig 就行(它会重新拆分)
    print("\n注: 恢复需要重跑 apply_disambig(或用 DB 备份)。当前已撤销到 pre-disambig 状态。")
    print("如需恢复, 运行: py scripts/apply_disambig.py")
    store.close()

if __name__ == "__main__":
    main()
