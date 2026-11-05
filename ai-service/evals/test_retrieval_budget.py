"""验证请求内去重和工具 JSON 文本预算，不调用真实模型或数据库。"""
import json
import unittest
from unittest.mock import patch

from agent_tools import create_agent_tools
from retrieval_budget import RetrievalBudget


def chunk(source_id: str, content: str = "原文内容") -> dict:
    return {"source_id": source_id, "content": content}


class RetrievalBudgetTests(unittest.TestCase):
    def test_duplicate_chunks_are_not_sent_again(self):
        budget = RetrievalBudget()
        budget.pack([chunk("doc-a:0")], "source_id")
        second = json.loads(budget.pack([chunk("doc-a:0"), chunk("doc-b:0")], "source_id"))
        self.assertEqual([item["source_id"] for item in second["items"]], ["doc-b:0"])
        self.assertEqual(budget.duplicate_items_skipped, 1)

    def test_duplicate_results_are_not_reported_as_no_search_results(self):
        budget = RetrievalBudget()
        budget.pack([chunk("doc:0")], "source_id")
        duplicate = json.loads(budget.pack([chunk("doc:0")], "source_id"))
        empty = json.loads(budget.pack([], "source_id"))
        self.assertEqual(duplicate["status"], "no_new_results")
        self.assertEqual(empty["status"], "no_results")

    def test_complete_items_and_all_notices_stay_within_shared_budget(self):
        budget = RetrievalBudget()
        item = chunk("doc:0", "long passage " * 40)
        first_cost = max(budget.count_tokens(budget.serialize(status, [item])) for status in ("ok", "partial"))
        budget.max_tokens = first_cost + 3 * budget.notice_tokens
        outputs = [budget.pack([item, chunk("doc:1", "second passage " * 40)], "source_id")]
        self.assertEqual(json.loads(outputs[0])["items"], [item])
        self.assertEqual(json.loads(outputs[0])["status"], "partial")
        outputs += [budget.pack([], "source_id") for _ in range(3)]
        actual_tokens = sum(budget.count_tokens(output) for output in outputs)
        self.assertEqual(actual_tokens, budget.used_tokens)
        self.assertLessEqual(actual_tokens, budget.max_tokens)
        self.assertTrue(budget.exhausted)

    def test_candidates_and_documents_share_the_same_budget(self):
        budget = RetrievalBudget()
        first = budget.pack([{"id": "kb", "name": "主题", "description": "简介"}], "id")
        second = budget.pack([chunk("doc:0")], "source_id")
        self.assertEqual(budget.used_tokens, budget.count_tokens(first) + budget.count_tokens(second))

    def test_request_state_is_not_shared(self):
        first, second = RetrievalBudget(), RetrievalBudget()
        first.pack([chunk("doc:0")], "source_id")
        self.assertEqual(second.used_tokens, 0)
        self.assertEqual(len(json.loads(second.pack([chunk("doc:0")], "source_id"))["items"]), 1)

    def test_unicode_and_special_token_text_are_preserved(self):
        budget = RetrievalBudget()
        item = chunk("doc:0", "中文与特殊标记 <|endoftext|> 都是文档原文。")
        self.assertEqual(json.loads(budget.pack([item], "source_id"))["items"], [item])

    def test_exhausted_tool_does_not_call_embedding_or_database(self):
        budget = RetrievalBudget(max_tokens=256)
        budget.pack([chunk("doc:0", "too large " * 5000)], "source_id")
        with patch("agent_tools.search_knowledge_base") as raw_tool:
            tool = create_agent_tools(budget)[1]
            result = json.loads(tool.invoke({
                "knowledge_base_id": "2dc719cc-a15f-4f9b-9647-ffb80cc7f795",
                "query": "test query",
            }))
            raw_tool.invoke.assert_not_called()
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["items"], [])


if __name__ == "__main__":
    unittest.main()
