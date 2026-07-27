"""地图路线规划工具。

调用高德地图 Web 服务 API，支持地理编码（地址→经纬度）
和多种出行方式的路线规划（驾车/公交/步行/骑行）。

典型场景：「广州南站怎么去仲恺白云校区」「从海珠校区到白云校区怎么走」
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from backend.config import settings

# 高德 Web 服务 API 基地址
AMAP_API_BASE = "https://restapi.amap.com"

# 广州城市编码（公交规划需要）
GUANGZHOU_CITY_CODE = "440100"

# 仲恺校区地址常量（按长度降序排列，长串优先替换避免部分匹配）
CAMPUS_LOCATIONS: list[tuple[str, str]] = [
    ("仲恺白云校区", "仲恺农业工程学院白云校区"),
    ("仲恺海珠校区", "仲恺农业工程学院海珠校区"),
    ("仲恺白云", "仲恺农业工程学院白云校区"),
    ("仲恺海珠", "仲恺农业工程学院海珠校区"),
    ("白云校区", "仲恺农业工程学院白云校区"),
    ("海珠校区", "仲恺农业工程学院海珠校区"),
]

# 模糊终点 → 默认海珠校区（本部）；用户可明确说白云/海珠校区
DEST_ALIASES: dict[str, str] = {
    "学校": "仲恺农业工程学院海珠校区",
    "本校": "仲恺农业工程学院海珠校区",
    "仲恺": "仲恺农业工程学院海珠校区",
    "仲恺农业工程学院": "仲恺农业工程学院海珠校区",
    "仲恺农学院": "仲恺农业工程学院海珠校区",
}

# 常见交通枢纽别名补全（高德地理编码需要完整站名）
ORIGIN_ALIASES: dict[str, str] = {
    "广州东": "广州东站",
    "广州南": "广州南站",
    "广州北": "广州北站",
    "广州站": "广州火车站",
    "天河客运站": "天河客运站",
    "白云机场": "广州白云国际机场",
}


class MapTool:
    """地图路线规划工具。

    第三方 API 工具，调用高德地图接口实现地理编码与路线规划。
    """

    name = "map_route"
    description = "路线规划与地点查询，支持驾车/公交/步行/骑行多种出行方式"

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        """执行路线规划。

        流程：LLM 提取参数 → 地理编码 → 路线规划 → 返回结构化结果
        """
        history: list[dict[str, str]] | None = kwargs.get("history")
        api_key = settings.amap_api_key
        if not api_key:
            return {
                "tool": self.name,
                "items": [],
                "total": 0,
                "error": "未配置高德地图 API Key，请在 .env 中设置 AMAP_API_KEY",
            }

        # 1. 从问题中提取起点、终点、出行方式（结合历史对话补全追问）
        params = await self._extract_params(question, history=history)
        if not params:
            return {
                "tool": self.name,
                "items": [],
                "total": 0,
                "error": "无法从问题中识别起点和终点，请明确说明，例如：从广州南站到仲恺白云校区怎么走",
            }

        origin_addr = params["origin"]
        dest_addr = params["destination"]
        travel_mode = params.get("travel_mode", "transit")

        # 2. 地理编码：地址 → 经纬度
        async with httpx.AsyncClient(timeout=10) as client:
            origin_loc = await self._geocode(client, api_key, origin_addr)
            dest_loc = await self._geocode(client, api_key, dest_addr)

        if not origin_loc:
            return {
                "tool": self.name,
                "items": [],
                "total": 0,
                "error": f"无法解析起点地址「{origin_addr}」，请提供更详细的地址",
            }
        if not dest_loc:
            return {
                "tool": self.name,
                "items": [],
                "total": 0,
                "error": f"无法解析终点地址「{dest_addr}」，请提供更详细的地址",
            }

        # 3. 路线规划
        async with httpx.AsyncClient(timeout=15) as client:
            route_data = await self._plan_route(
                client, api_key, origin_loc, dest_loc, travel_mode
            )

        if not route_data:
            return {
                "tool": self.name,
                "items": [],
                "total": 0,
                "error": "路线规划失败，请稍后重试",
            }

        # 4. 组装返回结果
        item = {
            "title": f"{origin_addr} → {dest_addr}",
            "department": "高德地图API",
            "url": "",
            "publish_date": "",
            "snippet": route_data.get("summary", ""),
            "origin": origin_addr,
            "origin_location": origin_loc,
            "destination": dest_addr,
            "destination_location": dest_loc,
            "travel_mode": travel_mode,
            "distance": route_data.get("distance", ""),
            "duration": route_data.get("duration", ""),
            "summary": route_data.get("summary", ""),
            "routes": route_data.get("routes", []),
            "steps": route_data.get("steps", []),
        }

        return {
            "tool": self.name,
            "items": [item],
            "total": 1,
        }

    # ------------------------------------------------------------------ #
    #  参数提取：LLM + 规则混合策略
    # ------------------------------------------------------------------ #

    async def _extract_params(
        self, question: str, *, history: list[dict[str, str]] | None = None
    ) -> dict[str, str] | None:
        """从自然语言问题中提取起点、终点、出行方式。

        优先使用规则匹配（快速），匹配失败则用 LLM 提取（可结合历史对话）。
        """
        result = self._extract_by_rules(question)
        if result:
            return result
        return await self._extract_by_llm(question, history=history)

    @staticmethod
    def _extract_by_rules(question: str) -> dict[str, str] | None:
        """基于规则的参数提取。

        匹配常见句式：
          - A怎么去B / A怎么走到B
          - 从A到B / 从A去B
          - A到B怎么走
        """
        # 出行方式关键词 → 识别出行方式（不用于地址清洗）
        mode_keywords: dict[str, list[str]] = {
            "driving": ["驾车", "开车", "自驾", "汽车"],
            "transit": ["公交", "地铁", "坐车", "乘车", "大巴"],
            "walking": ["步行", "走路", "走过去", "步行过去"],
            "cycling": ["骑行", "骑车", "自行车", "单车"],
        }

        # 识别出行方式
        travel_mode = "transit"
        for mode, keywords in mode_keywords.items():
            if any(k in question for k in keywords):
                travel_mode = mode
                break

        # 校区地址替换：用占位符避免二次替换
        q = question
        placeholders: dict[str, str] = {}
        for idx, (short, full) in enumerate(CAMPUS_LOCATIONS):
            ph = f"__CAMPUS_{idx}__"
            q = q.replace(short, ph)
            placeholders[ph] = full

        # 去掉出行方式词（仅去掉作为独立词出现的，如"坐公交""乘地铁"）
        q = re.sub(r"(坐|乘|搭)(公交|地铁|大巴|车)", "", q)
        q = re.sub(r"(驾车|开车|自驾|步行|走路|骑行|骑车)", "", q)

        # 去掉尾部问句/说明词（含「学校的交通指引」这类后缀）
        q = re.sub(r"的?(?:交通指引|交通方式|路线规划|出行方案)[？?]?$", "", q)
        q = re.sub(
            r"(怎么走|怎么去|怎么坐|路线|坐什么|搭什么|要多久|多远|怎么去学校)[？?]?$",
            "",
            q,
        )

        # 多种分隔模式，按优先级尝试
        patterns = [
            # 从A到/去/往B
            r"从(.+?)(?:到|去|往)(.+)",
            # 从A前往B
            r"从(.+?)前往(.+)",
            # A怎么去/走到B
            r"(.+?)(?:怎么去|怎么走到)(.+)",
            # 去/到B怎么走（无起点，交给 LLM 或历史补全）
            r"(?:去|到)(.+?)怎么走",
            # A到B（至少含2个字避免误匹配单字）
            r"(.{2,}?)(?:到|去)(.{2,})",
        ]

        origin = None
        dest = None
        for pattern in patterns:
            m = re.search(pattern, q)
            if m:
                if m.lastindex == 1:
                    # 仅目的地（去X怎么走）
                    dest = m.group(1).strip()
                else:
                    origin = m.group(1).strip()
                    dest = m.group(2).strip()
                break

        if not dest:
            return None
        if not origin:
            return None  # 无起点，交给 LLM / 历史补全

        # 清除残留助词与尾部修饰
        for w in ["从", "坐", "乘", "搭"]:
            origin = origin.replace(w, "").strip()
            dest = dest.replace(w, "").strip()
        origin = re.sub(r"^(明天|后天|今天|上午|下午)", "", origin).strip()
        origin = re.sub(r"(出发)$", "", origin).strip()
        dest = re.sub(r"^(明天|后天|今天)", "", dest).strip()
        dest = re.sub(r"的(?:交通指引|交通方式|路线|路径)$", "", dest).strip()
        dest = dest.rstrip("的").strip()

        if not origin or not dest:
            return None

        # 还原占位符
        for ph, full in placeholders.items():
            origin = origin.replace(ph, full)
            dest = dest.replace(ph, full)

        # 模糊终点解析
        dest = DEST_ALIASES.get(dest, dest)
        origin = ORIGIN_ALIASES.get(origin, origin)

        return {"origin": origin, "destination": dest, "travel_mode": travel_mode}

    async def _extract_by_llm(
        self, question: str, *, history: list[dict[str, str]] | None = None
    ) -> dict[str, str] | None:
        """使用 LLM 从问题中提取起点、终点、出行方式（可结合历史对话）。"""
        if not settings.deepseek_api_key:
            return None

        try:
            from langchain_deepseek import ChatDeepSeek

            llm = ChatDeepSeek(
                model=settings.deepseek_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=0,
                max_tokens=200,
            )

            history_block = ""
            if history:
                recent = history[-4:]
                lines = []
                for msg in recent:
                    role = "用户" if msg.get("role") == "user" else "助手"
                    lines.append(f"{role}: {msg.get('content', '')}")
                history_block = "\n历史对话（用于补全追问中的起点/终点）：\n" + "\n".join(lines) + "\n"

            prompt = f"""从以下用户问题中提取路线规划参数，以 JSON 格式返回。
