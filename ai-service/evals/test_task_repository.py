"""真实数据库验证；只操作本测试创建的任务，不发送 Kafka 消息。"""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from database import get_connection
from task_repository import claim_task


@unittest.skipUnless(os.getenv("RUN_DB_TESTS") == "1", "需显式设置 RUN_DB_TESTS=1")
class TaskRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.kb_id, self.document_id, self.task_id = uuid4(), uuid4(), uuid4()
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO biz.knowledge_bases (id, name) VALUES (%s, 'claim test')",
                (self.kb_id,),
            )
            connection.execute(
                """
                INSERT INTO biz.documents
                    (id, knowledge_base_id, filename, storage_key, size_bytes, content_hash)
                VALUES (%s, %s, 'claim-test.md', '_verification/no-object', 1, %s)
                """,
                (self.document_id, self.kb_id, "0" * 64),
            )
            connection.execute(
                "INSERT INTO biz.document_processing_tasks (id, document_id) VALUES (%s, %s)",
                (self.task_id, self.document_id),
            )

    def tearDown(self):
        # 没有创建 Outbox/MinIO 对象，仅清理本测试生成的 UUID 对应数据。
        with get_connection() as connection:
            connection.execute("DELETE FROM biz.document_processing_tasks WHERE id = %s", (self.task_id,))
            connection.execute("DELETE FROM biz.documents WHERE id = %s", (self.document_id,))
            connection.execute("DELETE FROM biz.knowledge_bases WHERE id = %s", (self.kb_id,))

    def test_concurrent_claim_has_exactly_one_winner(self):
        barrier = Barrier(4)

        def claim(index):
            barrier.wait(timeout=5)
            return claim_task(self.task_id, self.document_id, f"test-worker-{index}")

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(claim, range(4)))
        winners = [result for result in results if result is not None]
        self.assertEqual(len(winners), 1)
        winner = winners[0]
        self.assertEqual(winner["status"], "RUNNING")
        self.assertEqual(winner["stage"], "READING")
        self.assertEqual(winner["attempt_count"], 1)
        self.assertIsNotNone(winner["lease_token"])
        self.assertGreater(winner["lease_expires_at"], winner["heartbeat_at"])
        # 新连接读取，确认领取结果已提交，并发失败者未增加次数或覆盖执行令牌。
        with get_connection() as connection:
            saved = connection.execute(
                "SELECT worker_id, lease_token, attempt_count FROM biz.document_processing_tasks WHERE id = %s",
                (self.task_id,),
            ).fetchone()
        self.assertEqual(saved, (winner["worker_id"], winner["lease_token"], 1))

    def test_wrong_document_and_missing_task_cannot_claim(self):
        self.assertIsNone(claim_task(self.task_id, uuid4(), "test-worker"))
        self.assertIsNone(claim_task(uuid4(), self.document_id, "test-worker"))
        self.assertIsNotNone(claim_task(self.task_id, self.document_id, "test-worker"))

    def test_non_queued_task_cannot_be_claimed(self):
        for status in ("RUNNING", "SUCCEEDED", "FAILED"):
            with self.subTest(status=status):
                with get_connection() as connection:
                    connection.execute(
                        "UPDATE biz.document_processing_tasks SET status = %s WHERE id = %s",
                        (status, self.task_id),
                    )
                self.assertIsNone(claim_task(self.task_id, self.document_id, "test-worker"))


if __name__ == "__main__":
    unittest.main()
