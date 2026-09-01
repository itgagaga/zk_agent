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


def _format_tool_result(context_parts: list[str], tool_result: dict[str, Any]) -> None:
    """将单个工具结果格式化追加到 context_parts。"""
    tool_name = tool_result.get("tool", "")
    tool_labels = {
        "download_search": "【材料 Agent · 资料下载】",
        "contact_search": "【联系 Agent · 联系方式】",
        "service_link_search": "【入口 Agent · 服务入口】",
        "weather_search": "【天气 Agent】",
        "map_route": "【路线 Agent】",
        "academic_search": "【学术 Agent】",
        "major_search": "【专业 Agent】",
    }
    header = tool_labels.get(tool_name, f"【{tool_name}】")
    context_parts.append(header)
    if tool_result.get("error"):
        context_parts.append(f"工具调用提示：{tool_result['error']}")
    for item in tool_result.get("items", []) or []:
        if tool_name == "weather_search":
            context_parts.append(f"- 城市：{item.get('city', '')}")
            context_parts.append(
                f"  当前天气：{item.get('text', '')}，气温 {item.get('temp', '')}°C"
                f"（体感 {item.get('feels_like', '')}°C）"
            )
            context_parts.append(
                f"  风：{item.get('wind_dir', '')} {item.get('wind_scale', '')}级，"
                f"湿度：{item.get('humidity', '')}%，能见度：{item.get('visibility', '')}km"
            )
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
            context_parts.append("  【说明：以下论文由 LLM 优化搜索关键词后，通过 Crossref/arXiv 检索获得】")
            context_parts.append(f"- [{item.get('year', '')}] {item.get('title', '')}")
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
            mode_labels = {"driving": "驾车", "transit": "公交/地铁", "walking": "步行", "cycling": "骑行"}
            mode_label = mode_labels.get(item.get("travel_mode", ""), "公交/地铁")
            context_parts.append(f"- 路线：{item.get('origin', '')} → {item.get('destination', '')}")
            context_parts.append(f"  出行方式：{mode_label}")
            context_parts.append(f"  总距离：{item.get('distance', '')}，预计用时：{item.get('duration', '')}")
            if item.get("routes"):
                for route in item["routes"]:
                    context_parts.append(
                        f"  【{route.get('plan', '')}】{route.get('duration', '')}，{route.get('distance', '')}"
                    )
                    for seg in route.get("segments", []):
                        context_parts.append(f"    {seg}")
            if item.get("steps"):
                for i, step in enumerate(item["steps"], 1):
                    instr = step.get("instruction", "")
                    dist = step.get("distance", "")
                    context_parts.append(f"  {i}. {instr}（{dist}）")
        elif tool_name == "contact_search":
            context_parts.append(
                f"- {item.get('title', '')}：电话 {item.get('phone', '')}，"
                f"地址 {item.get('address') or item.get('location', '')}"
            )
        elif tool_name == "service_link_search":
            context_parts.append(
                f"- {item.get('title') or item.get('name', '')}："
                f"{item.get('url', '')}（{item.get('service_scope') or item.get('description', '')}）"
            )
        else:
            context_parts.append(f"- {item}")
    context_parts.append("")


# 按证据模式选择系统角色；模式描述如何组织已融合证据，不负责裁决或过滤证据。
_EVIDENCE_MODE_SYSTEM: dict[str, str] = {
    "api": """你是一个校园出行与天气信息 Agent，专门基于第三方实时 API 数据回答。

你的职责：
1. 仅基于【实时 API 取证】中的高德地图路线或和风天气数据回答；
2. 路线问题：列出方案、距离、用时、换乘/路段；来源标注「高德地图API」；
3. 天气问题：报气温、降水、穿衣建议；来源标注「和风天气API」；
4. 若 API 返回错误信息，如实转告用户并给出可操作建议；
5. 不要引用官网 RAG 资料，不要建议用户自行打开地图 App。""",

    "tool": """你是一个校园结构化信息查询 Agent，基于数据库/元数据查询结果回答。

你的职责：
1. 优先基于【结构化 Agent 取证】中的电话、专业、下载、入口等查询结果回答；
2. 必须引用对应来源（部门、链接）；
3. 若同时有实时 API 数据（路线/天气），一并整合回答；
4. 若无有效查询结果，明确说明未找到。""",

    "rag": """你是一个面向仲恺农业工程学院学生、教师和访客的校园信息服务智能体。

你的核心职责：
1. 基于官网公开资料回答问题；
2. 必须引用来源（标题、部门、URL、发布时间）；
3. 如果资料中没有可靠依据，明确说明"未找到可靠依据"，不要编造；
4. 涉及电话、地址、时间、流程、招生计划、专业设置等具体信息，必须以官网最新文件为准；
5. 不回答与仲恺校园信息无关的问题。""",

    "document": """你是一个智能文档问答 Agent，专门基于用户上传的永久文档和知识库回答。

你的职责：
1. 优先基于【知识库文档】内容回答；
2. 官网资料仅作补充；
3. 必须引用文档来源；
4. 若文档已能回答问题，不要再说「未找到」；
5. 【知识库文档】可能以多个片段提供；若已包含某章节（如专业必修/选修、教学进程表），请直接整理回答，不要说「片段不完整」或让用户再去查 PDF；
6. 仅当片段中确实完全没有用户所问的信息时，才说明该部分未在已检索内容中出现。
7. 对建议类问题，先提取文档中的具体事实（课程、学分、学期、实践要求等），再给出与这些事实对应的建议；不要只输出通用套话。""",

    "affairs": """你是一个校园办事指引 Agent，负责整合多 Agent 协作取证结果。

你的职责：
1. 整合材料 Agent、联系 Agent、入口 Agent、政策 Agent 的取证结果；
2. 按以下结构组织回答：
   - 办理概述
   - 所需材料/表格
   - 办理流程/步骤
   - 联系方式
   - 系统入口/链接
3. 各部分必须引用对应来源；某 Agent 无结果时说明该部分未找到依据，不要编造。""",

    "composite": """你是一个综合校园助手 Agent，用户一次提了多个不同领域的问题。

你的职责：按用户问题的顺序，分区逐一回答，每部分使用对应 Agent 的取证结果：
1. 学业/专业建议 → 优先【知识库文档】中的培养方案，其次【官网资料】和【专业 Agent】
2. 天气/出行建议 → 基于【天气 Agent】实时数据
3. 校园网/办事 → 基于【入口 Agent】【联系 Agent】和【官网资料】
4. 路线交通 → 基于【路线 Agent】高德地图数据；有 API 数据时直接给方案，不要让用户自己查地图

每部分用清晰小标题分隔，分别列出引用来源。
5. 当【知识库文档】与某个子问题相关时，它是该子问题的主要依据；官网资料和工具结果只用于补充或核对。
6. 建议类问题必须先引用个人资料中的具体事实，再给出可执行建议；不要用“打好基础、拓宽视野”等空泛表述替代课程、学分、学期或实践信息。
7. 明确区分“文档事实”和“基于事实的建议”；建议可以是合理推导，但不能伪装成文档原文要求。""",
}