只能返回 JSON，不要返回其他内容。
{history_block}
当前问题：{question}

仲恺农业工程学院有两个校区：
- 白云校区：广州市白云区广从八路1188号
- 海珠校区：广州市海珠区东沙街24号

若用户只说了起点或终点，请结合历史对话补全另一项。
若用户只说「去白云校区怎么走」且未给起点，origin 可设为「广州」。

返回格式：
{{"origin": "起点地址", "destination": "终点地址", "travel_mode": "出行方式"}}

出行方式只能是：driving（驾车）、transit（公交/地铁）、walking（步行）、cycling（骑行）
如果用户未指定，默认为 transit。

示例：
用户问「广州南站怎么去仲恺白云校区」→ {{"origin": "广州南站", "destination": "仲恺农业工程学院白云校区", "travel_mode": "transit"}}
用户问「从海珠校区开车到白云校区」→ {{"origin": "仲恺农业工程学院海珠校区", "destination": "仲恺农业工程学院白云校区", "travel_mode": "driving"}}
历史：用户问过去白云校区怎么走；当前问「从广州东站」→ {{"origin": "广州东站", "destination": "仲恺农业工程学院白云校区", "travel_mode": "transit"}}"""

            response = await llm.ainvoke(prompt)
            text = response.content.strip()

            # 提取 JSON（LLM 可能返回带 markdown 标记的 JSON）
            json_match = re.search(r"\{[^}]+\}", text)
            if not json_match:
                return None

            data = json.loads(json_match.group())
            origin = data.get("origin", "").strip()
            dest = data.get("destination", "").strip()
            mode = data.get("travel_mode", "transit")

            if not origin or not dest:
                return None

            dest = DEST_ALIASES.get(dest, dest)
            origin = ORIGIN_ALIASES.get(origin, origin)

            if mode not in ("driving", "transit", "walking", "cycling"):
                mode = "transit"

            return {"origin": origin, "destination": dest, "travel_mode": mode}

        except Exception as e:
            print(f"[MapTool] LLM 参数提取失败: {e}")
            return None

    # ------------------------------------------------------------------ #
    #  高德 API 调用
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _geocode(
        client: httpx.AsyncClient, api_key: str, address: str
    ) -> str | None:
        """地理编码：地址 → 经纬度字符串（"lng,lat"）。"""
        try:
            resp = await client.get(
                f"{AMAP_API_BASE}/v3/geocode/geo",
                params={"key": api_key, "address": address, "city": "广州"},
            )
            data = resp.json()
            if data.get("status") == "1" and data.get("count", "0") != "0":
                return data["geocodes"][0]["location"]
            return None
        except httpx.HTTPError:
            return None

    async def _plan_route(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        origin: str,
        destination: str,
        travel_mode: str,
    ) -> dict[str, Any] | None:
        """根据出行方式调用对应的路线规划 API。"""
        try:
            if travel_mode == "driving":
                return await self._route_driving(client, api_key, origin, destination)
            elif travel_mode == "transit":
                return await self._route_transit(client, api_key, origin, destination)
            elif travel_mode == "walking":
                return await self._route_walking(client, api_key, origin, destination)
            elif travel_mode == "cycling":
                return await self._route_cycling(client, api_key, origin, destination)
            # 默认公交
            return await self._route_transit(client, api_key, origin, destination)
        except httpx.HTTPError as e:
            print(f"[MapTool] 路线规划 API 请求失败: {e}")
            return None

    @staticmethod
    async def _route_driving(
        client: httpx.AsyncClient, api_key: str, origin: str, destination: str
    ) -> dict[str, Any]:
        """驾车路线规划（v5）。"""
        resp = await client.get(
            f"{AMAP_API_BASE}/v5/direction/driving",
            params={
                "key": api_key,
                "origin": origin,
                "destination": destination,
                "strategy": "32",  # 高德推荐
                "show_fields": "cost,step",
            },
        )
        data = resp.json()
        if data.get("status") != "1" or not data.get("route"):
            return None

        paths = data["route"].get("paths", [])
        if not paths:
            return None

        path = paths[0]
        cost = path.get("cost", {})
        distance_m = int(cost.get("distance", 0))
        duration_s = int(cost.get("duration", 0))

        steps = []
        for step in path.get("steps", []):
            instruction = step.get("instruction", "")
            step_cost = step.get("cost", {})
            step_dist = int(step_cost.get("distance", 0))
            steps.append({
                "instruction": instruction,
                "distance": f"{step_dist}米" if step_dist < 1000 else f"{step_dist / 1000:.1f}公里",
            })

        return {
            "distance": f"{distance_m}米" if distance_m < 1000 else f"{distance_m / 1000:.1f}公里",
            "duration": f"{duration_s // 60}分钟" if duration_s < 3600 else f"{duration_s // 3600}小时{(duration_s % 3600) // 60}分钟",
            "summary": f"驾车约{distance_m / 1000:.1f}公里，预计{duration_s // 60}分钟",
            "steps": steps,
        }

    @staticmethod
    async def _route_transit(
        client: httpx.AsyncClient, api_key: str, origin: str, destination: str
    ) -> dict[str, Any]:
        """公交路线规划（v3 综合换乘）。"""
        resp = await client.get(
            f"{AMAP_API_BASE}/v3/direction/transit/integrated",
            params={
                "key": api_key,
                "origin": origin,
                "destination": destination,
                "city": GUANGZHOU_CITY_CODE,
                "strategy": "0",  # 最快捷
                "nightflag": "0",
                "output": "json",
            },
        )
        data = resp.json()
        if data.get("status") != "1" or not data.get("route"):
            return None

        transits = data["route"].get("transits", [])
        if not transits:
            return None

        # 取前 3 条推荐方案
        routes = []
        for idx, transit in enumerate(transits[:3], 1):
            duration_s = int(transit.get("duration", 0))
            distance_m = int(transit.get("distance", 0))
            fare = transit.get("cost", "")

            # 解析换乘段
            segments_text = []
            for seg in transit.get("segments", []):
                bus_info = seg.get("bus", {})
                walking_info = seg.get("walking", {})

                if bus_info and bus_info.get("buslines"):
                    busline = bus_info["buslines"][0]
                    line_name = busline.get("name", "")
                    dep_stop = busline.get("departure_stop", {}).get("name", "")
                    arr_stop = busline.get("arrival_stop", {}).get("name", "")
                    via_num = busline.get("via_num", "0")
                    segments_text.append(
                        f"乘坐 {line_name}（{dep_stop} → {arr_stop}，{via_num}站）"
                    )
                elif walking_info:
                    walk_dist = int(walking_info.get("distance", 0))
                    if walk_dist > 0:
                        segments_text.append(f"步行 {walk_dist}米")

            routes.append({
                "plan": f"方案{idx}",
                "duration": f"{duration_s // 60}分钟" if duration_s < 3600 else f"{duration_s // 3600}小时{(duration_s % 3600) // 60}分钟",
                "distance": f"{distance_m}米" if distance_m < 1000 else f"{distance_m / 1000:.1f}公里",
                "fare": f"{fare}元" if fare else "",
                "segments": segments_text,
            })

        first = transits[0]
        first_duration = int(first.get("duration", 0)) // 60
        first_distance = int(first.get("distance", 0)) / 1000

        return {
            "distance": f"{first_distance:.1f}公里",
            "duration": f"{first_duration}分钟",
            "summary": f"公交/地铁约{first_distance:.1f}公里，预计{first_duration}分钟",
            "routes": routes,
            "steps": [],  # 公交用 routes 字段
        }

    @staticmethod
    async def _route_walking(
        client: httpx.AsyncClient, api_key: str, origin: str, destination: str
    ) -> dict[str, Any]:
        """步行路线规划（v3）。"""
        resp = await client.get(
            f"{AMAP_API_BASE}/v3/direction/walking",
            params={"key": api_key, "origin": origin, "destination": destination},
        )
        data = resp.json()
        if data.get("status") != "1" or not data.get("route"):
            return None

        paths = data["route"].get("paths", [])
        if not paths:
            return None

        path = paths[0]
        distance_m = int(path.get("distance", 0))
        duration_s = int(path.get("duration", 0))

        steps = []
        for step in path.get("steps", []):
            instruction = step.get("instruction", "")
            step_dist = int(step.get("distance", 0))
            steps.append({
                "instruction": instruction,
                "distance": f"{step_dist}米" if step_dist < 1000 else f"{step_dist / 1000:.1f}公里",
            })

        return {
            "distance": f"{distance_m}米" if distance_m < 1000 else f"{distance_m / 1000:.1f}公里",
            "duration": f"{duration_s // 60}分钟" if duration_s < 3600 else f"{duration_s // 3600}小时{(duration_s % 3600) // 60}分钟",
            "summary": f"步行约{distance_m / 1000:.1f}公里，预计{duration_s // 60}分钟",
            "steps": steps,
        }

    @staticmethod
    async def _route_cycling(
        client: httpx.AsyncClient, api_key: str, origin: str, destination: str
    ) -> dict[str, Any]:
        """骑行路线规划（v4）。"""
        resp = await client.get(
            f"{AMAP_API_BASE}/v4/direction/bicycling",
            params={
                "key": api_key,
                "origin": origin,
                "destination": destination,
                "output": "json",
            },
        )
        data = resp.json()
        if data.get("status") != "1" or not data.get("data"):
            return None

        paths = data["data"].get("paths", [])
        if not paths:
            return None

        path = paths[0]
        distance_m = int(path.get("distance", 0))
        duration_s = int(path.get("duration", 0))

        steps = []
        for step in path.get("steps", []):
            instruction = step.get("instruction", "")
            step_dist = int(step.get("distance", 0))
            steps.append({
                "instruction": instruction,
                "distance": f"{step_dist}米" if step_dist < 1000 else f"{step_dist / 1000:.1f}公里",
            })

        return {
            "distance": f"{distance_m}米" if distance_m < 1000 else f"{distance_m / 1000:.1f}公里",
            "duration": f"{duration_s // 60}分钟" if duration_s < 3600 else f"{duration_s // 3600}小时{(duration_s % 3600) // 60}分钟",
            "summary": f"骑行约{distance_m / 1000:.1f}公里，预计{duration_s // 60}分钟",
            "steps": steps,
        }
