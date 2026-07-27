"""Prompt 模板。

集中管理 RAG、文档问答、答案生成等场景的 Prompt。
"""
from __future__ import annotations

from typing import Any

# 系统角色 Prompt
SYSTEM_PROMPT = """你是一个面向仲恺农业工程学院学生、教师和访客的校园信息服务智能体。

你的核心职责：
1. 基于官网公开资料回答问题；
2. 必须引用来源（标题、部门、URL、发布时间）；
3. 如果资料中没有可靠依据，明确说明"未找到可靠依据"，不要编造；
4. 涉及电话、地址、时间、流程、招生计划、专业设置等具体信息，必须以官网最新文件为准；
5. 不回答与仲恺校园信息无关的问题。

可用信息来源包括：学校概况、机构学院、本科专业、培养方案、教务资料、研究生服务、招生就业、公共服务、新闻公告等。"""


def build_qa_prompt(
    question: str,
    sources: list[dict[str, Any]] | None = None,
    tool_result: dict[str, Any] | None = None,
    history: list[dict[str, str]] | None = None,
    user_sources: list[dict[str, Any]] | None = None,
) -> str:
    """构建问答 Prompt。

    Args:
        question: 当前用户问题
        sources: RAG 检索到的官网来源列表
        tool_result: 结构化工具返回结果
        history: 历史对话，格式 [{"role": "user"/"assistant", "content": "..."}]
        user_sources: 用户上传文档的检索来源列表（优先级高于官网资料）
    """
    context_parts: list[str] = []

    # 文档库（上传的永久文档）优先展示
    if user_sources:
        context_parts.append("【知识库文档（上传的永久文档，优先使用）】")
        for i, src in enumerate(user_sources, 1):
            context_parts.append(
                f"U{i}. {src.get('title', '')}\n"
                f"   片段：{src.get('snippet', '')}"
            )
        context_parts.append("")

    if sources:
        context_parts.append("【检索到的官网资料】")
        for i, src in enumerate(sources, 1):
            context_parts.append(
                f"{i}. {src.get('title', '')}\n"
                f"   来源：{src.get('department', '')} - {src.get('url', '')}\n"
                f"   发布时间：{src.get('publish_date', '未知')}\n"
                f"   片段：{src.get('snippet', '')}"
            )

    if tool_result:
        context_parts.append("\n【结构化工具返回】")
        tool_name = tool_result.get("tool", "")
        for item in tool_result.get("items", []) or []:
            if tool_name == "weather_search":
                # 天气工具：格式化展示
                context_parts.append(f"- 城市：{item.get('city', '')}")
                context_parts.append(f"  当前天气：{item.get('text', '')}，气温 {item.get('temp', '')}°C（体感 {item.get('feels_like', '')}°C）")
                context_parts.append(f"  风：{item.get('wind_dir', '')} {item.get('wind_scale', '')}级，湿度：{item.get('humidity', '')}%，能见度：{item.get('visibility', '')}km")
                if item.get("precip"):
                    context_parts.append(f"  降水量：{item.get('precip')}mm")
                context_parts.append(f"  数据更新时间：{item.get('update_time', '')}")
                for fc in item.get("forecast", []) or []:
                    context_parts.append(
                        f"  {fc.get('date', '')}：{fc.get('text_day', '')}→{fc.get('text_night', '')}，"
                        f"{fc.get('temp_min', '')}~{fc.get('temp_max', '')}°C，"
                        f"{fc.get('wind_dir_day', '')} {fc.get('wind_scale_day', '')}级"
                    )
            elif tool_name == "academic_search":
                # 学术搜索工具：格式化展示
                context_parts.append(
                    f"- [{item.get('year', '')}] {item.get('title', '')}"
                )
                if item.get("authors"):
                    context_parts.append(f"  作者：{item.get('authors', '')}")
                if item.get("cited"):
                    context_parts.append(f"  被引用次数：{item.get('cited', 0)}")
                if item.get("doi"):
                    context_parts.append(f"  DOI：{item.get('doi', '')}")
                if item.get("url"):
                    context_parts.append(f"  链接：{item.get('url', '')}")
                if item.get("snippet"):
                    context_parts.append(f"  摘要：{item.get('snippet', '')}")
                context_parts.append(f"  来源：{item.get('source', '')}")
            elif tool_name == "map_route":
                # 地图路线规划工具：格式化展示
                mode_labels = {"driving": "驾车", "transit": "公交/地铁", "walking": "步行", "cycling": "骑行"}
                mode_label = mode_labels.get(item.get("travel_mode", ""), "公交/地铁")
                context_parts.append(f"- 路线：{item.get('origin', '')} → {item.get('destination', '')}")
                context_parts.append(f"  出行方式：{mode_label}")
                context_parts.append(f"  总距离：{item.get('distance', '')}，预计用时：{item.get('duration', '')}")
                # 公交方案
                if item.get("routes"):
                    for route in item["routes"]:
                        context_parts.append(f"  【{route.get('plan', '')}】{route.get('duration', '')}，{route.get('distance', '')}")
                        for seg in route.get("segments", []):
                            context_parts.append(f"    {seg}")
                # 驾车/步行/骑行步骤
                if item.get("steps"):
                    for i, step in enumerate(item["steps"], 1):
                        instr = step.get("instruction", "")
                        dist = step.get("distance", "")
                        context_parts.append(f"  {i}. {instr}（{dist}）")
            else:
                context_parts.append(f"- {item}")

    context = "\n".join(context_parts) if context_parts else "(无可用资料)"

    # 构建历史对话（最多取最近 6 条 = 3 轮）
    history_block = ""
    if history:
        recent = history[-6:]
        lines = []
        for msg in recent:
            role = "用户" if msg.get("role") == "user" else "助手"
            lines.append(f"{role}: {msg.get('content', '')}")
        history_block = "【历史对话】\n" + "\n".join(lines) + "\n\n"

    user_hint = ""
    if user_sources:
        user_hint = (
            "\n重要提示（知识库文档）：\n"
            "- 知识库文档（标记为 U1, U2...）是用户上传的永久资料，"
            "如果其中包含与问题相关的内容，请优先基于这些内容回答。\n"
            "- 官网资料仅作为补充参考；若知识库文档已能回答问题，不要再说「未找到」或让用户去下载。\n"
        )

    return f"""{SYSTEM_PROMPT}

请根据以下信息回答用户问题。回答必须：
1. 优先基于资料内容；
2. 在回答末尾列出引用来源；
3. 如果资料不足以回答，明确说明"未在已采集的仲恺官网资料中找到可靠依据"。

重要提示：
- 请逐一检查每条来源的【标题】字段，确认是否有与用户问题关键词直接匹配的文档。
- 注意区分"本科"与"研究生"、"硕士"等不同类别，不要混淆。
- 如果来源中已包含与问题匹配的文档（标题包含用户询问的关键词），请基于该文档内容回答，不要遗漏。
- 不要仅依据片段内容或来源排序判断，必须检查所有来源的标题。
- 如果有历史对话，请结合上下文理解当前问题（如"它""这个"等指代词）。
{user_hint}
{history_block}【当前问题】
{question}

【可用资料】
{context}

【回答】
"""


