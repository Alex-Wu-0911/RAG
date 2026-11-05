from typing import Annotated
from uuid import UUID

from langchain_core.tools import tool
from pydantic import Field

from embeddings import embed_texts
from knowledge_base_repository import find_all_knowledge_bases
from vector_store import search_chunks


@tool
def list_knowledge_bases() -> list[dict]:
    """列出知识库的真实 ID、名称和简介。按问题选择知识库前先查看列表，不要猜测 ID。"""
    return [
        {**knowledge_base, "id": str(knowledge_base["id"])}
        for knowledge_base in find_all_knowledge_bases()
    ]


@tool
def search_knowledge_base(
    knowledge_base_id: UUID,
    query: Annotated[str, Field(min_length=1, max_length=4000)],
    top_k: Annotated[int, Field(ge=1, le=20)] = 3,
) -> list[dict]:
    """在指定知识库中检索相关原文；知识库 ID 必须来自 list_knowledge_bases 的结果。

    Args:
        knowledge_base_id: 从知识库列表中选择的真实 ID。
        query: 需要查找的问题或关键词。
        top_k: 最多返回的片段数量，默认 3。
    """
    query_vector = embed_texts([query])[0]
    hits = search_chunks(knowledge_base_id, query_vector, top_k)
    return [
        {
            **hit,
            "document_id": str(hit["document_id"]),
            "source_id": f"{hit['document_id']}:{hit['chunk_index']}",
        }
        for hit in hits
    ]

