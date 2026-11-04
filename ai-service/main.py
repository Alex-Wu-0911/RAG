from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from minio.error import S3Error

from storage import read_object
from text_processing import split_text
from embeddings import EMBEDDING_MODEL, embed_texts
from openai import APIConnectionError, APIStatusError

# 类似 Java 请求 DTO：定义字段类型，由框架解析并校验 JSON。
class ChatRequest(BaseModel):
    knowledge_base_id: UUID
    question: str = Field(min_length=1, max_length=4000, description="用户问题")

# 创建 FastAPI 应用，下面通过 @app.get、@app.post 注册接口。
app = FastAPI(title="RAG AI Service", version="0.1.0")


@app.get("/health", summary="检查 Python 服务是否运行")
def health() -> dict[str, str]:
    """返回进程健康状态，本步不检查数据库或大模型。"""
    return {"status": "UP"}


@app.post("/chat", summary="接收问题并回显，暂不调用模型")
def chat(request: ChatRequest) -> ChatRequest:
    """学习请求体：校验 UUID 和问题长度，返回接收到的内容。"""
    return request


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
