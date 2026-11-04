from uuid import UUID

from psycopg.rows import dict_row

from database import get_connection


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
        connection.execute(
            "UPDATE biz.documents SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (status, document_id),
        )
