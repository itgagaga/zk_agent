"""Read-only replay of the current curriculum chunks through retrieval/fusion."""
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.rag.contracts import Evidence
from backend.rag.evidence_fusion import EvidenceFusion
from backend.rag.retriever import RAGRetriever


def load_chunks():
    with sqlite3.connect("file:data/vector_store/chroma.sqlite3?mode=ro", uri=True) as conn:
        rows = conn.execute("""
            SELECT e.embedding_id, m.key, m.string_value, m.int_value
            FROM embeddings e JOIN embedding_metadata m ON e.id=m.id
            WHERE e.id IN (SELECT id FROM embedding_metadata WHERE key='user_id' AND int_value=2)
        """).fetchall()
    records = {}
    for chunk_id, key, value, integer in rows:
        records.setdefault(chunk_id, {})[key] = value if value is not None else integer
    return [
        {"chunk_id": chunk_id, "chunk_index": int(chunk_id.rsplit("_", 1)[1]),
         "title": meta.get("title"), "snippet": meta["chroma:document"], "score": 0.5,
         "url": "", "metadata": {k: v for k, v in meta.items() if k != "chroma:document"}}
        for chunk_id, meta in records.items() if meta.get("title") == "信计培养方案"
    ]


class SnapshotStore:
    def __init__(self, chunks):
        self.chunks = chunks

    def query(self, **kwargs):
        # Simulate a direct hit in the teaching schedule.
        hit = next(item for item in self.chunks if item["metadata"].get("chunk_role") == "child")
        return [{**hit, "score": 0.9}]

    def keyword_search(self, **kwargs):
        return []

    def get_chunks_by_parent_id(self, parent_id, **kwargs):
        return sorted(
            [item for item in self.chunks if item["metadata"].get("parent_id") == parent_id],
            key=lambda item: item["chunk_index"],
        )

    def count_documents(self, **kwargs):
        return len(self.chunks)

    def get_chunks_by_doc_id(self, doc_id, **kwargs):
        return sorted([item for item in self.chunks if item["metadata"].get("doc_id") == doc_id],
                      key=lambda item: item["chunk_index"])


async def main():
    retriever = RAGRetriever()
    chunks = load_chunks()
    retriever.store = SnapshotStore(chunks)
    hits = await retriever.search_user_documents("我是信计大三的学生，本学年我需要修什么课程", user_id=2)
    bundle = EvidenceFusion(max_items=100).fuse("信计课程", [Evidence.from_rag_hit(hit, retriever="user_docs") for hit in hits], retrievers=["user_docs"])
    context = "\n".join(item.snippet for item in bundle.evidences)
    print(json.dumps({"stored_chunks": len(chunks), "retrieved_sections": len(hits),
                      "fused_sections": len(bundle.evidences), "context_chars": len(context),
                      "has_database_course": "数据库原理与应用" in context,
                      "has_required_credit_breakdown": "其中必修24" in context,
                      "has_practice_table": "表四：实践教学平台" in context,
                      "has_credit_structure": "六、学时与学分" in context}, ensure_ascii=False))
    for item in bundle.evidences:
        print(item.chunk_id, len(item.snippet), item.metadata.get("section_title", ""))


if __name__ == "__main__":
    asyncio.run(main())
