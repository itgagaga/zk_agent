# 向量库目录

Chroma PersistentClient 持久化目录，包含两个集合：
- `zhku_campus` — 官网通用 RAG 知识库
- `zhku_documents` — 智能文档 RAG 知识库

由 crawler.build_kb 脚本写入，由 backend.rag.vector_store 读取。
