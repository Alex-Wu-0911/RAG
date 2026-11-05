package com.example.knowledgeagent.outbox.repository;

import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

import java.util.UUID;
import java.util.Optional;

@Repository
@Profile("db")
@SuppressWarnings("all")
public class OutboxRepository {
    public record PendingEvent(UUID id, String topic, UUID messageKey, String payload, int attemptCount) {}
    private final JdbcClient jdbc;

    public OutboxRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public void createDocumentTaskEvent(UUID taskId, UUID documentId) {
        UUID eventId = UUID.randomUUID();
        jdbc.sql("""
                INSERT INTO biz.outbox_events (id, task_id, message_key, payload)
                VALUES (:eventId, :taskId, :documentId,
                    jsonb_build_object('event_id', CAST(:eventId AS text),
                                       'task_id', CAST(:taskId AS text),
                                       'document_id', CAST(:documentId AS text)))
                """)
                .param("eventId", eventId).param("taskId", taskId)
                .param("documentId", documentId).update();
    }

    // 必须在事务内调用；锁保持到该条消息的发送结果写回数据库。
    public Optional<PendingEvent> lockNextPending() {
        return jdbc.sql("""
                SELECT id, topic, message_key, payload::text, attempt_count
                FROM biz.outbox_events
                WHERE status = 'PENDING' AND next_attempt_at <= CURRENT_TIMESTAMP
                ORDER BY next_attempt_at, created_at, id
                LIMIT 1 FOR UPDATE SKIP LOCKED
                """)
                .query((row, index) -> new PendingEvent(row.getObject("id", UUID.class),
                        row.getString("topic"), row.getObject("message_key", UUID.class),
                        row.getString("payload"), row.getInt("attempt_count"))).optional();
    }

    public void markSent(UUID eventId) {
        jdbc.sql("""
                UPDATE biz.outbox_events
                SET status = 'SENT', attempt_count = attempt_count + 1,
                    sent_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP, last_error = NULL
                WHERE id = :id
                """).param("id", eventId).update();
    }

    public void scheduleRetry(UUID eventId, int delaySeconds, String error) {
        jdbc.sql("""
                UPDATE biz.outbox_events
                SET attempt_count = attempt_count + 1, last_error = :error,
                    next_attempt_at = CURRENT_TIMESTAMP + (:delay * INTERVAL '1 second'),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """).param("id", eventId).param("delay", delaySeconds).param("error", error).update();
    }
}
