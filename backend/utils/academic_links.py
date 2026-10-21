"""在返回论文前验证最终落地页，限制并发、响应读取和总等待时间。"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx


class AcademicLinkChecker:
    def __init__(self, *, concurrency: int = 8, url_timeout: float = 4, budget: float = 12) -> None:
        self.concurrency = concurrency
        self.url_timeout = url_timeout
        self.budget = budget
        self._public_hosts: dict[str, bool] = {}
        self._unconfirmed: set[str] = set()
        self._connection_failures: dict[str, int] = {}

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.url_timeout), follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ZHKUAcademicSearch/1.0)",
                     "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8"},
            limits=httpx.Limits(max_connections=self.concurrency),
        )

    @staticmethod
    def url_for(paper: dict[str, Any]) -> str:
        url = paper.get("url")
        if isinstance(url, str) and url:
            return url
        doi = paper.get("doi")
        return f"https://doi.org/{doi}" if isinstance(doi, str) and doi else ""

    async def _public_url(self, url: str) -> bool:
        """论文元数据和重定向均不允许指向本机或内网地址。"""
        try:
            parsed = urlsplit(url)
            host = parsed.hostname
            if (parsed.scheme not in {"http", "https"} or not host
                    or parsed.username is not None or parsed.password is not None
                    or parsed.port not in {None, 80, 443}):
                return False
            host = host.rstrip(".").lower()
            if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
                return False
            if host not in self._public_hosts:
                try:
                    addresses = [ipaddress.ip_address(host)]
                except ValueError:
                    records = await asyncio.get_running_loop().getaddrinfo(
                        host, None, type=socket.SOCK_STREAM,
                    )
                    addresses = [ipaddress.ip_address(record[4][0]) for record in records]
                self._public_hosts[host] = bool(addresses) and all(a.is_global for a in addresses)
            return self._public_hosts[host]
        except (ValueError, OSError):
            return False

    async def _probe(self, client: httpx.AsyncClient, url: str) -> str | None:
        original = url
        host = ""
        try:
            async with asyncio.timeout(self.url_timeout):
                visited = set()
                for _ in range(6):
                    if url in visited or not await self._public_url(url):
                        return None
                    host = urlsplit(url).hostname or ""
                    if self._connection_failures.get(host, 0) >= 2:
                        return None
                    visited.add(url)
                    async with client.stream("GET", url) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                return None
                            url = urljoin(str(response.url), location)
                            continue
                        if not 200 <= response.status_code < 300:
                            return None
                        # 仅收到状态码不足以证明可读取；读到首个内容块即关闭连接。
                        async for chunk in response.aiter_bytes():
                            if chunk:
                                return str(response.url)
                        return None
        except (httpx.TimeoutException, TimeoutError):
            self._unconfirmed.add(original)
            return None
        except httpx.ConnectError:
            self._connection_failures[host] = self._connection_failures.get(host, 0) + 1
            return None
        except (httpx.HTTPError, ValueError, OSError):
            return None
        return None

    async def check(self, client: httpx.AsyncClient, url: str) -> dict[str, Any]:
        final_url = await self._probe(client, url)
        return {"status": "available" if final_url else "unconfirmed" if url in self._unconfirmed else "unavailable",
                "url": final_url, "checked_at": datetime.now(timezone.utc).isoformat()}

    @staticmethod
    def verified(paper: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
        return {**paper, "url": outcome["url"], "link_verified": True, "link_checked_at": outcome["checked_at"]}

    @classmethod
    def summary(cls, ranked, checks, items, timed_out=False):
        outcomes = [checks.get(cls.url_for(p)) for p in ranked]
        checked = sum(o is not None for o in outcomes)
        return {"candidates": len(ranked), "checked": checked,
                "rejected": sum(o is not None and o["status"] == "unavailable" for o in outcomes),
                "unconfirmed": sum(o is not None and o["status"] == "unconfirmed" for o in outcomes),
                "returned": len(items), "unchecked": len(ranked) - checked, "timed_out": timed_out}

    async def filter(self, ranked: list[dict[str, Any]], top_k: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        checks = {}
        pending = {}
        timed_out = False
        deadline = asyncio.get_running_loop().time() + self.budget
        urls = list(dict.fromkeys(self.url_for(p) for p in ranked))
        position = 0
        async with self.client() as client:
            try:
                while True:
                    available = [i for i, p in enumerate(ranked) if checks.get(self.url_for(p), {}).get("status") == "available"]
                    if len(available) >= top_k and all(self.url_for(p) in checks for p in ranked[:available[top_k - 1]]):
                        break
                    while position < len(urls) and len(pending) < self.concurrency:
                        url = urls[position]
                        position += 1
                        pending[asyncio.create_task(self.check(client, url))] = url
                    if not pending:
                        break
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        timed_out = True
                        break
                    done, _ = await asyncio.wait(pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
                    if not done:
                        timed_out = True
                        break
                    for task in done:
                        checks[pending.pop(task)] = task.result()
            finally:
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
        items = [self.verified(p, checks[self.url_for(p)]) for p in ranked if checks.get(self.url_for(p), {}).get("status") == "available"][:top_k]
        return items, self.summary(ranked, checks, items, timed_out)


async def check_paper_links(ranked: list[dict[str, Any]], top_k: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return await AcademicLinkChecker().filter(ranked, top_k)
