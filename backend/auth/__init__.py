"""用户鉴权：密码哈希、JWT、依赖注入。"""

from backend.auth.deps import get_current_user, get_current_user_optional
from backend.auth.security import create_access_token, hash_password, verify_password

__all__ = [
    "create_access_token",
    "hash_password",
    "verify_password",
    "get_current_user",
    "get_current_user_optional",
]
