import os
from pathlib import Path

import cohere
from cohere.core.api_error import ApiError
from dotenv import load_dotenv
from httpx import RequestError
from langchain_cohere import CohereRerank
from langchain_core.documents import Document

load_dotenv(Path(__file__).with_name(".env"))
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "false").lower() == "true"
RERANK_MODEL = os.getenv("RERANK_MODEL", "rerank-v5.0-fast")


class RerankError(RuntimeError):
    """重排服务调用失败，不用虚构分数代替真实结果。"""


def rerank_chunks(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    """通过 LangChain 调用 Cohere，保留原文、引用元数据及向量相似度。"""
    if not chunks or not RERANK_ENABLED:
        return chunks[:top_k]

    documents = [
        Document(
            page_content=chunk["content"],
            metadata={key: value for key, value in chunk.items() if key != "content"},
        )
        for chunk in chunks
    ]
    try:
        with cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"], timeout=20) as client:
            compressor = CohereRerank(model=RERANK_MODEL, top_n=top_k, client=client)
            ranked = compressor.compress_documents(documents, query)
    except (ApiError, RequestError) as error:
        raise RerankError("Cohere 重排 API 调用失败，请检查额度、网络和模型权限") from error

    result = []
    for document in ranked:
        metadata = dict(document.metadata)
        score = metadata.pop("relevance_score")
        result.append({**metadata, "content": document.page_content, "rerank_score": score})
    return result

