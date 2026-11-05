"""仅验证重排接线与元数据，不调用真实服务。"""
import unittest
from unittest.mock import patch

from cohere.core.api_error import ApiError
from langchain_core.documents import Document

import reranking


class RerankingTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            {"document_id": "doc", "chunk_index": 0, "content": "first", "similarity": 0.9},
            {"document_id": "doc", "chunk_index": 1, "content": "second", "similarity": 0.7},
        ]

    def test_empty_candidates_do_not_call_service(self):
        with patch.object(reranking, "CohereRerank") as compressor:
            self.assertEqual(reranking.rerank_chunks("question", [], 3), [])
            compressor.assert_not_called()

    def test_disabled_returns_vector_order(self):
        with patch.object(reranking, "RERANK_ENABLED", False), patch.object(reranking, "CohereRerank") as compressor:
            self.assertEqual(reranking.rerank_chunks("question", self.chunks, 1), self.chunks[:1])
            compressor.assert_not_called()

    def test_rerank_order_preserves_citations_and_vector_score(self):
        ranked = Document(page_content="second", metadata={
            "document_id": "doc", "chunk_index": 1, "similarity": 0.7, "relevance_score": 0.95,
        })
        with patch.object(reranking, "RERANK_ENABLED", True), patch.object(reranking.cohere, "ClientV2"), patch.object(reranking, "CohereRerank") as compressor:
            compressor.return_value.compress_documents.return_value = [ranked]
            result = reranking.rerank_chunks("question", self.chunks, 1)
        self.assertEqual(result[0]["chunk_index"], 1)
        self.assertEqual(result[0]["content"], "second")
        self.assertEqual(result[0]["similarity"], 0.7)
        self.assertEqual(result[0]["rerank_score"], 0.95)
        self.assertNotIn("relevance_score", result[0])

    def test_api_error_is_not_silently_replaced_by_vector_results(self):
        with patch.object(reranking, "RERANK_ENABLED", True), patch.object(reranking.cohere, "ClientV2"), patch.object(reranking, "CohereRerank") as compressor:
            compressor.return_value.compress_documents.side_effect = ApiError(status_code=429, body="rate limit")
            with self.assertRaises(reranking.RerankError):
                reranking.rerank_chunks("question", self.chunks, 1)


if __name__ == "__main__":
    unittest.main()
