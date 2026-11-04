from uuid import UUID

from fastapi import FastAPI
from pydantic import BaseModel, Field

# 类似 Java 请求 DTO：定义字段类型，由框架解析并校验 JSON。
class ChatRequest(BaseModel):
    knowledge_base_id: UUID
    question: str = Field(min_length=1, max_length=4000, description="用户问题")

# 创建应用实例，类似 Spring Boot 中承载接口的应用。
app = FastAPI(title="RAG AI Service", version="0.1.0")


@app.get("/health", summary="检查 Python 服务是否运行")
def health() -> dict[str, str]:
    """返回进程健康状态，本步不检查数据库或大模型。"""
    return {"status": "UP"}


@app.post("/chat", summary="接收问题并回显，暂不调用模型")
def chat(request: ChatRequest) -> ChatRequest:
    """学习请求体：校验 UUID 和问题长度，返回接收到的内容。"""
    return request
