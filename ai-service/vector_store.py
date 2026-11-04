from uuid import UUID

from database import get_connection


def save_document_chunks(
    document_id: UUID,
    knowledge_base_id: UUID,
    chunks: list[str],
    vectors: list[list[float]],
) -> int:
    """替换一个文档的全部分块，返回保存的分块数量。"""
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM biz.document_chunks WHERE document_id = %s",
            (document_id,),
        )
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO biz.document_chunks
                    (document_id, knowledge_base_id, chunk_index, content, embedding)
                VALUES (%s, %s, %s, %s, %s::public.vector)
                """,
                [
                    (document_id, knowledge_base_id, index, content, str(vector))
                    for index, (content, vector) in enumerate(zip(chunks, vectors, strict=True))
                ],
            )
        connection.execute(
            "UPDATE biz.documents SET status = 'READY', updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (document_id,),
        )
        # 分块替换和 READY 状态一起提交，失败则一起回滚。
    return len(chunks)
