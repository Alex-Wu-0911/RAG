from psycopg.rows import dict_row

from database import get_connection


def find_all_knowledge_bases() -> list[dict]:
    """查询知识库元数据，供主题向量维护脚本批量使用。"""
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT id, name, description FROM biz.knowledge_bases ORDER BY name, id"
            )
            return cursor.fetchall()


def find_similar_knowledge_bases(query_vector: list[float], limit: int = 3) -> list[dict]:
    """按主题向量的余弦距离排序，只返回指定数量的候选知识库。"""
    vector = str(query_vector)
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, name, description,
                       1 - (topic_embedding <=> %s::public.vector) AS similarity
                FROM biz.knowledge_bases
                WHERE topic_embedding IS NOT NULL
                ORDER BY topic_embedding <=> %s::public.vector, id
                LIMIT %s
                """,
                (vector, vector, limit),
            )
            return cursor.fetchall()

