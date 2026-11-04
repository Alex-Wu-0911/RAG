package com.example.knowledgeagent.document.repository;

import com.example.knowledgeagent.document.entity.Document;
import com.example.knowledgeagent.document.entity.DocumentStatus;
import com.example.knowledgeagent.knowledgebase.entity.KnowledgeBase;
import com.example.knowledgeagent.knowledgebase.repository.KnowledgeBaseRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.PageRequest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.support.DependencyInjectionTestExecutionListener;
import org.springframework.test.context.transaction.TransactionalTestExecutionListener;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** 使用本地 PostgreSQL，测试数据通过事务自动回滚。 */
@DataJpaTest
@ActiveProfiles("db")
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@EnabledIfEnvironmentVariable(named = "DB_URL", matches = ".+")
@TestExecutionListeners(listeners = {DependencyInjectionTestExecutionListener.class,
        TransactionalTestExecutionListener.class},
        mergeMode = TestExecutionListeners.MergeMode.REPLACE_DEFAULTS)
class DocumentRepositoryTest {
    @Autowired
    private DocumentRepository documents;
    @Autowired
    private KnowledgeBaseRepository knowledgeBases;
    @Autowired
    private TestEntityManager entityManager;
    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void savesMetadataAndUpdatesStatusAsString() {
        UUID kbId = createKnowledgeBase();
        Document saved = documents.saveAndFlush(new Document(
                kbId, "部署手册.md", "sample.md", 128, "a".repeat(64)));
        UUID id = saved.getId();
        entityManager.clear();

        Document loaded = documents.findById(id).orElseThrow();
        assertThat(loaded.getKnowledgeBaseId()).isEqualTo(kbId);
        assertThat(loaded.getFilename()).isEqualTo("部署手册.md");
        assertThat(loaded.getStorageKey()).isEqualTo("sample.md");
        assertThat(loaded.getSizeBytes()).isEqualTo(128);
        assertThat(loaded.getContentHash()).isEqualTo("a".repeat(64));
        assertThat(loaded.getStatus()).isEqualTo(DocumentStatus.PENDING);
        assertThat(loaded.getCreatedAt()).isNotNull();
        var createdAt = loaded.getCreatedAt();

        entityManager.clear();
        jdbc.update("UPDATE biz.documents SET updated_at = created_at - INTERVAL '1 day' WHERE id = ?", id);
        loaded = documents.findById(id).orElseThrow();
        var previousUpdatedAt = loaded.getUpdatedAt();
        loaded.changeStatus(DocumentStatus.PROCESSING);
        documents.flush();
        entityManager.clear();

        Document updated = documents.findById(id).orElseThrow();
        assertThat(updated.getStatus()).isEqualTo(DocumentStatus.PROCESSING);
        assertThat(updated.getCreatedAt()).isEqualTo(createdAt);
        assertThat(updated.getUpdatedAt()).isAfter(previousUpdatedAt);
        assertThat(jdbc.queryForObject("SELECT status FROM biz.documents WHERE id = ?", String.class, id))
                .isEqualTo("PROCESSING");
    }

    @Test
    void queriesWithinKnowledgeBaseAndAllowsSameContentInAnotherKnowledgeBase() {
        UUID firstKb = createKnowledgeBase();
        UUID secondKb = createKnowledgeBase();
        String hash = "b".repeat(64);
        Document first = documents.saveAndFlush(new Document(firstKb, "first.md", "first.md", 10, hash));
        Document second = documents.saveAndFlush(new Document(secondKb, "second.md", "second.md", 10, hash));
        entityManager.clear();

        assertThat(documents.findByKnowledgeBaseIdAndContentHash(firstKb, hash).orElseThrow().getId())
                .isEqualTo(first.getId());
        assertThat(documents.findByKnowledgeBaseIdAndContentHash(secondKb, hash).orElseThrow().getId())
                .isEqualTo(second.getId());
        var page = documents.findByKnowledgeBaseIdOrderByCreatedAtDescIdDesc(firstKb, PageRequest.of(0, 20));
        assertThat(page.getTotalElements()).isEqualTo(1);
        assertThat(page.getContent()).extracting(Document::getId).containsExactly(first.getId());
    }

    @Test
    void refusesDuplicateContentWithinSameKnowledgeBase() {
        UUID kbId = createKnowledgeBase();
        String hash = "c".repeat(64);
        documents.saveAndFlush(new Document(kbId, "first.md", "first.md", 10, hash));
        assertThatThrownBy(() -> documents.saveAndFlush(
                new Document(kbId, "renamed.md", "another.md", 10, hash)))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    private UUID createKnowledgeBase() {
        return knowledgeBases.saveAndFlush(new KnowledgeBase("文档测试", "")).getId();
    }
}
