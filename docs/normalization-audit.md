# 数据归一化缺口排查 + 撞车别名分类报告

> 2026-09-01

## T1: entity 归一化对实体去重与消歧的影响

### 结论：无影响，entity 去重已使用归一化名称

| 检查项 | 结果 |
|---|---|
| canonical_name 含空格 | 0 条（已归一化） |
| display_name 含空格 | 1106 条（原始名，正常） |
| 同一归一化名对应多个 entity_id | **0 组** |
| 拆分实体参与的边 | 0 |

### 代码出处

- `src/store/schema.sql:25` — `UNIQUE (entity_type, canonical_name)` 约束
- `src/data/ingest.py:94` — `canonical_for()` 计算 canonical_name
- `src/normalize/name.py:29` — `normalize_name()` 做 NFKC + 去所有空白 + 连字符归一
- `src/normalize/name.py:43` — `normalize_person()` 人名用 normalize_name（去空格）
- `src/normalize/name.py:48` — `org_match_key()` 机构用 normalize_name + 剥后缀

entity 入库时 canonical_name = normalize_name(原始名)，空格在入库时已去除。display_name 保留原始名（含空格）用于展示。UNIQUE 约束保证同一归一化名不会产生多个 entity_id。

**T2 不执行** — 无需合并，无拆分实体。

## T3: 22 条撞车别名分类

| 分类 | 数量 | 处理 |
|---|---|---|
| A/B 股同体 | 0 | — |
| 真实撞名 | 22 | 保持澄清 |

全部 22 条撞车是不同城市的同行业公司去地名前缀后同名：
- "银行" → 15 家城市银行（兰州/宁波/郑州/青岛/苏州/无锡/江苏/杭州/南京/北京/厦门/上海/长沙/成都/重庆）
- "能源" → 8 家能源公司（深圳/甘肃/湖北/陕西/广西/上海/辽宁/宁波）
- "燃气" → 5 家燃气公司
- "高速" → 5 家高速公司
- "建工" → 5 家建工公司

A/B 股同体（如万科A vs 万科B）已在 `_norm()` 的 A/B 后缀去除中处理，不进入别名派生路径。

## T4: 并发排队（已知特性）

50 并发 P50=12s，归因确认为 LLM API 排队：
- 单请求 P50 = 5s
- 50 并发 P50 = 12s（2.4x 放大）
- 非 LLM 阶段（分类+抽取+链接+执行）稳定 <350ms，并发下无显著上升
- 系统自身无串行瓶颈（每请求独立 Store，无全局锁）

暂不做并发信号量与排队提示。单请求延迟可接受，高并发场景是外部 LLM API 的限制，非系统可控。
