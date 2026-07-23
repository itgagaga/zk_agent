# 原始采集数据目录

存放 crawler 模块抓取的原始 HTML / PDF / DOC 文件。

子目录按来源站点划分：
- `zhku_main/` — 学校主站
- `jwc/` — 教务部
- `yjs/` — 研究生处
- `job/` — 就业指导中心
- `hqyzc/` — 总务后勤部
- `wlzx/` — 现代教育技术中心
- `xys/` — 校医院

该目录由 crawler 模块自动写入，内容默认不被 git 跟踪。
