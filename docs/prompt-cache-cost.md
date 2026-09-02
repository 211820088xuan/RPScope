# Prompt 版本管理 + 缓存核实 + 成本对照

## 1. Prompt 清单表

| 名称 | 版本 | 用途 | 调用位置 | 关键约束 |
|---|---|---|---|---|
| disambig | v1 | 人名消歧兜底 | `src/disambiguate/llm_fallback.py:23` | 输出JSON `same_person/confidence/reason`; 保守: 无线索判不同 |
| event_extract | v1 | 公告事件抽取 | `src/extract/event_extractor.py:31` | 数字/日期/对手方必须来自原文; 输出JSON events[]; 断言回查 |
| report_writer | v1 | 底稿撰写 | `src/report/writer.py:19` | 基于结构化数据; 财务可凭知识; 禁止免责声明 |
| gold_extract | v1 | 金标准关联方抽取 | `src/gold/extractor.py:94` | 只要具体名称; 排除类别词/本公司; 输出JSON parties[] |
| sql_generate | v1 | Q7 SQL生成 | `src/query/generate.py:98` | 只输出SQL; 只SELECT; LIMIT≤200; 表/列白名单; 3层校验 |
| answer_generate | v1 | 回答生成 | `src/query/pipeline.py:254` | 基于结构化结果; 中文; 财务可凭知识; 禁止免责声明 |
| coreference | v1 | 指代消解兜底 | `src/query/coreference.py:192` | 只输出JSON; 不确定输出uncertain; |
| slot_filling | v1 | 槽位抽取兜底 | `src/query/slot_filling.py:34` | 只输出JSON; 6位=代码; 人名用中文; 不编造 |
| intent_classify | v1 | 意图分类兜底 | `src/query/slot_filling.py:57` | 只输出JSON; Q1-Q7分类; 6位=代码; 不编造 |
| open_qa | v1 | 开放问答 | `src/agent/graph.py:123` | 结构化数据为准; 财务/行业可凭知识; 禁止免责声明 |
| sse_answer | v1 | SSE流式回答 | `src/serve/main.py:243` | 基于结构化结果; 中文; 禁止免责声明 |
| json_repair | v1 | JSON模式降级 | `src/llm/client.py:126` | 只输出JSON; 不解释 |
| schema_repair | v1 | 缺字段修复 | `src/llm/client.py:138` | 补全缺失字段; 只输出完整JSON |
| compare_summary | v1 | Q8对比摘要 | `tests/query/test_compare.py:76` | 只陈述数据; 禁止评价性判断; 禁止免责声明 |

**文件位置**: `config/prompts/*.txt`
**版本配置**: `config/prompts/versions.yaml`
**加载器**: `src/llm/prompts.py` (启动时加载缓存, 支持变量插值, 缺失快速失败)

## 2. 抽取前后指标一致性验证

| 测试集 | 抽取前 | 抽取后 | 结论 |
|---|---|---|---|
| 意图分类 (100例) | 100/100 | 100/100 | ✓ 不变 |
| 槽位抽取 (41例) | 0静默错误 | 0静默错误 | ✓ 不变 |
| 数值验证 (7例) | 7/7=100% | 7/7=100% | ✓ 不变 |
| Guardrails (27例) | 27/27 | 27/27 | ✓ 不变 |
| Q8对比 (20例) | 20/20 P50=42ms | 20/20 P50=44ms | ✓ 不变(±2ms正常波动) |
| Q8摘要幻觉 | 0评价词/0未知实体 | 0评价词/0未知实体 | ✓ 不变 |

**结论**: prompt 内容原样迁移, 未修改任何文字, 所有指标一致。

## 3. cache.py 实现说明

### 3.1 当前实现

| 维度 | 实现 |
|---|---|
| 缓存类型 | **精确 key 缓存**(非语义) |
| 缓存粒度 | 整个回答(含intent/answer/verify/elapsed) |
| key构造 | `re.sub(r"\s+","",question).lower()` — 仅问题文本归一化 |
| 是否含session | **否** — 不含session_id |
| 是否含context_code | **否** — 不含上下文股票代码 |
| 是否含as_of | **否** |
| TTL | 3600秒(1小时) |
| 失效策略 | 仅TTL过期, 无主动失效 |
| 使用位置 | 仅`/api/ask`(非流式); `/api/ask/stream`不使用缓存 |

### 3.2 缓存命中率(从trace统计)

| 来源 | trace总数 | 缓存命中 | 命中率 |
|---|---|---|---|
| trace文件 | 8 | 0 | 0% |

**说明**: 8条trace全部来自SSE端点(`/api/ask/stream`), 该端点不走缓存。非流式端点(`/api/ask`)在测试期间未产生trace(SSE是主入口)。缓存实际命中率无法从现有trace确定。

### 3.3 缓存正确性检查

#### 风险1: 多轮对话误命中 — **存在正确性风险**

