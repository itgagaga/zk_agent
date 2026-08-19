"""基于当前项目真实数据生成论文用统计图。"""

from __future__ import annotations

from collections import Counter
from statistics import fmean
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy import inspect, text

from analytics.core import (
    build_confusion_matrix,
    calculate_recall_at_k,
    chunk_length_summary,
)
from analytics.data_access import load_chroma_records
from analytics.evaluation import (
    RAG_CASES,
    ROUTE_CASES,
    ROUTE_LABELS,
    normalize_title,
    title_matches,
)


def latency_annotation_y(values: list[float]) -> float:
    """把均值注释放在上四分位附近，避开极端值和图标题。"""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("values must not be empty")
    if len(ordered) == 1 or ordered[0] == ordered[-1]:
        return ordered[-1] + max(abs(ordered[-1]) * 0.05, 0.5)

    index = 0.75 * (len(ordered) - 1)
    lower = int(index)
    fraction = index - lower
    upper_quartile = ordered[lower] + (
        ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]
    ) * fraction
    span = ordered[-1] - ordered[0]
    return min(upper_quartile + span * 0.06, ordered[-1] - span * 0.08)


def _mysql_counts() -> dict[str, int]:
    """只读统计当前 MySQL 各表记录数。"""
    from backend.database.session import engine

    counts: dict[str, int] = {}
    with engine.connect() as connection:
        for table in inspect(connection).get_table_names():
            counts[table] = int(
                connection.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar_one()
            )
    return counts


def build_offline_metrics(project_root: Path) -> dict[str, Any]:
    """汇总 Chroma、清洗文档和 MySQL 的离线数据指标。"""
    root = Path(project_root).resolve()
    records = load_chroma_records(
        root / "data" / "vector_store" / "chroma.sqlite3"
    )
    collection_counts = Counter(record["collection"] for record in records)
    campus_records = [
        record for record in records if record["collection"] == "zhku_campus"
    ]
    department_counts = Counter(
        record["department"] for record in campus_records
    )
    lengths = [len(record["document"]) for record in records]

    fields = {
        "标题": "title",
        "部门": "department",
        "来源链接": "source_url",
        "发布日期": "publish_date",
        "正文内容": "document",
    }
    completeness = {
        label: sum(bool(record.get(field)) for record in records) / len(records)
        if records
        else 0.0
        for label, field in fields.items()
    }

    cleaned_files = list((root / "data" / "cleaned").rglob("*.md"))
    cleaned_files += list((root / "data" / "cleaned").rglob("*.txt"))
    metadata_files = list((root / "data" / "metadata").rglob("*.json"))

    return {
        "records": records,
        "total_chunks": len(records),
        "collection_counts": dict(collection_counts),
        "department_counts": dict(department_counts),
        "chunk_lengths": lengths,
        "chunk_summary": chunk_length_summary(
            [record["document"] for record in records]
        ),
        "metadata_completeness": completeness,
        "cleaned_file_count": len(cleaned_files),
        "metadata_file_count": len(metadata_files),
        "cleaned_total_bytes": sum(path.stat().st_size for path in cleaned_files),
        "mysql_counts": _mysql_counts(),
    }


def evaluate_routes() -> dict[str, Any]:
    """使用项目当前规则路由器评测意图分类。"""
    from backend.agents.router import QuestionRouter

    router = QuestionRouter()
    expected = [case.expected_label for case in ROUTE_CASES]
    predicted = [router.route_rule(case.query).primary.intent_label for case in ROUTE_CASES]
    matrix = build_confusion_matrix(expected, predicted, ROUTE_LABELS)
    correct = sum(truth == guess for truth, guess in zip(expected, predicted))
    return {
        "total": len(ROUTE_CASES),
        "expected": expected,
        "predicted": predicted,
        "labels": ROUTE_LABELS,
        "matrix": matrix,
        "accuracy": correct / len(ROUTE_CASES),
    }


