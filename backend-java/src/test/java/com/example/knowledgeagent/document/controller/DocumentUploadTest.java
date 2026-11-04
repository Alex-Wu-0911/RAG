package com.example.knowledgeagent.document.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.example.knowledgeagent.document.repository.DocumentRepository;
import com.example.knowledgeagent.knowledgebase.entity.KnowledgeBase;
import com.example.knowledgeagent.knowledgebase.repository.KnowledgeBaseRepository;
import io.minio.GetObjectArgs;
import io.minio.MinioClient;
import io.minio.RemoveObjectArgs;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.support.DependencyInjectionTestExecutionListener;
import org.springframework.test.context.transaction.TransactionalTestExecutionListener;
import org.springframework.test.context.web.ServletTestExecutionListener;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles({"db", "storage"})
@Transactional
@EnabledIfEnvironmentVariable(named = "DB_URL", matches = ".+")
@EnabledIfEnvironmentVariable(named = "MINIO_ACCESS_KEY", matches = ".+")
@TestExecutionListeners(listeners = {ServletTestExecutionListener.class,
        DependencyInjectionTestExecutionListener.class, TransactionalTestExecutionListener.class},
        mergeMode = TestExecutionListeners.MergeMode.REPLACE_DEFAULTS)
@SuppressWarnings("all")
class DocumentUploadTest {
    @Autowired private MockMvc mvc;
    @Autowired private ObjectMapper mapper;
    @Autowired private KnowledgeBaseRepository knowledgeBases;
    @Autowired private DocumentRepository documents;
    @Autowired private MinioClient minio;
    @Value("${storage.bucket}") private String bucket;

    @Test
    void uploadsToObjectStorageAndReusesDuplicateContent() throws Exception {
        UUID kbId = knowledgeBases.saveAndFlush(new KnowledgeBase("上传测试", "")).getId();
        byte[] content = ("# upload test " + UUID.randomUUID()).getBytes(StandardCharsets.UTF_8);
        String key = null;
        try {
            var response = mvc.perform(multipart("/api/knowledge-bases/{id}/documents", kbId)
                            .file(new MockMultipartFile("file", "notes.md", "text/markdown", content)))
                    .andExpect(status().isCreated())
                    .andExpect(jsonPath("$.filename").value("notes.md"))
                    .andExpect(jsonPath("$.status").value("PENDING"))
                    .andReturn().getResponse();
            UUID documentId = UUID.fromString(mapper.readTree(
                    response.getContentAsString(StandardCharsets.UTF_8)).get("id").asText());
            var document = documents.findById(documentId).orElseThrow();
            key = document.getStorageKey();
            try (var stored = minio.getObject(GetObjectArgs.builder().bucket(bucket).object(key).build())) {
                assertThat(stored.readAllBytes()).isEqualTo(content);
            }
            mvc.perform(multipart("/api/knowledge-bases/{id}/documents", kbId)
                            .file(new MockMultipartFile("file", "renamed.md", "text/markdown", content)))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.id").value(documentId.toString()));
            assertThat(documents.findByKnowledgeBaseIdOrderByCreatedAtDescIdDesc(
                    kbId, org.springframework.data.domain.PageRequest.of(0, 20)).getTotalElements()).isEqualTo(1);
        } finally {
            if (key != null) minio.removeObject(RemoveObjectArgs.builder().bucket(bucket).object(key).build());
        }
    }

    @Test
    void rejectsUnsupportedFileAndUnknownKnowledgeBase() throws Exception {
        UUID kbId = knowledgeBases.saveAndFlush(new KnowledgeBase("上传校验", "")).getId();
        mvc.perform(multipart("/api/knowledge-bases/{id}/documents", kbId)
                        .file(new MockMultipartFile("file", "notes.exe", "application/octet-stream", new byte[]{1})))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.code").value("UNSUPPORTED_FILE_TYPE"));
        mvc.perform(multipart("/api/knowledge-bases/{id}/documents", UUID.randomUUID())
                        .file(new MockMultipartFile("file", "notes.md", "text/markdown", new byte[]{1})))
                .andExpect(status().isNotFound());
    }
}
