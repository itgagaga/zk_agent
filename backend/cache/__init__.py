"""应用级缓存组件。"""

from backend.cache.qa_file_cache import CachedAnswer, QAFileCache, qa_cache

__all__ = ["CachedAnswer", "QAFileCache", "qa_cache"]
