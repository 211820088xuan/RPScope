# P0 接口探测原始结果

> 探测时间 2026-08-22 19:11:43 | 可用 14/18

| 接口 | 用途 | 可调用 | 行数 | 列数 | 耗时s | 错误 |
|---|---|---|---|---|---|---|
| `stock_info_a_code_name` | canonical ID | 是 | 5549 | 2 | 0.045 |  |
| `stock_individual_info_em` |  | 是 | 0 | 0 | 11.596 | ConnectionError: ('Connection aborted.',… |
| `stock_gdfx_free_holding_detail_em` | 共同股东边 | 是 | 55603 | 12 | 0.083 |  |
| `stock_gdfx_top_10_em` |  | 是 | 10 | 7 | 1.388 |  |
| `stock_gdfx_free_top_10_em` |  | 是 | 0 | 0 | 0.882 | KeyError: 'sdltgd' |
| `stock_gdfx_holding_analyse_em` |  | 是 | 124980 | 15 | 540.76 |  |
| `stock_hold_control_cninfo` | R2 同一控制 | 是 | 5577 | 8 | 5.708 |  |
| `stock_hold_management_detail_cninfo` |  | 是 | 0 | 0 | 0.21 | KeyError: '002594' |
| `stock_hold_num_cninfo` |  | 是 | 5207 | 9 | 1.882 |  |
| `stock_zh_a_disclosure_relation_cninfo` | P4 金标准捷径 | 是 | 67 | 5 | 1.927 |  |
| `stock_zh_a_disclosure_report_cninfo` | P4 金标准 | 是 | 92 | 5 | 0.998 |  |
| `stock_board_industry_cons_ths` |  | 否 | 0 | 0 | 0.0 | 接口不存在(该 akshare 版本无此函数) |
| `stock_ggcg_em` |  | 是 | 146086 | 16 | 387.002 |  |
| `stock_inner_trade_xq` |  | 是 | 24968 | 9 | 3.269 |  |
| `stock_gdfx_free_holding_change_em` |  | 是 | 34481 | 10 | 89.474 |  |
| `stock_cg_guarantee_cninfo` | R7 担保关联 | 是 | 3106 | 7 | 1.72 |  |
| `stock_cg_lawsuit_cninfo` |  | 是 | 953 | 5 | 1.335 |  |
| `stock_cg_equity_mortgage_cninfo` |  | 是 | 103 | 10 | 1.157 |  |

## 各接口列名
### `stock_info_a_code_name` (A股代码简称全表)
- 签名: `() -> pandas.DataFrame`
- 参数: `{}`
- 列名(2): ['code', 'name']

### `stock_individual_info_em` (个股基本信息)
- 签名: `(symbol: str = '603777', timeout: float = None) -> pandas.DataFrame`
- 参数: `{'symbol': '002594'}`
- 列名(0): []
- 错误: ConnectionError: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))

### `stock_gdfx_free_holding_detail_em` (十大流通股东明细(批量,核心))
- 签名: `(date: str = '20210930') -> pandas.DataFrame`
- 参数: `{'date': '20251231'}`
- 列名(12): ['序号', '股东名称', '股东类型', '股票代码', '股票简称', '报告期', '期末持股-数量', '期末持股-数量变化', '期末持股-数量变化比例', '期末持股-持股变动', '期末持股-流通市值', '公告日']

### `stock_gdfx_top_10_em` (十大股东(个股))
- 签名: `(symbol: str = 'sh688686', date: str = '20210630') -> pandas.DataFrame`
- 参数: `{'symbol': 'sz002594', 'date': '20251231'}`
- 列名(7): ['名次', '股东名称', '股份类型', '持股数', '占总股本持股比例', '增减', '变动比率']

### `stock_gdfx_free_top_10_em` (十大流通股东(个股))
- 签名: `(symbol: str = 'sh688686', date: str = '20240930') -> pandas.DataFrame`
- 参数: `{'symbol': '002594'}`
- 列名(0): []
- 错误: KeyError: 'sdltgd'

### `stock_gdfx_holding_analyse_em` (股东持股分析)
- 签名: `(date: str = '20230331') -> pandas.DataFrame`
- 参数: `{'date': '20251231'}`
- 列名(15): ['序号', '股东名称', '股东类型', '股票代码', '股票简称', '报告期', '期末持股-数量', '期末持股-数量变化', '期末持股-数量变化比例', '期末持股-持股变动', '期末持股-流通市值', '公告日', '公告日后涨跌幅-10个交易日', '公告日后涨跌幅-30个交易日', '公告日后涨跌幅-60个交易日']