def build_summary_prompt(doc_text: str, max_length: int = 300) -> str:
    """构建文档摘要 Prompt。"""
    return f"""{SYSTEM_PROMPT}

请将以下文档内容总结为不超过 {max_length} 字的中文摘要，突出核心要点。

【文档内容】
{doc_text}

【摘要】
"""


def build_compare_prompt(doc_a: dict[str, Any], doc_b: dict[str, Any]) -> str:
    """构建多文档对比 Prompt。"""
    return f"""{SYSTEM_PROMPT}

请对比以下两份文档的差异，从适用对象、关键条款、办理流程、时间地点等维度对比。

【文档 A】标题：{doc_a.get('title', '')}
内容：
{doc_a.get('content', '')}

【文档 B】标题：{doc_b.get('title', '')}
内容：
{doc_b.get('content', '')}

【对比分析】
"""


def build_extract_prompt(doc_text: str, fields: list[str]) -> str:
    """构建关键字段抽取 Prompt。"""
    fields_str = "、".join(fields)
    return f"""{SYSTEM_PROMPT}

请从以下文档中抽取以下字段：{fields_str}。
以 JSON 格式返回，键为字段名，值为抽取结果。如果文档中未提及，值为 null。

【文档内容】
{doc_text}

【抽取结果 JSON】
"""
