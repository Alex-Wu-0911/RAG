package com.example.knowledgeagent.document.controller;

import com.example.knowledgeagent.document.dto.DocumentResponse;
import com.example.knowledgeagent.document.service.DocumentService;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.UUID;

@RestController
@RequestMapping("/api/knowledge-bases/{knowledgeBaseId}/documents")
@Profile("db & storage")
@SuppressWarnings("all")
public class DocumentController {
    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    /** 上传 Markdown/PDF 到知识库；file 为文件字段，新文档返回 201，重复内容返回 200。 */
    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<DocumentResponse> upload(@PathVariable("knowledgeBaseId") UUID knowledgeBaseId,
                                                   @RequestParam("file") MultipartFile file) throws Exception {
        var result = service.upload(knowledgeBaseId, file);
        return ResponseEntity.status(result.created() ? HttpStatus.CREATED : HttpStatus.OK)
                .body(result.document());
    }
}
