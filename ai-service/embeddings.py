import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).with_name(".env"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


def embed_texts(texts: list[str]) -> list[list[float]]:
    """调用真实 Embedding API，每个文本片段对应一个向量。"""
    vectors = []
    # SDK 自动读取 OPENAI_API_KEY；不在代码中写入密钥。
    with OpenAI(timeout=30, max_retries=0) as client:
        # 分批请求，避免一次提交过多片段；顺序与原片段一致。
        for start in range(0, len(texts), 128):
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts[start:start + 128],
            )
            vectors.extend(item.embedding for item in response.data)
    return vectors
