"""按用户隔离的本地文件目录。

约定：
  data/users/{user_id}/uploads/{doc_id}.ext
  data/users/{user_id}/resume/{filename}
"""
from __future__ import annotations

from pathlib import Path

from backend.config import DATA_DIR

USERS_ROOT = DATA_DIR / "users"


def user_root(user_id: int) -> Path:
    return USERS_ROOT / str(user_id)


def user_uploads_dir(user_id: int) -> Path:
    path = user_root(user_id) / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_resume_dir(user_id: int) -> Path:
    path = user_root(user_id) / "resume"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_user_file(relative_or_abs: str | None) -> Path | None:
    """将库中记录的路径解析为绝对 Path。"""
    if not relative_or_abs:
        return None
    p = Path(relative_or_abs)
    if not p.is_absolute():
        p = DATA_DIR / relative_or_abs
    return p


def to_data_relative(path: Path) -> str:
    """尽量存成相对 data/ 的路径，便于迁移。"""
    try:
        return str(path.resolve().relative_to(DATA_DIR.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def delete_path(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.is_file():
            path.unlink(missing_ok=True)
    except OSError:
        pass
