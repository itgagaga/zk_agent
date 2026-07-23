"""Embedding 模型封装。

支持本地 sentence-transformers / bge 模型，也支持在线 Embedding API。
"""
from __future__ import annotations

from typing import Any

from backend.config import settings


class Embedder:
    """文本向量化封装。"""

    def __init__(self) -> None:
        self.provider = settings.embedding_provider
        self.model_name = settings.embedding_model
        self._model: Any = None

    def _load_local(self) -> Any:
        """加载本地 sentence-transformers 模型。"""
        if self._model is not None:
            return self._model
        import os

        # 模型已下载到本地缓存，设置离线模式避免 huggingface_hub httpx 客户端 bug
        os.environ["HF_HUB_OFFLINE"] = "1"
        # 延迟导入，避免启动慢
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """生成文本向量。"""
        if self.provider == "local":
            model = self._load_local()
            return model.encode(texts, normalize_embeddings=True).tolist()
        # TODO: 支持 openai / dashscope
        raise NotImplementedError(f"Embedding provider {self.provider} 未实现")

    def embed_one(self, text: str) -> list[float]:
        """生成单条文本向量。"""
        return self.embed([text])[0]


# 全局单例
_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