def _build_context(
    *,
    sources: list[dict[str, Any]] | None,
    user_sources: list[dict[str, Any]] | None,
    tool_results: list[dict[str, Any]] | None,
    evidence_mode: str,
) -> str:
    """按证据模式格式化已融合资料，不执行来源优先级裁决。"""
    context_parts: list[str] = []

    if evidence_mode in ("document", "affairs", "composite") and user_sources:
        context_parts.append("【知识库文档 · 个人资料主要依据】")
        for i, src in enumerate(user_sources, 1):
            context_parts.append(
                f"U{i}. {src.get('title', '')}\n   片段：{src.get('snippet', '')}"
            )
        context_parts.append("")

    if evidence_mode in ("rag", "document", "affairs", "composite") and sources:
        label = "【官网资料 · 政策 Agent】" if evidence_mode in ("affairs", "composite") else "【检索到的官网资料】"
        context_parts.append(label)
        for i, src in enumerate(sources, 1):
            context_parts.append(
                f"{i}. {src.get('title', '')}\n"
                f"   来源：{src.get('department', '')} - {src.get('url', '')}\n"
                f"   发布时间：{src.get('publish_date', '未知')}\n"
                f"   片段：{src.get('snippet', '')}"
            )

    if tool_results and evidence_mode in ("api", "tool", "affairs", "composite"):
        if evidence_mode == "composite":
            label = "\n【多 Agent 协作取证 · 按领域分区使用】"
        elif evidence_mode == "api":
            label = "\n【实时 API 取证】"
        elif evidence_mode == "affairs":
            label = "\n【多 Agent 协作取证】"
        else:
            label = "\n【结构化 Agent 取证】"
        context_parts.append(label)
        for tr in tool_results:
            _format_tool_result(context_parts, tr)

    return "\n".join(context_parts) if context_parts else "(无可用资料)"


def build_qa_prompt(
    question: str,
    sources: list[dict[str, Any]] | None = None,
    tool_result: dict[str, Any] | None = None,
    tool_results: list[dict[str, Any]] | None = None,
    history: list[dict[str, str]] | None = None,
    user_sources: list[dict[str, Any]] | None = None,
    evidence_priority: str | None = None,
    evidence_mode: str | None = None,
) -> str:
    """构建问答 Prompt。

    ``evidence_mode`` 是新编排路径使用的上下文格式模式；
    ``evidence_priority`` 仅作为旧调用方的兼容参数。当两者同时存在时，
    新模式优先，避免旧字段重新成为证据裁决入口。
    """
    all_tool_results = tool_results or []
    if not all_tool_results and tool_result:
        all_tool_results = [tool_result]

    mode = evidence_mode or evidence_priority or "rag"
    system = _EVIDENCE_MODE_SYSTEM.get(mode, _EVIDENCE_MODE_SYSTEM["rag"])
    context = _build_context(
        sources=sources,
        user_sources=user_sources,
        tool_results=all_tool_results,
        evidence_mode=mode,
    )

    history_block = ""
    if history:
        recent = history[-6:]
        lines = []
        for msg in recent:
            role = "用户" if msg.get("role") == "user" else "助手"
            lines.append(f"{role}: {msg.get('content', '')}")
        history_block = "【历史对话】\n" + "\n".join(lines) + "\n\n"

    return f"""{system}

请根据以下信息回答用户问题，并在回答末尾列出引用来源。
只回答当前问题实际涉及的内容；不要说明哪些领域未涉及、哪些工具或 Agent 未调用，也不要为这些内容生成空小节。
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
