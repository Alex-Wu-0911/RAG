package com.example.knowledgeagent.document.controller;

import com.example.knowledgeagent.document.dto.DocumentResponse;
import com.example.knowledgeagent.common.web.PageResponse;
import com.example.knowledgeagent.document.service.DocumentService;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.UUID;

@RestController
@RequestMapping("/api")
@Profile("db & storage")
@SuppressWarnings("all")
public class DocumentController {
    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    /** 上传 Markdown/PDF 到知识库；file 为文件字段，新文档返回 201，重复内容返回 200。 */
    @PostMapping(value = "/knowledge-bases/{knowledgeBaseId}/documents", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<DocumentResponse> upload(@PathVariable("knowledgeBaseId") UUID knowledgeBaseId,
                                                   @RequestParam("file") MultipartFile file) throws Exception {
        var result = service.upload(knowledgeBaseId, file);
        return ResponseEntity.status(result.created() ? HttpStatus.CREATED : HttpStatus.OK)
                .body(result.document());
    }

    /** 分页查看知识库中的文档；page 从 0 开始，size 默认 20。 */
    @GetMapping("/knowledge-bases/{knowledgeBaseId}/documents")
    public PageResponse<DocumentResponse> list(@PathVariable("knowledgeBaseId") UUID knowledgeBaseId,
                                               @RequestParam(name = "page", defaultValue = "0") int page,
                                               @RequestParam(name = "size", defaultValue = "20") int size) {
        return service.list(knowledgeBaseId, page, size);
    }

    /** 查询文档元数据和处理状态；文档不存在时返回 404，不返回原文件内容。 */
    @GetMapping("/documents/{id}")
    public DocumentResponse getById(@PathVariable("id") UUID id) {
        return service.getById(id);
    }
}
