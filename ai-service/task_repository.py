from uuid import UUID, uuid4

from psycopg.rows import dict_row

from database import get_connection


def claim_task(task_id: UUID, document_id: UUID, worker_id: str) -> dict | None:
    """原子领取排队任务；成功返回任务和执行令牌，未领取到返回 None。"""
    lease_token = uuid4()
    # with 正常退出时先提交事务，再把结果交给调用方；提交失败会抛出异常。
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            # 状态检查与更新在同一条 SQL 中完成，并发 Worker 只有一个能成功。
            cursor.execute(
                """
                UPDATE biz.document_processing_tasks
                SET status = 'RUNNING', stage = 'READING',
                    worker_id = %s, lease_token = %s,
                    attempt_count = attempt_count + 1,
                    started_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP,
                    heartbeat_at = CURRENT_TIMESTAMP,
                    lease_expires_at = CURRENT_TIMESTAMP + INTERVAL '120 seconds',
                    error_message = NULL, finished_at = NULL
                WHERE id = %s AND document_id = %s AND status = 'QUEUED'
                RETURNING id, document_id, status, stage, attempt_count,
                          worker_id, lease_token, heartbeat_at, lease_expires_at
                """,
                (worker_id, lease_token, task_id, document_id),
            )
            return cursor.fetchone()
