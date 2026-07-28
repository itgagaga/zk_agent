"""今日校园：天气与 AI 建议的数据库缓存。"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.database.models import CampusAdviceCache, CampusWeatherCache

GUEST_USER_ID = 0


def _today_str(today: date | None = None) -> str:
    return (today or date.today()).isoformat()


def load_weather_cache(db: Session, today: date | None = None) -> dict[str, Any] | None:
    row = (
        db.query(CampusWeatherCache)
        .filter(CampusWeatherCache.cache_date == _today_str(today))
        .first()
    )
    if row is None:
        return None
    try:
        data = json.loads(row.data or "{}")
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    data["_cached_at"] = row.updated_at.isoformat() if row.updated_at else None
    return data


def save_weather_cache(db: Session, weather: dict[str, Any], today: date | None = None) -> None:
    day = _today_str(today)
    payload = {k: v for k, v in weather.items() if not str(k).startswith("_")}
    row = (
        db.query(CampusWeatherCache)
        .filter(CampusWeatherCache.cache_date == day)
        .first()
    )
    now = datetime.utcnow()
    if row is None:
        row = CampusWeatherCache(
            cache_date=day,
            data=json.dumps(payload, ensure_ascii=False),
            updated_at=now,
        )
        db.add(row)
    else:
        row.data = json.dumps(payload, ensure_ascii=False)
        row.updated_at = now
    db.commit()


def load_advice_cache(
    db: Session,
    user_id: int | None,
    today: date | None = None,
) -> str | None:
    uid = user_id if user_id is not None else GUEST_USER_ID
    row = (
        db.query(CampusAdviceCache)
        .filter(
            CampusAdviceCache.user_id == uid,
            CampusAdviceCache.cache_date == _today_str(today),
        )
        .first()
    )
    if row is None or not row.advice:
        return None
    return row.advice


def save_advice_cache(
    db: Session,
    user_id: int | None,
    advice: str,
    today: date | None = None,
) -> None:
    uid = user_id if user_id is not None else GUEST_USER_ID
    day = _today_str(today)
    row = (
        db.query(CampusAdviceCache)
        .filter(
            CampusAdviceCache.user_id == uid,
            CampusAdviceCache.cache_date == day,
        )
        .first()
    )
    now = datetime.utcnow()
    if row is None:
        row = CampusAdviceCache(
            user_id=uid,
            cache_date=day,
            advice=advice,
            updated_at=now,
        )
        db.add(row)
    else:
        row.advice = advice
        row.updated_at = now
    db.commit()


def clear_advice_cache(
    db: Session,
    user_id: int,
    today: date | None = None,
) -> None:
    """课表变更等场景下清除当日建议，下次访问会重新生成。"""
    db.query(CampusAdviceCache).filter(
        CampusAdviceCache.user_id == user_id,
        CampusAdviceCache.cache_date == _today_str(today),
    ).delete(synchronize_session=False)
    db.commit()


def advice_cache_updated_at(
    db: Session,
    user_id: int | None,
    today: date | None = None,
) -> datetime | None:
    uid = user_id if user_id is not None else GUEST_USER_ID
    row = (
        db.query(CampusAdviceCache)
        .filter(
            CampusAdviceCache.user_id == uid,
            CampusAdviceCache.cache_date == _today_str(today),
        )
        .first()
    )
    return row.updated_at if row else None
