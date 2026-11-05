from database import get_connection
from embeddings import embed_texts
from knowledge_base_repository import find_all_knowledge_bases


def rebuild_topic_embeddings() -> int:
    """为现有知识库重新生成主题向量；这是手动维护脚本，不在每次问答时执行。"""
    knowledge_bases = find_all_knowledge_bases()
    if not knowledge_bases:
        return 0

    texts = [
        f"知识库名称：{item['name']}\n知识库简介：{item['description']}"
        for item in knowledge_bases
    ]
    vectors = embed_texts(texts)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                "UPDATE biz.knowledge_bases SET topic_embedding = %s::public.vector WHERE id = %s",
                [
                    (str(vector), item["id"])
                    for item, vector in zip(knowledge_bases, vectors, strict=True)
                ],
            )
    return len(knowledge_bases)


if __name__ == "__main__":
    count = rebuild_topic_embeddings()
    print(f"已更新 {count} 个知识库的主题向量。")
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT name, vector_dims(topic_embedding) FROM biz.knowledge_bases ORDER BY name, id"
        ).fetchall()
        for name, dimensions in rows:
            print(f"{name}: {dimensions} 维")
