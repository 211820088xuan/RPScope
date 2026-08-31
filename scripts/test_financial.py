"""测试 akshare 能否取到财务/估值/行业数据。"""
import sys
sys.path.insert(0, ".")
from src.data.akshare_client import AkshareClient

c = AkshareClient()
code = "002594"

# 1. 公司基本信息(行业/市值/上市日)
try:
    df = c.get("stock_individual_info_em", symbol=code)
    print("=== stock_individual_info_em ===")
    print(df.to_string() if df is not None else "None")
except Exception as e:
    print(f"stock_individual_info_em: {e}")

# 2. 估值指标(PE/PB)
try:
    df = c.get("stock_a_indicator_lg", symbol=code)
    print("\n=== stock_a_indicator_lg (PE/PB) ===")
    if df is not None:
        print(df.tail(3).to_string())
except Exception as e:
    print(f"stock_a_indicator_lg: {e}")

# 3. 财务摘要
try:
    df = c.get("stock_financial_abstract", symbol=code)
    print("\n=== stock_financial_abstract ===")
    if df is not None:
        print(df.head(3).to_string())
except Exception as e:
    print(f"stock_financial_abstract: {e}")

# 4. 实时行情(含 PE/PB/市值)
try:
    df = c.get("stock_zh_a_spot_em")
    print("\n=== stock_zh_a_spot_em (实时行情) ===")
    if df is not None:
        row = df[df['代码'].astype(str).str.zfill(6) == code]
        if not row.empty:
            print(row.to_string())
except Exception as e:
    print(f"stock_zh_a_spot_em: {e}")
