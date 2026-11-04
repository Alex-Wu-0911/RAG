-- 在当前数据库启用向量类型和相似度计算；重复执行不会重复创建。
CREATE EXTENSION IF NOT EXISTS vector;

-- 返回版本即表示扩展已经启用。
SELECT extversion FROM pg_extension WHERE extname = 'vector';

-- 简单验证向量类型，预期返回 3。
SELECT vector_dims('[1,2,3]'::vector) AS dimensions;
