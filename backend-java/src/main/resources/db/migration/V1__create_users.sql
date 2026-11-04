-- biz 存放 Java 端业务表；Flyway 的历史表仍保留在现有 public schema。
CREATE SCHEMA IF NOT EXISTS biz;

CREATE TABLE biz.users (
    -- UUID 是业务标识；后续 Java 实体也可在保存前生成 UUID。
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) NOT NULL,
    -- 存储 PasswordEncoder 生成的哈希，不保存明文密码。
    password_hash VARCHAR(255) NOT NULL,
    -- TIMESTAMPTZ 表示时间点，显示时可按客户端时区转换。
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uk_users_username UNIQUE (username),
    CONSTRAINT ck_users_username_not_blank
        CHECK (length(btrim(username)) > 0 AND username = btrim(username)),
    CONSTRAINT ck_users_password_hash_not_blank
        CHECK (length(btrim(password_hash)) > 0)
);

COMMENT ON TABLE biz.users IS '用户账户';
COMMENT ON COLUMN biz.users.id IS '用户唯一标识';
COMMENT ON COLUMN biz.users.username IS '用户名，当前按大小写区分，禁止首尾空格';
COMMENT ON COLUMN biz.users.password_hash IS '密码哈希，不允许存储明文密码';
COMMENT ON COLUMN biz.users.created_at IS '创建时间点';
