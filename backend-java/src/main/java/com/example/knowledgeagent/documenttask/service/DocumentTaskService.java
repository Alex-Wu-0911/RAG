package com.example.knowledgeagent.documenttask.service;

import com.example.knowledgeagent.common.error.BusinessException;
import com.example.knowledgeagent.common.error.ErrorCode;
import com.example.knowledgeagent.documenttask.dto.DocumentTaskResponse;
import com.example.knowledgeagent.documenttask.repository.DocumentTaskRepository;
import com.example.knowledgeagent.outbox.repository.OutboxRepository;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
@Profile("db")
@SuppressWarnings("all")
public class DocumentTaskService {
    private final DocumentTaskRepository tasks;
    private final OutboxRepository outbox;

    public DocumentTaskService(DocumentTaskRepository tasks, OutboxRepository outbox) {
        this.tasks = tasks;
        this.outbox = outbox;
    }

    @Transactional
    public DocumentTaskResponse submit(UUID documentId) {
        tasks.lockDocument(documentId)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND));
        var existing = tasks.findActiveByDocumentId(documentId);
        if (existing.isPresent()) {
            return existing.get();
        }
        var task = tasks.create(documentId);
        outbox.createDocumentTaskEvent(task.id(), documentId);
        return task;
    }

    @Transactional(readOnly = true)
    public DocumentTaskResponse getById(UUID taskId) {
        return tasks.findById(taskId)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND));
    }
}
