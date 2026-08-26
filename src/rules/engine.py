"""P3 规则引擎 - 加载 rules.yaml, 实例化 R1-R7, 并发/顺序执行, 置信度合并。

铁律2: 判定 100% 确定性, 无 LLM。
R4 置信度不得高于消歧置信度 -> 在 R4 内部 clamp(已实现)。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml

from src.rules.base import RelatedPartyCandidate, Rule, merge_confidence
from src.rules.r1_direct import R1Direct
from src.rules.r2_direct import R2SameControl
from src.rules.r3_common import R3CommonHolder
from src.rules.r4_director import R4ChainDirector
from src.rules.r5_keyperson import R5KeyPerson
from src.rules.r6_penetrate import R6Penetrate
from src.rules.r7_event import R7Event

RULE_CLASSES = [R1Direct, R2SameControl, R3CommonHolder, R4ChainDirector, R5KeyPerson, R6Penetrate, R7Event]


class RuleEngine:
    def __init__(self, config_path: str = "config/rules.yaml") -> None:
        cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
        self.rules_cfg: dict[str, dict] = cfg.get("rules", {})
        self.rules: list[Rule] = []
        rid_to_cls = {c.rule_id: c for c in RULE_CLASSES}
        for rid, rcfg in self.rules_cfg.items():
            cls = rid_to_cls.get(rid)
            if cls and rcfg.get("enabled", True):
                self.rules.append(cls(rcfg))

    def evaluate(self, store, subject_code: str, as_of: str | None = None) -> list[RelatedPartyCandidate]:
        cands: list[RelatedPartyCandidate] = []
        for rule in self.rules:
            try:
                cands.extend(rule.evaluate(store, subject_code, as_of))
            except Exception as e:  # 单规则出错不拖垮整体
                print(f"  [warn] {rule.rule_id} on {subject_code}: {type(e).__name__}: {e}")
        return merge_confidence(cands)

    def evaluate_timed(self, store, subject_code: str, as_of: str | None = None) -> tuple[list[RelatedPartyCandidate], float]:
        t0 = time.perf_counter()
        cands = self.evaluate(store, subject_code, as_of)
        return cands, time.perf_counter() - t0
