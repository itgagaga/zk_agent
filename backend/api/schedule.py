"""课表与今日校园 API。

- 上传/读取个人课表（Excel）
- 今日课程 + 天气 + LLM 出行建议
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.deps import get_current_user, get_current_user_optional
from backend.config import settings
from backend.database.models import User
from backend.database.session import get_db
from backend.services.schedule_parser import (
    WEEKDAY_HEADERS,
    estimate_current_week,
    get_today_courses,
    parse_schedule_excel,
)
from backend.services.schedule_store import (
    delete_schedule_data,
    load_schedule_data,
    save_schedule_data,
)
from backend.storage.user_files import delete_path, to_data_relative, user_schedule_dir
from backend.tools.weather_tool import WeatherTool

router = APIRouter()

ALLOWED_EXT = {".xls", ".xlsx"}
MAX_SIZE = 5 * 1024 * 1024


class ScheduleProfileResponse(BaseModel):
    ok: bool = True
    schedule: dict[str, Any] | None = None
    message: str = ""


class TodayCampusResponse(BaseModel):
    ok: bool = True
    has_schedule: bool = False
    weekday: str = ""
    current_week: int = 1
    today_courses: list[dict[str, Any]] = Field(default_factory=list)
    weather: dict[str, Any] | None = None
    advice: str = ""
    advice_cached: bool = False
    schedule_meta: dict[str, Any] | None = None


def _init_llm() -> Any:
    if not settings.deepseek_api_key:
        return None
    try:
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=0.7,
            max_tokens=800,
        )
    except Exception as e:
        print(f"[ScheduleAPI] LLM 初始化失败: {e}")
        return None


def _build_advice_prompt(
    *,
    weekday: str,
    week: int,
    courses: list[dict[str, Any]],
    weather: dict[str, Any] | None,
    meta: dict[str, Any],
) -> str:
    course_lines = []
    if courses:
        for c in courses:
            course_lines.append(
                f"- {c.get('start', '')}-{c.get('end', '')} "
                f"{c.get('name', '')} @ {c.get('location', '待定')} "
                f"（{c.get('teacher', '')}）"
            )
    else:
        course_lines.append("- 今日无排课或当前教学周不上课")

    w = weather or {}
    weather_block = (
        f"天气：{w.get('text', '未知')}，气温 {w.get('temp', '?')}°C，"
        f"体感 {w.get('feels_like', '?')}°C，"
        f"{w.get('wind_dir', '')}{w.get('wind_scale', '')}级风，"
        f"湿度 {w.get('humidity', '?')}%"
        if w
        else "天气：暂无数据"
    )

    return f"""你是仲恺农业工程学院学生的贴心校园助手。请根据今日课表与天气，给出简洁实用的出行与学习建议。

## 背景
- 学校：仲恺农业工程学院（广州，白云/海珠校区）
- 学生：{meta.get('major', '在校生')} · {meta.get('class_name', '')}
- 学期：{meta.get('semester', '')}
- 今天是{weekday}，第 {week} 教学周

## 今日课程
{chr(10).join(course_lines)}

## 今日天气（广州）
{weather_block}

