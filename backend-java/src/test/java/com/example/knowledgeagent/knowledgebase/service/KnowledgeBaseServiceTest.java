package com.example.knowledgeagent.knowledgebase.service;

import com.example.knowledgeagent.common.error.BusinessException;
import com.example.knowledgeagent.common.error.ErrorCode;
import com.example.knowledgeagent.knowledgebase.repository.KnowledgeBaseRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.support.DependencyInjectionTestExecutionListener;
import org.springframework.test.context.transaction.TransactionalTestExecutionListener;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataJpaTest
@ActiveProfiles("db")
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@EnabledIfEnvironmentVariable(named = "DB_URL", matches = ".+")
@Import(KnowledgeBaseService.class)
@TestExecutionListeners(listeners = {DependencyInjectionTestExecutionListener.class,
        TransactionalTestExecutionListener.class},
        mergeMode = TestExecutionListeners.MergeMode.REPLACE_DEFAULTS)
class KnowledgeBaseServiceTest {
    @Autowired
    private KnowledgeBaseService service;
    @Autowired
    private KnowledgeBaseRepository repository;

    @Test
    void createsAndReadsKnowledgeBaseWithoutUser() {
        long before = repository.count();
        var created = service.create("研发文档", "使用说明");
        repository.flush();
        assertThat(created.id()).isNotNull();
        assertThat(created.name()).isEqualTo("研发文档");
        assertThat(service.getById(created.id()).description()).isEqualTo("使用说明");
        assertThat(service.list(0, 20).total()).isEqualTo(before + 1);
    }

    @Test
    void missingKnowledgeBaseReturnsNotFound() {
        assertThatThrownBy(() -> service.getById(UUID.randomUUID()))
                .isInstanceOfSatisfying(BusinessException.class,
                        exception -> assertThat(exception.getErrorCode()).isEqualTo(ErrorCode.RESOURCE_NOT_FOUND));
    }

    @Test
    void rejectsInvalidPagination() {
        assertThatThrownBy(() -> service.list(-1, 20)).isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> service.list(0, 101)).isInstanceOf(BusinessException.class);
    }
}
