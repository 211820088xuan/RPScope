"""T1: 核实 000858 记录 + short_name repr。"""
import sqlite3

conn = sqlite3.connect("rpscope.db")
conn.row_factory = sqlite3.Row

# T1: 000858 实际记录
print("=== T1: 000858 记录 ===")
r = conn.execute("SELECT stock_code, short_name, full_name FROM company WHERE stock_code='000858'").fetchone()
if r:
    print(f"  stock_code: {r['stock_code']!r}")
    print(f"  short_name: {r['short_name']!r}")
    print(f"  short_name bytes: {r['short_name'].encode('utf-8')!r}")
    print(f"  full_name: {r['full_name']!r}")
else:
    print("  NOT FOUND")

# 茅台
print("\n=== 茅台(600519) ===")
r2 = conn.execute("SELECT stock_code, short_name, full_name FROM company WHERE stock_code='600519'").fetchone()
if r2:
    print(f"  short_name: {r2['short_name']!r}")
    print(f"  short_name bytes: {r2['short_name'].encode('utf-8')!r}")

# T2: 排版空格影响范围
print("\n=== T2: 排版空格/全角字符统计 ===")
# company 表
total = conn.execute("SELECT COUNT(*) FROM company").fetchone()[0]
has_space = conn.execute("SELECT COUNT(*) FROM company WHERE short_name LIKE '% %' OR short_name LIKE '%\u3000%'").fetchone()[0]
has_fullwidth = conn.execute("SELECT COUNT(*) FROM company WHERE short_name LIKE '%\uff21%' OR short_name LIKE '%\uff22%' OR short_name LIKE '%\uff23%' OR short_name GLOB '*[ＡＢＣＤ]*'").fetchone()[0]
# 用更通用的方式: 含非 ASCII 字母
has_special = conn.execute("SELECT COUNT(*) FROM company WHERE short_name GLOB '*[＊Ａ-Ｚａ-ｚ０-９]*'").fetchone()[0]
print(f"company 表: total={total}")
print(f"  含半角空格: {has_space}")
# 逐行检查全角字符
fullwidth_count = 0
space_count = 0
samples = []
for row in conn.execute("SELECT stock_code, short_name FROM company"):
    sn = row["short_name"] or ""
    has_fw = any(ord(c) > 0xFF00 and ord(c) < 0xFFFF for c in sn)
    has_sp = " " in sn or "\u3000" in sn or "\t" in sn
    if has_fw:
        fullwidth_count += 1
        if len(samples) < 10:
            samples.append((row["stock_code"], sn, "fullwidth"))
    if has_sp and not has_fw:
        space_count += 1
        if len(samples) < 20:
            samples.append((row["stock_code"], sn, "space"))
print(f"  含全角字符: {fullwidth_count}")
print(f"  含空格(无全角): {space_count}")
print(f"  合计受影响: {fullwidth_count + space_count} = {(fullwidth_count+space_count)/total*100:.1f}%")

print(f"\n  受影响样例:")
for code, name, typ in samples[:20]:
    print(f"    {code} {name!r:20s} ({typ}) bytes={name.encode('utf-8')!r}")

# entity 表
print(f"\nentity 表:")
etotal = conn.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
efw = 0
esp = 0
esamples = []
for row in conn.execute("SELECT entity_id, display_name FROM entity LIMIT 70000"):
    dn = row["display_name"] or ""
    has_fw = any(ord(c) > 0xFF00 and ord(c) < 0xFFFF for c in dn)
    has_sp = " " in dn or "\u3000" in dn
    if has_fw:
        efw += 1
        if len(esamples) < 10:
            esamples.append((row["entity_id"], dn, "fullwidth"))
    if has_sp and not has_fw:
        esp += 1
        if len(esamples) < 20:
            esamples.append((row["entity_id"], dn, "space"))
print(f"  total={etotal}")
print(f"  含全角字符: {efw}")
print(f"  含空格: {esp}")
print(f"  合计受影响: {efw+esp} = {(efw+esp)/etotal*100:.1f}%")
print(f"\n  entity 受影响样例:")
for eid, name, typ in esamples[:15]:
    print(f"    {eid} {name!r:30s} ({typ})")

conn.close()