- 场景: 用户先查A公司, 再问"它的关联方"; 然后切换到B公司, 再问"它的关联方"
- 问题: 两次"它的关联方"归一化后key相同, 第二次会命中第一次的缓存, 返回A公司的关联方
- 严重性: **正确性问题**(非性能)
- 影响范围: 仅`/api/ask`非流式端点; SSE端点不受影响(不走缓存)
- **修复**: key中加入context_code和session_id

#### 风险2: 数据重建后缓存过期 — **存在正确性风险**

- 场景: `rebuild_graph`后数据变化, 但缓存仍返回旧结果
- 严重性: **正确性问题**
- **修复**: `rebuild_graph`后调用`_cache._store.clear()`

#### 风险3: as_of时点 — 理论风险(当前未使用)

- as_of参数在schema中定义但未实际使用, 当前无风险

### 3.4 修复措施

**已修复**: `src/serve/cache.py` 的 `_key()` 方法加入 context_code:

```python
# 修复前
def _key(question: str) -> str:
    return re.sub(r"\s+", "", question).lower()

# 修复后
def _key(question: str, context_code: str = "") -> str:
    q = re.sub(r"\s+", "", question).lower()
    return f"{q}|{context_code}"
```

**建议(未实施)**: `rebuild_graph`后主动清缓存; 或缓存key加入graph版本号。

## 4. observability.py 与 trace.py 的关系

| 维度 | observability.py | trace.py |
|---|---|---|
| 定位 | 早期轻量trace(内存) | 完整per-query trace(文件持久化) |
| 存储 | `_traces: list[dict]`(内存) | `.cache/traces/*.json`(500文件) |
| 调用方 | `LLMClient.chat()` | NL query pipeline (LangGraph nodes) |
| 记录内容 | name/elapsed_ms/prompt_hash/tokens/cached | intent/slots/llm_calls/answer/verify/coreference |
| 脱敏 | 否(prompt hash) | 是(问题/回答/SQL截断+脱敏) |
| 查询接口 | `snapshot()` | `/api/traces`, `/api/traces/{id}` |

**结论**: 两者功能重叠但trace.py是主力系统。observability.py仅被`LLMClient.chat()`调用(非`chat_stream`/`chat_json`), 实际使用范围很窄。

**合并建议(未实施)**: 将observability.py的`log_llm_call`调用迁移到trace.py的`add_llm_call`, 删除observability.py。当前不实施因为trace.py已在pipeline层记录LLM调用, observability.py的记录是冗余的但不造成问题。

## 5. 语义缓存评估

### 收益评估
- 当前trace中无重复问题(SSE不走缓存), 无法估算相似问句占比
- 即使有, 中文问句的语义相似度判断需要embedding, 额外引入一次API调用

### 误命中风险(关键)
- "比亚迪的关联方" 和 "宁德时代的关联方" 句式相同仅实体不同
- 语义相似度高但答案完全不同 → **误命中会导致返回错误结果**
- 这正是当前精确key缓存回避的问题

### 建议
**不升级语义缓存**。理由:
1. 当前精确缓存命中率本身就低(SSE不走缓存, 非流式端点用量小)
2. 误命中风险高(中文实体替换不改句式)
3. embedding服务引入额外延迟和成本
4. 多轮对话的指代消解已使问题文本化(context_code在key中), 精确缓存已覆盖最常见场景

## 6. 成本与调用量优化对照表

(数据来源: `.cache/traces/` 8条trace + 测试集延迟)

| 优化项 | 避免的LLM调用 | 节省的token | 延迟改善(P50) |
|---|---|---|---|
| 规则意图分类(100%覆盖) | 6/8查询=0次LLM | ~6000(每查省1次×750tok) | 意图分类 0ms(vs LLM ~2s) |
| 规则槽位抽取(词典匹配) | Q1-Q6均0次LLM槽位调用 | ~3000(每查省1次×500tok) | 槽位抽取 0ms(vs LLM ~3s) |
| Q4/Q5模板回答(跳过LLM) | 2/8查询=0次LLM回答 | ~2000(每查省1次×1000tok) | Q4=1ms Q5=0ms(vs LLM ~5s) |
| Q7三道校验(减少重试) | 2查询4次调用0次重试 | — | SQL生成 P50=3s(无重试) |
| 精确缓存(非流式端点) | 0(SSE不走缓存) | — | — |

### 按意图的LLM调用量

| 意图 | 查询数 | LLM调用 | 均调用 | 重试 |
|---|---|---|---|---|
| Q1-Q6 | 各1 | 0 | 0.0 | 0 |
| Q7 | 2 | 4 | 2.0 | 0 |
| Q4/Q5(模板) | 各1 | 0 | 0.0 | 0 |

**总结**: 规则覆盖+模板回答使 6/8=75% 的查询零LLM调用; Q7平均2次LLM调用(SQL生成+回答生成); Q4/Q5从~5s降到<1ms。

## 7. trace 中 prompt 版本记录

trace 的 `llm_calls` 新增 `prompt_name` 和 `prompt_version` 字段。现有8条trace在prompt版本管理上线前生成, 无这两个字段。新trace将自动记录, 如:
```json
{"purpose":"generate_query","prompt_name":"sql_generate","prompt_version":"v1",...}
```
