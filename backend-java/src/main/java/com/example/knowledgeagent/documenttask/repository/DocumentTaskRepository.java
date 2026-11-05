package com.example.knowledgeagent.documenttask.repository;

import com.example.knowledgeagent.documenttask.dto.DocumentTaskResponse;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

@Repository
@Profile("db")
@SuppressWarnings("all")
public class DocumentTaskRepository {
    private static final RowMapper<DocumentTaskResponse> MAPPER = (row, index) -> new DocumentTaskResponse(
            row.getObject("id", UUID.class), row.getObject("document_id", UUID.class),
            row.getString("status"), row.getString("stage"), row.getInt("attempt_count"),
            row.getString("error_message"), instant(row, "created_at"), instant(row, "updated_at"),
            instant(row, "started_at"), instant(row, "finished_at"));

    private final JdbcClient jdbc;

    public DocumentTaskRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<UUID> lockDocument(UUID documentId) {
        // 事务结束前锁住这一文档，让同一文档的并发提交依次检查已有任务。
        return jdbc.sql("SELECT id FROM biz.documents WHERE id = :id FOR UPDATE")
                .param("id", documentId).query(UUID.class).optional();
    }

    public Optional<DocumentTaskResponse> findActiveByDocumentId(UUID documentId) {
        return jdbc.sql("""
                SELECT * FROM biz.document_processing_tasks
                WHERE document_id = :documentId AND status IN ('QUEUED', 'RUNNING')
                """)
                .param("documentId", documentId).query(MAPPER).optional();
    }

    public DocumentTaskResponse create(UUID documentId) {
        return jdbc.sql("""
                INSERT INTO biz.document_processing_tasks (document_id)
                VALUES (:documentId) RETURNING *
                """)
                .param("documentId", documentId).query(MAPPER).single();
    }

    public Optional<DocumentTaskResponse> findById(UUID taskId) {
        return jdbc.sql("SELECT * FROM biz.document_processing_tasks WHERE id = :id")
                .param("id", taskId).query(MAPPER).optional();
    }

    private static Instant instant(ResultSet row, String column) throws SQLException {
        var value = row.getTimestamp(column);
        return value == null ? null : value.toInstant();
    }
}
