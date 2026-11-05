from psycopg.rows import dict_row

from database import get_connection


def find_all_knowledge_bases() -> list[dict]:
    """查询知识库 ID、名称和简介，供 Agent 判断应检索哪个库。"""
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT id, name, description FROM biz.knowledge_bases ORDER BY name, id"
            )
            return cursor.fetchall()
