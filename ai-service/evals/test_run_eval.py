"""仅验证评测统计与 HTTP 失败记录，不调用真实模型。"""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from run_eval import call_agent, score_retrieval, summarize, write_review


CASE = {
    "id": "test-case",
    "category": "test",
    "question": "test question",
    "expected_knowledge_base_id": "target-kb",
    "relevant_chunk_indices": [1, 3],
    "answerable": True,
    "expected_points": ["reference point"],
    "forbidden_claims": ["unsupported statement"],
}


class EvalRunnerTests(unittest.TestCase):
    def test_evidence_requires_correct_document_and_deduplicates_chunks(self):
        result = score_retrieval(CASE, "target-doc", {
            "tool_calls": [
                {"name": "search_knowledge_bases", "args": {"query": "test"}},
                {"name": "search_knowledge_base", "args": {"knowledge_base_id": "target-kb"}},
                {"name": "search_knowledge_base", "args": {"knowledge_base_id": "other-kb"}},
            ],
            "sources": [
                {"document_id": "other-doc", "chunk_index": 3},
                {"document_id": "target-doc", "chunk_index": 1},
                {"document_id": "target-doc", "chunk_index": 1},
            ],
        })
        self.assertTrue(result["knowledge_base_hit"])
        self.assertEqual(result["unexpected_knowledge_base_ids"], ["other-kb"])
        self.assertEqual(result["retrieved_chunk_indices"], [1])
        self.assertEqual(result["evidence_coverage"], 0.5)

    def test_failures_stay_in_denominator_but_not_success_latency(self):
        success = {"success": True, "elapsed_ms": 10, "metrics": {
            "knowledge_base_hit": True, "evidence_coverage": 0.5, "tool_call_count": 2}}
        failure = {"success": False, "elapsed_ms": 999, "metrics": score_retrieval(CASE, "doc", {})}
        result = summarize([success, failure])
        self.assertEqual(result["api_success_rate"], 0.5)
        self.assertEqual(result["knowledge_base_hit_rate"], 0.5)
        self.assertEqual(result["mean_evidence_coverage"], 0.25)
        self.assertEqual(result["mean_success_latency_ms"], 10)

    def test_http_failure_is_recorded_and_answers_are_not_sent(self):
        error = HTTPError("http://example.test/agent/chat", 503, "unavailable", {}, io.BytesIO(b'{"detail":"unavailable"}'))
        with patch("run_eval.urlopen", side_effect=error) as request:
            record = call_agent(CASE, "doc", "http://example.test/agent/chat", 1)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(json.loads(request.call_args.args[0].data), {"question": CASE["question"]})
        self.assertFalse(record["success"])
        self.assertEqual(record["http_status"], 503)
        self.assertIn("unavailable", record["raw_body"])

    def test_malformed_json_shape_is_failure_and_review_still_writes(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'[]'
        with patch("run_eval.urlopen", return_value=response):
            record = call_agent(CASE, "doc", "http://example.test/agent/chat", 1)
        self.assertFalse(record["success"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.md"
            write_review(path, [record])
            self.assertIn("test-case", path.read_text(encoding="utf-8"))

    def test_empty_run_has_no_invented_rates(self):
        result = summarize([])
        self.assertEqual(result["attempted_count"], 0)
        self.assertIsNone(result["api_success_rate"])
        self.assertIsNone(result["p95_success_latency_ms"])


if __name__ == "__main__":
    unittest.main()
