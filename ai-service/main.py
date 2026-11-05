from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from minio.error import S3Error

from storage import read_object
from text_processing import split_text
from embeddings import EMBEDDING_MODEL, embed_texts
from openai import APIConnectionError, APIStatusError
from document_repository import DocumentBusyError, find_document, update_document_status
from vector_store import save_document_chunks, search_chunks
from generation import generate_answer
from agent_service import run_agent
from agent_sse import AgentStreamingResponse, agent_sse_events
from reranking import RerankError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langgraph.errors import GraphRecursionError

# 类似 Java 请求 DTO：定义字段类型，由框架解析并校验 JSON。
class ChatRequest(BaseModel):
    knowledge_base_id: UUID
    question: str = Field(min_length=1, max_length=4000, description="用户问题")
    top_k: int = Field(default=3, ge=1, le=20, description="检索的参考片段数量")

# 创建 FastAPI 应用，下面通过 @app.get、@app.post 注册接口。
app = FastAPI(title="RAG AI Service", version="0.1.0")


@app.get("/health", summary="检查 Python 服务是否运行")
def health() -> dict[str, str]:
    """返回进程健康状态，本步不检查数据库或大模型。"""
    return {"status": "UP"}


class DocumentReadRequest(BaseModel):
    storage_key: str = Field(min_length=1, description="bucket 内的完整对象 Key，不是原始文件名")


class DocumentPreviewResponse(BaseModel):
    storage_key: str
    size_bytes: int
    text_length: int
    preview: str


@app.post("/documents/read", summary="读取对象存储中的 Markdown 并返回文本预览")
def read_document(request: DocumentReadRequest) -> DocumentPreviewResponse:
    """接收完整 storage_key，返回大小和前 1000 个字符；暂不解析 PDF 或生成向量。"""
    content, text = load_markdown(request.storage_key)
    return DocumentPreviewResponse(
        storage_key=request.storage_key,
        size_bytes=len(content),
        text_length=len(text),
        preview=text[:1000],
    )


def load_markdown(storage_key: str) -> tuple[bytes, str]:
    if not storage_key.lower().endswith(".md"):
        raise HTTPException(status_code=415, detail="本步仅支持 Markdown 文件")
    try:
        content = read_object(storage_key)
    except S3Error as error:
        if error.code == "NoSuchKey":
            raise HTTPException(status_code=404, detail="文件不存在") from error
        raise HTTPException(status_code=502, detail="对象存储读取失败") from error
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=400, detail="请使用 UTF-8 编码的 Markdown 文件") from error
    return content, text


class DocumentChunksRequest(BaseModel):
    storage_key: str = Field(min_length=1, description="Markdown 的完整对象 Key")
    chunk_size: int = Field(default=500, gt=0, le=10000, description="每块字符数上限，不是 token 数")
    chunk_overlap: int = Field(default=50, ge=0, description="相邻片段目标重叠字符数，必须小于 chunk_size")


class TextChunk(BaseModel):
    index: int
    content: str
    length: int


class DocumentChunksResponse(BaseModel):
    storage_key: str
    chunk_size: int
    chunk_overlap: int
    total: int
    chunks: list[TextChunk]


@app.post("/documents/chunks", summary="预览 Markdown 分块，不调用模型或保存向量")
def preview_chunks(request: DocumentChunksRequest) -> DocumentChunksResponse:
    """读取对象并按字符分块，返回全部片段；序号从 0 开始。"""
    if request.chunk_overlap >= request.chunk_size:
        raise HTTPException(status_code=422, detail="chunk_overlap 必须小于 chunk_size")
    _, text = load_markdown(request.storage_key)
    parts = split_text(text, request.chunk_size, request.chunk_overlap)
    chunks = [TextChunk(index=index, content=part, length=len(part))
              for index, part in enumerate(parts)]
    return DocumentChunksResponse(
        storage_key=request.storage_key,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
        total=len(chunks),
        chunks=chunks,
    )


class DocumentEmbeddingsResponse(BaseModel):
    storage_key: str
    model: str
    chunk_count: int
    vector_count: int
    dimensions: int
    sample_vector: list[float]


@app.post("/documents/embeddings", summary="调用真实 Embedding 模型生成文档片段向量")
def preview_embeddings(request: DocumentReadRequest) -> DocumentEmbeddingsResponse:
    """使用默认 500/50 分块，返回数量、维度及首个向量的前 8 个数值，不保存向量。"""
    _, text = load_markdown(request.storage_key)
    parts = split_text(text)
    if not parts:
        raise HTTPException(status_code=400, detail="文档没有可生成向量的文本")
    try:
        vectors = embed_texts(parts)
    except APIStatusError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Embedding API 返回 {error.status_code}，请检查 Key、额度与模型权限",
        ) from error
    except APIConnectionError as error:
        raise HTTPException(status_code=502, detail="无法连接 Embedding API") from error
    return DocumentEmbeddingsResponse(
        storage_key=request.storage_key,
        model=EMBEDDING_MODEL,
        chunk_count=len(parts),
        vector_count=len(vectors),
        dimensions=len(vectors[0]),
        sample_vector=vectors[0][:8],
    )


class DocumentProcessResponse(BaseModel):
    document_id: UUID
    status: str
    chunk_count: int


