import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))


def get_connection() -> psycopg.Connection:
    """创建 PostgreSQL 连接，调用方使用 with 自动关闭连接。"""
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "15432")),
        dbname=os.getenv("DB_NAME", "knowledge_agent"),
        user=os.getenv("DB_USER", "rag"),
        password=os.environ["DB_PASSWORD"],
        connect_timeout=5,
    )


if __name__ == "__main__":
    # 只读检查，不建表、不调用大模型。
    with get_connection() as connection:
        database = connection.execute("SELECT current_database()").fetchone()[0]
        extension = connection.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        table = connection.execute(
            "SELECT to_regclass('biz.document_chunks')"
        ).fetchone()[0]
        print(f"Database: {database}")
        print(f"pgvector: {extension[0] if extension else 'not enabled'}")
        print(f"Chunks table: {table if table else 'not created'}")
