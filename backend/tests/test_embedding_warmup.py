import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor

from backend.rag.embedder import Embedder


def test_concurrent_embedding_calls_construct_local_model_once(monkeypatch):
    calls = 0

    class FakeEncoded:
        def tolist(self):
            return [[0.1, 0.2, 0.3]]

    class FakeSentenceTransformer:
        def __init__(self, model_name):
            nonlocal calls
            calls += 1
            time.sleep(0.05)

        def encode(self, texts, normalize_embeddings=True):
            assert normalize_embeddings is True
            return FakeEncoded()

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )

    embedder = Embedder()
    embedder.provider = "local"
    with ThreadPoolExecutor(max_workers=10) as pool:
        vectors = list(pool.map(embedder.embed_one, [f"文本-{i}" for i in range(10)]))

    assert calls == 1
    assert vectors == [[0.1, 0.2, 0.3]] * 10