### `stock_hold_control_cninfo` (实控人持股变动(R2关键))
- 签名: `(symbol: str = '全部') -> pandas.DataFrame`
- 参数: `{'symbol': '全部'}`
- 列名(8): ['证券代码', '证券简称', '变动日期', '实际控制人名称', '控股数量', '控股比例', '直接控制人名称', '控制类型']

### `stock_hold_management_detail_cninfo` (高管持股变动明细)
- 签名: `(symbol: str = '增持') -> pandas.DataFrame`
- 参数: `{'symbol': '002594'}`
- 列名(0): []
- 错误: KeyError: '002594'

### `stock_hold_num_cninfo` (股东人数)
- 签名: `(date: str = '20210630') -> pandas.DataFrame`
- 参数: `{'date': '20251231'}`
- 列名(9): ['证券代码', '证券简称', '变动日期', '本期股东人数', '上期股东人数', '股东人数增幅', '本期人均持股数量', '上期人均持股数量', '人均持股数量增幅']

### `stock_zh_a_disclosure_relation_cninfo` (关联方披露(P4优先验证))
- 签名: `(symbol: str = '000001', market: str = '沪深京', start_date: str = '20230618', end_date: str = '20231219') -> pandas.DataFrame`
- 参数: `{'symbol': '002594'}`
- 列名(5): ['代码', '简称', '公告标题', '公告时间', '公告链接']

### `stock_zh_a_disclosure_report_cninfo` (信披公告(P4金标准))
- 签名: `(symbol: str = '000001', market: str = '沪深京', keyword: str = '', category: str = '', start_date: str = '20230618', end_date: str = '20231219') -> pandas.DataFrame`
- 参数: `{'symbol': '002594'}`
- 列名(5): ['代码', '简称', '公告标题', '公告时间', '公告链接']

### `stock_board_industry_cons_ths` (行业板块成分股)
- 签名: ``
- 参数: `{}`
- 列名(0): []
- 错误: 接口不存在(该 akshare 版本无此函数)

### `stock_ggcg_em` (高管持股)
- 签名: `(symbol: str = '全部') -> pandas.DataFrame`
- 参数: `{}`
- 列名(16): ['代码', '名称', '最新价', '涨跌幅', '股东名称', '持股变动信息-增减', '持股变动信息-变动数量', '持股变动信息-占总股本比例', '持股变动信息-占流通股比例', '变动后持股情况-持股总数', '变动后持股情况-占总股本比例', '变动后持股情况-持流通股数', '变动后持股情况-占流通股比例', '变动开始日', '变动截止日', '公告日']

### `stock_inner_trade_xq` (内部交易(含董监高关系))
- 签名: `() -> pandas.DataFrame`
- 参数: `{}`
- 列名(9): ['股票代码', '股票名称', '变动日期', '变动人', '变动股数', '成交均价', '变动后持股数', '与董监高关系', '董监高职务']

### `stock_gdfx_free_holding_change_em` (股东持股变动)
- 签名: `(date: str = '20210930') -> pandas.DataFrame`
- 参数: `{'date': '20251231'}`
- 列名(10): ['序号', '股东名称', '股东类型', '期末持股只数统计-总持有', '期末持股只数统计-新进', '期末持股只数统计-增加', '期末持股只数统计-不变', '期末持股只数统计-减少', '流通市值统计', '持有个股']

### `stock_cg_guarantee_cninfo` (对外担保(R7))
- 签名: `(symbol: str = '全部', start_date: str = '20180630', end_date: str = '20210927') -> pandas.DataFrame`
- 参数: `{}`
- 列名(7): ['证券代码', '证券简称', '公告统计区间', '担保笔数', '担保金额', '归属于母公司所有者权益', '担保金融占净资产比例']

### `stock_cg_lawsuit_cninfo` (公司诉讼)
- 签名: `(symbol: str = '全部', start_date: str = '20180630', end_date: str = '20210927') -> pandas.DataFrame`
- 参数: `{}`
- 列名(5): ['证券代码', '证券简称', '公告统计区间', '诉讼次数', '诉讼金额']

### `stock_cg_equity_mortgage_cninfo` (股权质押)
- 签名: `(date: str = '20210930') -> pandas.DataFrame`
- 参数: `{}`
- 列名(10): ['股票代码', '股票简称', '公告日期', '出质人', '质权人', '质押数量', '占总股本比例', '质押解除数量', '质押事项', '累计质押占总股本比例']
