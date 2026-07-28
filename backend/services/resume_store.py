"""简历档案读写（按 user_id）。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.database.models import ResumeProfile


def load_resume_data(db: Session, user_id: int) -> dict[str, Any] | None:
    row = db.query(ResumeProfile).filter(ResumeProfile.user_id == user_id).first()
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
    return data


def save_resume_data(
    db: Session,
    user_id: int,
    data: dict[str, Any],
    *,
    file_path: str | None = None,
) -> ResumeProfile:
    payload = {k: v for k, v in data.items() if not str(k).startswith("_")}
    row = db.query(ResumeProfile).filter(ResumeProfile.user_id == user_id).first()
    now = datetime.utcnow()
    if row is None:
        row = ResumeProfile(
            user_id=user_id,
            data=json.dumps(payload, ensure_ascii=False),
            file_path=file_path,
            updated_at=now,
        )
        db.add(row)
    else:
        row.data = json.dumps(payload, ensure_ascii=False)
        if file_path is not None:
            row.file_path = file_path
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return row
