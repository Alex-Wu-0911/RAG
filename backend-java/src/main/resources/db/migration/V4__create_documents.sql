-- Java 保存原始文件与元数据；解析、分块、Embedding 和向量由 Python 负责。
CREATE TABLE biz.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_base_id UUID NOT NULL,
    filename VARCHAR(255) NOT NULL,
    -- 服务端生成的相对存储标识，不直接使用上传文件名作为路径。
    storage_key VARCHAR(255) NOT NULL,
    size_bytes BIGINT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_documents_knowledge_base
        FOREIGN KEY (knowledge_base_id) REFERENCES biz.knowledge_bases (id) ON DELETE RESTRICT,
    CONSTRAINT uk_documents_kb_hash UNIQUE (knowledge_base_id, content_hash),
    CONSTRAINT ck_documents_size_positive CHECK (size_bytes > 0),
    CONSTRAINT ck_documents_status
        CHECK (status IN ('PENDING', 'PROCESSING', 'READY', 'FAILED'))
);

CREATE INDEX idx_documents_kb_created_id
    ON biz.documents (knowledge_base_id, created_at DESC, id DESC);

COMMENT ON TABLE biz.documents IS '知识库文档元数据，不包含分块或向量';
COMMENT ON COLUMN biz.documents.knowledge_base_id IS '所属知识库';
COMMENT ON COLUMN biz.documents.filename IS '原始文件名，仅用于展示';
COMMENT ON COLUMN biz.documents.storage_key IS '相对于文件存储根目录的存储标识';
COMMENT ON COLUMN biz.documents.size_bytes IS '文件大小，单位字节';
COMMENT ON COLUMN biz.documents.content_hash IS '文件内容的 SHA-256，小写十六进制字符串';
COMMENT ON COLUMN biz.documents.status IS 'PENDING 待处理、PROCESSING 处理中、READY 可检索、FAILED 失败';
COMMENT ON COLUMN biz.documents.updated_at IS '最后修改时间，由应用维护';
