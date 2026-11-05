-- 文档的一次后台处理任务。文档总体状态仍保存在 biz.documents。
CREATE TABLE biz.document_processing_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES biz.documents (id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'QUEUED',
    stage VARCHAR(20) NOT NULL DEFAULT 'QUEUED',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,

    -- Worker 领取任务时设置；每次执行生成新的令牌，用于区分旧执行与新执行。
    worker_id VARCHAR(100),
    lease_token UUID,
    heartbeat_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,

    CONSTRAINT ck_document_tasks_status
        CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    CONSTRAINT ck_document_tasks_stage
        CHECK (stage IN ('QUEUED', 'READING', 'SPLITTING', 'EMBEDDING', 'SAVING', 'COMPLETED', 'FAILED')),
    CONSTRAINT ck_document_tasks_attempt_count CHECK (attempt_count >= 0)
);

-- 并发提交时由数据库保证：同一文档最多有一个排队中或执行中的任务。
CREATE UNIQUE INDEX uk_document_tasks_active_document
    ON biz.document_processing_tasks (document_id)
    WHERE status IN ('QUEUED', 'RUNNING');

CREATE INDEX idx_document_tasks_document_created
    ON biz.document_processing_tasks (document_id, created_at DESC, id DESC);

-- 后续恢复进程查找租约过期的执行中任务。
CREATE INDEX idx_document_tasks_expired_lease
    ON biz.document_processing_tasks (lease_expires_at)
    WHERE status = 'RUNNING';

COMMENT ON TABLE biz.document_processing_tasks IS '异步文档处理任务，供提交、状态查询和 Worker 执行使用';
COMMENT ON COLUMN biz.document_processing_tasks.status IS 'QUEUED 排队、RUNNING 执行中、SUCCEEDED 成功、FAILED 失败';
COMMENT ON COLUMN biz.document_processing_tasks.stage IS '当前处理阶段，作为进度展示，不表示精确百分比';
COMMENT ON COLUMN biz.document_processing_tasks.attempt_count IS '实际领取执行的次数，提交时为 0';
COMMENT ON COLUMN biz.document_processing_tasks.error_message IS '最近一次处理失败原因';
COMMENT ON COLUMN biz.document_processing_tasks.worker_id IS '当前领取任务的 Worker 标识';
COMMENT ON COLUMN biz.document_processing_tasks.lease_token IS '当前执行令牌，后续状态更新与入库需校验，避免过期 Worker 覆盖新结果';
COMMENT ON COLUMN biz.document_processing_tasks.heartbeat_at IS '最近一次心跳时间';
COMMENT ON COLUMN biz.document_processing_tasks.lease_expires_at IS '租约到期时间，后续用于识别失联 Worker';
COMMENT ON COLUMN biz.document_processing_tasks.updated_at IS '最后修改时间，由应用维护';

-- Java 在创建任务的同一事务中写入事件，之后由投递程序发送到 Kafka。
CREATE TABLE biz.outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES biz.document_processing_tasks (id) ON DELETE RESTRICT,
    event_type VARCHAR(100) NOT NULL DEFAULT 'DOCUMENT_PROCESS_REQUESTED',
    topic VARCHAR(200) NOT NULL DEFAULT 'rag.document.process',
    message_key UUID NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMPTZ,

    CONSTRAINT ck_outbox_status CHECK (status IN ('PENDING', 'SENT')),
    CONSTRAINT ck_outbox_attempt_count CHECK (attempt_count >= 0),
    CONSTRAINT ck_outbox_payload CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX idx_outbox_pending_dispatch
    ON biz.outbox_events (next_attempt_at, created_at, id)
    WHERE status = 'PENDING';

CREATE INDEX idx_outbox_task_created
    ON biz.outbox_events (task_id, created_at DESC, id DESC);

COMMENT ON TABLE biz.outbox_events IS '与业务任务同事务保存的待发送事件，可靠投递 Kafka 允许重复消息';
COMMENT ON COLUMN biz.outbox_events.id IS '事件唯一标识，后续随消息发送';
COMMENT ON COLUMN biz.outbox_events.message_key IS 'Kafka 消息 Key，使用文档 ID';
COMMENT ON COLUMN biz.outbox_events.payload IS 'JSON 消息内容，仅包含任务和文档标识等，不保存文件本体';
COMMENT ON COLUMN biz.outbox_events.status IS 'PENDING 等待投递、SENT Kafka 已确认接收，不代表文档处理完成';
COMMENT ON COLUMN biz.outbox_events.attempt_count IS '发送消息的尝试次数，与任务执行次数独立';
COMMENT ON COLUMN biz.outbox_events.next_attempt_at IS '下次允许投递时间，后续用于发送失败退避';
COMMENT ON COLUMN biz.outbox_events.last_error IS '最近一次消息投递失败原因';
COMMENT ON COLUMN biz.outbox_events.sent_at IS 'Kafka 确认接收后记录的时间';
COMMENT ON COLUMN biz.outbox_events.updated_at IS '最后修改时间，由应用维护';
