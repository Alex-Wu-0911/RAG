package com.example.knowledgeagent.documenttask.controller;

import com.example.knowledgeagent.documenttask.service.DocumentTaskService;
import com.example.knowledgeagent.outbox.repository.OutboxRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.support.DependencyInjectionTestExecutionListener;
import org.springframework.test.context.web.ServletTestExecutionListener;
import org.springframework.test.web.servlet.MockMvc;

import java.util.ArrayList;
import java.util.UUID;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** 使用真实 PostgreSQL，覆盖并发提交及任务/Outbox 的事务原子性。 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("db")
@Import(DocumentTaskControllerTest.FaultConfiguration.class)
@EnabledIfEnvironmentVariable(named = "DB_URL", matches = ".+")
@TestExecutionListeners(listeners = {ServletTestExecutionListener.class, DependencyInjectionTestExecutionListener.class},
        mergeMode = TestExecutionListeners.MergeMode.REPLACE_DEFAULTS)
@SuppressWarnings("all")
class DocumentTaskControllerTest {
    @Autowired private MockMvc mvc;
    @Autowired private ObjectMapper mapper;
    @Autowired private JdbcClient jdbc;
    @Autowired private DocumentTaskService service;
    @Autowired private FaultOutboxRepository outbox;
    private UUID kbId;
    private UUID documentId;

    @BeforeEach
    void prepare() {
        kbId = UUID.randomUUID();
        documentId = UUID.randomUUID();
        outbox.fail = false;
        jdbc.sql("INSERT INTO biz.knowledge_bases (id, name) VALUES (:id, 'task integration test')")
                .param("id", kbId).update();
        jdbc.sql("""
                INSERT INTO biz.documents (id, knowledge_base_id, filename, storage_key, size_bytes, content_hash)
                VALUES (:id, :kb, 'task-test.md', '_verification/no-object', 1, :hash)
                """)
                .param("id", documentId).param("kb", kbId).param("hash", "0".repeat(64)).update();
    }

    @AfterEach
    void cleanup() {
        outbox.fail = false;
        jdbc.sql("DELETE FROM biz.outbox_events WHERE task_id IN (SELECT id FROM biz.document_processing_tasks WHERE document_id = :id)")
                .param("id", documentId).update();
        jdbc.sql("DELETE FROM biz.document_processing_tasks WHERE document_id = :id").param("id", documentId).update();
        jdbc.sql("DELETE FROM biz.documents WHERE id = :id").param("id", documentId).update();
        jdbc.sql("DELETE FROM biz.knowledge_bases WHERE id = :id").param("id", kbId).update();
    }

    @Test
    void submitsReadsAndReusesTaskWithOneOutboxEvent() throws Exception {
        String taskId = submit();
        mvc.perform(get("/api/document-tasks/{id}", taskId))
                .andExpect(status().isOk()).andExpect(jsonPath("$.id").value(taskId))
                .andExpect(jsonPath("$.documentId").value(documentId.toString()))
                .andExpect(jsonPath("$.status").value("QUEUED"))
                .andExpect(jsonPath("$.stage").value("QUEUED"))
                .andExpect(jsonPath("$.attemptCount").value(0));
        assertThat(submit()).isEqualTo(taskId);
        assertThat(taskCount()).isEqualTo(1);
        var event = jdbc.sql("SELECT * FROM biz.outbox_events WHERE task_id = :id")
                .param("id", UUID.fromString(taskId)).query().singleRow();
        assertThat(event.get("status")).isEqualTo("PENDING");
        assertThat(event.get("topic")).isEqualTo("rag.document.process");
        assertThat(event.get("message_key")).isEqualTo(documentId);
        var payload = mapper.readTree(event.get("payload").toString());
        assertThat(payload.get("event_id").asText()).isEqualTo(event.get("id").toString());
        assertThat(payload.get("task_id").asText()).isEqualTo(taskId);
        assertThat(payload.get("document_id").asText()).isEqualTo(documentId.toString());
        assertThat(jdbc.sql("SELECT count(*) FROM biz.outbox_events WHERE task_id = :id")
                .param("id", UUID.fromString(taskId)).query(Long.class).single()).isEqualTo(1);
    }

