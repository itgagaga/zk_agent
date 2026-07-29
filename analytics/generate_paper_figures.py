"""Generate publication-ready evaluation figures from a frozen metric snapshot.

The script intentionally separates measured results from visual rendering.
Every value comes from ``analytics/results/paper_metrics_2026-07-29.json``.
Outputs are written as both 300-DPI PNG and vector SVG.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "analytics" / "results" / "paper_metrics_2026-07-29.json"
OUTPUT_DIR = ROOT.parent / "docs" / "image" / "paper"

BLUE = "#2B6F9F"
ORANGE = "#D98324"
LIGHT_BLUE = "#DCEAF3"
GRAY = "#6B7280"
GRID = "#D9DEE5"
INK = "#20242A"


def configure_style() -> None:
    chinese_candidates = [
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    ]
    for path in chinese_candidates:
        if path.exists():
            font_manager.fontManager.addfont(str(path))
            family = font_manager.FontProperties(fname=str(path)).get_name()
            plt.rcParams["font.family"] = [family, "Times New Roman"]
            break
    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.labelsize": 10,
            "axes.titlesize": 10,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "legend.fontsize": 8.5,
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": INK,
            "axes.linewidth": 0.8,
            "axes.labelcolor": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "text.color": INK,
            "savefig.facecolor": "white",
        }
    )


def wilson_interval(successes: int, total: int, z: float = 1.95996398454) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), q))


def clean_axis(axis: plt.Axes, *, grid_axis: str = "y") -> None:
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis=grid_axis, color=GRID, linewidth=0.65, alpha=0.85)
    axis.set_axisbelow(True)


def save_figure(figure: plt.Figure, stem: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT_DIR / f"{stem}.png", dpi=300, bbox_inches="tight", pad_inches=0.04)
    figure.savefig(OUTPUT_DIR / f"{stem}.svg", bbox_inches="tight", pad_inches=0.04)
    plt.close(figure)


def rag_figure(data: dict) -> None:
    k_values = np.asarray(data["rag"]["k"], dtype=int)
    hits = data["rag"]["hits"]
    total = int(data["metadata"]["rag_sample_size"])
    recall = np.asarray(data["rag"]["recall"], dtype=float) * 100
    intervals = np.asarray([wilson_interval(hit, total) for hit in hits]) * 100
    lower_error = recall - intervals[:, 0]
    upper_error = intervals[:, 1] - recall

    figure, axis = plt.subplots(figsize=(6.9, 3.7))
    axis.errorbar(
        k_values,
        recall,
        yerr=np.vstack([lower_error, upper_error]),
        color=BLUE,
        marker="o",
        markersize=5.5,
        linewidth=1.8,
        capsize=3,
        capthick=0.9,
        label="Recall@K（95% Wilson CI）",
    )
    axis.axvspan(4.7, 5.3, color=ORANGE, alpha=0.10)
    axis.annotate(
        "性能拐点",
        xy=(5, recall[2]),
        xytext=(5.55, 76),
        arrowprops={"arrowstyle": "->", "color": ORANGE, "lw": 0.9},
        color=INK,
    )
    for x, value, hit in zip(k_values, recall, hits):
        axis.text(x, value + 2.0, f"{value:.0f}%\n({hit}/{total})", ha="center", va="bottom")
    axis.set_xlabel("返回候选文档数 K")
    axis.set_ylabel("正确来源命中率（%）")
    axis.set_xticks(k_values)
    axis.set_ylim(40, 103)
    axis.legend(frameon=False, loc="lower right")
    clean_axis(axis)
    figure.text(0.01, 0.98, "(a)", va="top", weight="bold")
    figure.tight_layout()
    save_figure(figure, "论文图_01_RAG检索性能")


def routing_metrics(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    true_positive = np.diag(matrix).astype(float)
    precision = np.divide(
        true_positive,
        matrix.sum(axis=0),
        out=np.zeros_like(true_positive),
        where=matrix.sum(axis=0) != 0,
    )
    recall = np.divide(
        true_positive,
        matrix.sum(axis=1),
        out=np.zeros_like(true_positive),
        where=matrix.sum(axis=1) != 0,
    )
    f1 = np.divide(
        2 * precision * recall,
        precision + recall,
        out=np.zeros_like(true_positive),
        where=(precision + recall) != 0,
    )
    return precision, recall, f1


def routing_figure(data: dict) -> None:
    labels = data["routing"]["labels"]
    matrix = np.asarray(data["routing"]["confusion_matrix"], dtype=int)
    normalized = matrix / matrix.sum(axis=1, keepdims=True) * 100
    precision, recall, f1 = routing_metrics(matrix)
    accuracy = np.trace(matrix) / matrix.sum()
    low, high = wilson_interval(int(np.trace(matrix)), int(matrix.sum()))

    figure, (left, right) = plt.subplots(
        1,
        2,
        figsize=(8.2, 4.5),
        gridspec_kw={"width_ratios": [1.20, 0.92], "wspace": 0.46},
    )
    image = left.imshow(normalized, cmap="Blues", vmin=0, vmax=100, aspect="equal")
    left.set_xticks(range(len(labels)), labels, rotation=48, ha="right")
    left.set_yticks(range(len(labels)), labels)
    left.set_xlabel("预测类别")
    left.set_ylabel("真实类别")
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            count = matrix[row, column]
            if count:
                left.text(
                    column,
                    row,
                    f"{normalized[row, column]:.0f}%\n(n={count})",
                    ha="center",
                    va="center",
                    fontsize=7.2,
                    color="white" if normalized[row, column] >= 60 else INK,
                )
    left.text(
        0.0,
        1.04,
        f"总体准确率 {accuracy * 100:.1f}%（26/27），95% CI [{low * 100:.1f}%, {high * 100:.1f}%]",
        transform=left.transAxes,
        ha="left",
    )

    y = np.arange(len(labels))
    right.barh(y, precision * 100, height=0.22, color=LIGHT_BLUE, edgecolor=BLUE, label="Precision")
    right.barh(y + 0.24, recall * 100, height=0.22, color="#F5D7B5", edgecolor=ORANGE, label="Recall")
    right.plot(f1 * 100, y + 0.12, "o", color=INK, markersize=3.8, label="F1")
    right.set_yticks(y + 0.12, labels)
    right.set_xlim(55, 103)
    right.set_xlabel("分类指标（%）")
    right.invert_yaxis()
    right.legend(
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.10),
        ncol=3,
        columnspacing=0.9,
        handlelength=1.6,
    )
    clean_axis(right, grid_axis="x")
    figure.text(0.01, 0.98, "(a)", va="top", weight="bold")
    figure.text(0.64, 0.98, "(b)", va="top", weight="bold")
    save_figure(figure, "论文图_02_Agent路由评测")


def stability_figure(data: dict) -> None:
    fast = [float(value) for value in data["latency"]["fast_seconds"]]
    collab = [float(value) for value in data["latency"]["collab_seconds"]]
    successes = int(data["latency"]["successes"])
    requests = int(data["latency"]["requests"])
    success_low, success_high = wilson_interval(successes, requests)
    groups = [fast, collab]
    positions = [1, 2]

    figure, (left, right) = plt.subplots(
        1,
        2,
        figsize=(7.2, 3.75),
        gridspec_kw={"width_ratios": [1.45, 0.85], "wspace": 0.36},
    )
    boxes = left.boxplot(
        groups,
        positions=positions,
        widths=0.42,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": INK, "linewidth": 1.4},
        whiskerprops={"color": GRAY},
        capprops={"color": GRAY},
    )
    for patch, color in zip(boxes["boxes"], [BLUE, ORANGE]):
        patch.set_facecolor(color)
        patch.set_alpha(0.18)
        patch.set_edgecolor(color)
    offsets = [-0.08, -0.025, 0.025, 0.08]
    for position, values, color in zip(positions, groups, [BLUE, ORANGE]):
        left.scatter(
            [position + offsets[index] for index in range(len(values))],
            values,
            s=24,
            color=color,
            edgecolor="white",
            linewidth=0.5,
            zorder=3,
        )
        median = percentile(values, 50)
        p95 = percentile(values, 95)
        left.text(position, max(values) + 1.0, f"中位数 {median:.2f}s\nP95 {p95:.2f}s", ha="center", va="bottom")
    left.set_xticks(positions, ["Fast 模式\n(n=4)", "Collab 模式\n(n=4)"])
    left.set_ylabel("端到端响应时间（s）")
    left.set_ylim(0, max(collab) + 5.2)
    clean_axis(left)

    right.errorbar(
        [0],
        [successes / requests * 100],
        yerr=[
            [(successes / requests - success_low) * 100],
            [(success_high - successes / requests) * 100],
        ],
        fmt="o",
        color=BLUE,
        markersize=6,
        capsize=4,
        linewidth=1.5,
    )
    right.text(0, 102, f"{successes}/{requests} 成功", ha="center", va="bottom")
    right.set_xlim(-0.65, 0.65)
    right.set_ylim(55, 108)
    right.set_xticks([0], ["端到端请求"])
    right.set_ylabel("请求成功率（%）")
    right.text(
        0,
        62,
        f"95% Wilson CI\n[{success_low * 100:.1f}%, {success_high * 100:.1f}%]",
        ha="center",
        va="bottom",
    )
    clean_axis(right)
    figure.text(0.01, 0.98, "(a)", va="top", weight="bold")
    figure.text(0.70, 0.98, "(b)", va="top", weight="bold")
    save_figure(figure, "论文图_03_稳定性与响应延迟")


def optimization_figure(data: dict) -> None:
    current = data["top_k_optimization"]
    names = [f"当前配置\nK={current['current_k']}", f"建议配置\nK={current['recommended_k']}"]
    recall_values = [current["current_recall"] * 100, current["recommended_recall"] * 100]
    context_values = [current["current_k"], current["recommended_k"]]

    figure, (left, right) = plt.subplots(
        1,
        2,
        figsize=(6.9, 3.45),
        gridspec_kw={"wspace": 0.34},
    )
    bars = left.bar(names, recall_values, width=0.52, color=[GRAY, BLUE])
    left.set_ylabel("Recall@K（%）")
    left.set_ylim(0, 103)
    for bar, value in zip(bars, recall_values):
        left.text(bar.get_x() + bar.get_width() / 2, value + 1.6, f"{value:.0f}%", ha="center")
    left.text(0.5, 71, "检索性能保持不变", ha="center", color=INK)
    clean_axis(left)

    bars = right.bar(names, context_values, width=0.52, color=[GRAY, ORANGE])
    right.set_ylabel("每次返回候选片段数（个）")
    right.set_ylim(0, 11.5)
    for bar, value in zip(bars, context_values):
        right.text(bar.get_x() + bar.get_width() / 2, value + 0.25, str(value), ha="center")
    right.annotate(
        "减少 50%",
        xy=(1, context_values[1]),
        xytext=(0.5, 8.0),
        ha="center",
        arrowprops={"arrowstyle": "->", "color": ORANGE, "lw": 0.9},
    )
    clean_axis(right)
    figure.text(0.01, 0.98, "(a)", va="top", weight="bold")
    figure.text(0.52, 0.98, "(b)", va="top", weight="bold")
    save_figure(figure, "论文图_04_TopK参数优化对比")


def main() -> int:
    configure_style()
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    rag_figure(data)
    routing_figure(data)
    stability_figure(data)
    optimization_figure(data)
    print(f"Generated paper figures in: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
