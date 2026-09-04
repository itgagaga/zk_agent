"""从冻结评测快照生成竞赛统计报告、指标 JSON 和图表。

运行方式：

    python -m analytics.generate_competition_report

默认读取 ``analytics/results/paper_metrics_2026-07-29.json``，所有图表都由
同一份统计结果派生，避免报告、图和口头答辩中的数字互相矛盾。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    import matplotlib.pyplot as plt


plt: Any = None
font_manager: Any = None

from analytics.competition_statistics import (
    classification_metrics,
    compare_latency,
    latency_distribution,
    rag_metrics,
    required_sample_size_for_proportion,
    snapshot_digest,
    wilson_interval,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "analytics" / "results" / "paper_metrics_2026-07-29.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "competition-analytics"

BLUE = "#2B6F9F"
ORANGE = "#D98324"
GREEN = "#3B7D5B"
RED = "#B44B4B"
GRAY = "#6B7280"
LIGHT_BLUE = "#DCEAF3"
LIGHT_ORANGE = "#F5E1C9"
GRID = "#D9DEE5"
INK = "#20242A"


def configure_style() -> None:
    """配置适合中文答辩材料的 Matplotlib 样式。"""
    global plt, font_manager
    if plt is None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as pyplot
        from matplotlib import font_manager as matplotlib_font_manager

        plt = pyplot
        font_manager = matplotlib_font_manager
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    ]
    for path in candidates:
        if path.exists():
            font_manager.fontManager.addfont(str(path))
            family = font_manager.FontProperties(fname=str(path)).get_name()
            plt.rcParams["font.family"] = family
            break
    plt.rcParams.update(
        {
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#B8C1CC",
            "axes.labelcolor": INK,
            "axes.titlecolor": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "text.color": INK,
            "savefig.facecolor": "white",
            "font.size": 9.5,
        }
    )


def build_analysis(snapshot: dict[str, Any]) -> dict[str, Any]:
    """把原始快照转换为完整、机器可读的竞赛统计结果。"""
    metadata = snapshot["metadata"]
    rag_source = snapshot["rag"]
    routing_source = snapshot["routing"]
    latency_source = snapshot["latency"]

    rag = rag_metrics(
        rag_source["k"],
        rag_source["hits"],
        int(metadata["rag_sample_size"]),
    )
    routing = classification_metrics(
        routing_source["confusion_matrix"], routing_source["labels"]
    )
    fast = latency_distribution(latency_source["fast_seconds"])
    collab = latency_distribution(latency_source["collab_seconds"])
    comparison = compare_latency(
        latency_source["collab_seconds"], latency_source["fast_seconds"]
    )
    success_low, success_high = wilson_interval(
        int(latency_source["successes"]), int(latency_source["requests"])
    )

    optimization = dict(snapshot.get("top_k_optimization", {}))
    if optimization:
        optimization["empirically_dominated"] = (
            int(optimization["current_k"]) in rag["dominated_k"]
        )

    target_half_width = 0.05
    sample_planning = {
        "target_95_ci_half_width": target_half_width,
        "worst_case_required_n": required_sample_size_for_proportion(target_half_width),
        "rag_recall_90pct_required_n": required_sample_size_for_proportion(
            target_half_width, expected_proportion=0.90
        ),
        "routing_accuracy_96pct_required_n": required_sample_size_for_proportion(
            target_half_width, expected_proportion=0.96
        ),
        "note": "正态近似的规划值，用于扩充测试集，不代表当前结果无效。",
    }

    evidence_intervals: list[dict[str, Any]] = []
    for point in rag["points"]:
        if int(point["k"]) == 5:
            evidence_intervals.append(
                {
                    "metric": "RAG Recall@5",
                    "estimate": point["recall"],
                    "ci_95": point["ci_95"],
                    "sample_size": point["total"],
                }
            )
            break
    evidence_intervals.extend(
        [
            {
                "metric": "Agent 路由准确率",
                "estimate": routing["accuracy"],
                "ci_95": routing["accuracy_ci_95"],
                "sample_size": routing["sample_size"],
            },
            {
                "metric": "端到端请求成功率",
                "estimate": latency_source["successes"] / latency_source["requests"],
                "ci_95": [success_low, success_high],
                "sample_size": latency_source["requests"],
            },
        ]
    )

    return {
        "provenance": {
            "evaluated_at": metadata.get("evaluated_at"),
            "source_digest_sha256": snapshot_digest(snapshot),
            "confidence_level": metadata.get("confidence_level", 0.95),
            "bootstrap_resamples": 5000,
            "bootstrap_seed": 20260901,
        },
        "rag": rag,
        "routing": routing,
        "latency": {
            "fast": fast,
            "collab": collab,
            "collab_vs_fast": comparison,
            "success_rate": latency_source["successes"] / latency_source["requests"],
            "success_rate_ci_95": [success_low, success_high],
            "successes": latency_source["successes"],
            "requests": latency_source["requests"],
        },
        "top_k_optimization": optimization,
        "evidence_intervals": evidence_intervals,
        "sample_planning": sample_planning,
        "interpretation_limits": [
            "RAG 与路由测试集仍属于小样本，点估计必须与 95% 置信区间同时展示。",
            "延迟每种模式仅 4 次观测，显著性检验属于探索性证据，不能替代扩大样本后的复验。",
            "当前快照未保存逐查询排序列表，因此不能从聚合 Recall 反推 MRR 或 nDCG。",
            "Top-K=5 的结论是离线建议；只有实际部署并做前后对照后才能宣称线上收益。",
        ],
    }


def _clean_axis(axis: plt.Axes, *, grid_axis: str = "y") -> None:
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis=grid_axis, color=GRID, linewidth=0.7, alpha=0.9)
    axis.set_axisbelow(True)


def _save(figure: plt.Figure, output_dir: Path, stem: str) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    png = output_dir / f"{stem}.png"
    svg = output_dir / f"{stem}.svg"
    figure.savefig(png, dpi=300, bbox_inches="tight", pad_inches=0.08)
    figure.savefig(svg, bbox_inches="tight", pad_inches=0.08)
    plt.close(figure)
    return [png, svg]


def plot_rag_diagnostics(analysis: dict[str, Any], output_dir: Path) -> list[Path]:
    points = analysis["rag"]["points"]
    k_values = [int(point["k"]) for point in points]
    recalls = [float(point["recall"]) * 100 for point in points]
    lower = [
        (float(point["recall"]) - float(point["ci_95"][0])) * 100 for point in points
    ]
    upper = [
        (float(point["ci_95"][1]) - float(point["recall"])) * 100 for point in points
    ]
    marginal = [float(point["incremental_recall"]) * 100 for point in points]
    dominated = set(analysis["rag"]["dominated_k"])

    figure, (left, right) = plt.subplots(
        1, 2, figsize=(9.4, 4.0), gridspec_kw={"width_ratios": [1.35, 1], "wspace": 0.32}
    )
    left.errorbar(
        k_values,
        recalls,
        yerr=[lower, upper],
        marker="o",
        color=BLUE,
        capsize=4,
        linewidth=2,
        label="Recall@K（95% Wilson CI）",
    )
    for k, recall in zip(k_values, recalls):
        left.annotate(
            f"{recall:.0f}%" + ("  被支配" if k in dominated else ""),
            (k, recall),
            xytext=(0, 9 if k != 10 else -17),
            textcoords="offset points",
            ha="center",
            color=RED if k in dominated else INK,
        )
    left.plot(
        [k for k in k_values if k not in dominated],
        [recall for k, recall in zip(k_values, recalls) if k not in dominated],
        color=GREEN,
        linestyle="--",
        linewidth=1,
        label="帕累托前沿",
    )
    left.set_title("检索性能、统计不确定性与帕累托前沿")
    left.set_xlabel("候选片段数 K")
    left.set_ylabel("正确来源命中率（%）")
    left.set_xticks(k_values)
    left.set_ylim(35, 105)
    left.legend(frameon=False, loc="lower right")
    _clean_axis(left)

    colors = [BLUE if value > 0 else GRAY for value in marginal]
    bars = right.bar([str(k) for k in k_values], marginal, color=colors, width=0.62)
    for bar, point, gain in zip(bars, points, marginal):
        right.text(
            bar.get_x() + bar.get_width() / 2,
            gain + 1.2,
            f"+{int(point['incremental_hits'])} 条\n+{gain:.0f} pp",
            ha="center",
            va="bottom",
        )
    right.set_title("增加检索深度带来的边际收益")
    right.set_xlabel("Recall@K 的 K")
    right.set_ylabel("相对上一档的增益（百分点）")
    right.set_ylim(0, max(marginal) * 1.25)
    _clean_axis(right)
    return _save(figure, output_dir, "01_RAG不确定性与边际收益")


def plot_routing_diagnostics(
    snapshot: dict[str, Any], analysis: dict[str, Any], output_dir: Path
) -> list[Path]:
    labels = snapshot["routing"]["labels"]
    matrix = snapshot["routing"]["confusion_matrix"]
    normalized = [
        [value / sum(row) * 100 if sum(row) else 0 for value in row] for row in matrix
    ]
    per_class = analysis["routing"]["per_class"]

    figure, (left, right) = plt.subplots(
        1, 2, figsize=(10.4, 4.8), gridspec_kw={"width_ratios": [1.2, 0.9], "wspace": 0.42}
    )
    image = left.imshow(normalized, cmap="Blues", vmin=0, vmax=100, aspect="equal")
    left.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    left.set_yticks(range(len(labels)), labels)
    left.set_xlabel("预测意图")
    left.set_ylabel("真实意图")
    left.set_title("按真实类别归一化的混淆矩阵")
    for row_index, row in enumerate(matrix):
        for column_index, count in enumerate(row):
            if count:
                percent = normalized[row_index][column_index]
                left.text(
                    column_index,
                    row_index,
                    f"{percent:.0f}%\n(n={count})",
                    ha="center",
                    va="center",
                    fontsize=7.5,
                    color="white" if percent >= 60 else INK,
                )
    figure.colorbar(image, ax=left, fraction=0.046, pad=0.04, label="行内占比（%）")

    f1_values = [float(item["f1"]) * 100 for item in per_class]
    y = list(range(len(labels)))
    colors = [ORANGE if value < 90 else BLUE for value in f1_values]
    right.barh(y, f1_values, color=colors, height=0.62)
    right.set_yticks(y, labels)
    right.invert_yaxis()
    right.set_xlim(0, 105)
    right.set_xlabel("F1（%）")
    right.set_title(
        "逐类 F1 与一致性统计\n"
        f"Macro-F1={analysis['routing']['macro_f1']:.3f}，"
        f"Kappa={analysis['routing']['cohen_kappa']:.3f}，"
        f"MCC={analysis['routing']['multiclass_mcc']:.3f}"
    )
    for position, value in zip(y, f1_values):
        right.text(min(value + 1.2, 101), position, f"{value:.1f}%", va="center")
    _clean_axis(right, grid_axis="x")
    return _save(figure, output_dir, "02_Agent路由诊断")


def _ecdf(values: Sequence[float]) -> tuple[list[float], list[float]]:
    ordered = sorted(float(value) for value in values)
    return ordered, [(index + 1) / len(ordered) * 100 for index in range(len(ordered))]


def plot_latency_inference(
    snapshot: dict[str, Any], analysis: dict[str, Any], output_dir: Path
) -> list[Path]:
    fast_values = snapshot["latency"]["fast_seconds"]
    collab_values = snapshot["latency"]["collab_seconds"]
    fast = analysis["latency"]["fast"]
    collab = analysis["latency"]["collab"]
    comparison = analysis["latency"]["collab_vs_fast"]

    figure, (left, right) = plt.subplots(
        1, 2, figsize=(9.6, 4.0), gridspec_kw={"width_ratios": [1.2, 1], "wspace": 0.34}
    )
    for values, label, color in [
        (fast_values, "Fast", BLUE),
        (collab_values, "Collab", ORANGE),
    ]:
        x, y = _ecdf(values)
        left.step(x, y, where="post", linewidth=2, color=color, label=f"{label}（n={len(values)}）")
        left.scatter(x, y, s=26, color=color, zorder=3)
    left.set_title("端到端延迟经验累积分布（ECDF）")
    left.set_xlabel("响应时间（秒）")
    left.set_ylabel("累计请求占比（%）")
    left.set_ylim(0, 105)
    left.legend(frameon=False, loc="lower right")
    _clean_axis(left)

    groups = [fast, collab]
    positions = [0, 1]
    colors = [BLUE, ORANGE]
    for position, summary, color in zip(positions, groups, colors):
        low, high = summary["median_ci_95_bootstrap"]
        center = summary["median"]
        right.errorbar(
            center,
            position,
            xerr=[[center - low], [high - center]],
            fmt="o",
            color=color,
            capsize=5,
            linewidth=2,
            markersize=6,
        )
        right.text(high + 0.4, position, f"P50 {center:.2f}s｜P95 {summary['p95']:.2f}s", va="center")
    right.set_yticks(positions, ["Fast", "Collab"])
    right.invert_yaxis()
    right.set_xlabel("响应时间（秒）")
    right.set_title(
        "中位数的 Bootstrap 95% CI\n"
        f"Cliff's δ={comparison['cliffs_delta']:.2f}，"
        f"精确检验 p={comparison['mann_whitney_exact_two_sided_p']:.4f}"
    )
    right.set_xlim(0, max(collab_values) * 1.25)
    _clean_axis(right, grid_axis="x")
    return _save(figure, output_dir, "03_延迟分布与效应量")


def plot_evidence_intervals(analysis: dict[str, Any], output_dir: Path) -> list[Path]:
    items = analysis["evidence_intervals"]
    figure, axis = plt.subplots(figsize=(7.4, 3.4))
    positions = list(range(len(items)))
    for position, item, color in zip(positions, items, [BLUE, GREEN, ORANGE]):
        estimate = float(item["estimate"]) * 100
        low = float(item["ci_95"][0]) * 100
        high = float(item["ci_95"][1]) * 100
        axis.errorbar(
            estimate,
            position,
            xerr=[[estimate - low], [high - estimate]],
            fmt="o",
            color=color,
            capsize=5,
            markersize=7,
            linewidth=2,
        )
        axis.text(high + 1.2, position, f"{estimate:.1f}%  [{low:.1f}, {high:.1f}]  n={item['sample_size']}", va="center")
    axis.set_yticks(positions, [item["metric"] for item in items])
    axis.invert_yaxis()
    axis.set_xlim(35, 112)
    axis.set_xlabel("比例估计与 95% Wilson 置信区间（%）")
    axis.set_title("核心结论的统计不确定性（答辩时应与点估计同时展示）")
    _clean_axis(axis, grid_axis="x")
    return _save(figure, output_dir, "04_核心指标置信区间")


def generate_charts(
    snapshot: dict[str, Any], analysis: dict[str, Any], output_dir: Path
) -> list[Path]:
    configure_style()
    paths: list[Path] = []
    paths.extend(plot_rag_diagnostics(analysis, output_dir))
    paths.extend(plot_routing_diagnostics(snapshot, analysis, output_dir))
    paths.extend(plot_latency_inference(snapshot, analysis, output_dir))
    paths.extend(plot_evidence_intervals(analysis, output_dir))
    return paths


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_markdown(analysis: dict[str, Any], source_name: str) -> str:
    """生成适合项目文档和答辩材料引用的中文统计报告。"""
    rag_points = analysis["rag"]["points"]
    route = analysis["routing"]
    latency = analysis["latency"]
    comparison = latency["collab_vs_fast"]
    sample_plan = analysis["sample_planning"]
    recall_rows = "\n".join(
        "| {k} | {hits}/{total} | {recall} | [{low}, {high}] | +{incremental_hits} |".format(
            k=point["k"],
            hits=point["hits"],
            total=point["total"],
            recall=_percent(float(point["recall"])),
            low=_percent(float(point["ci_95"][0])),
            high=_percent(float(point["ci_95"][1])),
            incremental_hits=point["incremental_hits"],
        )
        for point in rag_points
    )
    class_rows = "\n".join(
        f"| {item['label']} | {item['support']} | {_percent(float(item['precision']))} | "
        f"{_percent(float(item['recall']))} | {_percent(float(item['f1']))} |"
        for item in route["per_class"]
    )
    limitations = "\n".join(f"- {item}" for item in analysis["interpretation_limits"])
    return f"""# 竞赛统计评测报告

