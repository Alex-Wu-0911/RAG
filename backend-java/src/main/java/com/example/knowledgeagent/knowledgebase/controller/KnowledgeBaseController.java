package com.example.knowledgeagent.knowledgebase.controller;

import com.example.knowledgeagent.common.web.PageResponse;
import com.example.knowledgeagent.knowledgebase.dto.CreateKnowledgeBaseRequest;
import com.example.knowledgeagent.knowledgebase.dto.KnowledgeBaseResponse;
import com.example.knowledgeagent.knowledgebase.service.KnowledgeBaseService;
import jakarta.validation.Valid;
import org.springframework.context.annotation.Profile;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;
import java.util.UUID;

@RestController
@RequestMapping("/api/knowledge-bases")
@Profile("db")
public class KnowledgeBaseController {
    private final KnowledgeBaseService service;

    public KnowledgeBaseController(KnowledgeBaseService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<KnowledgeBaseResponse> create(
            @Valid @RequestBody CreateKnowledgeBaseRequest request) {
        KnowledgeBaseResponse created = service.create(request.name(), request.description());
        return ResponseEntity.created(URI.create("/api/knowledge-bases/" + created.id()))
                .body(created);
    }

    @GetMapping
    public PageResponse<KnowledgeBaseResponse> list(
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "20") int size) {
        return service.list(page, size);
    }

    @GetMapping("/{id}")
    public KnowledgeBaseResponse getById(@PathVariable("id") UUID id) {
        return service.getById(id);
    }
}
