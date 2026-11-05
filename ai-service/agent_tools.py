from typing import Annotated
from uuid import UUID

from langchain_core.tools import tool
from pydantic import Field

from embeddings import embed_texts
from knowledge_base_repository import find_similar_knowledge_bases
from vector_store import search_chunks


@tool
def search_knowledge_base(
    knowledge_base_id: UUID,
    query: Annotated[str, Field(min_length=1, max_length=4000)],
    top_k: Annotated[int, Field(ge=1, le=20)] = 3,
) -> list[dict]:
    """在指定知识库中检索相关原文；知识库 ID 必须来自 search_knowledge_bases 的候选结果。

    Args:
        knowledge_base_id: 从语义搜索候选知识库中选择的真实 ID。
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


@tool
def search_knowledge_bases(
    query: Annotated[str, Field(min_length=1, max_length=4000)],
    limit: Annotated[int, Field(ge=1, le=5)] = 3,
) -> list[dict]:
    """按问题的语义搜索候选知识库，返回真实 ID、名称、简介和相似度，不返回文档内容。

    Args:
        query: 用户问题或希望查找的主题。
        limit: 最多返回的候选知识库数量，默认 3，上限 5。
    """
    query_vector = embed_texts([query])[0]
    knowledge_bases = find_similar_knowledge_bases(query_vector, limit)
    return [{**item, "id": str(item["id"])} for item in knowledge_bases]