> 数据源：`{source_name}`  
> 评测日期：{analysis['provenance']['evaluated_at']}  
> 数据指纹：`sha256:{analysis['provenance']['source_digest_sha256']}`

## 结论摘要

- RAG 在 K=5 时达到 90.0% 命中率，K 从 5 增至 10 没有新增命中，因此 K=10 被 K=5 帕累托支配。
- Agent 路由准确率为 {_percent(float(route['accuracy']))}，Macro-F1 为 {route['macro_f1']:.3f}；Cohen's κ={route['cohen_kappa']:.3f}、多分类 MCC={route['multiclass_mcc']:.3f}，说明高准确率不是类别分布偶然造成的。
- Collab 延迟中位数是 Fast 的 {comparison['median_ratio']:.2f} 倍，Cliff's δ={comparison['cliffs_delta']:.2f}；双侧 Mann–Whitney 精确置换检验 p={comparison['mann_whitney_exact_two_sided_p']:.4f}。由于每组仅 4 次，这一结果应表述为探索性证据。
- 8/8 请求成功的点估计为 100%，但 95% Wilson 区间仍为 [{_percent(float(latency['success_rate_ci_95'][0]))}, {_percent(float(latency['success_rate_ci_95'][1]))}]，不能简单宣称系统可靠性已经达到 100%。

