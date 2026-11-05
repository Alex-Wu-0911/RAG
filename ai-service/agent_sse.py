"""把 Agent Python 事件编码成 SSE，并在客户端断开时关闭上游。"""

import asyncio
import json
import logging
from contextlib import suppress

import anyio
from fastapi import Request
from fastapi.responses import StreamingResponse
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langgraph.errors import GraphRecursionError
from openai import APIConnectionError, APIStatusError

from agent_service import stream_agent
from reranking import RerankError

log = logging.getLogger(__name__)


class AgentStreamingResponse(StreamingResponse):
    """写响应失败时也关闭生成器，而不等垃圾回收才释放模型流。"""

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()


def encode_sse(event: dict) -> str:
    # JSON 会转义正文中的换行，空行只用于分隔 SSE 事件。
    data = json.dumps(event["data"], ensure_ascii=False, separators=(",", ":"))
    return f"event: {event['event']}\ndata: {data}\n\n"


def error_data(error: Exception) -> dict:
    if isinstance(error, RerankError):
        return {"code": "RERANK_ERROR", "message": "重排调用失败，请检查服务额度和配置"}
    if isinstance(error, (ToolCallLimitExceededError, GraphRecursionError)):
        return {"code": "AGENT_LIMIT", "message": "Agent 达到执行次数上限，请缩小问题范围"}
    if isinstance(error, APIStatusError):
        return {"code": "MODEL_API_ERROR", "message": f"模型 API 返回 {error.status_code}，请检查额度和配置"}
    if isinstance(error, APIConnectionError):
        return {"code": "MODEL_CONNECTION_ERROR", "message": "无法连接模型 API"}
    if isinstance(error, RuntimeError):
        return {"code": "AGENT_ERROR", "message": "Agent 未能完成回答，请重试"}
    return {"code": "INTERNAL_ERROR", "message": "服务执行失败，请稍后重试"}


async def agent_sse_events(request: Request, question: str):
    pending = None
    stream = stream_agent(question)
    try:
        try:
            while not await request.is_disconnected():
                # 等待模型/工具时也检查断连，不能只在收到下一段文本后检查。
                pending = asyncio.create_task(anext(stream))
                while not pending.done():
                    await asyncio.wait({pending}, timeout=0.25)
                    if await request.is_disconnected():
                        return
                try:
                    event = pending.result()
                except StopAsyncIteration:
                    return
                pending = None
                yield encode_sse(event)
                if event["event"] == "done":
                    return
        finally:
            # 清理不能被 Starlette 的断连取消作用域中途打断。
            with anyio.CancelScope(shield=True):
                if pending is not None:
                    pending.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await pending
                await stream.aclose()
    except asyncio.CancelledError:
        # 服务器或响应任务被取消时，不能再向已断开的客户端发送 error。
        raise
    except Exception as error:
        log.exception("Agent SSE 执行失败")
        if not await request.is_disconnected():
            yield encode_sse({"event": "error", "data": error_data(error)})
