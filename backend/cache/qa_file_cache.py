"""Redis 问题—答案文件缓存。

启动时只连接 Redis，不预热。首次生成成功后把回答写入统一 JSON 文件，
并在 Redis 中记录问题到分类的映射。再次遇到同一问题则直接读文件返回。
服务停止时删除这些运行时缓存。Redis 不可用时视为未命中，继续原有问答流程。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backend.config import Settings, settings

logger = logging.getLogger(__name__)

AnswerKind = Literal["preset", "generated"]
_STORE_SECTIONS: tuple[AnswerKind, ...] = ("preset", "generated")
_ANSWERS_FILENAME = "answers.json"


@dataclass(frozen=True)
class CachedAnswer:
    """从统一答案文件读取到的回答。"""

    answer: str
    relative_path: str
    kind: AnswerKind


class QAFileCache:
    """Redis 映射与统一答案文件读写服务。"""

    def __init__(self, config: Settings) -> None:
        self.config = config
        self.client = None
        self.status = "disabled" if not config.qa_cache_enabled else "unavailable"
        self._file_lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.config.qa_cache_enabled and self.client is not None)

    def _key(self, question: str) -> str:
        return f"{self.config.qa_cache_prefix}{question.strip()}"

    @staticmethod
    def _key_hash(question: str) -> str:
        return hashlib.sha256(question.strip().encode("utf-8")).hexdigest()[:16]

    def _answers_path(self) -> Path:
        """解析统一答案文件路径，并阻止写出答案根目录。"""
        configured = getattr(self.config, "qa_answers_file", None)
        candidate = Path(configured) if configured else (self.config.qa_answer_dir / _ANSWERS_FILENAME)
        if not candidate.is_absolute():
            candidate = self.config.qa_answer_dir / candidate

        root = self.config.qa_answer_dir.resolve()
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError("答案文件路径超出答案根目录") from exc
        return resolved

    @staticmethod
    def _empty_store() -> dict[str, dict[str, str]]:
        return {"preset": {}, "generated": {}}

    def _normalize_store(self, raw: object) -> dict[str, dict[str, str]]:
        store = self._empty_store()
        if not isinstance(raw, dict):
            return store

        for kind in _STORE_SECTIONS:
            section = raw.get(kind)
            if isinstance(section, dict):
                store[kind] = {
                    question.strip(): answer.strip()
                    for question, answer in section.items()
                    if isinstance(question, str)
                    and question.strip()
                    and isinstance(answer, str)
                    and answer.strip()
                }
        return store

    def _read_store(self) -> dict[str, dict[str, str]]:
        path = self._answers_path()
        if not path.is_file():
            return self._empty_store()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return self._normalize_store(raw)

    def _write_store(self, store: dict[str, dict[str, str]]) -> None:
        path = self._answers_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(store, ensure_ascii=False, indent=2) + "\n"
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)

    async def connect(self) -> None:
        """连接 Redis；依赖缺失或 Redis 不可用时安全降级。"""
        if not self.config.qa_cache_enabled:
            self.status = "disabled"
            return
        try:
            import redis.asyncio as redis
        except ImportError:
            logger.warning("qa_cache event=bypass reason=redis_dependency_missing")
            self.status = "unavailable"
            return

        try:
            self.client = redis.Redis.from_url(
                self.config.redis_url,
                decode_responses=True,
            )
            await self.client.ping()
            self.status = "ready"
            logger.info("qa_cache event=connected")
            print("[QACache] connected")
        except Exception as exc:
            logger.warning(
                "qa_cache event=bypass reason=redis_unavailable error_type=%s",
                type(exc).__name__,
            )
            print(f"[QACache] bypass reason=redis_unavailable error_type={type(exc).__name__}")
            self.status = "unavailable"
            self.client = None

    async def close(self) -> None:
        """停止服务时清空运行时缓存，再释放 Redis 连接。"""
        await self.clear_runtime_cache()
        if self.client is None:
            if self.config.qa_cache_enabled:
                self.status = "unavailable"
            return
        try:
            await self.client.aclose()
        except Exception as exc:
            logger.warning("qa_cache event=close_failed error_type=%s", type(exc).__name__)
        finally:
            self.client = None
            if self.config.qa_cache_enabled:
                self.status = "unavailable"

    async def clear_runtime_cache(self) -> None:
        """删除 Redis 问答键，并清空 answers.json 中的 generated 段。"""
        deleted = 0
        if self.client is not None:
            try:
                keys = await self._list_cache_keys()
                if keys:
                    await self.client.delete(*keys)
                    deleted = len(keys)
            except Exception as exc:
                logger.warning(
                    "qa_cache event=clear_redis_failed error_type=%s",
                    type(exc).__name__,
                )
        try:
            async with self._file_lock:
                store = await asyncio.to_thread(self._read_store)
                store["generated"] = {}
                await asyncio.to_thread(self._write_store, store)
        except Exception as exc:
            logger.warning(
                "qa_cache event=clear_file_failed error_type=%s",
                type(exc).__name__,
            )
            print(f"[QACache] clear_failed error_type={type(exc).__name__}")
            return

        logger.info("qa_cache event=cleared redis_keys=%s", deleted)
        print(f"[QACache] cleared redis_keys={deleted}")

    async def _list_cache_keys(self) -> list[str]:
        pattern = f"{self.config.qa_cache_prefix}*"
        scan_iter = getattr(self.client, "scan_iter", None)
        if callable(scan_iter):
            return [key async for key in scan_iter(match=pattern)]
        keys = await self.client.keys(pattern)
        return list(keys or [])

    async def get_answer(self, question: str) -> CachedAnswer | None:
        """根据问题读取 Redis 分类映射和统一答案文件。"""
        normalized = (question or "").strip()
        if not normalized:
            return None
        if not self.enabled:
            logger.info("qa_cache event=bypass reason=%s", self.status)
            print(f"[QACache] bypass status={self.status}")
            return None

        try:
            kind = await self.client.get(self._key(normalized))
            if not kind:
                logger.info(
                    "qa_cache event=miss key_hash=%s",
                    self._key_hash(normalized),
                )
                print(f"[QACache] MISS question={normalized}")
                return None

            if kind not in _STORE_SECTIONS:
                logger.warning(
                    "qa_cache event=stale_mapping key_hash=%s reason=invalid_kind",
                    self._key_hash(normalized),
                )
                await self._delete_mapping(normalized)
                return None

            try:
                store = await asyncio.to_thread(self._read_store)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                logger.warning(
                    "qa_cache event=stale_mapping key_hash=%s reason=file_unreadable",
                    self._key_hash(normalized),
                )
                await self._delete_mapping(normalized)
                return None

            answer = store.get(kind, {}).get(normalized, "")
            if not answer:
                logger.warning(
                    "qa_cache event=stale_mapping key_hash=%s reason=missing_entry",
                    self._key_hash(normalized),
                )
                await self._delete_mapping(normalized)
                return None

            logger.info(
                "qa_cache event=hit key_hash=%s kind=%s",
                self._key_hash(normalized),
                kind,
            )
            print(f"[QACache] HIT kind={kind} question={normalized}")
            return CachedAnswer(
                answer=answer,
                relative_path=_ANSWERS_FILENAME,
                kind=kind,
            )
        except Exception as exc:
            logger.warning(
                "qa_cache event=bypass reason=redis_read_failed error_type=%s",
                type(exc).__name__,
            )
            return None

    async def save_generated_answer(self, question: str, answer: str) -> str | None:
        """将动态回答写入统一答案文件的 generated 段，再建立 Redis 映射。"""
        normalized = (question or "").strip()
        content = (answer or "").strip()
        if not normalized or not content or not self.enabled:
            return None

        try:
            async with self._file_lock:
                store = await asyncio.to_thread(self._read_store)
                store["generated"][normalized] = content
                await asyncio.to_thread(self._write_store, store)
            await self._set_mapping(normalized, "generated")
            logger.info(
                "qa_cache event=write key_hash=%s kind=generated",
                self._key_hash(normalized),
            )
            return _ANSWERS_FILENAME
        except Exception as exc:
            logger.warning(
                "qa_cache event=write_failed key_hash=%s error_type=%s",
                self._key_hash(normalized),
                type(exc).__name__,
            )
            return None

    async def _set_mapping(self, question: str, kind: AnswerKind) -> None:
        if self.client is None:
            return
        ttl = self.config.qa_cache_ttl_seconds
        if ttl > 0:
            await self.client.set(self._key(question), kind, ex=ttl)
        else:
            await self.client.set(self._key(question), kind)

    async def _delete_mapping(self, question: str) -> None:
        if self.client is None:
            return
        try:
            await self.client.delete(self._key(question))
        except Exception:
            pass


qa_cache = QAFileCache(settings)
