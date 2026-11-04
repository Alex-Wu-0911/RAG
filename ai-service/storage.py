import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from minio import Minio

# 显式读取本目录的 .env，已有进程环境变量优先。
load_dotenv(Path(__file__).with_name(".env"))

endpoint = urlsplit(os.getenv("MINIO_ENDPOINT", "http://localhost:19000"))
client = Minio(
    endpoint.netloc,
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=endpoint.scheme == "https",
)
bucket = os.getenv("MINIO_BUCKET", "rag-documents")


def read_object(storage_key: str) -> bytes:
    """从固定 bucket 读取对象内容，不保存到本地文件。"""
    response = client.get_object(bucket, storage_key)
    try:
        return response.read()
    finally:
        # 释放 HTTP 连接，让 SDK 后续请求能复用连接池。
        response.close()
        response.release_conn()
