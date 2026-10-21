"""手动端到端回归：生产前端 + 真实 SSE 路由/调度器 + 模拟论文网络。"""
from __future__ import annotations

import asyncio
import json
import socket
import sys
import threading
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import expect, sync_playwright

from backend.api import resources
from backend.config import settings
from backend.tools.academic_search_tool import AcademicSearchTool
from backend.utils.academic_links import AcademicLinkChecker


def main():
    settings.academic_search_timeout_seconds = 2
    release_more = threading.Event()
    source_calls, probe_calls = Counter(), Counter()
    tool = object.__new__(AcademicSearchTool)
    tool.llm = None

    def paper(title, path, source="Crossref"):
        return {"title": title, "source": source, "url": f"https://papers.example/{path}", "cited": 0}

    async def crossref(query, limit):
        chinese = "软件工程" in query
        source_calls["zh" if chinese else "en"] += 1
        await asyncio.sleep(0.15 if chinese else 0.05)
        return ([paper("软件工程测试论文一", "zh-early"), paper("软件工程测试论文二", "zh-later")]
                if chinese else [paper("Software engineering test one", "en-early")])

    async def arxiv(query, limit):
        source_calls["arxiv"] += 1
        while not release_more.is_set():
            await asyncio.sleep(0.02)
        return [paper("Software engineering test two", "en-later", "arXiv")]

    def make_checker():
        checker = AcademicLinkChecker()

        async def probe(client, url):
            path = url.rsplit("/", 1)[-1]
            probe_calls[path] += 1
            if path == "zh-later":
                while not release_more.is_set():
                    await asyncio.sleep(0.02)
            await asyncio.sleep(0.03)
            return url

        checker._probe = probe
        return checker

    tool._search_crossref = crossref
    tool._search_arxiv = arxiv
    tool._make_link_checker = make_checker
    resources._academic_search_tool = tool
    app = FastAPI()
    app.include_router(resources.router, prefix="/api/resources")

    @app.get("/resume")
    async def resume():
        return FileResponse(ROOT / "frontend/dist/index.html")

    app.mount("/", StaticFiles(directory=ROOT / "frontend/dist", html=True))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="off"))
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.02)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}/resume", wait_until="domcontentloaded")
            page.get_by_role("button", name="学术搜索", exact=True).click()
            field = page.get_by_placeholder("输入研究方向或关键词，如：深度学习、物联网 农业、transformer")
            field.fill("软件工程")
            page.get_by_role("button", name="搜索论文", exact=True).click()
            expect(page.locator(".as-paper-card").first).to_be_visible()
            expect(page.get_by_role("button", name="停止等待", exact=True)).to_be_visible()
            expect(page.locator(".as-paper-card")).to_have_count(2)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            expect(page.get_by_role("button", name="继续完善结果", exact=True)).to_be_visible()
            assert source_calls == {"en": 1, "zh": 1, "arxiv": 1}
            release_more.set()
            page.get_by_role("button", name="继续完善结果", exact=True).click()
            expect(page.locator(".as-paper-card")).to_have_count(4)
            expect(page.get_by_role("button", name="继续完善结果", exact=True)).to_have_count(0)
            assert source_calls == {"en": 1, "zh": 1, "arxiv": 2}
            assert probe_calls["en-early"] == probe_calls["zh-early"] == 1
            titles = page.locator(".as-paper-title").all_text_contents()
            assert all("软件工程" in title for title in titles[:2])

            # 中途停止后保留卡片；过期的续查游标应提示重搜，不能反复出现无效按钮。
            release_more.clear()
            page.get_by_role("button", name="搜索论文", exact=True).click()
            expect(page.locator(".as-paper-card").first).to_be_visible()
            page.get_by_role("button", name="停止等待", exact=True).click()
            expect(page.get_by_role("button", name="继续完善结果", exact=True)).to_be_visible()
            session = list(tool._pipeline.sessions.values())[-1]
            for _ in range(100):
                if not session.active:
                    break
                time.sleep(0.01)
            assert not session.active
            session.expires = 0
            page.get_by_role("button", name="继续完善结果", exact=True).click()
            expect(page.get_by_role("alert")).to_contain_text("搜索记录已过期")
            expect(page.get_by_role("button", name="继续完善结果", exact=True)).to_have_count(0)
            assert page.locator(".as-paper-card").count() > 0
            assert not errors, errors
            browser.close()
            print(json.dumps({"browser": "Edge", "checks": ["results visible before stream ends", "deadline retains results", "resume without repeating completed sources/checks", "Chinese priority", "stop cancels backend work", "expired continuation", "mobile layout"], "page_errors": errors}), flush=True)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()


if __name__ == "__main__":
    main()
