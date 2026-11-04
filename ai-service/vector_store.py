from uuid import UUID

from psycopg.rows import dict_row

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


def search_chunks(
    knowledge_base_id: UUID, query_vector: list[float], top_k: int = 3
) -> list[dict]:
    """在指定知识库的 READY 文档中，按余弦距离查找最相关的文本块。"""
    vector = str(query_vector)
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT c.document_id, d.filename, c.chunk_index, c.content,
                       1 - (c.embedding <=> %s::public.vector) AS similarity
                FROM biz.document_chunks c
                JOIN biz.documents d ON d.id = c.document_id
                WHERE c.knowledge_base_id = %s AND d.status = 'READY'
                ORDER BY c.embedding <=> %s::public.vector, c.id
                LIMIT %s
                """,
                (vector, knowledge_base_id, vector, top_k),
            )
            return cursor.fetchall()