    @Test
    void rejectsMissingResourcesAndInvalidId() throws Exception {
        mvc.perform(post("/api/documents/{id}/tasks", UUID.randomUUID()))
                .andExpect(status().isNotFound()).andExpect(jsonPath("$.code").value("RESOURCE_NOT_FOUND"));
        mvc.perform(get("/api/document-tasks/{id}", UUID.randomUUID()))
                .andExpect(status().isNotFound());
        mvc.perform(post("/api/documents/not-a-uuid/tasks")).andExpect(status().isBadRequest());
        assertThat(taskCount()).isZero();
    }

    @Test
    void concurrentSubmissionsReturnTheSameTask() throws Exception {
        var barrier = new CyclicBarrier(4);
        try (var executor = Executors.newFixedThreadPool(4)) {
            var futures = new ArrayList<java.util.concurrent.Future<String>>();
            for (int index = 0; index < 4; index++) {
                futures.add(executor.submit(() -> {
                    barrier.await(10, TimeUnit.SECONDS);
                    return submit();
                }));
            }
            var ids = new ArrayList<String>();
            for (var future : futures) {
                ids.add(future.get(20, TimeUnit.SECONDS));
            }
            assertThat(ids).containsOnly(ids.getFirst());
        }
        assertThat(taskCount()).isEqualTo(1);
        assertThat(jdbc.sql("""
                SELECT count(*) FROM biz.outbox_events e
                JOIN biz.document_processing_tasks t ON t.id = e.task_id WHERE t.document_id = :id
                """).param("id", documentId).query(Long.class).single()).isEqualTo(1);
    }

    @Test
    void rollsBackBothTaskAndEventWhenSubmissionFails() {
        outbox.fail = true;
        assertThatThrownBy(() -> service.submit(documentId)).isInstanceOf(IllegalStateException.class);
        assertThat(taskCount()).isZero();
        assertThat(jdbc.sql("SELECT count(*) FROM biz.outbox_events WHERE message_key = :id")
                .param("id", documentId).query(Long.class).single()).isZero();
    }

    @Test
    void createsAnotherTaskAfterPreviousTaskEnds() throws Exception {
        String first = submit();
        jdbc.sql("UPDATE biz.document_processing_tasks SET status = 'FAILED', stage = 'FAILED' WHERE id = :id")
                .param("id", UUID.fromString(first)).update();
        assertThat(submit()).isNotEqualTo(first);
        assertThat(taskCount()).isEqualTo(2);
    }

    private String submit() throws Exception {
        var response = mvc.perform(post("/api/documents/{id}/tasks", documentId))
                .andExpect(status().isAccepted()).andReturn().getResponse();
        String id = mapper.readTree(response.getContentAsString()).get("id").asText();
        assertThat(response.getHeader("Location")).isEqualTo("/api/document-tasks/" + id);
        return id;
    }

    private long taskCount() {
        return jdbc.sql("SELECT count(*) FROM biz.document_processing_tasks WHERE document_id = :id")
                .param("id", documentId).query(Long.class).single();
    }

    @TestConfiguration
    static class FaultConfiguration {
        @Bean
        @Primary
        FaultOutboxRepository faultOutboxRepository(JdbcClient jdbc) {
            return new FaultOutboxRepository(jdbc);
        }
    }

    static class FaultOutboxRepository extends OutboxRepository {
        boolean fail;

        FaultOutboxRepository(JdbcClient jdbc) {
            super(jdbc);
        }

        @Override
        public void createDocumentTaskEvent(UUID taskId, UUID documentId) {
            super.createDocumentTaskEvent(taskId, documentId);
            if (fail) {
                throw new IllegalStateException("Intentional rollback test after outbox insert");
            }
        }
    }
}