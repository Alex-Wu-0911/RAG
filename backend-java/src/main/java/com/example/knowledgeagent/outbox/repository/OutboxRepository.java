package com.example.knowledgeagent.outbox.repository;

import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
@Profile("db")
@SuppressWarnings("all")
public class OutboxRepository {
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
}
