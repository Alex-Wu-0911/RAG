from typing import Annotated
from uuid import UUID

from langchain_core.tools import BaseTool, tool
from pydantic import Field

from embeddings import embed_texts
from knowledge_base_repository import find_similar_knowledge_bases
from vector_store import search_chunks
from retrieval_budget import RetrievalBudget
from reranking import RERANK_ENABLED, rerank_chunks


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
        top_k: 重排后最多返回的片段数量，默认 3。
    """
    query_vector = embed_texts([query])[0]
    candidate_count = max(20, top_k) if RERANK_ENABLED else top_k
    hits = search_chunks(knowledge_base_id, query_vector, candidate_count)
    hits = rerank_chunks(query, hits, top_k)
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



def create_agent_tools(budget: RetrievalBudget) -> list[BaseTool]:
    """每个请求创建一组工具，候选库和文档片段共用预算与去重记录。"""
    @tool("search_knowledge_bases")
    def search_candidates(
        query: Annotated[str, Field(min_length=1, max_length=4000)],
        limit: Annotated[int, Field(ge=1, le=5)] = 3,
    ) -> str:
        """语义搜索候选知识库。返回 status 和 items；重复候选不再返回。"""
        if budget.exhausted:
            return budget.pack([], key="id")
        items = search_knowledge_bases.invoke({"query": query, "limit": limit})
        return budget.pack(items, key="id")

    @tool("search_knowledge_base")
    def search_documents(
        knowledge_base_id: UUID,
        query: Annotated[str, Field(min_length=1, max_length=4000)],
        top_k: Annotated[int, Field(ge=1, le=20)] = 3,
    ) -> str:
        """使用候选中的真实 ID 检索原文，返回 status 和未发送过的完整片段 items。"""
        if budget.exhausted:
            return budget.pack([], key="source_id")
        items = search_knowledge_base.invoke({
            "knowledge_base_id": knowledge_base_id, "query": query, "top_k": top_k,
        })
        return budget.pack(items, key="source_id")

    return [search_candidates, search_documents]

