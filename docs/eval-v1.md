# P5 评测 v1（口径修正版）

> 107 家公司 | 三组口径: 严格/可比(upstream)/能力外(downstream)

## 一、评测口径说明

### 为什么严格口径不适用
- 金标准取自年报「关联方及关联交易」全部条目, 含大量下游(子公司/联营/合营)。系统基于公开接口只覆盖上游(股东/董监高/实控人)。两个集合天生几乎不相交, 全量算 recall 不反映真实性能。
- gold_related_party 的 scope_class 分类: upstream(系统能力内) / downstream(能力外) / other(relation_desc 空无法判定)。

### scope_class 分布

| scope_class | 条数 | 占比 |
|---|---|---|
| upstream | 1475 | 36.2% |
| downstream | 883 | 21.7% |
| other | 1711 | 42.0% |
| 合计 | 4069 | 100% |

other 1711 条(42.0%)来自 relation_desc 为空的表格抽取项, 名称含公司后缀但无关系描述, 无法按规则判定上下游。不硬分, 排除出可比口径。

## 二、三组口径对照

| 口径 | gold 分母 | P | R | F1 | matched | sys_only | gold_only |
|---|---|---|---|---|---|---|---|
| strict (全部 gold(含上下游+other)) | 3620 | 12.6% | 1.4% | 2.5% | 50 | 347 | 3570 |
| comparable (仅系统能力内(upstream)) | 1474 | 7.6% | 2.0% | 3.2% | 30 | 367 | 1444 |
| capability_out (仅系统能力外(downstream)) | 866 | 0.3% | 0.1% | 0.2% | 1 | 396 | 865 |

### 可比口径(主指标)说明
- **可比口径 precision = 7.6%**: 系统 matched 30 / 系统候选 397
- **可比口径 recall = 2.0%**: 系统 matched 30 / upstream gold 1474
- 这是系统能力范围内的真实 recall, 反映系统在「应该能找到」的关联方上的表现。

## 三、按规则分档(可比口径)

| 规则 | 候选总数 | matched | precision |
|---|---|---|---|
| R1 | 195 | 30 | 15.4% |
| R2 | 152 | 0 | 0.0% |
| R3 | 21 | 0 | 0.0% |
| R4 | 24 | 0 | 0.0% |
| R5 | 8 | 0 | 0.0% |

## 四、按置信度分档(可比口径)

| 置信度 | 候选总数 | matched | precision |
|---|---|---|---|
| high | 374 | 30 | 8.0% |
| low | 23 | 0 | 0.0% |
| medium | 2 | 0 | 0.0% |

## 五、阈值敏感性(R1 related_party, 可比口径)

| R1 阈值% | matched | sys_only | P | R |
|---|---|---|---|---|
| 3.0 | 32 | 418 | 7.1% | 2.2% |
| 5.0 | 30 | 367 | 7.6% | 2.0% |
| 7.0 | 24 | 314 | 7.1% | 1.6% |
| 10.0 | 21 | 282 | 6.9% | 1.4% |

## 六、规则消融(可比口径)

| 禁用规则 | matched | sys_only | P | R |
|---|---|---|---|---|
| (全开基线) | 30 | 367 | 7.6% | 2.0% |
| -R1 | 0 | 204 | 0.0% | 0.0% |
| -R2 | 30 | 216 | 12.2% | 2.0% |
| -R3 | 30 | 346 | 8.0% | 2.0% |
| -R4 | 30 | 344 | 8.0% | 2.0% |

## 七、人工三分类(system_only 核查)
- CSV: data/reviews/system_only_review.csv (50 条待人工填 human_class)
- 判定标准: true_omission(真漏报,系统价值) / reasonable_undisclosed(合理未披露) / system_error(系统误报)
- 人工未填时留占位; 填后跑 scripts/summarize_review.py 算修正后 precision

## 八、本评测局限性
- scope_class 分类基于 relation_desc 关键词, other 37.1% 是 relation_desc 空白所致(表格抽取未抓关系列)。
- 可比口径 gold=upstream 子集, 仍受名称对齐限制(别名/简称不一致导致假 gold_only)。
- 107 家非全市场, 非分层抽样。
- system_only 待人工核查; 不核查则 P 偏严(系统发现未披露全算 FP, 但其中真漏报是 TP)。