## RAG 检索分析

| K | 命中数 | Recall@K | 95% Wilson CI | 新增命中 |
|---:|---:|---:|---:|---:|
{recall_rows}

- Recall-K 曲线归一化面积：{analysis['rag']['normalized_auc_recall_vs_k']:.3f}。
- 帕累托前沿 K：{', '.join(map(str, analysis['rag']['pareto_frontier_k']))}。
- 被支配 K：{', '.join(map(str, analysis['rag']['dominated_k'])) or '无'}。

## Agent 路由分析

| 意图 | 样本数 | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
{class_rows}

总体指标：Balanced Accuracy={route['balanced_accuracy']:.3f}，Weighted-F1={route['weighted_f1']:.3f}，κ={route['cohen_kappa']:.3f}，MCC={route['multiclass_mcc']:.3f}。

## 延迟与效应量

| 模式 | n | Mean | P50 | P90 | P95 | CV | P50 Bootstrap 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|
| Fast | {latency['fast']['count']} | {latency['fast']['mean']:.2f}s | {latency['fast']['median']:.2f}s | {latency['fast']['p90']:.2f}s | {latency['fast']['p95']:.2f}s | {latency['fast']['coefficient_of_variation']:.3f} | [{latency['fast']['median_ci_95_bootstrap'][0]:.2f}, {latency['fast']['median_ci_95_bootstrap'][1]:.2f}]s |
| Collab | {latency['collab']['count']} | {latency['collab']['mean']:.2f}s | {latency['collab']['median']:.2f}s | {latency['collab']['p90']:.2f}s | {latency['collab']['p95']:.2f}s | {latency['collab']['coefficient_of_variation']:.3f} | [{latency['collab']['median_ci_95_bootstrap'][0]:.2f}, {latency['collab']['median_ci_95_bootstrap'][1]:.2f}]s |

