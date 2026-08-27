# 人名消歧评测使用说明

## 人工标注
1. 打开 `data/annotations/person_disambig_sheet.md`
2. 逐对判断是否同一人, 在 person_disambig.jsonl 的每条 same_person 字段填 true/false
3. 标注原则: 保守(信息不足判不同人)

## 跑真金标准准确率
```
py scripts/eval_disambig.py --gold
```
输出: 准确率/precision/recall/混淆矩阵/按置信度分档

## 与银标 93.3% 对照
- 银标(qwen3.7-max 裁判) 93.3% 是独立模型判定, 非人工金标准
- 人工金标准完成后, 与银标逐条对照, 算银标相对人工的准确率
- 若人工 vs 银标差异大, 说明银标存在系统性偏差(如对常见名过度保守)
