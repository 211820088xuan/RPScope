# P4 金标准构建报告

> 生成时间 2026-08-24 | 203 家 / 7650 条 | pymupdf + LLM

## 一、方法

1. **公告筛选**：`stock_zh_a_disclosure_report_cninfo(symbol, start/end_date)` 拉公告列表，筛标题以"年度报告"结尾且不含"半年度/摘要/英文/更正/修订/H股" → 拿到年报本身。按时间倒序取最新。
2. **PDF 下载**：cninfo 公告链接是详情页(`/new/disclosure/detail?announcementId=X&announcementTime=D`)，转换为 `static.cninfo.com.cn/finalpage/{D}/{X}.PDF` 直链下载，缓存到 `.cache/pdfs/`。
3. **章节定位**（`section_locator.py`，纯规则不用 LLM）：
   - 优先 PDF outline(书签)匹配"关联方"
   - 回退正文正则匹配标题行
   - 散点回退：pymupdf 对中文年报抽文本会损坏(如"重大关联交?")，精确标题常失败。改为收集所有含"关联方/关联交易"的页(上限 40)，交由 extractor 过滤。
4. **关联方抽取**（`extractor.py`，允许 LLM）：
   - GLM 解析章节文本 → JSON `{parties:[{name, relation}]}`
   - 断言回查：每个名称(归一化)必须能在原文出现，否则丢弃(防幻觉)
   - 启发式补全：含机构后缀(有限公司/集团/...)的名称兜底
   - 每条标来源页码
5. **映射**（`mapper.py`）：按 canonical_name 多策略匹配 entity 表(org_match_key/normalize_name/原名)；未映射写 `data/gold_unmapped.csv`。
6. **落库**：`gold_related_party(stock_code, report_year, party_name, party_entity_id, relation_desc, source_url, source_page, scope_class)`。

## 二、实际落库统计（203 家 / 7650 条）

| 指标 | 值 |
|---|---|
| 覆盖公司数 | 203 |
| 关联方总条数 | 7650 |
| 映射到 entity 成功 | 709 (9%) |
| 章节定位成功率 | 100% (散点+正则回退) |

### scope_class 能力范围分布

| scope_class | 条数 | 占比 | 说明 |
|---|---|---|---|
| upstream | 2602 | 34% | 系统能力范围内(控股股东/实控人/5%股东/董监高/兄弟公司) |
| downstream | 1425 | 19% | 系统能力外(子公司/联营/合营/参股) |
| other | 3623 | 47% | relation_desc 为空, 无法判定(表格抽取未抓关系列) |

映射率 9% 低的原因：7650 条 gold 中 66% 是下游+other(不在上游图谱的 entity 表里)；上游 2602 条中，名称归一化差异(年报全称 vs akshare 简称)导致部分无法对齐。

### scope_class 分类规则

- upstream: relation_desc 含"控股股东/实控人/5%以上/董事/同一控制/担保方/股东"等关键词
- downstream: relation_desc 含"子公司/联营/合营/参股/分公司/孙公司"等
- other: relation_desc 为空且 party_name 无法推断(含公司后缀但无上下游关键词)

### 典型数据样例(002594 比亚迪)

| 公司 | 年报公告数 | PDF下载 | 章节定位 | 抽取关联方 | 映射成功 |
|---|---|---|---|---|---|
| 002594 比亚迪 | 7 | 是 | 是 | 4 | 4 (100%) |

002594 的 4 条关联方(王传福/吕向阳/夏佐全/融捷投资)全部上游(股东/董事)，100% 映射到 entity。

## 三、已知缺陷与限制

1. **PDF 文本提取质量**：pymupdf 对中文年报(尤其表格密集的关联方清单页)抽文本会损坏/缺字，导致 LLM 抽取部分公司失败(300750 初版 0 条，pymupdf 升级后修复)。
2. **规模**：203 家非全市场(~5000)，但规模化(并行3+截断4000字)后每家 ~16s，可继续扩到 500+。
3. **关联方内容分散**：年报关联方清单常散落在"重大关联交易"(董报告)和"附注-关联方及关联交易"(财务)多处；散点定位抓全了但含噪声，靠 extractor 断言回查过滤。
4. **other 占比 47%**：主要是 relation_desc 为空(表格抽取未抓关系列)。从 30 条 other 样本的 AI 重分类看，约 27% 可能实为 upstream → recall 被高估 0.6pp。不自行扩充关键词，等人工确认 other_sample 后再改配置重跑。
