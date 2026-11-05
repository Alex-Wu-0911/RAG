from uuid import UUID, uuid4

from psycopg.rows import dict_row

from database import get_connection
from vector_store import write_document_chunks


class LeaseLostError(RuntimeError):
    """本次执行已不再持有有效租约，不能写回结果。"""


def claim_task(task_id: UUID, document_id: UUID, worker_id: str) -> dict | None:
    """原子领取排队任务；成功返回任务和执行令牌，未领取到返回 None。"""
    lease_token = uuid4()
    # with 正常退出时先提交事务，再把结果交给调用方；提交失败会抛出异常。
    with get_connection() as connection:
        connection.execute("SELECT id FROM biz.documents WHERE id = %s FOR UPDATE", (document_id,))
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
            task = cursor.fetchone()
        if task is not None:
            connection.execute(
                "UPDATE biz.documents SET status = 'PROCESSING', updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (document_id,),
            )
        return task


def renew_lease(task_id: UUID, lease_token: UUID) -> bool:
    """每次续租 120 秒；已过期或被其他执行替代时返回 False。"""
    with get_connection() as connection:
        row = connection.execute(
            """
            UPDATE biz.document_processing_tasks
            SET heartbeat_at = clock_timestamp(),
                lease_expires_at = clock_timestamp() + INTERVAL '120 seconds',
                updated_at = clock_timestamp()
            WHERE id = %s AND lease_token = %s AND status = 'RUNNING'
              AND lease_expires_at > clock_timestamp()
            RETURNING id
            """, (task_id, lease_token),
        ).fetchone()
        return row is not None


def set_task_stage(task_id: UUID, lease_token: UUID, stage: str) -> None:
    with get_connection() as connection:
        row = connection.execute(
            """
            UPDATE biz.document_processing_tasks SET stage = %s, updated_at = clock_timestamp()
            WHERE id = %s AND lease_token = %s AND status = 'RUNNING'
              AND lease_expires_at > clock_timestamp()
            RETURNING id
            """, (stage, task_id, lease_token),
        ).fetchone()
        if row is None:
            raise LeaseLostError("更新阶段失败：执行租约已失效")


def complete_task(task_id: UUID, document_id: UUID, lease_token: UUID,
                  knowledge_base_id: UUID, chunks: list[str], vectors: list[list[float]]) -> None:
    """校验执行资格、替换向量、完成任务在同一个事务中提交。"""
    with get_connection() as connection:
        connection.execute("SELECT id FROM biz.documents WHERE id = %s FOR UPDATE", (document_id,))
        row = connection.execute(
            """
            SELECT id FROM biz.document_processing_tasks
            WHERE id = %s AND document_id = %s AND lease_token = %s
              AND status = 'RUNNING' AND lease_expires_at > clock_timestamp()
            FOR UPDATE
            """, (task_id, document_id, lease_token),
        ).fetchone()
        if row is None:
            raise LeaseLostError("保存结果失败：执行租约已失效")
        write_document_chunks(connection, document_id, knowledge_base_id, chunks, vectors)
        row = connection.execute(
            """
            UPDATE biz.document_processing_tasks
            SET status = 'SUCCEEDED', stage = 'COMPLETED', error_message = NULL,
                finished_at = clock_timestamp(), updated_at = clock_timestamp(), lease_expires_at = NULL
            WHERE id = %s AND lease_token = %s AND status = 'RUNNING'
              AND lease_expires_at > clock_timestamp()
            RETURNING id
            """, (task_id, lease_token),
        ).fetchone()
        if row is None:
            # 入库期间租约也可能到期，抛异常让向量和文档状态一起回滚。
            raise LeaseLostError("保存期间租约到期，结果已回滚")


def fail_task(task_id: UUID, document_id: UUID, lease_token: UUID, reason: str) -> None:
    with get_connection() as connection:
        connection.execute("SELECT id FROM biz.documents WHERE id = %s FOR UPDATE", (document_id,))
        row = connection.execute(
            """
            UPDATE biz.document_processing_tasks
            SET status = 'FAILED', stage = 'FAILED', error_message = %s,
                finished_at = clock_timestamp(), updated_at = clock_timestamp(), lease_expires_at = NULL
            WHERE id = %s AND document_id = %s AND lease_token = %s
              AND status = 'RUNNING' AND lease_expires_at > clock_timestamp()
            RETURNING id
            """, (reason, task_id, document_id, lease_token),
        ).fetchone()
        if row is None:
            raise LeaseLostError("记录失败状态时租约已失效")
        connection.execute(
            "UPDATE biz.documents SET status = 'FAILED', updated_at = clock_timestamp() WHERE id = %s",
            (document_id,),
        )


def find_task(task_id: UUID, document_id: UUID) -> dict | None:
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT status FROM biz.document_processing_tasks WHERE id = %s AND document_id = %s",
                (task_id, document_id),
            )
            return cursor.fetchone()