@app.post("/documents/{document_id}/process", summary="处理 Markdown 文档并将文本块与真实向量入库")
def process_document(document_id: UUID) -> DocumentProcessResponse:
    """按文档 ID 同步完成读取、分块、Embedding 和入库；重复处理替换旧分块。"""
    document = find_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    try:
        update_document_status(document_id, "PROCESSING")
    except DocumentBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    try:
        _, text = load_markdown(document["storage_key"])
        chunks = split_text(text)
        if not chunks:
            raise HTTPException(status_code=400, detail="文档没有可生成向量的文本")
        vectors = embed_texts(chunks)
        count = save_document_chunks(
            document_id, document["knowledge_base_id"], chunks, vectors
        )
    except Exception as error:
        # 失败必须记录状态；仍将原错误交给框架处理，不返回虚假的成功结果。
        try:
            update_document_status(document_id, "FAILED")
        except DocumentBusyError as busy:
            raise HTTPException(status_code=409, detail=str(busy)) from busy
        if isinstance(error, APIStatusError):
            raise HTTPException(
                status_code=502,
                detail=f"Embedding API 返回 {error.status_code}，请检查 Key、额度与模型权限",
            ) from error
        if isinstance(error, APIConnectionError):
            raise HTTPException(status_code=502, detail="无法连接 Embedding API") from error
        raise

    return DocumentProcessResponse(
        document_id=document_id, status="READY", chunk_count=count
    )


class SearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000, description="需要检索的问题")
    top_k: int = Field(default=3, ge=1, le=20, description="最多返回的文本块数量")


class SearchHit(BaseModel):
    document_id: UUID
    filename: str
    chunk_index: int
    content: str
    similarity: float
    rerank_score: float | None = None


class SearchResponse(BaseModel):
    knowledge_base_id: UUID
    items: list[SearchHit]


@app.post("/knowledge-bases/{knowledge_base_id}/search", summary="根据问题检索知识库中最相关的文本块")
def search_knowledge_base(knowledge_base_id: UUID, request: SearchRequest) -> SearchResponse:
    """真实调用 Embedding，再按余弦相似度返回最多 top_k 个片段，不生成回答。"""
    try:
        query_vector = embed_texts([request.question])[0]
    except APIStatusError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Embedding API 返回 {error.status_code}，请检查 Key、额度与模型权限",
        ) from error
    except APIConnectionError as error:
        raise HTTPException(status_code=502, detail="无法连接 Embedding API") from error

    items = search_chunks(knowledge_base_id, query_vector, request.top_k)
    return SearchResponse(knowledge_base_id=knowledge_base_id, items=items)


class ChatSource(SearchHit):
    source_id: int


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]


@app.post("/chat", summary="检索知识库并调用聊天模型生成带来源编号的回答")
def chat(request: ChatRequest) -> ChatResponse:
    """先检索再生成；sources 是传给模型的参考片段，编号与回答中的 [1] 等对应。"""
    try:
        query_vector = embed_texts([request.question])[0]
        hits = search_chunks(request.knowledge_base_id, query_vector, request.top_k)
        sources = [ChatSource(source_id=index, **hit) for index, hit in enumerate(hits, start=1)]
        if not sources:
            return ChatResponse(answer="该知识库没有可检索的文档片段，请先上传并处理文档。", sources=[])
        answer = generate_answer(
            request.question, [source.model_dump(mode="json") for source in sources]
        )
    except APIStatusError as error:
        raise HTTPException(
            status_code=502,
            detail=f"模型 API 返回 {error.status_code}，请检查 Key、额度与模型权限",
        ) from error
    except APIConnectionError as error:
        raise HTTPException(status_code=502, detail="无法连接模型 API") from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail="聊天模型没有返回完整回答，请重试") from error
    return ChatResponse(answer=answer, sources=sources)


class AgentChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000, description="交给 Agent 的问题")


class AgentSource(SearchHit):
    source_id: str


class AgentContextUsage(BaseModel):
    token_budget: int
    used_tokens: int
    duplicate_items_skipped: int
    budget_exhausted: bool


class AgentToolCall(BaseModel):
    name: str
    args: dict
    result_count: int
    status: str


class AgentChatResponse(BaseModel):
    answer: str
    tool_calls: list[AgentToolCall]
    context_usage: AgentContextUsage
    sources: list[AgentSource]


@app.post("/agent/chat", summary="由 Agent 自动选择知识库并检索回答，返回实际工具调用记录")
def agent_chat(request: AgentChatRequest) -> AgentChatResponse:
    """单轮 Agent 问答，只需问题；先语义搜索候选库，最多调用工具 4 次。"""
    try:
        result = run_agent(request.question)
    except RerankError as error:
        raise HTTPException(status_code=502, detail="Cohere 重排调用失败，请检查额度、网络和模型权限") from error
    except (ToolCallLimitExceededError, GraphRecursionError) as error:
        raise HTTPException(status_code=502, detail="Agent 达到执行次数上限，请缩小问题范围后重试") from error
    except APIStatusError as error:
        raise HTTPException(
            status_code=502,
            detail=f"模型 API 返回 {error.status_code}，请检查 Key、额度与模型权限",
        ) from error
    except APIConnectionError as error:
        raise HTTPException(status_code=502, detail="无法连接模型 API") from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail="Agent 没有生成完整回答，请重试") from error
    return AgentChatResponse(**result)


@app.post(
    "/agent/chat/stream", summary="流式返回 Agent 工具事件、回答片段和最终结果",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def agent_chat_stream(request: AgentChatRequest, http_request: Request) -> StreamingResponse:
    """POST 提交问题；SSE 逐条返回，done 表示成功结束，error 表示流内执行失败。"""
    return AgentStreamingResponse(
        agent_sse_events(http_request, request.question),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )




