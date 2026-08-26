"""P2 贪心聚类 - 单链法, O(N*K) 而非 O(N^2)。

每条记录与各已有簇的代表比较, 同人则并入, 否则新簇。
decider(i, rep_i) -> Verdict(same_person, confidence, note)。
"""
from __future__ import annotations

from typing import Callable, Any


def greedy_cluster(n: int, decider: Callable[[int, int], Any]) -> list[list[int]]:
    clusters: list[list[int]] = []
    reps: list[int] = []
    for i in range(n):
        placed = False
        for ci, rep in enumerate(reps):
            v = decider(i, rep)
            if getattr(v, "same_person", False):
                clusters[ci].append(i)
                placed = True
                break
        if not placed:
            clusters.append([i])
            reps.append(i)
    return clusters
