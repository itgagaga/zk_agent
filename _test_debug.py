"""调试：检查 RAG 检索和工具查询的原始结果。"""
import asyncio
from backend.rag.vector_store import get_vector_store
from backend.tools.download_tool import DownloadTool
from backend.tools.contact_tool import ContactTool
from backend.tools.major_tool import MajorTool


async def main():
    store = get_vector_store()

    # 1. 检查 RAG 检索（不过滤阈值）
    print("=" * 60)
    print("RAG 检索测试（原始结果）")
    print("=" * 60)
    for query in ["仲恺农业工程学院有几个校区", "学校有哪些教学机构", "2026年硕士研究生招生章程"]:
        hits = store.query(text=query, top_k=3)
        print(f"\n查询: {query}")
        print(f"  命中数: {len(hits)}")
        for h in hits:
            print(f"  - score={h.get('score', 0):.4f} title={h.get('title', '')[:30]} snippet={h.get('snippet', '')[:60]}")

    # 2. 检查工具查询
    print("\n" + "=" * 60)
    print("工具查询测试")
    print("=" * 60)

    for tool_cls in [DownloadTool, ContactTool, MajorTool]:
        tool = tool_cls()
        result = await tool.run("补办学生证申请表在哪里")
        print(f"\n{tool.name}: total={result.get('total', 0)}")
        for item in result.get("items", [])[:3]:
            print(f"  - {item.get('title', '')[:50]}")

    # 3. 检查 major_tool 对 "教学机构" 的查询
    major = MajorTool()
    result = await major.run("学校有哪些教学机构")
    print(f"\nmajor_search '教学机构': total={result.get('total', 0)}")
    for item in result.get("items", [])[:3]:
        print(f"  - {item.get('title', '')[:50]}")


if __name__ == "__main__":
    asyncio.run(main())
