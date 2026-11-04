-- 简化为无用户模型；保留已有知识库，仅移除所有者字段和关联。
ALTER TABLE biz.knowledge_bases DROP CONSTRAINT fk_knowledge_bases_owner;
DROP INDEX biz.idx_knowledge_bases_owner_created_id;
ALTER TABLE biz.knowledge_bases DROP COLUMN owner_id;

DROP TABLE biz.users;

CREATE INDEX idx_knowledge_bases_created_id
    ON biz.knowledge_bases (created_at DESC, id DESC);
