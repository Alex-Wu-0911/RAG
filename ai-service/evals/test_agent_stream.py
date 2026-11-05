"""只用本地测试模型和工具，验证真实 LangChain 事件流，不调用外部 API。"""

import asyncio
import json
import unittest
from unittest.mock import patch

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from agent_service import run_agent, stream_agent
from retrieval_budget import RetrievalBudget


class LocalToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        message = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs).generations[0].message
        if message.tool_calls:
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_calls=message.tool_calls))
        else:
            middle = len(message.text) // 2
            for text in (message.text[:middle], message.text[middle:]):
                yield ChatGenerationChunk(message=AIMessageChunk(content=text))


def model_event(chunk):
    return {"event": "on_chat_model_stream", "name": "model", "run_id": "model-run",
            "parent_ids": ["root"], "data": {"chunk": chunk}}


def root_end(message):
    return {"event": "on_chain_end", "name": "agent", "run_id": "root", "parent_ids": [],
            "data": {"output": {"messages": [message]}}}


class LocalEventAgent:
    def __init__(self, events):
        self.events = events
        self.closed = False

    async def astream_events(self, *args, **kwargs):
        try:
            for event in self.events:
                if isinstance(event, Exception):
                    raise event
                yield event
        finally:
            self.closed = True


class AgentStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_graph_tools_deltas_and_final_summary(self):
        kb_id = "2dc719cc-a15f-4f9b-9647-ffb80cc7f795"
        model = LocalToolModel(messages=iter([
            AIMessage(content="", tool_calls=[{
                "id": "call-1", "name": "search_knowledge_bases", "args": {"query": "fixture"},
            }]),
            AIMessage(content="", tool_calls=[{
                "id": "call-2", "name": "search_knowledge_base",
                "args": {"knowledge_base_id": kb_id, "query": "fixture", "top_k": 1},
            }]),
            AIMessage(content="fixture answer [doc:0]"),
        ]))
        hit = {"document_id": "doc", "filename": "test.md", "chunk_index": 0,
               "content": "fixture evidence", "similarity": 0.8, "source_id": "doc:0"}
        with (patch("agent_service.ChatOpenAI", return_value=model) as constructor,
              patch("agent_tools.embed_texts", return_value=[[0.1]]),
              patch("agent_tools.find_similar_knowledge_bases", return_value=[{
                  "id": kb_id, "name": "fixture", "description": "test", "similarity": 0.9,
              }]),
              patch("agent_tools.search_chunks", return_value=[hit]),
              patch("agent_tools.rerank_chunks", return_value=[hit])):
            events = [event async for event in stream_agent("fixture question")]
        self.assertTrue(constructor.call_args.kwargs["streaming"])
        names = [event["event"] for event in events]
        self.assertEqual(names[:4], ["tool_start", "tool_end", "tool_start", "tool_end"])
        self.assertEqual(names[-1], "done")
        self.assertEqual(names.count("done"), 1)
        deltas = [event["data"]["text"] for event in events if event["event"] == "answer_delta"]
        self.assertGreater(len(deltas), 1)
        self.assertEqual("".join(deltas), "fixture answer [doc:0]")
        self.assertEqual(events[0]["data"]["id"], events[1]["data"]["id"])
        final = events[-1]["data"]
        self.assertEqual(final["answer"], "fixture answer [doc:0]")
        self.assertEqual(final["sources"], [hit])
        self.assertEqual([call["result_count"] for call in final["tool_calls"]], [1, 1])
        self.assertEqual([call["status"] for call in final["tool_calls"]], ["ok", "ok"])
        self.assertGreater(final["context_usage"]["used_tokens"], 0)
        # 下一步可直接 JSON 编码，不含 LangChain 消息对象。
        json.dumps(events)

    async def test_only_visible_text_is_emitted_and_nested_end_is_ignored(self):
        agent = LocalEventAgent([
            model_event(AIMessageChunk(content=[{"type": "reasoning", "reasoning": "hidden"}])),
            model_event(AIMessageChunk(content="", tool_call_chunks=[{
                "id": "call", "name": "search_knowledge_bases", "args": '{"query":', "index": 0,
            }])),
            model_event(AIMessageChunk(content=[{"type": "text", "text": "visible"}])),
            {"event": "on_chain_end", "name": "inner", "run_id": "inner", "parent_ids": ["root"],
             "data": {"output": {"messages": [AIMessage(content="wrong")]}}},
            root_end(AIMessage(content="visible")),
        ])
        with patch("agent_service._create_agent", return_value=(agent, RetrievalBudget())):
            events = [event async for event in stream_agent("test")]
        self.assertEqual([event["event"] for event in events], ["answer_delta", "done"])
        self.assertEqual(events[0]["data"]["text"], "visible")
        self.assertEqual(events[-1]["data"]["answer"], "visible")
        self.assertTrue(agent.closed)

    async def test_error_propagates_without_fake_done(self):
        agent = LocalEventAgent([model_event(AIMessageChunk(content="partial")), RuntimeError("test failure")])
        events = []
        with patch("agent_service._create_agent", return_value=(agent, RetrievalBudget())):
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                async for event in stream_agent("test"):
                    events.append(event)
        self.assertNotIn("done", [event["event"] for event in events])
        self.assertTrue(agent.closed)

    async def test_incomplete_or_missing_final_result_is_not_success(self):
        cases = [[], [root_end(AIMessage(content="partial", response_metadata={"status": "incomplete"}))],
                 [root_end(AIMessage(content=""))]]
        for inputs in cases:
            with self.subTest(inputs=inputs):
                agent = LocalEventAgent(inputs)
                with patch("agent_service._create_agent", return_value=(agent, RetrievalBudget())):
                    with self.assertRaises(RuntimeError):
                        _ = [event async for event in stream_agent("test")]
                self.assertTrue(agent.closed)

    async def test_early_close_closes_upstream(self):
        agent = LocalEventAgent([model_event(AIMessageChunk(content="first")), root_end(AIMessage(content="first"))])
        with patch("agent_service._create_agent", return_value=(agent, RetrievalBudget())):
            stream = stream_agent("test")
            self.assertEqual((await anext(stream))["event"], "answer_delta")
            await stream.aclose()
        self.assertTrue(agent.closed)

    async def test_cancellation_closes_waiting_upstream(self):
        waiting = asyncio.Event()
        closed = asyncio.Event()

        class WaitingAgent:
            async def astream_events(self, *args, **kwargs):
                try:
                    waiting.set()
                    await asyncio.Event().wait()
                    yield {}
                finally:
                    closed.set()

        with patch("agent_service._create_agent", return_value=(WaitingAgent(), RetrievalBudget())):
            task = asyncio.create_task(anext(stream_agent("test")))
            await asyncio.wait_for(waiting.wait(), timeout=2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(closed.is_set())


class SyncAgentCompatibilityTest(unittest.TestCase):
    def test_existing_sync_response_shape_is_preserved(self):
        from unittest.mock import Mock
        agent = Mock()
        agent.invoke.return_value = {"messages": [AIMessage(content="answer")]}
        with patch("agent_service._create_agent", return_value=(agent, RetrievalBudget())):
            result = run_agent("test")
        self.assertEqual(set(result), {"answer", "tool_calls", "sources", "context_usage"})
        self.assertEqual(result["answer"], "answer")


if __name__ == "__main__":
    unittest.main()
