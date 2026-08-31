"""今日校园 · 去哪儿：预设地点路线规划 + 天气关联 LLM 分析。"""
from __future__ import annotations

import json
import re
from typing import Any

from backend.config import settings
from backend.tools.map_tool import MapTool
from backend.utils.llm_content import extract_text_content

# 前端可选地点 key → 高德 geocode 用完整地址
NAVIGATION_LOCATIONS: dict[str, str] = {
    "海珠校区": "仲恺农业工程学院海珠校区",
    "白云校区": "仲恺农业工程学院白云校区",
    "广州南站": "广州南站",
    "广州东站": "广州东站",
    "广州火车站": "广州火车站",
    "白云机场": "广州白云国际机场",
    "天河客运站": "天河客运站",
}

CAMPUS_KEYS = frozenset({"海珠校区", "白云校区"})
HUB_KEYS = frozenset(NAVIGATION_LOCATIONS.keys()) - CAMPUS_KEYS

TRAVEL_MODES: dict[str, str] = {
    "transit": "公交/地铁",
    "driving": "驾车",
    "walking": "步行",
    "cycling": "骑行",
}


def list_navigation_locations() -> list[dict[str, str]]:
    """返回前端下拉选项。"""
    items: list[dict[str, str]] = []
    for key in ("海珠校区", "白云校区"):
        items.append({"key": key, "label": key, "category": "campus"})
    for key in sorted(HUB_KEYS):
        items.append({"key": key, "label": key, "category": "hub"})
    return items


def resolve_location(key: str) -> str | None:
    return NAVIGATION_LOCATIONS.get(key)


def default_travel_mode(origin_key: str, destination_key: str) -> str:
    """两校区互达默认公交；其余默认公交/地铁。"""
    if origin_key in CAMPUS_KEYS and destination_key in CAMPUS_KEYS:
        return "transit"
    return "transit"


def _format_routes_for_prompt(item: dict[str, Any]) -> str:
    lines: list[str] = []
    travel_label = TRAVEL_MODES.get(item.get("travel_mode", "transit"), "公交/地铁")
    lines.append(
        f"起终点：{item.get('origin', '')} → {item.get('destination', '')}（{travel_label}）"
    )
    lines.append(f"首选方案概览：{item.get('summary', '')}，全程 {item.get('distance', '')}，约 {item.get('duration', '')}")

    routes = item.get("routes") or []
    if routes:
        for route in routes:
            segs = " → ".join(route.get("segments") or [])
            fare = f"，票价约 {route['fare']}" if route.get("fare") else ""
            lines.append(
                f"- {route.get('plan', '方案')}：{route.get('duration', '')}，"
                f"{route.get('distance', '')}{fare}；{segs}"
            )
    else:
        steps = item.get("steps") or []
        for idx, step in enumerate(steps[:8], 1):
            lines.append(f"- 步骤{idx}：{step.get('instruction', '')}（{step.get('distance', '')}）")
        if len(steps) > 8:
            lines.append(f"- …共 {len(steps)} 步")

    return "\n".join(lines)


def _build_travel_analysis_prompt(
    *,
    origin_key: str,
    destination_key: str,
    travel_mode: str,
    route_item: dict[str, Any],
    weather: dict[str, Any] | None,
) -> str:
    w = weather or {}
    weather_block = (
        f"天气：{w.get('text', '未知')}，气温 {w.get('temp', '?')}°C，"
        f"体感 {w.get('feels_like', '?')}°C，"
        f"{w.get('wind_dir', '')}{w.get('wind_scale', '')}级风，"
        f"湿度 {w.get('humidity', '?')}%"
        if w and not w.get("error")
        else "天气：暂无数据"
    )

    mode_label = TRAVEL_MODES.get(travel_mode, travel_mode)

    return f"""你是仲恺农业工程学院学生的出行助手。请根据高德地图返回的路线方案与当前广州天气，给出对比推荐与出行提醒。

## 出行请求
- 起点：{origin_key}
- 终点：{destination_key}
- 出行方式：{mode_label}

## 路线方案（来自高德地图，不得编造站点/时间/距离）
{_format_routes_for_prompt(route_item)}

## 当前天气（广州）
{weather_block}

## 要求
1. 推荐一条最合适的方案（方案1/2/3 或「首选方案」），并说明理由（时间、费用、换乘、步行距离等）
2. 结合天气给出 1–2 条实用提醒（如带伞、防晒、保暖、预留缓冲时间）
3. 所有时间、距离、站点、线路必须来自上方【路线方案】；天气描述必须来自【当前天气】
4. 语气亲切简洁，像学长学姐提醒
5. 只返回 JSON，不要 markdown：
{{"recommended_plan":"方案1或首选方案","summary":"一两句总述","route_reason":"推荐理由","weather_tips":"天气相关提醒","extra_tips":"其他可选提醒，无则空字符串"}}"""


