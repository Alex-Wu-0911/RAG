-- 每个知识库有且只有一位所有者；成员授权后续单独迁移。
CREATE TABLE biz.knowledge_bases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(1000) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- 默认值只在插入时生效；后续更新由 Java 显式维护。
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_knowledge_bases_owner
        FOREIGN KEY (owner_id) REFERENCES biz.users (id) ON DELETE RESTRICT,
    CONSTRAINT ck_knowledge_bases_name_not_blank
        CHECK (length(btrim(name)) > 0 AND name = btrim(name))
);

-- 支持按所有者分页，并按创建时间及 ID 稳定排序。
CREATE INDEX idx_knowledge_bases_owner_created_id
    ON biz.knowledge_bases (owner_id, created_at DESC, id DESC);

COMMENT ON TABLE biz.knowledge_bases IS '知识库';
COMMENT ON COLUMN biz.knowledge_bases.id IS '知识库唯一标识';
COMMENT ON COLUMN biz.knowledge_bases.owner_id IS '所有者用户 ID，后续从当前用户入口获取';
COMMENT ON COLUMN biz.knowledge_bases.name IS '知识库名称，允许同一用户创建同名知识库';
COMMENT ON COLUMN biz.knowledge_bases.description IS '知识库描述，无描述时为空字符串';
COMMENT ON COLUMN biz.knowledge_bases.created_at IS '创建时间点';
COMMENT ON COLUMN biz.knowledge_bases.updated_at IS '最后修改时间点，由应用维护';
