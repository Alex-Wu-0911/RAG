-- 主题向量用于选择知识库；文档片段向量仍保存在 document_chunks。
ALTER TABLE biz.knowledge_bases
    ADD COLUMN topic_embedding public.vector(1536);

COMMENT ON COLUMN biz.knowledge_bases.topic_embedding
    IS '知识库名称与简介的 Embedding，由 Python 生成；NULL 表示尚未生成主题向量';
