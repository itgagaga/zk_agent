# 清洗后文本目录

存放 crawler.parse_documents 解析后的纯文本 / Markdown。

子目录与 data/raw 对应，每个原始文件对应一个 .txt 文件，
供 crawler.build_kb 切分并向量化后写入 Chroma 向量库。

特殊子目录：
- `documents/` — 智能文档切片（培养方案、招生章程、申请表等）