def _parse_analysis_json(text: str) -> dict[str, str] | None:
    json_match = re.search(r"\{[\s\S]*\}", text)
    if not json_match:
        return None
    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return {
        "recommended_plan": str(data.get("recommended_plan", "")).strip(),
        "summary": str(data.get("summary", "")).strip(),
        "route_reason": str(data.get("route_reason", "")).strip(),
        "weather_tips": str(data.get("weather_tips", "")).strip(),
        "extra_tips": str(data.get("extra_tips", "")).strip(),
    }


def _fallback_analysis(
    route_item: dict[str, Any],
    weather: dict[str, Any] | None,
) -> dict[str, str]:
    summary = route_item.get("summary") or "已为你规划路线"
    tips = ""
    if weather and not weather.get("error"):
        text = weather.get("text", "")
        if "雨" in text:
            tips = "当前有降水，建议带伞并注意步行路段防滑。"
        elif weather.get("temp") and str(weather.get("temp")).isdigit() and int(weather["temp"]) >= 33:
            tips = "气温较高，注意防晒补水，尽量缩短户外步行时间。"
        elif weather.get("temp") and str(weather.get("temp")).isdigit() and int(weather["temp"]) <= 10:
            tips = "天气较冷，户外候车或步行时注意保暖。"

    return {
        "recommended_plan": "首选方案",
        "summary": summary,
        "route_reason": f"全程约 {route_item.get('duration', '')}，{route_item.get('distance', '')}",
        "weather_tips": tips,
        "extra_tips": "建议比导航时间多预留 10 分钟缓冲。",
    }


async def plan_navigation(
    origin_key: str,
    destination_key: str,
    travel_mode: str | None = None,
) -> dict[str, Any]:
    """查表 → 高德路线规划。"""
    origin_addr = resolve_location(origin_key)
    dest_addr = resolve_location(destination_key)

    if not origin_addr:
        return {"ok": False, "error": f"未知起点「{origin_key}」"}
    if not dest_addr:
        return {"ok": False, "error": f"未知终点「{destination_key}」"}
    if origin_key == destination_key:
        return {"ok": False, "error": "起点与终点不能相同，请重新选择"}

    mode = travel_mode or default_travel_mode(origin_key, destination_key)
    tool = MapTool()
    result = await tool.run_structured(origin_addr, dest_addr, mode)

    if result.get("error"):
        return {"ok": False, "error": result["error"]}

    items = result.get("items") or []
    if not items:
        return {"ok": False, "error": "未获取到路线方案"}

    item = items[0]
    return {
        "ok": True,
        "origin_key": origin_key,
        "destination_key": destination_key,
        "origin": item.get("origin", origin_addr),
        "destination": item.get("destination", dest_addr),
        "travel_mode": item.get("travel_mode", mode),
        "distance": item.get("distance", ""),
        "duration": item.get("duration", ""),
        "summary": item.get("summary", ""),
        "routes": item.get("routes", []),
        "steps": item.get("steps", []),
        "route_item": item,
    }


async def generate_travel_analysis(
    *,
    origin_key: str,
    destination_key: str,
    travel_mode: str,
    route_item: dict[str, Any],
    weather: dict[str, Any] | None,
) -> dict[str, str]:
    """LLM 结合路线与天气生成推荐分析。"""
    if not settings.deepseek_api_key:
        return _fallback_analysis(route_item, weather)

    try:
        from langchain_deepseek import ChatDeepSeek

        llm = ChatDeepSeek(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=0.3,
            max_tokens=500,
        )
        prompt = _build_travel_analysis_prompt(
            origin_key=origin_key,
            destination_key=destination_key,
            travel_mode=travel_mode,
            route_item=route_item,
            weather=weather,
        )
        response = await llm.ainvoke(prompt)
        parsed = _parse_analysis_json(extract_text_content(response).strip())
        if parsed and parsed.get("summary"):
            return parsed
    except Exception as e:
        print(f"[TravelNavigate] LLM 分析失败: {e}")

    return _fallback_analysis(route_item, weather)
