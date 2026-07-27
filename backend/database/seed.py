"""数据库初始化种子脚本（MySQL）。

运行方式：
    python -m backend.database.seed

功能：
    1. 确保 MySQL 库存在并创建表结构；
    2. 若本地仍有旧 SQLite（data/sqlite/zhku.db），自动迁移数据（不覆盖已有行）；
    3. 写入少量占位数据（仅在对应表为空时）。
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from backend.config import settings
from backend.database.session import SessionLocal, apply_schema, engine


def init_schema() -> None:
    """根据 schema.sql 初始化 MySQL 表结构。"""
    apply_schema()
    print(f"[seed] MySQL schema 初始化完成: {settings.mysql_database}")


def init_orm() -> None:
    """使用 SQLAlchemy ORM 补齐模型中定义的表。"""
    from backend.database.models import Base

    Base.metadata.create_all(engine)
    print("[seed] SQLAlchemy ORM 表创建完成")


def seed_placeholder_data() -> None:
    """写入少量占位数据（仅在表为空时）。"""
    with SessionLocal() as session:
        count = session.execute(text("SELECT COUNT(*) FROM school_profile")).scalar() or 0
        if count == 0:
            session.execute(
                text(
                    "INSERT INTO school_profile (name, description, source_url) "
                    "VALUES (:name, :description, :source_url)"
                ),
                {
                    "name": "仲恺农业工程学院",
                    "description": "（占位）真实描述由 crawler 采集 https://www.zhku.edu.cn/xxgk.htm 后填充。",
                    "source_url": "https://www.zhku.edu.cn/xxgk.htm",
                },
            )

        org_count = session.execute(text("SELECT COUNT(*) FROM organization")).scalar() or 0
        if org_count == 0:
            sample_orgs = [
                ("农业与生物学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("园艺园林学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("轻工食品学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("动物科技学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("经贸学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("管理学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("人工智能学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("外国语学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("机电工程学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("何香凝艺术设计学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("化工与材料学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("资源与环境学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("数学与数据科学学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("城乡建设学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("自动化学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("人文与社会科学学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("体育学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("马克思主义学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("创新创业教育学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("继续教育学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("国际教育学院", "教学机构", "https://www.zhku.edu.cn/"),
                ("乡村振兴培训学院", "教学机构", "https://www.zhku.edu.cn/"),
            ]
            session.execute(
                text(
                    "INSERT INTO organization (name, type, source_url) "
                    "VALUES (:name, :type, :source_url)"
                ),
                [
                    {"name": n, "type": t, "source_url": u}
                    for n, t, u in sample_orgs
                ],
            )

        session.commit()
        print("[seed] 占位数据写入完成")


def maybe_migrate_from_sqlite() -> None:
    """若旧 SQLite 存在，则迁移到 MySQL（保留原文件）。"""
    sqlite_path = Path(settings.sqlite_path)
    if not sqlite_path.exists():
        print(f"[seed] 未发现旧 SQLite（{sqlite_path}），跳过迁移")
        return

    from backend.database.migrate_sqlite_to_mysql import migrate

    print(f"[seed] 发现旧 SQLite，开始迁移: {sqlite_path}")
    migrate(sqlite_path)


def main() -> None:
    """主入口。"""
    print("[seed] 开始初始化 MySQL 数据库 ...")
    init_schema()
    init_orm()
    maybe_migrate_from_sqlite()
    seed_placeholder_data()
    print("[seed] 完成")


if __name__ == "__main__":
    main()