## 要求
1. 用 3–5 条要点给出建议（穿搭、是否带伞、通勤时间、课间安排、学习提醒等）
2. 语气亲切自然，像学长学姐在聊天，不要官腔
3. 若今日无课，侧重天气与自习/休闲建议
4. 总字数 120–220 字，不要使用 markdown 标题
5. 直接输出正文，不要 JSON"""


async def _generate_advice(prompt: str) -> str:
    llm = _init_llm()
    if llm is None:
        return (
            "今天也要元气满满！记得查看实时天气再出门，"
            "有课的话提前 10 分钟到教室，带好校园卡和水杯。"
        )
    try:
        response = await llm.ainvoke(prompt)
        return (response.content or "").strip()
    except Exception as e:
        print(f"[ScheduleAPI] LLM 建议生成失败: {e}")
        return "暂时无法生成 AI 建议，请稍后刷新重试。"


async def _fetch_weather() -> dict[str, Any] | None:
    tool = WeatherTool()
    result = await tool.run("广州天气")
    if result.get("error") or not result.get("items"):
        return {"error": result.get("error", "天气数据不可用")}
    item = result["items"][0]
    return {
        "city": item.get("city", "广州"),
        "text": item.get("text", ""),
        "temp": item.get("temp", ""),
        "feels_like": item.get("feels_like", ""),
        "wind_dir": item.get("wind_dir", ""),
        "wind_scale": item.get("wind_scale", ""),
        "humidity": item.get("humidity", ""),
        "visibility": item.get("visibility", ""),
        "update_time": item.get("update_time", ""),
        "forecast": item.get("forecast", []),
    }


@router.get("/profile", response_model=ScheduleProfileResponse)
async def get_schedule_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScheduleProfileResponse:
    data = load_schedule_data(db, current_user.id)
    if data is None:
        return ScheduleProfileResponse(ok=False, schedule=None, message="尚未上传课表")
    return ScheduleProfileResponse(ok=True, schedule=data)


@router.post("/upload")
async def upload_schedule(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    filename = file.filename or "schedule.xls"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXT:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "detail": f"不支持的文件类型，请上传 {', '.join(sorted(ALLOWED_EXT))}",
            },
        )

    content = await file.read()
    if not content:
        return JSONResponse(status_code=400, content={"ok": False, "detail": "文件为空"})
    if len(content) > MAX_SIZE:
        return JSONResponse(status_code=400, content={"ok": False, "detail": "文件超过 5MB"})

    try:
        parsed = parse_schedule_excel(content, filename)
    except Exception as e:
        return JSONResponse(
            status_code=422,
            content={"ok": False, "detail": f"课表解析失败: {e}"},
        )

    sched_dir = user_schedule_dir(current_user.id)
    for old in sched_dir.glob("schedule*"):
        delete_path(old)
    raw_path = sched_dir / f"schedule{suffix}"
    raw_path.write_bytes(content)

    rel = to_data_relative(raw_path)
    parsed["filename"] = filename
    save_schedule_data(db, current_user.id, parsed, file_path=rel, filename=filename)

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "filename": filename,
            "schedule": parsed,
            "course_count": len(parsed.get("courses", [])),
            "message": "课表上传成功",
        },
    )


@router.delete("/profile")
async def remove_schedule(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    data = load_schedule_data(db, current_user.id)
    if data and data.get("_file_path"):
        from backend.storage.user_files import resolve_user_file

        delete_path(resolve_user_file(data["_file_path"]))
    delete_schedule_data(db, current_user.id)
    return JSONResponse(status_code=200, content={"ok": True, "message": "课表已删除"})


@router.get("/today", response_model=TodayCampusResponse)
async def get_today_campus(
    refresh_advice: bool = False,
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> TodayCampusResponse:
    today = date.today()
    weekday = WEEKDAY_HEADERS[today.weekday()]

    schedule: dict[str, Any] | None = None
    if current_user:
        schedule = load_schedule_data(db, current_user.id)

    weather = await _fetch_weather()

    if not schedule:
        advice = await _generate_advice(
            _build_advice_prompt(
                weekday=weekday,
                week=1,
                courses=[],
                weather=weather if not weather.get("error") else None,
                meta={},
            )
        )
        return TodayCampusResponse(
            ok=True,
            has_schedule=False,
            weekday=weekday,
            weather=weather,
            advice=advice,
        )

    week = schedule.get("current_week") or estimate_current_week(
        schedule.get("meta", {}).get("semester", ""), today
    )
    schedule["current_week"] = week
    today_courses = get_today_courses(schedule, today)
    meta = schedule.get("meta", {})

    cache_key = f"_advice_{today.isoformat()}"
    advice = schedule.get(cache_key, "") if not refresh_advice else ""
    advice_cached = bool(advice)

    if not advice or refresh_advice:
        advice = await _generate_advice(
            _build_advice_prompt(
                weekday=weekday,
                week=week,
                courses=today_courses,
                weather=weather if not weather.get("error") else None,
                meta=meta,
            )
        )
        if current_user:
            schedule[cache_key] = advice
            save_schedule_data(db, current_user.id, schedule)

    return TodayCampusResponse(
        ok=True,
        has_schedule=True,
        weekday=weekday,
        current_week=week,
        today_courses=today_courses,
        weather=weather,
        advice=advice,
        advice_cached=advice_cached and not refresh_advice,
        schedule_meta=meta,
    )


@router.get("/week")
async def get_week_grid(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    schedule = load_schedule_data(db, current_user.id)
    if not schedule:
        return JSONResponse(status_code=404, content={"ok": False, "detail": "尚未上传课表"})
    week = schedule.get("current_week") or estimate_current_week(
        schedule.get("meta", {}).get("semester", "")
    )
    return JSONResponse(
        content={
            "ok": True,
            "current_week": week,
            "grid": schedule.get("grid", []),
            "meta": schedule.get("meta", {}),
        }
    )
