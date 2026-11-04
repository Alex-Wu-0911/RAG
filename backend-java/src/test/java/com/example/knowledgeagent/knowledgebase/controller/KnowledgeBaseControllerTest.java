package com.example.knowledgeagent.knowledgebase.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.support.DependencyInjectionTestExecutionListener;
import org.springframework.test.context.transaction.TransactionalTestExecutionListener;
import org.springframework.test.context.web.ServletTestExecutionListener;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** 使用真实 Service 和 PostgreSQL；测试请求产生的数据通过事务回滚。 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("db")
@Transactional
@EnabledIfEnvironmentVariable(named = "DB_URL", matches = ".+")
@TestExecutionListeners(listeners = {ServletTestExecutionListener.class,
        DependencyInjectionTestExecutionListener.class, TransactionalTestExecutionListener.class},
        mergeMode = TestExecutionListeners.MergeMode.REPLACE_DEFAULTS)
@SuppressWarnings("all")
class KnowledgeBaseControllerTest {
    @Autowired
    private MockMvc mvc;
    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void createsListsAndReadsKnowledgeBaseWithoutAuthentication() throws Exception {
        var result = mvc.perform(post("/api/knowledge-bases")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"name":"研发知识库","description":"部署与接口文档"}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("研发知识库"))
                .andExpect(jsonPath("$.createdAt").isNotEmpty())
                .andReturn();
        String id = objectMapper.readTree(result.getResponse()
                .getContentAsString(StandardCharsets.UTF_8)).get("id").asText();
        org.assertj.core.api.Assertions.assertThat(result.getResponse().getHeader("Location"))
                .isEqualTo("/api/knowledge-bases/" + id);

        mvc.perform(get("/api/knowledge-bases/{id}", id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(id))
                .andExpect(jsonPath("$.description").value("部署与接口文档"));
        mvc.perform(get("/api/knowledge-bases").param("size", "100"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[*].id", hasItem(id)))
                .andExpect(jsonPath("$.page").value(0));
    }

    @Test
    void returnsConsistentErrorsForInvalidRequestsAndMissingResource() throws Exception {
        mvc.perform(post("/api/knowledge-bases").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fieldErrors[0].field").value("name"));
        mvc.perform(get("/api/knowledge-bases").param("size", "101"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
        mvc.perform(get("/api/knowledge-bases/{id}", UUID.randomUUID()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("RESOURCE_NOT_FOUND"));
    }
}
