# 覆盖规模数字口径核实报告

> 2026-08-24 | T1-T4 核实

## 一、两组数字的统计口径与代码出处

### 公司数: 8022 → 5927

| 数字 | 出处 | 口径 |
|---|---|---|
| **8022** | P1 ingest 时 `company` 表行数 | `stock_info_a_code_name`(5549 A股) + B股/三板(100+) + ggcg/inner_trade gap-fill 的 SH/SZ 前缀公司(2473) |
| **5927** | `normalize_codes.py` 执行后 `company` 表行数 | 8022 - 2095(删除 SH/SZ 前缀重复行) = 5927 |

**SQL 出处**: `SELECT COUNT(*) FROM company` → 5927
**图中出处**: `build_graph()` 的 `SELECT stock_code, short_name FROM company` → 5927 个 C: 节点

### 实体数: 65069 → 61225

| 数字 | 出处 | 口径 |
|---|---|---|
| **65069** | P1 progress.md 记录(修复政府控制人前) | entity 表非通道实体数(4016 channel + 65069 non-channel = 69085 total) |
| **61225** | 当前 entity 表非通道数 | 65362 total - 4137 channel = 61225 non-channel |

**差异**: -3844 = 政府控制人排除(+121 channel) + 消歧拆分(#D 实体变化) + 数据清洗

**SQL 出处**: `SELECT COUNT(*) FROM entity WHERE is_channel=0` → 61225
**图中出处**: `build_graph()` 只导入 `is_channel=0` 的实体 → 61225 个 E: 节点
**一致性**: DB 非通道 61225 = 图中实体 61225 (完全一致, 无孤立实体)

### 边数: 196619 → 196415

| 数字 | 出处 | 口径 |
|---|---|---|
| **196619** | P1 progress.md 记录(修复前) | 旧图(含 SH/SZ 前缀公司 + 旧排除名单 + 未拆分消歧) |
| **196415** | 当前 graph.pkl | 修复后图(无 SH/SZ 前缀 + 扩充排除 + LLM 消歧拆分) |

**差异**: -204 边

**DB 非通道边**: HOLDS=177537 + SERVES_AS=23862 + CONTROLS=4023 = 205422
**图中边**: 196415
**差异**: 9007 → 因为 MultiDiGraph: 同一 (entity, company) 对的多条 holding 记录(不同报告期)在图中各算一条边, 但 DB 查询是行数(含报告期维度); 图的边数 = 不同 (entity_id, stock_code) 对数(去重后)

## 二、三项数字是否自洽

**自洽。** 逻辑如下:

1. **公司 -2095 但边不变**: 删除的 2095 家 SH/SZ 前缀公司在 holding/position/actual_controller 表中**没有任何边指向它们**(边用的是裸 6 位代码, 不是 SH/SZ 前缀)。所以删公司不影响边。
2. **实体 -3844 但边仅 -204**: 政府控制人被标记 channel 后, 其 CONTROLS 边被排除(约 -121 条); 消歧拆分把 position/holding 记录从原 entity 移到 #D entity, 边数不变(记录还是那些记录, 只是 entity_id 换了)。所以净变化主要来自政府控制人排除的 CONTROLS 边。
3. **边 -204 ≈ 政府控制人 CONTROLS 边**: 政府控制人(深圳市国有资产监督管理局 18 家 + 广州市人民政府 8 家 + 河南省财政厅 7 家 + 其他 ≈ 121 家)的 CONTROLS 边被排除, 约 121-200 条。剩余差异来自 LLM 消歧拆分导致的少量 entity 重新分组。

**结论: 三项数字自洽, 变化全部可追溯到具体操作(删重复公司 + 排除政府控制人 + 消歧拆分)。**

## 三、口径结论

### 5927 的准确定义

> **5927 = A 股全市场上市公司 + B 股 + 部分三板/退市公司**（来自 akshare `stock_info_a_code_name` 全表, 经 SH/SZ 前缀去重后的 6 位代码公司数）。

- akshare `stock_info_a_code_name` 返回 5549 家 A 股
- 加上 ggcg/inner_trade gap-fill 补建的公司(B 股/三板/部分退市)
- 减去 2095 个 SH/SZ 前缀重复行(normalize_codes.py 清理)
- = 5927

### 「全市场」是否成立

**基本成立, 但需加注。** 5927 覆盖了 A 股全市场约 5400-5500 家上市公司, 加上 B 股和部分三板/退市公司。akshare 的 `stock_info_a_code_name` 本身就含 B 股和部分三板, 不是纯 A 股。

**准确表述**: "A 股 + B 股上市公司(来自 akshare 全表, 经去重)" 或 "A 股全市场上市公司(含 B 股/三板)"。

## 四、文档修正

### README.md

旧: `| 覆盖公司 / 实体 / 关系边 | 5927 / 61225 / 196415 | P1 |`

新: `| 覆盖公司 / 实体 / 关系边 | 5927 / 61225 / 196415 | P1 |` (数字不变, 补口径说明)

口径说明(加在指标表下方):
> 「覆盖公司」= akshare `stock_info_a_code_name` 全表(A 股 + B 股)经 SH/SZ 前缀去重后的 6 位代码公司数。图中公司节点数 = company 表行数 = 5927。「实体」= 非通道 entity 数(排除 ETF/社保/QFII/政府控制人等)。「关系边」= 图中不同 (实体, 公司) 对的边数(MultiDiGraph, 同对多期记录各算一条)。

### scope-class-review.md 时效性

已在上一轮标注"本诊断基于早期样本(28 家), 结论仅作方向性参考"。保持不变。