## 样本量规划

- 若希望比例指标的 95% 区间半宽约为 ±5 个百分点，最保守情形需要约 {sample_plan['worst_case_required_n']} 条样本。
- 若预期 RAG Recall 约为 90%，规划值约为 {sample_plan['rag_recall_90pct_required_n']} 条。
- 若预期路由准确率约为 96%，规划值约为 {sample_plan['routing_accuracy_96pct_required_n']} 条。

## 解释边界

{limitations}

## 图表索引

1. `01_RAG不确定性与边际收益.png`：Recall@K、Wilson 区间、边际收益和帕累托前沿。
2. `02_Agent路由诊断.png`：归一化混淆矩阵、逐类 F1、Kappa 与 MCC。
3. `03_延迟分布与效应量.png`：ECDF、Bootstrap 区间、Cliff's delta 与精确检验。
4. `04_核心指标置信区间.png`：核心比例指标的点估计、区间和样本量。
"""


def write_outputs(
    snapshot: dict[str, Any], source_path: Path, output_dir: Path, *, charts: bool = True
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis = build_analysis(snapshot)
    metrics_path = output_dir / "competition_metrics.json"
    report_path = output_dir / "competition_report.md"
    metrics_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report_path.write_text(render_markdown(analysis, source_path.name), encoding="utf-8")
    outputs = [metrics_path, report_path]
    if charts:
        outputs.extend(generate_charts(snapshot, analysis, output_dir))
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="生成竞赛统计评测报告与图表")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="冻结指标快照 JSON")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="输出目录")
    parser.add_argument("--no-charts", action="store_true", help="仅生成 JSON 和 Markdown")
    args = parser.parse_args()
    snapshot = json.loads(args.input.read_text(encoding="utf-8"))
    outputs = write_outputs(
        snapshot, args.input, args.output_dir, charts=not args.no_charts
    )
    print(f"已生成 {len(outputs)} 个竞赛统计产物：")
    for path in outputs:
        print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
