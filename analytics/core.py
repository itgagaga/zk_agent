"""与绘图无关的统计核心函数。"""

from __future__ import annotations

from collections import Counter
from statistics import fmean, median
from typing import Iterable, Mapping, Sequence


def count_by_field(
    rows: Iterable[Mapping[str, object]],
    field: str,
    *,
    missing_label: str = "未标注",
) -> dict[str, int]:
    """按字段统计记录数量，空值统一归入 ``missing_label``。"""
    counts: Counter[str] = Counter()
    for row in rows:
        raw = row.get(field)
        label = str(raw).strip() if raw is not None else ""
        counts[label or missing_label] += 1
    return dict(counts)


def _percentile(values: Sequence[float], percentile: float) -> float:
    """使用线性插值计算百分位数，与 NumPy 默认算法一致。"""
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def chunk_length_summary(chunks: Sequence[str]) -> dict[str, float | int]:
    """汇总文本片段字符长度。"""
    lengths = [len(chunk or "") for chunk in chunks]
    if not lengths:
        return {
            "count": 0,
            "min": 0,
            "max": 0,
            "mean": 0.0,
            "median": 0.0,
            "p95": 0.0,
        }
    return {
        "count": len(lengths),
        "min": min(lengths),
        "max": max(lengths),
        "mean": fmean(lengths),
        "median": median(lengths),
        "p95": _percentile(lengths, 0.95),
    }


def calculate_recall_at_k(
    ranked_titles: Sequence[Sequence[str]],
    expected_titles: Sequence[set[str]],
    k_values: Sequence[int],
) -> dict[int, float]:
    """计算每个 K 值下至少命中一个期望标题的查询比例。"""
    if len(ranked_titles) != len(expected_titles):
        raise ValueError("检索结果数量与标准答案数量不一致")
    if not ranked_titles:
        return {int(k): 0.0 for k in k_values}

    recall: dict[int, float] = {}
    for raw_k in k_values:
        k = int(raw_k)
        if k <= 0:
            raise ValueError("K 必须大于 0")
        hits = sum(
            bool(set(results[:k]) & expected)
            for results, expected in zip(ranked_titles, expected_titles)
        )
        recall[k] = hits / len(ranked_titles)
    return recall


def build_confusion_matrix(
    expected: Sequence[str],
    predicted: Sequence[str],
    labels: Sequence[str],
) -> list[list[int]]:
    """生成以真实标签为行、预测标签为列的混淆矩阵。"""
    if len(expected) != len(predicted):
        raise ValueError("真实标签和预测标签数量不一致")
    index = {label: position for position, label in enumerate(labels)}
    matrix = [[0 for _ in labels] for _ in labels]
    for truth, guess in zip(expected, predicted):
        if truth not in index or guess not in index:
            raise ValueError(f"未知标签：{truth!r} 或 {guess!r}")
        matrix[index[truth]][index[guess]] += 1
    return matrix


def latency_summary(values: Sequence[float]) -> dict[str, float | int]:
    """汇总响应耗时，单位由调用方决定。"""
    numeric = [float(value) for value in values]
    if not numeric:
        return {"count": 0, "mean": 0.0, "median": 0.0, "p95": 0.0}
    return {
        "count": len(numeric),
        "mean": fmean(numeric),
        "median": median(numeric),
        "p95": _percentile(numeric, 0.95),
    }
