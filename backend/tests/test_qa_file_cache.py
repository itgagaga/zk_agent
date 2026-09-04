import asyncio
import json
from types import SimpleNamespace

from backend.cache.qa_file_cache import QAFileCache


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.closed = False

    async def ping(self):
        return True

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value
        return True

    async def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)

    async def keys(self, pattern):
        prefix = str(pattern).rstrip("*")
        return [key for key in self.values if key.startswith(prefix)]

    async def aclose(self):
        self.closed = True


def _config(tmp_path, answers_file=None):
    return SimpleNamespace(
        qa_cache_enabled=True,
        qa_cache_prefix="qa:answer-file:",
        qa_cache_ttl_seconds=0,
        qa_answer_dir=tmp_path,
        qa_answers_file=answers_file or tmp_path / "answers.json",
        redis_url="redis://unused",
    )


def test_generated_answer_is_stored_in_shared_file(tmp_path):
    async def scenario():
        (tmp_path / "answers.json").write_text(
            json.dumps(
                {"preset": {"固定问题": "预设答案"}, "generated": {}},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cache = QAFileCache(_config(tmp_path))
        cache.client = FakeRedis()
        question = "测试问题"

        relative_path = await cache.save_generated_answer(question, "这是答案")

        assert relative_path == "answers.json"
        assert cache.client.values["qa:answer-file:测试问题"] == "generated"
        store = json.loads((tmp_path / "answers.json").read_text(encoding="utf-8"))
        assert store["preset"]["固定问题"] == "预设答案"
        assert store["generated"][question] == "这是答案"
        cached = await cache.get_answer(question)
        assert cached is not None
        assert cached.answer == "这是答案"
        assert cached.relative_path == "answers.json"
        assert cached.kind == "generated"

    asyncio.run(scenario())


def test_first_question_misses_until_generated_answer_is_saved(tmp_path):
    async def scenario():
        (tmp_path / "answers.json").write_text(
            json.dumps({"preset": {}, "generated": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
        cache = QAFileCache(_config(tmp_path))
        cache.client = FakeRedis()

        assert await cache.get_answer("你好") is None
        await cache.save_generated_answer("你好", "你好，我是校园助手")
        cached = await cache.get_answer("你好")
        assert cached is not None
        assert cached.kind == "generated"
        assert cached.answer == "你好，我是校园助手"

    asyncio.run(scenario())


def test_invalid_mapping_is_not_read(tmp_path):
    async def scenario():
        (tmp_path / "answers.json").write_text(
            json.dumps({"preset": {}, "generated": {}}, ensure_ascii=False),
            encoding="utf-8",
        )
        cache = QAFileCache(_config(tmp_path))
        cache.client = FakeRedis()
        cache.client.values["qa:answer-file:测试"] = "../outside.md"

        assert await cache.get_answer("测试") is None
        assert "qa:answer-file:测试" not in cache.client.values


def test_close_clears_redis_and_generated_answers(tmp_path):
    async def scenario():
        (tmp_path / "answers.json").write_text(
            json.dumps(
                {"preset": {"固定问题": "预设答案"}, "generated": {"你好": "缓存回答"}},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cache = QAFileCache(_config(tmp_path))
        redis = FakeRedis()
        cache.client = redis
        await cache.save_generated_answer("你好", "缓存回答")
        redis.values["qa:answer-file:旧预热"] = "preset"

        await cache.close()

        assert cache.client is None
        assert redis.closed is True
        assert redis.values == {}
        store = json.loads((tmp_path / "answers.json").read_text(encoding="utf-8"))
        assert store["preset"]["固定问题"] == "预设答案"
        assert store["generated"] == {}

    asyncio.run(scenario())

    asyncio.run(scenario())
