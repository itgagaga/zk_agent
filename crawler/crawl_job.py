"""采集就业指导中心信息。

采集范围：
- 职位信息（https://job.zhku.edu.cn/web/index/job-list）
- 校园宣讲会 / 招聘会
- 就业政策与办事指南
"""
from __future__ import annotations

from typing import Any


def crawl_job_postings(top_k: int = 100) -> list[dict[str, Any]]:
    """采集职位信息列表。

    TODO: 实现具体解析逻辑。注意该站点可能为动态渲染，需要 Playwright。
    """
    return []


def crawl_job_fairs() -> list[dict[str, Any]]:
    """采集校园宣讲会 / 招聘会。"""
    return []


def main() -> None:
    print("[crawl_job] 开始采集就业指导中心 ...")
    jobs = crawl_job_postings()
    print(f"  - 职位条目数: {len(jobs)}")
    print("[crawl_job] 完成")


if __name__ == "__main__":
    main()
