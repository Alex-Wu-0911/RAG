package com.example.knowledgeagent.knowledgebase.repository;

import com.example.knowledgeagent.knowledgebase.entity.KnowledgeBase;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.data.domain.PageRequest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.support.DependencyInjectionTestExecutionListener;
import org.springframework.test.context.transaction.TransactionalTestExecutionListener;

import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@ActiveProfiles("db")
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@EnabledIfEnvironmentVariable(named = "DB_URL", matches = ".+")
@TestExecutionListeners(listeners = {DependencyInjectionTestExecutionListener.class,
        TransactionalTestExecutionListener.class},
        mergeMode = TestExecutionListeners.MergeMode.REPLACE_DEFAULTS)
@SuppressWarnings("all")
class KnowledgeBaseRepositoryTest {
    @Autowired
    private KnowledgeBaseRepository repository;
    @Autowired
    private TestEntityManager entityManager;
    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void savesReloadsAndUpdatesKnowledgeBaseWithoutOwner() {
        KnowledgeBase saved = repository.saveAndFlush(new KnowledgeBase("研发文档", null));
        var id = saved.getId();
        entityManager.clear();

        KnowledgeBase loaded = repository.findById(id).orElseThrow();
        assertThat(loaded.getName()).isEqualTo("研发文档");
        assertThat(loaded.getDescription()).isEmpty();
        assertThat(loaded.getCreatedAt()).isNotNull();
        Instant createdAt = loaded.getCreatedAt();

        entityManager.clear();
        jdbc.update("UPDATE biz.knowledge_bases SET updated_at = created_at - INTERVAL '1 day' WHERE id = ?", id);
        loaded = repository.findById(id).orElseThrow();
        Instant oldUpdatedAt = loaded.getUpdatedAt();
        loaded.updateDetails("部署手册", "部署说明");
        repository.flush();
        entityManager.clear();

        KnowledgeBase updated = repository.findById(id).orElseThrow();
        assertThat(updated.getName()).isEqualTo("部署手册");
        assertThat(updated.getDescription()).isEqualTo("部署说明");
        assertThat(updated.getCreatedAt()).isEqualTo(createdAt);
        assertThat(updated.getUpdatedAt()).isAfter(oldUpdatedAt);
    }

    @Test
    void listsAllKnowledgeBasesWithStablePagination() {
        long before = repository.count();
        repository.saveAndFlush(new KnowledgeBase("同名", "第一份"));
        repository.saveAndFlush(new KnowledgeBase("同名", "第二份"));
        var page = repository.findAllByOrderByCreatedAtDescIdDesc(PageRequest.of(0, 2));
        assertThat(page.getTotalElements()).isEqualTo(before + 2);
        var expectedIds = jdbc.query("""
                SELECT id FROM biz.knowledge_bases
                ORDER BY created_at DESC, id DESC LIMIT 2
                """, (row, index) -> row.getObject("id", java.util.UUID.class));
        assertThat(page.getContent()).extracting(KnowledgeBase::getId).containsExactlyElementsOf(expectedIds);
    }
}
