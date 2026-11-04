package com.example.knowledgeagent.document.dto;

import com.example.knowledgeagent.document.entity.Document;
import com.example.knowledgeagent.document.entity.DocumentStatus;

import java.time.Instant;
import java.util.UUID;

@SuppressWarnings("all")
public record DocumentResponse(UUID id, UUID knowledgeBaseId, String filename, long sizeBytes,
                               String contentHash, DocumentStatus status,
                               Instant createdAt, Instant updatedAt) {
    public static DocumentResponse from(Document document) {
        return new DocumentResponse(document.getId(), document.getKnowledgeBaseId(),
                document.getFilename(), document.getSizeBytes(), document.getContentHash(),
                document.getStatus(), document.getCreatedAt(), document.getUpdatedAt());
    }
}
