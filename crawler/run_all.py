"""采集入口脚本。

运行方式：
    python -m crawler.run_all            # 采集全部
    python -m crawler.run_all --skip-job # 跳过就业（动态渲染较慢）

按顺序执行所有采集任务，将原始数据保存到 data/raw/，
清洗后文本保存到 data/cleaned/，元数据保存到 data/metadata/。
"""
from __future__ import annotations

import argparse


def run_all(skip_job: bool = False) -> None:
    """按顺序执行所有采集任务。"""
    print("=" * 60)
    print("ZHKU Campus Agent 数据采集")
    print("=" * 60)

    from crawler.crawl_jwc import main as run_jwc
    from crawler.crawl_services import main as run_services
    from crawler.crawl_yjs import main as run_yjs
    from crawler.crawl_zhku_main import main as run_main

    print("\n[1/5] 学校主站")
    run_main()
    print("\n[2/5] 教务部")
    run_jwc()
    print("\n[2.5/5] 培养方案 PDF（可能较慢）")
    from crawler.crawl_training_plans import main as run_training_plans

    run_training_plans()
    print("\n[3/5] 研究生处")
    run_yjs()
    if not skip_job:
        print("\n[4/5] 就业指导中心（可能较慢）")
        from crawler.crawl_job import main as run_job

        run_job()
    print("\n[5/6] 公共服务模块（后勤 / 网络 / 校医院）")
    run_services()
    print("\n[6/6] 新增模块（学生处 / 招生网 / 研究生补充 / 财务部）")
    from crawler.crawl_extra import main as run_extra

    run_extra()

    print("\n" + "=" * 60)
    print("采集完成，可执行 python -m crawler.build_kb 构建知识库")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="ZHKU 数据采集入口")
    parser.add_argument(
        "--skip-job", action="store_true", help="跳过就业指导中心采集"
    )
    args = parser.parse_args()
    run_all(skip_job=args.skip_job)


if __name__ == "__main__":
    main()