def evaluate_rag(api_base: str) -> dict[str, Any]:
    """调用运行中的 RAG 检索接口计算真实 Recall@K。"""
    import requests

    ranked_titles: list[list[str]] = []
    ranked_keys: list[list[str]] = []
    expected_titles: list[set[str]] = []
    top1_scores_correct: list[float] = []
    top1_scores_incorrect: list[float] = []
    category_totals: Counter[str] = Counter()
    category_hits: Counter[str] = Counter()
    gate_statuses: Counter[str] = Counter()
    gate_coverages: list[float] = []
    case_results: list[dict[str, Any]] = []

    for case in RAG_CASES:
        response = requests.get(
            f"{api_base.rstrip('/')}/api/search/rag",
            params={"q": case.query, "top_k": 10},
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
        hits = payload.get("hits", [])
        summary = payload.get("retrieval_summary") or {}
        assessment = summary.get("evidence_assessment") or {}
        if assessment.get("status"):
            gate_statuses[assessment["status"]] += 1
        if assessment.get("coverage") is not None:
            gate_coverages.append(float(assessment["coverage"]))
        titles = [str(hit.get("title") or "") for hit in hits]
        ids = [str(hit.get("chunk_id") or (hit.get("metadata") or {}).get("doc_id") or "") for hit in hits]
        scores = [float(hit.get("score") or 0.0) for hit in hits]
        ranked_titles.append(titles)
        expected_keys = case.expected_doc_ids or {
            normalize_title(title) for title in case.expected_titles
        }
        ranked_keys.append(ids if case.expected_doc_ids else [normalize_title(title) for title in titles])
        expected_titles.append(expected_keys)

        top1_correct = bool(
            (ids and ids[0] in expected_keys)
            or (titles and title_matches(titles[0], case.expected_titles))
        )
        top1_score = scores[0] if scores else 0.0
        if top1_correct:
            top1_scores_correct.append(top1_score)
        else:
            top1_scores_incorrect.append(top1_score)

        category_totals[case.category] += 1
        top3_correct = bool(
            set(ids[:3]) & expected_keys
            or any(title_matches(title, case.expected_titles) for title in titles[:3])
        )
        if top3_correct:
            category_hits[case.category] += 1

        case_results.append(
            {
                "query": case.query,
                "category": case.category,
                "expected_titles": sorted(case.expected_titles),
                "expected_doc_ids": sorted(case.expected_doc_ids),
                "titles": titles,
                "ids": ids,
                "scores": scores,
                "top1_correct": top1_correct,
                "top3_correct": top3_correct,
                "gate_status": assessment.get("status"),
                "gate_coverage": assessment.get("coverage"),
            }
        )

    recall_at_k = calculate_recall_at_k(
        ranked_keys,
        expected_titles,
        [1, 3, 5, 10],
    )
    category_accuracy = {
        category: category_hits[category] / total
        for category, total in category_totals.items()
    }
    return {
        "total": len(RAG_CASES),
        "recall_at_k": recall_at_k,
        "category_accuracy": category_accuracy,
        "gate_status_counts": dict(gate_statuses),
        "mean_gate_coverage": fmean(gate_coverages) if gate_coverages else 0.0,
        "top1_scores_correct": top1_scores_correct,
        "top1_scores_incorrect": top1_scores_incorrect,
        "cases": case_results,
    }


def project_vectors(project_root: Path) -> dict[str, list[Any]]:
    """读取 Chroma 实际 Embedding，并用 PCA 投影到二维。"""
    import chromadb
    import numpy as np
    from sklearn.decomposition import PCA

    store_path = Path(project_root).resolve() / "data" / "vector_store"
    client = chromadb.PersistentClient(path=str(store_path))
    collection_map = {
        "zhku_campus": "校园知识库",
        "zhku_user_docs": "用户私有文档库",
    }
    vectors: list[list[float]] = []
    labels: list[str] = []
    departments: list[str] = []
    for collection_name, display_name in collection_map.items():
        collection = client.get_collection(collection_name)
        result = collection.get(include=["embeddings", "metadatas"])
        embeddings = result.get("embeddings")
        metadatas = result.get("metadatas") or []
        if embeddings is None:
            continue
        for vector, metadata in zip(embeddings, metadatas):
            vectors.append([float(value) for value in vector])
            labels.append(display_name)
            departments.append(str((metadata or {}).get("department") or "未标注"))

    if len(vectors) < 2:
        raise RuntimeError("向量数量不足，无法进行 PCA 投影")
    coordinates = PCA(n_components=2).fit_transform(np.asarray(vectors))
    return {
        "x": coordinates[:, 0].tolist(),
        "y": coordinates[:, 1].tolist(),
        "collection": labels,
        "department": departments,
    }


def evaluate_latency(
    api_base: str,
    *,
    username: str,
    password: str,
    limit_per_mode: int = 4,
) -> dict[str, Any]:
    """登录运行中系统，执行少量 Fast/Collab 真实问答并统计总耗时。"""
    import requests

    base = api_base.rstrip("/")
    login = requests.post(
        f"{base}/api/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    login.raise_for_status()
    token = login.json().get("access_token")
    if not token:
        raise RuntimeError("登录响应未返回 access_token")
    headers = {"Authorization": f"Bearer {token}"}

    query_groups = {
        "fast": [
            "仲恺农业工程学院有几个校区？",
            "白云校区网络报障电话是多少？",
            "广州今天天气怎么样？",
            "学校有哪些本科专业？",
        ],
        "collab": [
            "补办学生证需要什么材料，在哪里办理，联系电话是多少？",
            "信息与计算科学应该如何规划课程和就业发展？",
            "校园网怎么办理，需要哪些材料和联系谁？",
            "去白云校区怎么走，今天会下雨吗，同时需要准备什么？",
        ],
    }

    results: list[dict[str, Any]] = []
    for expected_mode, queries in query_groups.items():
        for query in queries[: max(0, limit_per_mode)]:
            started = perf_counter()
            try:
                response = requests.post(
                    f"{base}/api/chat",
                    json={"question": query, "user_role": "student", "history": []},
                    headers=headers,
                    timeout=240,
                )
                elapsed = perf_counter() - started
                response.raise_for_status()
                payload = response.json()
                results.append(
                    {
                        "question": query,
                        "expected_mode": expected_mode,
                        "actual_mode": payload.get("route_mode") or "unknown",
                        "latency_seconds": elapsed,
                        "success": True,
                    }
                )
            except requests.RequestException as error:
                results.append(
                    {
                        "question": query,
                        "expected_mode": expected_mode,
                        "actual_mode": "error",
                        "latency_seconds": perf_counter() - started,
                        "success": False,
                        "error": type(error).__name__,
                    }
                )

    successful = [item for item in results if item["success"]]
    by_mode: dict[str, list[float]] = {}
    for mode in query_groups:
        by_mode[mode] = [
            item["latency_seconds"]
            for item in successful
            if item["expected_mode"] == mode
        ]
    return {
        "total": len(results),
        "success_count": len(successful),
        "results": results,
        "by_mode": by_mode,
    }


def generate_figures(
    *,
    offline: dict[str, Any],
    rag: dict[str, Any],
    routes: dict[str, Any],
    vectors: dict[str, list[Any]],
    latency: dict[str, Any] | None,
    output_dir: Path,
) -> list[Path]:
    """生成全部中文论文图，并返回文件路径。"""
    import matplotlib.pyplot as plt
    import numpy as np

    from analytics.plotting import COLORS, _configure_style, save_horizontal_bar_chart

    _configure_style()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    def save(figure: Any, filename: str) -> None:
        path = output / filename
        figure.tight_layout()
        figure.savefig(path, dpi=300, bbox_inches="tight")
        plt.close(figure)
        paths.append(path)

    collection_labels = {
        "zhku_campus": "校园知识库",
        "zhku_documents": "共享文档库",
        "zhku_user_docs": "用户私有文档库",
    }
    collection_counts = {
        collection_labels.get(key, key): value
        for key, value in offline["collection_counts"].items()
    }
    path = output / "数据分析_01_知识库集合规模.png"
    save_horizontal_bar_chart(
        collection_counts,
        title="Chroma 向量知识库片段规模",
        xlabel="片段数量（个）",
        output=path,
    )
    paths.append(path)

    path = output / "数据分析_02_校园知识片段部门分布.png"
    save_horizontal_bar_chart(
        offline["department_counts"],
        title="校园知识库各来源部门片段分布",
        xlabel="片段数量（个）",
        output=path,
    )
    paths.append(path)

    lengths = offline["chunk_lengths"]
    figure, axis = plt.subplots(figsize=(10.5, 6))
    axis.hist(lengths, bins=16, color=COLORS[0], edgecolor="white", linewidth=0.8)
    median_value = offline["chunk_summary"]["median"]
    axis.axvline(
        median_value,
        color=COLORS[4],
        linewidth=2,
        linestyle="--",
        label=f"中位数：{median_value:.0f} 字符",
    )
    axis.set_title("知识库文本片段长度分布", pad=16, fontsize=16)
    axis.set_xlabel("片段字符数")
    axis.set_ylabel("片段数量（个）")
    axis.grid(axis="y", color="#E7ECF0", linewidth=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False)
    save(figure, "数据分析_03_文本片段长度分布.png")

    records = offline["records"]
    top_departments = [
        name
        for name, _ in sorted(
            offline["department_counts"].items(),
            key=lambda item: item[1],
            reverse=True,
        )[:10]
    ]
    department_lengths = [
        [
            len(record["document"])
            for record in records
            if record["collection"] == "zhku_campus"
            and record["department"] == department
        ]
        for department in top_departments
    ]
    figure, axis = plt.subplots(figsize=(11.5, 6.5))
    box = axis.boxplot(
        department_lengths,
        tick_labels=top_departments,
        patch_artist=True,
        showfliers=True,
        medianprops={"color": COLORS[4], "linewidth": 1.8},
    )
    for patch in box["boxes"]:
        patch.set_facecolor("#D9E8F2")
        patch.set_edgecolor(COLORS[0])
    axis.set_title("主要来源部门的文本片段长度差异", pad=16, fontsize=16)
    axis.set_ylabel("片段字符数")
    axis.tick_params(axis="x", rotation=28)
    axis.grid(axis="y", color="#E7ECF0", linewidth=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    save(figure, "数据分析_04_部门片段长度箱线图.png")

    completeness = offline["metadata_completeness"]
    figure, axis = plt.subplots(figsize=(10.5, 5.8))
    labels = list(completeness)
    values = [completeness[label] * 100 for label in labels]
    bars = axis.bar(labels, values, color=COLORS[: len(labels)], width=0.62)
    axis.set_title("知识片段 Metadata 完整度", pad=16, fontsize=16)
    axis.set_ylabel("完整率（%）")
    axis.set_ylim(0, 112)
    axis.grid(axis="y", color="#E7ECF0", linewidth=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    for bar, value in zip(bars, values):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            value + 2,
            f"{value:.1f}%",
            ha="center",
        )
    save(figure, "数据分析_05_Metadata完整度.png")

    table_labels = {
        "organization": "机构",
        "user": "用户",
        "chat_session": "聊天会话",
        "chat_message": "聊天消息",
        "resume_profile": "简历档案",
        "user_document": "用户文档",
        "user_schedule": "用户课表",
        "school_profile": "学校概况",
        "campus_advice_cache": "AI建议缓存",
        "campus_weather_cache": "天气缓存",
    }
    mysql_values = {
        table_labels.get(name, name): count
        for name, count in offline["mysql_counts"].items()
        if count > 0
    }
    path = output / "数据分析_06_MySQL业务数据规模.png"
    save_horizontal_bar_chart(
        mysql_values,
        title="MySQL 主要业务表数据规模",
        xlabel="记录数量（条）",
        output=path,
    )
    paths.append(path)

    figure, axis = plt.subplots(figsize=(10.5, 6.5))
    collections = list(dict.fromkeys(vectors["collection"]))
    for index, collection in enumerate(collections):
        mask = [
            position
            for position, value in enumerate(vectors["collection"])
            if value == collection
        ]
        axis.scatter(
            [vectors["x"][position] for position in mask],
            [vectors["y"][position] for position in mask],
            s=46,
            alpha=0.78,
            color=COLORS[index],
            edgecolor="white",
            linewidth=0.5,
            label=collection,
        )
    axis.set_title("Chroma 文档向量 PCA 二维分布", pad=16, fontsize=16)
    axis.set_xlabel("主成分 1")
    axis.set_ylabel("主成分 2")
    axis.grid(color="#E7ECF0", linewidth=0.7)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False)
    save(figure, "数据分析_07_文档向量PCA分布.png")

    recall = rag["recall_at_k"]
    k_values = sorted(recall)
    recall_values = [recall[k] * 100 for k in k_values]
    figure, axis = plt.subplots(figsize=(10.5, 5.8))
    axis.plot(
        k_values,
        recall_values,
        color=COLORS[0],
        marker="o",
        linewidth=2.2,
        markersize=7,
    )
    axis.fill_between(k_values, recall_values, alpha=0.12, color=COLORS[0])
    for k, value in zip(k_values, recall_values):
        axis.text(k, value + 2.2, f"{value:.1f}%", ha="center")
    axis.set_title("RAG 不同 Top-K 的正确来源命中率", pad=16, fontsize=16)
    axis.set_xlabel("K 值")
    axis.set_ylabel("Recall@K（%）")
    axis.set_xticks(k_values)
    axis.set_ylim(0, 110)
    axis.grid(color="#E7ECF0", linewidth=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    save(figure, "数据分析_08_RAG_TopK命中率.png")

    path = output / "数据分析_09_RAG类别命中率.png"
    save_horizontal_bar_chart(
        {
            category: value * 100
            for category, value in rag["category_accuracy"].items()
        },
        title="不同问题类别的 RAG Top-3 命中率",
        xlabel="Top-3 命中率（%）",
        output=path,
        value_format="{:.1f}%",
    )
    paths.append(path)

    correct_scores = rag["top1_scores_correct"]
    incorrect_scores = rag["top1_scores_incorrect"]
    figure, axis = plt.subplots(figsize=(9.5, 5.8))
    score_groups = []
    score_labels = []
    if correct_scores:
        score_groups.append(correct_scores)
        score_labels.append("Top-1 正确")
    if incorrect_scores:
        score_groups.append(incorrect_scores)
        score_labels.append("Top-1 未命中")
    parts = axis.violinplot(
        score_groups,
        showmeans=True,
        showmedians=True,
        widths=0.72,
    )
    for body in parts["bodies"]:
        body.set_facecolor(COLORS[0])
        body.set_edgecolor(COLORS[0])
        body.set_alpha(0.4)
    axis.set_xticks(range(1, len(score_labels) + 1), score_labels)
    axis.set_title("RAG Top-1 结果的相似度分数分布", pad=16, fontsize=16)
    axis.set_ylabel("相似度分数")
    axis.grid(axis="y", color="#E7ECF0", linewidth=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    save(figure, "数据分析_10_RAG相似度分布.png")

    matrix = np.asarray(routes["matrix"])
    figure, axis = plt.subplots(figsize=(10.5, 8.2))
    image = axis.imshow(matrix, cmap="Blues")
    axis.set_xticks(range(len(routes["labels"])), routes["labels"], rotation=35, ha="right")
    axis.set_yticks(range(len(routes["labels"])), routes["labels"])
    axis.set_xlabel("系统预测意图")
    axis.set_ylabel("标准意图")
    axis.set_title(
        f"Agent Router 意图识别混淆矩阵（准确率 {routes['accuracy'] * 100:.1f}%）",
        pad=16,
        fontsize=16,
    )
    threshold = matrix.max() / 2 if matrix.size else 0
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            axis.text(
                column,
                row,
                str(matrix[row, column]),
                ha="center",
                va="center",
                color="white" if matrix[row, column] > threshold else "#1F2937",
            )
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04, label="问题数量")
    save(figure, "数据分析_11_Agent路由混淆矩阵.png")

    if latency:
        fast_values = latency["by_mode"].get("fast", [])
        collab_values = latency["by_mode"].get("collab", [])
        if fast_values and collab_values:
            figure, axis = plt.subplots(figsize=(9.5, 5.8))
            boxes = axis.boxplot(
                [fast_values, collab_values],
                tick_labels=["Fast 快速模式", "Collab 协作模式"],
                patch_artist=True,
                showmeans=True,
            )
            for patch, color in zip(boxes["boxes"], [COLORS[0], COLORS[1]]):
                patch.set_facecolor(color)
                patch.set_alpha(0.35)
                patch.set_edgecolor(color)
            for position, values in enumerate([fast_values, collab_values], start=1):
                axis.scatter(
                    [position] * len(values),
                    values,
                    color=COLORS[position - 1],
                    s=34,
                    zorder=3,
                )
                axis.text(
                    position,
                    latency_annotation_y(values),
                    f"平均 {fmean(values):.2f} 秒",
                    ha="center",
                )
            axis.set_ylim(top=max(max(fast_values), max(collab_values)) * 1.12)
            axis.set_title("Fast 与 Collab 模式端到端响应时间", pad=16, fontsize=16)
            axis.set_ylabel("响应时间（秒）")
            axis.grid(axis="y", color="#E7ECF0", linewidth=0.8)
            axis.set_axisbelow(True)
            axis.spines[["top", "right"]].set_visible(False)
            save(figure, "数据分析_12_Fast与Collab响应时间.png")

    return paths


def main() -> int:
    """命令行入口。"""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="生成项目数据分析图片")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default=os.getenv("ANALYTICS_USERNAME", ""))
    parser.add_argument("--password", default=os.getenv("ANALYTICS_PASSWORD", ""))
    parser.add_argument("--skip-latency", action="store_true")
    parser.add_argument("--limit-per-mode", type=int, default=4)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    output_dir = args.output_dir or project_root.parent / "docs" / "image"
    offline = build_offline_metrics(project_root)
    rag = evaluate_rag(args.api_base)
    routes = evaluate_routes()
    vectors = project_vectors(project_root)
    latency = None
    if not args.skip_latency:
        if not args.username or not args.password:
            raise SystemExit("在线耗时评测需要 --username 和 --password")
        latency = evaluate_latency(
            args.api_base,
            username=args.username,
            password=args.password,
            limit_per_mode=args.limit_per_mode,
        )
    outputs = generate_figures(
        offline=offline,
        rag=rag,
        routes=routes,
        vectors=vectors,
        latency=latency,
        output_dir=output_dir,
    )
    print(f"已生成 {len(outputs)} 张图片：")
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
