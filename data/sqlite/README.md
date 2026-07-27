# 结构化数据库目录

业务数据已切换到 **MySQL**（库名默认 `zhku`，见 `.env` 中 `MYSQL_*`）。

本目录仅用于保留旧版 `zhku.db`，供一次性迁移：

```bash
python -m backend.database.migrate_sqlite_to_mysql
```

迁移不会删除或覆盖本目录中的 SQLite 文件。表结构见 `backend/database/schema.sql`。
