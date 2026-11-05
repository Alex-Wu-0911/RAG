package com.example.knowledgeagent.documenttask.controller;

import com.example.knowledgeagent.documenttask.dto.DocumentTaskResponse;
import com.example.knowledgeagent.documenttask.service.DocumentTaskService;
import org.springframework.context.annotation.Profile;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;
import java.util.UUID;

@RestController
@RequestMapping("/api")
@Profile("db")
@SuppressWarnings("all")
public class DocumentTaskController {
    private final DocumentTaskService service;

    public DocumentTaskController(DocumentTaskService service) {
        this.service = service;
    }

    /** 提交文档处理任务，无请求体；已有未完成任务时复用，返回 202 和查询地址。 */
    @PostMapping("/documents/{documentId}/tasks")
    public ResponseEntity<DocumentTaskResponse> submit(@PathVariable("documentId") UUID documentId) {
        var task = service.submit(documentId);
        return ResponseEntity.accepted().location(URI.create("/api/document-tasks/" + task.id())).body(task);
    }

    /** 查询任务状态、当前处理阶段、执行次数和失败原因。 */
    @GetMapping("/document-tasks/{taskId}")
    public DocumentTaskResponse getById(@PathVariable("taskId") UUID taskId) {
        return service.getById(taskId);
    }
}
