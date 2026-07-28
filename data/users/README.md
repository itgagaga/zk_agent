# 用户私有文件目录

按账号隔离，运行时由后端自动创建，**不要提交到 Git**。

```text
data/users/{user_id}/
  uploads/   # 智能文档原件（PDF / Word / TXT / MD）
  resume/    # 简历上传原件
```

- 元数据在 MySQL：`user_document`、`resume_profile`
- 文档向量在 Chroma 集合 `zhku_user_docs`（路径见 `data/vector_store/`）
- 备份时需同时备份本目录、MySQL 与向量库

旧版全局路径（已废弃，仅兼容遗留数据）：

- `data/uploads/`
- `data/resume/`
