package com.example.knowledgeagent.documenttask.dto;

import java.time.Instant;
import java.util.UUID;

/** 任务进度快照，不暴露 Worker 的租约令牌。 */
@SuppressWarnings("all")
public record DocumentTaskResponse(UUID id, UUID documentId, String status, String stage,
                                   int attemptCount, String errorMessage,
                                   Instant createdAt, Instant updatedAt,
                                   Instant startedAt, Instant finishedAt) {
}
