"""HTTP/ASGI 层测试，Agent 事件使用测试夹具，不调用模型或数据库。"""

import asyncio
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


def parse_events(text):
    result = []
    for frame in text.strip().split("\n\n"):
        name, data = frame.split("\n", 1)
        result.append({"event": name.removeprefix("event: "),
                       "data": json.loads(data.removeprefix("data: "))})
    return result


class AgentSseHttpTests(unittest.TestCase):
    def test_event_format_order_headers_and_unicode(self):
        events = [
            {"event": "tool_start", "data": {"id": "1", "name": "search_knowledge_base", "args": {"query": "测试"}}},
            {"event": "tool_end", "data": {"id": "1", "status": "ok", "result_count": 1}},
            {"event": "answer_delta", "data": {"message_id": "m", "text": "中文\n第二行"}},
            {"event": "done", "data": {"answer": "中文\n第二行", "sources": [], "tool_calls": [], "context_usage": {}}},
        ]
        closed = []

        async def fixture(question):
            self.assertEqual(question, "测试问题")
            try:
                for event in events:
                    yield event
            finally:
                closed.append(True)

        with patch("agent_sse.stream_agent", fixture), TestClient(app) as client:
            response = client.post("/agent/chat/stream", json={"question": "测试问题"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        self.assertEqual(response.headers["cache-control"], "no-cache")
        self.assertEqual(response.headers["x-accel-buffering"], "no")
        self.assertNotIn("content-length", response.headers)
        self.assertTrue(response.text.endswith("\n\n"))
        self.assertEqual(parse_events(response.text), events)
        self.assertEqual(closed, [True])

    def test_failure_after_partial_output_returns_error_not_done(self):
        async def fixture(question):
            yield {"event": "answer_delta", "data": {"text": "partial", "message_id": "m"}}
            raise RuntimeError("sensitive fixture detail")

        with (patch("agent_sse.stream_agent", fixture), self.assertLogs("agent_sse", level="ERROR"),
              TestClient(app) as client):
            response = client.post("/agent/chat/stream", json={"question": "test"})
        self.assertEqual(response.status_code, 200)
        events = parse_events(response.text)
        self.assertEqual([event["event"] for event in events], ["answer_delta", "error"])
        self.assertEqual(events[-1]["data"]["code"], "AGENT_ERROR")
        self.assertNotIn("sensitive fixture detail", response.text)

    def test_failure_before_first_event_uses_sanitized_error(self):
        async def fixture(question):
            raise ValueError("private fixture detail")
            yield {}

        with (patch("agent_sse.stream_agent", fixture), self.assertLogs("agent_sse", level="ERROR"),
              TestClient(app) as client):
            response = client.post("/agent/chat/stream", json={"question": "test"})
        self.assertEqual(parse_events(response.text)[0]["data"]["code"], "INTERNAL_ERROR")
        self.assertNotIn("private fixture detail", response.text)

    def test_invalid_request_does_not_start_agent(self):
        with patch("agent_sse.stream_agent") as agent, TestClient(app) as client:
            for payload in ({}, {"question": ""}, {"question": "x" * 4001}):
                response = client.post("/agent/chat/stream", json=payload)
                self.assertEqual(response.status_code, 422)
            agent.assert_not_called()

    def test_openapi_documents_sse(self):
        content = app.openapi()["paths"]["/agent/chat/stream"]["post"]["responses"]["200"]["content"]
        self.assertIn("text/event-stream", content)
        self.assertNotIn("application/json", content)


def http_scope(spec="2.4"):
    return {"type": "http", "asgi": {"version": "3.0", "spec_version": spec},
            "http_version": "1.1", "method": "POST", "scheme": "http",
            "path": "/agent/chat/stream", "raw_path": b"/agent/chat/stream", "query_string": b"",
            "root_path": "", "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 1234), "server": ("127.0.0.1", 8000)}


def request_receiver(disconnected):
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": b'{"question":"fixture"}', "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}

    return receive


class AgentSseAsgiTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_event_is_sent_before_agent_finishes(self):
        first_sent, release, disconnected = asyncio.Event(), asyncio.Event(), asyncio.Event()
        messages = []

        async def fixture(question):
            yield {"event": "answer_delta", "data": {"text": "first"}}
            await release.wait()
            yield {"event": "done", "data": {"answer": "first"}}

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.body" and message.get("body"):
                first_sent.set()

        with patch("agent_sse.stream_agent", fixture):
            task = asyncio.create_task(app(http_scope(), request_receiver(disconnected), send))
            try:
                await asyncio.wait_for(first_sent.wait(), timeout=2)
                self.assertFalse(task.done())
                self.assertFalse(any(b"event: done" in msg.get("body", b"") for msg in messages))
                release.set()
                await asyncio.wait_for(task, timeout=2)
            finally:
                task.cancel()
        self.assertTrue(any(b"event: done" in msg.get("body", b"") for msg in messages))

    async def test_disconnect_while_waiting_cancels_upstream(self):
        for spec in ("2.3", "2.4"):
            with self.subTest(spec=spec):
                started, closed, disconnected = asyncio.Event(), asyncio.Event(), asyncio.Event()
                bodies = []

                async def fixture(question):
                    try:
                        started.set()
                        await asyncio.Event().wait()
                        yield {}
                    finally:
                        closed.set()

                async def send(message):
                    bodies.append(message.get("body", b""))

                with patch("agent_sse.stream_agent", fixture):
                    task = asyncio.create_task(app(http_scope(spec), request_receiver(disconnected), send))
                    try:
                        await asyncio.wait_for(started.wait(), timeout=2)
                        disconnected.set()
                        await asyncio.wait_for(task, timeout=2)
                    finally:
                        task.cancel()
                self.assertTrue(closed.is_set())
                self.assertNotIn(b"event: error", b"".join(bodies))

    async def test_response_write_failure_closes_upstream(self):
        closed, disconnected = asyncio.Event(), asyncio.Event()

        async def fixture(question):
            try:
                yield {"event": "answer_delta", "data": {"text": "first"}}
                await asyncio.Event().wait()
            finally:
                closed.set()

        async def send(message):
            if message["type"] == "http.response.body":
                raise OSError("fixture client closed socket")

        from starlette.requests import ClientDisconnect
        with patch("agent_sse.stream_agent", fixture):
            with self.assertRaises(ClientDisconnect):
                await app(http_scope(), request_receiver(disconnected), send)
        self.assertTrue(closed.is_set())


if __name__ == "__main__":
    unittest.main()
