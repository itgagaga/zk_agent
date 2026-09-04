"""竞赛评测使用的可复现统计方法。

模块只依赖 Python 标准库，负责把原始计数和耗时样本转换为可审计的
统计量。绘图与报告生成放在 ``generate_competition_report`` 中，避免把
展示逻辑混进指标计算。
"""

from __future__ import annotations

from hashlib import sha256
from itertools import combinations
import json
import math
import random
from statistics import fmean, median, stdev
from typing import Callable, Sequence


Z_95 = 1.959963984540054


def percentile(values: Sequence[float], q: float) -> float:
    """按线性插值计算分位数，``q`` 的范围为 0 到 1。"""
    if not 0 <= q <= 1:
        raise ValueError("q 必须位于 [0, 1]")
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("values 不能为空")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def wilson_interval(successes: int, total: int, z: float = Z_95) -> tuple[float, float]:
    """计算二项比例的 Wilson 置信区间。"""
    if total <= 0:
        raise ValueError("total 必须大于 0")
    if not 0 <= successes <= total:
        raise ValueError("successes 必须位于 [0, total]")
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    half_width = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total + z * z / (4 * total * total)
        )
        / denominator
    )
    return max(0.0, center - half_width), min(1.0, center + half_width)


def bootstrap_interval(
    values: Sequence[float],
    statistic: Callable[[Sequence[float]], float],
    *,
    confidence: float = 0.95,
    resamples: int = 5000,
    seed: int = 20260901,
) -> tuple[float, float]:
    """使用固定随机种子的百分位 Bootstrap 区间。"""
    numeric = [float(value) for value in values]
    if not numeric:
        raise ValueError("values 不能为空")
    if not 0 < confidence < 1:
        raise ValueError("confidence 必须位于 (0, 1)")
    if resamples <= 0:
        raise ValueError("resamples 必须大于 0")
    generator = random.Random(seed)
    sample_size = len(numeric)
    estimates = [
        float(statistic([numeric[generator.randrange(sample_size)] for _ in numeric]))
        for _ in range(resamples)
    ]
    alpha = (1 - confidence) / 2
    return percentile(estimates, alpha), percentile(estimates, 1 - alpha)


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def classification_metrics(
    matrix: Sequence[Sequence[int]], labels: Sequence[str]
) -> dict[str, object]:
    """由多分类混淆矩阵计算逐类和总体统计指标。

    总体部分同时给出 accuracy、macro/micro/weighted F1、balanced
    accuracy、Cohen's kappa 和多分类 MCC。
    """
    size = len(labels)
    if size == 0 or len(matrix) != size or any(len(row) != size for row in matrix):
        raise ValueError("matrix 必须是与 labels 等长的非空方阵")
    numeric = [[int(value) for value in row] for row in matrix]
    if any(value < 0 for row in numeric for value in row):
        raise ValueError("混淆矩阵计数不能为负数")

    row_totals = [sum(row) for row in numeric]
    column_totals = [sum(numeric[row][column] for row in range(size)) for column in range(size)]
    total = sum(row_totals)
    if total <= 0:
        raise ValueError("混淆矩阵总样本数必须大于 0")

    correct = sum(numeric[index][index] for index in range(size))
    per_class: list[dict[str, object]] = []
    for index, label in enumerate(labels):
        true_positive = numeric[index][index]
        false_positive = column_totals[index] - true_positive
        false_negative = row_totals[index] - true_positive
        true_negative = total - true_positive - false_positive - false_negative
        precision = _safe_divide(true_positive, true_positive + false_positive)
        recall = _safe_divide(true_positive, true_positive + false_negative)
        f1 = _safe_divide(2 * precision * recall, precision + recall)
        specificity = _safe_divide(true_negative, true_negative + false_positive)
        per_class.append(
            {
                "label": str(label),
                "support": row_totals[index],
                "predicted": column_totals[index],
                "tp": true_positive,
                "fp": false_positive,
                "fn": false_negative,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "specificity": specificity,
            }
        )

    accuracy = correct / total
    macro_precision = fmean(float(item["precision"]) for item in per_class)
    macro_recall = fmean(float(item["recall"]) for item in per_class)
    macro_f1 = fmean(float(item["f1"]) for item in per_class)
    weighted_f1 = sum(
        float(item["f1"]) * int(item["support"]) for item in per_class
    ) / total
    expected_agreement = sum(
        row_totals[index] * column_totals[index] for index in range(size)
    ) / (total * total)
    kappa = _safe_divide(accuracy - expected_agreement, 1 - expected_agreement)
    mcc_numerator = correct * total - sum(
        row_totals[index] * column_totals[index] for index in range(size)
    )
    mcc_denominator = math.sqrt(
        (total * total - sum(value * value for value in column_totals))
        * (total * total - sum(value * value for value in row_totals))
    )
    accuracy_low, accuracy_high = wilson_interval(correct, total)
    return {
        "sample_size": total,
        "correct": correct,
        "accuracy": accuracy,
        "accuracy_ci_95": [accuracy_low, accuracy_high],
        "micro_f1": accuracy,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "balanced_accuracy": macro_recall,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "cohen_kappa": kappa,
        "multiclass_mcc": _safe_divide(mcc_numerator, mcc_denominator),
        "per_class": per_class,
    }


