package com.example.knowledgeagent.knowledgebase.dto;

import com.example.knowledgeagent.knowledgebase.entity.KnowledgeBase;

import java.time.Instant;
import java.util.UUID;

public record KnowledgeBaseResponse(UUID id, String name, String description,
                                    Instant createdAt, Instant updatedAt) {
    public static KnowledgeBaseResponse from(KnowledgeBase entity) {
        return new KnowledgeBaseResponse(entity.getId(), entity.getName(),
                entity.getDescription(), entity.getCreatedAt(), entity.getUpdatedAt());
    }
}
