-- 扩展由 PostgreSQL 镜像提供；在当前数据库中启用。
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

-- Python 将文档分块后，把原文和对应的 Embedding 一起存入此表。
CREATE TABLE biz.document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES biz.documents (id) ON DELETE CASCADE,
    knowledge_base_id UUID NOT NULL REFERENCES biz.knowledge_bases (id),
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding public.vector(1536) NOT NULL,

    CONSTRAINT uk_document_chunks_document_index UNIQUE (document_id, chunk_index),
    CONSTRAINT ck_document_chunks_index CHECK (chunk_index >= 0)
);

-- 检索时先限定知识库；当前数据量较小，暂不添加向量近似索引。
CREATE INDEX idx_document_chunks_knowledge_base
    ON biz.document_chunks (knowledge_base_id);

COMMENT ON TABLE biz.document_chunks IS '文档文本块及其 Embedding，由 Python 写入和检索';
COMMENT ON COLUMN biz.document_chunks.document_id IS '所属文档';
COMMENT ON COLUMN biz.document_chunks.knowledge_base_id IS '所属知识库，检索时用于限定范围';
COMMENT ON COLUMN biz.document_chunks.chunk_index IS '在原文档中的分块序号，从 0 开始';
COMMENT ON COLUMN biz.document_chunks.content IS '文本块原文，检索后作为大模型的参考内容';
COMMENT ON COLUMN biz.document_chunks.embedding IS 'text-embedding-3-small 默认输出的 1536 维向量';