def latency_distribution(values: Sequence[float]) -> dict[str, object]:
    """汇总延迟的集中趋势、尾部风险、离散度和 Bootstrap 区间。"""
    numeric = [float(value) for value in values]
    if not numeric:
        raise ValueError("values 不能为空")
    if any(value < 0 for value in numeric):
        raise ValueError("延迟不能为负数")
    mean_value = fmean(numeric)
    median_value = median(numeric)
    deviation = stdev(numeric) if len(numeric) > 1 else 0.0
    return {
        "count": len(numeric),
        "min": min(numeric),
        "max": max(numeric),
        "mean": mean_value,
        "standard_deviation": deviation,
        "coefficient_of_variation": _safe_divide(deviation, mean_value),
        "median": median_value,
        "p90": percentile(numeric, 0.90),
        "p95": percentile(numeric, 0.95),
        "iqr": percentile(numeric, 0.75) - percentile(numeric, 0.25),
        "mean_ci_95_bootstrap": list(bootstrap_interval(numeric, fmean)),
        "median_ci_95_bootstrap": list(bootstrap_interval(numeric, median)),
    }


def _average_ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(indexed):
        end = start + 1
        while end < len(indexed) and indexed[end][1] == indexed[start][1]:
            end += 1
        average_rank = ((start + 1) + end) / 2
        for position in range(start, end):
            ranks[indexed[position][0]] = average_rank
        start = end
    return ranks


def mann_whitney_exact(first: Sequence[float], second: Sequence[float]) -> dict[str, float]:
    """计算小样本双侧 Mann-Whitney U 精确置换检验。"""
    left = [float(value) for value in first]
    right = [float(value) for value in second]
    if not left or not right:
        raise ValueError("两组样本都不能为空")
    pooled = left + right
    ranks = _average_ranks(pooled)
    left_size = len(left)
    right_size = len(right)
    observed = sum(ranks[:left_size]) - left_size * (left_size + 1) / 2
    center = left_size * right_size / 2
    observed_distance = abs(observed - center)
    extreme = 0
    permutations = 0
    for selected in combinations(range(len(pooled)), left_size):
        u_value = sum(ranks[index] for index in selected) - left_size * (left_size + 1) / 2
        if abs(u_value - center) >= observed_distance - 1e-12:
            extreme += 1
        permutations += 1
    return {
        "u": observed,
        "two_sided_p": extreme / permutations,
        "exact_permutations": float(permutations),
    }


def cliffs_delta(first: Sequence[float], second: Sequence[float]) -> float:
    """计算 Cliff's delta；正值表示第一组整体更大。"""
    left = [float(value) for value in first]
    right = [float(value) for value in second]
    if not left or not right:
        raise ValueError("两组样本都不能为空")
    greater = sum(a > b for a in left for b in right)
    smaller = sum(a < b for a in left for b in right)
    return (greater - smaller) / (len(left) * len(right))


