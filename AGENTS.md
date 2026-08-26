# RPScope 项目约定

> opencode 每次进入项目时读取此文件以获取上下文。本文件是 `docs/RPScope-开发指导.md` 的压缩版。

## 项目一句话
给定一家 A 股上市公司，自动产出一份**关联方与风险底稿**：谁是它的关联方、通过什么路径关联、依据是哪条规则和哪份数据、这些关联方最近发生了什么风险事件。

## 绝对约束
- 关联方判定逻辑中不得调用 LLM。判定只能用确定性规则 + Cypher 查询。
- LLM 仅允许出现在三处：`src/disambiguate/llm_fallback.py`、`src/extract/event_extractor.py`、`src/report/writer.py`
- 所有图上的边必须带 `valid_from` / `valid_to`，所有查询必须接受 `as_of_date` 参数
- 所有对外结论必须携带：规则编号、路径、数据来源、报告期、置信度等级
- 系统不输出任何投资建议、评级或价值判断

## 技术栈
Python 3.11 / FastAPI / Neo4j 5.x / PostgreSQL 16 + pgvector / akshare / LangGraph / GLM-5.2(OpenAI 兼容, 经 DashScope)
> 实际运行环境为 Python 3.14（机器未装 3.11）；akshare 为纯 Python 栈，3.14 兼容。
> **P1 存储（用户决策 2026-08-22）**：机器无 Docker/Java/Neo4j，P1 起临时用 **SQLite(事实源) + networkx(图计算视图)**，背后抽象 `src/store/` 与 `src/graph/` 接口。Docker 就绪后换 Neo4j+Postgres，仅重写 query 层，ETL/normalize/disambig 不受影响。

## 编码规范
- 所有外部数据接入必须有本地缓存层，禁止在开发循环中反复打真实接口
- 所有 LLM 调用必须走 `src/llm/client.py` 的统一封装（内含重试/JSON修复/成本计数）
- 新增规则必须同时新增对应的单元测试和 fixture
- 提交前跑 `make check`（ruff + mypy + pytest）

## 里程碑顺序（不许跳）
P0 数据探针 → P1 数据层+图Schema → P2 实体消歧 → P3 规则引擎 → P4 金标准 → P5 评测v1 → P6 事件层 → P7 检索+Agent → P8 评测v2 → P9 底稿产品层 → P10 工程化 → P11 文档开源

## 三条铁律
1. P0 数据探针必须第一个做，且必须诚实记录结果。所有阈值建立在真实数据分布上。
2. 关联方判定逻辑里不允许出现 LLM。
3. 每个里程碑必须产出可验证的数字，并写进 `docs/progress.md`。

## 目录结构（关键）
- `src/data/` akshare 接入 + 缓存 + ETL
- `src/normalize/` 名称规范化与机构归并
- `src/disambiguate/` 人名消歧（含 LLM 兜底）
- `src/graph/` Neo4j 客户端与重建
- `src/rules/` R1-R7 规则引擎【无 LLM】
- `src/gold/` 金标准构建
- `src/extract/` 事件抽取（LLM）
- `src/retrieval/` 向量/BM25/RRF
- `src/agent/` LangGraph 编排 + 意图路由
- `src/report/` 底稿组装与撰写 + 回查
- `src/eval/` 评测与消融
- `src/llm/` LLM 统一封装
- `src/serve/` FastAPI + 缓存 + 限流 + 追踪
- `scripts/` 一次性/批量脚本
- `docs/progress.md` 每个里程碑追加
