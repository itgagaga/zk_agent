"""数据库初始化种子脚本。

运行方式：
    python -m backend.database.seed

功能：
    1. 创建所有数据表（如果不存在）；
    2. 写入少量占位数据（学校基础信息、教学机构示例）；
    3. 真实数据由 crawler 模块采集后填充。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.config import settings


def init_schema() -> None:
    """根据 schema.sql 初始化数据库。"""
    db_path = Path(settings.sqlite_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()

    print(f"[seed] SQLite schema 初始化完成: {db_path}")


def init_orm() -> None:
    """使用 SQLAlchemy ORM 初始化（与 schema.sql 等价）。"""
    from backend.database.models import Base
    from sqlalchemy import create_engine

    engine = create_engine(
        f"sqlite:///{settings.sqlite_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    print("[seed] SQLAlchemy ORM 表创建完成")


def seed_placeholder_data() -> None:
    """写入少量占位数据。

    真实数据由 crawler 模块采集。这里只放最小占位用于验证流程。
    """
    conn = sqlite3.connect(str(settings.sqlite_path))
    try:
        cur = conn.cursor()

        # 学校概况占位
        cur.execute(
            "SELECT COUNT(*) FROM school_profile"
        )
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO school_profile (name, description, source_url) VALUES (?, ?, ?)",
                (
                    "仲恺农业工程学院",
                    "（占位）真实描述由 crawler 采集 https://www.zhku.edu.cn/xxgk.htm 后填充。",
                    "https://www.zhku.edu.cn/xxgk.htm",
                ),
            )

        # 教学机构占位
        cur.execute("SELECT COUNT(*) FROM organization")
        if cur.fetchone()[0] == 0:
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
            cur.executemany(
                "INSERT INTO organization (name, type, source_url) VALUES (?, ?, ?)",
                sample_orgs,
            )

        conn.commit()
        print("[seed] 占位数据写入完成")
    finally:
        conn.close()


def main() -> None:
    """主入口。"""
    print("[seed] 开始初始化数据库 ...")
    init_schema()
    init_orm()
    seed_placeholder_data()
    print("[seed] 完成")


if __name__ == "__main__":
    main()
