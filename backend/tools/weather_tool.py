"""天气查询工具。

调用和风天气（QWeather）API，查询仲恺校区所在城市的实时天气。
仲恺两个校区均在广州（海珠校区、白云校区）。
"""
from __future__ import annotations

from typing import Any

import httpx

from backend.config import settings

# 仲恺校区 → 城市 Location ID（和风天气城市编码）
# 广州: 101280101
CAMPUS_CITY_MAP: dict[str, str] = {
    "白云": "101280101",
    "海珠": "101280101",
    "广州": "101280101",
    "仲恺": "101280101",
    "默认": "101280101",
}

# 和风天气 API 基地址（免费订阅用 devapi）
API_BASE = "https://devapi.qweather.com/v7"


class WeatherTool:
    """天气查询工具。

    第三方 API 工具，调用和风天气接口获取实时天气数据。
    不继承 BaseTool（因为不走本地 metadata 检索）。
    """

    name = "weather_search"
    description = "查询仲恺校区所在城市（广州）的实时天气、气温、风力、湿度等信息"

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        """查询天气。

        从问题中识别校区/城市，调用和风天气 API 获取实时天气。
        """
        location_id = self._resolve_location(question)
        api_key = settings.qweather_api_key

        if not api_key:
            return {
                "tool": self.name,
                "items": [],
                "total": 0,
                "error": "未配置和风天气 API Key，请在 .env 中设置 QWEATHER_API_KEY",
            }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # 实时天气
                weather_resp = await client.get(
                    f"{API_BASE}/weather/now",
                    params={"location": location_id, "key": api_key},
                )
                weather_data = weather_resp.json()

                if weather_data.get("code") != "200":
                    return {
                        "tool": self.name,
                        "items": [],
                        "total": 0,
                        "error": f"天气 API 返回错误: code={weather_data.get('code')}",
                    }

                now = weather_data.get("now", {})
                # 3天预报
                forecast_resp = await client.get(
                    f"{API_BASE}/weather/3d",
                    params={"location": location_id, "key": api_key},
                )
                forecast_data = forecast_resp.json()
                daily = forecast_data.get("daily", [])

                item = {
                    "title": f"广州实时天气：{now.get('text', '')} {now.get('temp', '')}°C",
                    "department": "和风天气API",
                    "url": "",
                    "publish_date": weather_data.get("updateTime", ""),
                    "snippet": (
                        f"当前{now.get('text', '')}，气温{now.get('temp', '')}°C，"
                        f"体感{now.get('feelsLike', '')}°C，"
                        f"风{now.get('windDir', '')}{now.get('windScale', '')}级，"
                        f"湿度{now.get('humidity', '')}%，"
                        f"能见度{now.get('vis', '')}km，"
                        f"气压{now.get('pressure', '')}hPa"
                    ),
                    "city": "广州",
                    "temp": now.get("temp", ""),
                    "feels_like": now.get("feelsLike", ""),
                    "text": now.get("text", ""),
                    "wind_dir": now.get("windDir", ""),
                    "wind_scale": now.get("windScale", ""),
                    "humidity": now.get("humidity", ""),
                    "precip": now.get("precip", ""),
                    "visibility": now.get("vis", ""),
                    "pressure": now.get("pressure", ""),
                    "update_time": weather_data.get("updateTime", ""),
                }

                # 简化预报数据
                forecast_items = []
                for day in daily[:3]:
                    forecast_items.append({
                        "date": day.get("fxDate", ""),
                        "text_day": day.get("textDay", ""),
                        "text_night": day.get("textNight", ""),
                        "temp_max": day.get("tempMax", ""),
                        "temp_min": day.get("tempMin", ""),
                        "wind_dir_day": day.get("windDirDay", ""),
                        "wind_scale_day": day.get("windScaleDay", ""),
                    })

                item["forecast"] = forecast_items

                return {
                    "tool": self.name,
                    "items": [item],
                    "total": 1,
                }

        except httpx.HTTPError as e:
            return {
                "tool": self.name,
                "items": [],
                "total": 0,
                "error": f"天气 API 请求失败: {e}",
            }

    @staticmethod
    def _resolve_location(question: str) -> str:
        """从问题中识别校区/城市，返回 Location ID。"""
        for campus, loc_id in CAMPUS_CITY_MAP.items():
            if campus in question:
                return loc_id
        return CAMPUS_CITY_MAP["默认"]
