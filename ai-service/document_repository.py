from uuid import UUID

from psycopg.rows import dict_row

from database import get_connection


class DocumentBusyError(RuntimeError):
    pass


def guard_sync_processing(connection, document_id: UUID) -> None:
    """旧的同步入口不能覆盖异步任务的状态和结果。"""
    connection.execute("SELECT id FROM biz.documents WHERE id = %s FOR UPDATE", (document_id,))
    active = connection.execute(
        """
        SELECT id FROM biz.document_processing_tasks
        WHERE document_id = %s
        """, (document_id,),
    ).fetchone()
    if active:
        raise DocumentBusyError("文档已使用异步任务，请通过任务接口处理和查询进度")


def find_document(document_id: UUID) -> dict | None:
    """读取文档所属知识库和对象存储位置。"""
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT id, knowledge_base_id, storage_key FROM biz.documents WHERE id = %s",
                (document_id,),
            )
            return cursor.fetchone()


def update_document_status(document_id: UUID, status: str) -> None:
    """记录文档处理状态。"""
    with get_connection() as connection:
        guard_sync_processing(connection, document_id)
        connection.execute(
            "UPDATE biz.documents SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (status, document_id),
        )