def compare_latency(candidate: Sequence[float], baseline: Sequence[float]) -> dict[str, float]:
    """比较候选模式与基线模式的延迟差异和效应量。"""
    candidate_numeric = [float(value) for value in candidate]
    baseline_numeric = [float(value) for value in baseline]
    test = mann_whitney_exact(candidate_numeric, baseline_numeric)
    return {
        "mean_ratio": _safe_divide(fmean(candidate_numeric), fmean(baseline_numeric)),
        "median_ratio": _safe_divide(median(candidate_numeric), median(baseline_numeric)),
        "median_difference_seconds": median(candidate_numeric) - median(baseline_numeric),
        "cliffs_delta": cliffs_delta(candidate_numeric, baseline_numeric),
        "mann_whitney_u": test["u"],
        "mann_whitney_exact_two_sided_p": test["two_sided_p"],
        "exact_permutations": test["exact_permutations"],
    }


def rag_metrics(k_values: Sequence[int], hits: Sequence[int], total: int) -> dict[str, object]:
    """计算 Recall@K 区间、边际收益、AUC 和帕累托前沿。"""
    if len(k_values) != len(hits) or not k_values:
        raise ValueError("k_values 与 hits 必须非空且等长")
    points: list[dict[str, object]] = []
    previous_hits = 0
    previous_k = 0
    for raw_k, raw_hits in sorted(zip(k_values, hits), key=lambda item: item[0]):
        k = int(raw_k)
        hit = int(raw_hits)
        if k <= 0 or not previous_k < k or not previous_hits <= hit <= total:
            raise ValueError("K 必须递增，hits 必须单调且位于 [0, total]")
        low, high = wilson_interval(hit, total)
        points.append(
            {
                "k": k,
                "hits": hit,
                "total": total,
                "recall": hit / total,
                "ci_95": [low, high],
                "incremental_hits": hit - previous_hits,
                "incremental_recall": (hit - previous_hits) / total,
                "extra_k": k - previous_k,
                "gain_per_extra_candidate": _safe_divide(
                    hit - previous_hits, (k - previous_k) * total
                ),
            }
        )
        previous_k = k
        previous_hits = hit

    pareto_k: list[int] = []
    for point in points:
        dominated = any(
            int(other["k"]) <= int(point["k"])
            and float(other["recall"]) >= float(point["recall"])
            and (
                int(other["k"]) < int(point["k"])
                or float(other["recall"]) > float(point["recall"])
            )
            for other in points
        )
        if not dominated:
            pareto_k.append(int(point["k"]))

    min_k = int(points[0]["k"])
    max_k = int(points[-1]["k"])
    area = sum(
        (int(right["k"]) - int(left["k"]))
        * (float(left["recall"]) + float(right["recall"]))
        / 2
        for left, right in zip(points, points[1:])
    )
    normalized_auc = _safe_divide(area, max_k - min_k)
    return {
        "points": points,
        "normalized_auc_recall_vs_k": normalized_auc,
        "pareto_frontier_k": pareto_k,
        "dominated_k": [int(point["k"]) for point in points if int(point["k"]) not in pareto_k],
    }


def required_sample_size_for_proportion(
    half_width: float, *, expected_proportion: float = 0.5, z: float = Z_95
) -> int:
    """估算给定比例置信区间半宽所需样本数（正态近似）。"""
    if not 0 < half_width < 1:
        raise ValueError("half_width 必须位于 (0, 1)")
    if not 0 < expected_proportion < 1:
        raise ValueError("expected_proportion 必须位于 (0, 1)")
    return math.ceil(
        z * z * expected_proportion * (1 - expected_proportion) / (half_width * half_width)
    )


def snapshot_digest(data: object) -> str:
    """返回与 JSON 格式空白无关的 SHA-256 数据指纹。"""
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()

