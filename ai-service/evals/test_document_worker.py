import json
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from document_worker import TaskHeartbeat, process_task
from kafka_consumer import consume
from task_repository import LeaseLostError


class DocumentWorkerTest(unittest.TestCase):
    def test_heartbeat_stops_when_lease_is_lost(self):
        with patch("document_worker.renew_lease", return_value=False) as renew:
            with TaskHeartbeat(uuid4(), uuid4(), interval=0.01) as heartbeat:
                self.assertTrue(heartbeat.lost.wait(2))
                with self.assertRaises(LeaseLostError):
                    heartbeat.check()
            self.assertFalse(heartbeat.thread.is_alive())
            renew.assert_called_once()

    def test_processing_checks_lease_before_saving_and_records_failure(self):
        task_id, doc_id, token, kb_id = [uuid4() for _ in range(4)]
        with (patch("document_worker.claim_task", return_value={"lease_token": token}),
              patch("document_worker.TaskHeartbeat"),
              patch("document_worker.find_document", return_value={"storage_key": "test.md", "knowledge_base_id": kb_id}),
              patch("document_worker.read_object", return_value=b"fixture text"),
              patch("document_worker.split_text", return_value=["fixture text"]),
              patch("document_worker.set_task_stage"),
              patch("document_worker.embed_texts", side_effect=RuntimeError("test API failure")),
              patch("document_worker.complete_task") as complete,
              patch("document_worker.fail_task") as fail):
            self.assertEqual(process_task(task_id, doc_id, "test-worker"), "FAILED")
            complete.assert_not_called()
            fail.assert_called_once_with(task_id, doc_id, token, "RuntimeError: test API failure")

    def test_duplicate_finished_task_does_not_call_embedding(self):
        with (patch("document_worker.claim_task", return_value=None),
              patch("document_worker.find_task", return_value={"status": "SUCCEEDED"}),
              patch("document_worker.embed_texts") as embed):
            self.assertEqual(process_task(uuid4(), uuid4(), "test-worker"), "SKIPPED")
            embed.assert_not_called()

    def test_offset_committed_only_after_durable_result(self):
        payload = {name: str(uuid4()) for name in ("event_id", "task_id", "document_id")}
        message = MagicMock()
        message.error.return_value = None
        message.value.return_value = json.dumps(payload).encode()
        message.topic.return_value = "rag.document.process"
        message.partition.return_value = 0
        message.offset.return_value = 0
        for result in ("SUCCEEDED", "FAILED", "SKIPPED", LeaseLostError("lost")):
            with self.subTest(result=result):
                with (patch("kafka_consumer.Consumer") as consumer_class,
                      patch("document_worker.process_task") as process,
                      patch("builtins.print")):
                    consumer = consumer_class.return_value
                    consumer.poll.return_value = message
                    def finish(*args):
                        consumer.commit.assert_not_called()
                        if isinstance(result, Exception):
                            raise result
                        return result
                    process.side_effect = finish
                    if isinstance(result, Exception):
                        with self.assertRaises(LeaseLostError):
                            consume(once=True, process=True)
                        consumer.commit.assert_not_called()
                    else:
                        self.assertEqual(consume(once=True, process=True), 0)
                        consumer.commit.assert_called_once_with(message=message, asynchronous=False)
                    consumer.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
