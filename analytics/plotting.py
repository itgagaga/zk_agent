"""统一的中文论文图表样式。"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager


FONT_PATH = Path(r"C:\Windows\Fonts\simhei.ttf")
COLORS = ["#2F6B9A", "#4F8FBF", "#63A6B8", "#7A79B8", "#B68658", "#6B8E76"]


def format_chart_value(value: int | float, value_format: str = "{:g}") -> str:
    return value_format.format(value)


def _configure_style() -> None:
    if FONT_PATH.exists():
        font_manager.fontManager.addfont(str(FONT_PATH))
        family = font_manager.FontProperties(fname=str(FONT_PATH)).get_name()
        plt.rcParams["font.family"] = family
    plt.rcParams.update(
        {
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#CCD4DC",
            "axes.labelcolor": "#334155",
            "xtick.color": "#52606D",
            "ytick.color": "#334155",
            "text.color": "#1F2937",
            "axes.titleweight": "normal",
        }
    )


def save_horizontal_bar_chart(
    values: Mapping[str, int | float],
    *,
    title: str,
    xlabel: str,
    output: Path,
    value_format: str = "{:g}",
) -> None:
    """保存适合论文排版的横向柱状图。"""
    _configure_style()
    ordered = sorted(values.items(), key=lambda item: item[1])
    labels = [item[0] for item in ordered]
    numbers = [item[1] for item in ordered]
    height = max(4.8, 0.42 * len(labels) + 1.8)
    figure, axis = plt.subplots(figsize=(10.5, height))
    bars = axis.barh(labels, numbers, color=COLORS[0], height=0.62)
    axis.set_title(title, pad=16, fontsize=16)
    axis.set_xlabel(xlabel)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.grid(axis="x", color="#E7ECF0", linewidth=0.8)
    axis.set_axisbelow(True)
    max_value = max(numbers, default=1)
    axis.set_xlim(0, max_value * 1.16 if max_value else 1)
    for bar, value in zip(bars, numbers):
        axis.text(
            bar.get_width() + max_value * 0.015,
            bar.get_y() + bar.get_height() / 2,
            format_chart_value(value, value_format),
            va="center",
            fontsize=10,
        )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(figure)
