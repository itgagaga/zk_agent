"""用户课表读写（按 user_id）。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.database.models import UserSchedule


def load_schedule_data(db: Session, user_id: int) -> dict[str, Any] | None:
    row = db.query(UserSchedule).filter(UserSchedule.user_id == user_id).first()
    if row is None:
        return None
    try:
        data = json.loads(row.data or "{}")
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if row.file_path:
        data["_file_path"] = row.file_path
    if row.filename:
        data["_filename"] = row.filename
    data["_updated_at"] = row.updated_at.isoformat() if row.updated_at else None
    return data


def save_schedule_data(
    db: Session,
    user_id: int,
    data: dict[str, Any],
    *,
    file_path: str | None = None,
    filename: str | None = None,
) -> UserSchedule:
    payload = {k: v for k, v in data.items() if not str(k).startswith("_")}
    row = db.query(UserSchedule).filter(UserSchedule.user_id == user_id).first()
    now = datetime.utcnow()
    if row is None:
        row = UserSchedule(
            user_id=user_id,
            data=json.dumps(payload, ensure_ascii=False),
            file_path=file_path,
            filename=filename,
            updated_at=now,
        )
        db.add(row)
    else:
        row.data = json.dumps(payload, ensure_ascii=False)
        if file_path is not None:
            row.file_path = file_path
        if filename is not None:
            row.filename = filename
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def delete_schedule_data(db: Session, user_id: int) -> bool:
    row = db.query(UserSchedule).filter(UserSchedule.user_id == user_id).first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
