# 自然语言图查询 (NL2GraphQuery) 评测报告

> 2026-08-31 | T1-T7 完成

## 一、7 类查询模板

| ID | 意图 | 槽位 | 执行函数 | 确定性 |
|---|---|---|---|---|
| Q1 | 查某公司的关联方 | company, rule_ids?, min_confidence?, as_of? | 规则引擎 R1-R7 | ✓ |
| Q2 | 查两实体间关系路径 | entity_a, entity_b, max_hops?, as_of? | 规则引擎+图遍历 | ✓ |
| Q3 | 反向查询某人控制哪些公司 | entity, relation_type?, min_ratio?, as_of? | SQL | ✓ |
| Q4 | 查公司股东/董监高/实控人 | company, role_type, top_n?, as_of? | SQL | ✓ |
| Q5 | 查公司风险事件 | company, event_types?, date_range? | SQL | ✓ |
| Q6 | 两公司关联方重合 | company_a, company_b, as_of? | 规则引擎 | ✓ |
| Q7 | 模板外(兜底) | — | LLM 生成 SQL + 三道校验 | △ |

模板定义: `config/query_templates.yaml`
模板实现: `src/query/templates/q1_related_party.py` — `q7_generated.py`

## 二、意图分类

- 规则分类器: `src/query/intent.py` (关键词+正则模式)
- 关键词配置: `config/intent_keywords.yaml`
- 测试集: `tests/query/test_intent_data.py` (100 条, 每类 ≥10 条)

### 结果

| 指标 | 值 |
|---|---|
| 规则准确率 | **100/100 = 100%** |
| 目标 | ≥80% |
| LLM 兜底率 | 0% (15 条 Q7 全部规则命中) |

按意图分布:

| 意图 | 条数 | 准确 |
|---|---|---|
| Q1 related_party | 15 | 15 |
| Q2 relation_path | 15 | 15 |
| Q3 reverse_control | 15 | 15 |
| Q4 company_role | 15 | 15 |
| Q5 risk_events | 15 | 15 |
| Q6 overlap | 10 | 10 |
| Q7 open | 15 | 15 |

## 三、槽位抽取与实体链接

- 槽位抽取: `src/query/slot_filling.py` (LLM 输出 JSON)
- 实体链接: `src/query/entity_link.py` (5 级匹配: 代码→简称→全称→归一化→模糊)

### 实体链接三级处理

| 结果 | 处理 |
|---|---|
| 唯一命中 | 继续执行 |
| 多个候选 | 返回澄清请求, 列出候选让用户选 |
| 无命中 | 返回"未找到"+ 最接近候选 |

### 澄清机制示例

用户问"茅台的前十大股东", 如果"茅台"匹配到多家公司(如贵州茅台、茅台啤酒), 系统返回:
```
以下实体有多种匹配, 请选择:
「茅台」的候选:
  1. 贵州茅台
  2. 茅台啤酒
```
不自选最高分, 等待用户选择。

## 四、模板外查询生成路径 (Q7)

- 生成器: `src/query/generate.py`
- LLM 生成 SQL → 三道校验 → 执行

### 三道校验

| 校验 | 内容 |
|---|---|
| 结构校验 | 检查表名/列名是否在 schema 白名单 (AST 级, 非字符串包含) |
| 只读校验 | 禁止 INSERT/UPDATE/DELETE/DROP/ALTER 等写操作 |
| 资源约束 | 强制 LIMIT ≤200, 限制嵌套层数 |

校验失败带具体错误重试, 最多 2 次; 仍失败降级为"无法回答此类问题"。
结果标记 `source: "generated_query"`。

## 五、Agent 链路改造

原链路: `classify → route → {fact|related|relation|open} → verify → END`

新链路 (`src/query/pipeline.py`):

```
规则意图分类
├─ 确定 → 槽位抽取(LLM) → 实体链接 → 模板执行 → 结果组装 → 回答生成(LLM) → 回查
├─ 不确定 → LLM 意图分类+槽位抽取(合并) → 同上
└─ 模板外(Q7) → LLM 生成 SQL → 三道校验 → 执行 → 结果组装 → 回答生成 → 回查
实体链接歧义 → 澄清请求(中断)
校验失败 → 能力边界说明
```

### 端到端测试

| 问题 | 意图 | 延迟 | 答案长度 |
|---|---|---|---|
| 002594的关联方 | Q1 ✓ | 13s | 310 |
| 比亚迪的前十大股东 | Q4 ✓ | 18.6s | 635 |
| 002594的担保情况 | Q5 ✓ | 11s | 205 |
| 这个股的后续增长情况 | Q7 ✓ | 21.7s | 988 |

## 六、trace 埋点

- 实现: `src/query/trace.py`
- 输出: `.cache/traces/{hash}.json`
- 每次查询一个 trace 文件, 记录:

| 节点 | 记录内容 |
|---|---|
| 原始问句 | question |
| 规则分类 | intent, confidence, uncertain, classification_source |
| LLM 调用 | purpose, elapsed_ms, tokens, retried |
| 槽位 | extracted slots |
| 实体链接 | 每个实体的匹配方式, 候选集, 最终选择 |
| 查询执行 | template_id + params, 或 generated SQL + validation |
| 查询结果 | 条数, 耗时 |
| 最终回答 | answer[:500] |
| 回查结果 | passed, violations |

## 七、架构约束验证

| 约束 | 状态 |
|---|---|
| 判定环节 LLM 调用数 = 0 | ✓ (R1-R7 不调 LLM) |
| LLM 只做理解/生成 | ✓ (意图分类, 槽位抽取, 答案生成, SQL 生成) |
| 所有事实来自确定性执行 | ✓ (规则引擎 + SQL) |
| 能用规则不调 LLM | ✓ (意图分类 100% 规则覆盖, 0% LLM 兜底) |
| 实体歧义必须澄清 | ✓ (不自选最高分) |
| 模板外查询必须校验 | ✓ (三道校验) |
| 所有 LLM 走统一封装 | ✓ (LLMClient) |

## 八、文件清单

| 文件 | 说明 |
|---|---|
| `config/query_templates.yaml` | 7 类模板定义 |
| `config/intent_keywords.yaml` | 意图分类关键词 |
| `src/query/__init__.py` | 包初始化 |
| `src/query/intent.py` | 规则意图分类器 |
| `src/query/slot_filling.py` | 槽位抽取 (LLM) |
| `src/query/entity_link.py` | 实体链接 (5 级匹配 + 澄清) |
| `src/query/generate.py` | 模板外 SQL 生成 + 三道校验 |
| `src/query/trace.py` | trace 埋点 |
| `src/query/pipeline.py` | Agent 链路 (LangGraph) |
| `src/query/templates/__init__.py` | 模板注册 |
| `src/query/templates/q1-q7_*.py` | 7 个模板执行器 |
| `tests/query/test_intent.py` | 意图分类测试 |
| `tests/query/test_intent_data.py` | 100 条测试集 |
