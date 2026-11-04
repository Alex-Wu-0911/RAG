package com.example.knowledgeagent.document.repository;

import com.example.knowledgeagent.document.entity.Document;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;
import java.util.UUID;

@SuppressWarnings("all")
public interface DocumentRepository extends JpaRepository<Document, UUID> {
    // 上传时按文件内容哈希检查同一知识库中是否已有该文件。
    Optional<Document> findByKnowledgeBaseIdAndContentHash(UUID knowledgeBaseId, String contentHash);

    Page<Document> findByKnowledgeBaseIdOrderByCreatedAtDescIdDesc(UUID knowledgeBaseId, Pageable pageable);
}
