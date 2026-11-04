from typing import Annotated
from uuid import UUID

from langchain_core.tools import BaseTool, tool
from pydantic import Field

from embeddings import embed_texts
from vector_store import search_chunks


def create_search_tool(knowledge_base_id: UUID) -> BaseTool:
    """为当前知识库创建检索工具；知识库 ID 由程序固定，不作为模型参数。"""
    @tool
    def search_knowledge_base(
        query: Annotated[str, Field(min_length=1, max_length=4000)],
        top_k: Annotated[int, Field(ge=1, le=20)] = 3,
    ) -> list[dict]:
        """检索当前知识库的相关原文。回答知识库问题时使用，可更换关键词再次检索。

        Args:
            query: 需要查找的问题或关键词。
            top_k: 最多返回的片段数量，默认 3。
        """
        query_vector = embed_texts([query])[0]
        hits = search_chunks(knowledge_base_id, query_vector, top_k)
        # 工具结果会传回模型，将 UUID 转为可序列化的字符串。
        return [
            {
                **hit,
                "document_id": str(hit["document_id"]),
                "source_id": f"{hit['document_id']}:{hit['chunk_index']}",
            }
            for hit in hits
        ]

    return search_knowledge_base
