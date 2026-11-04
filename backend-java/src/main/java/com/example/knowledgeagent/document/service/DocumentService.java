package com.example.knowledgeagent.document.service;

import com.example.knowledgeagent.common.error.BusinessException;
import com.example.knowledgeagent.common.error.ErrorCode;
import com.example.knowledgeagent.common.web.PageResponse;
import com.example.knowledgeagent.document.dto.DocumentResponse;
import com.example.knowledgeagent.document.entity.Document;
import com.example.knowledgeagent.document.repository.DocumentRepository;
import com.example.knowledgeagent.knowledgebase.repository.KnowledgeBaseRepository;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import io.minio.RemoveObjectArgs;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;
import org.springframework.data.domain.PageRequest;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.OutputStream;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Locale;
import java.util.UUID;

@Service
@Profile("db & storage")
@SuppressWarnings("all")
public class DocumentService {
    private final DocumentRepository documents;
    private final KnowledgeBaseRepository knowledgeBases;
    private final MinioClient minio;
    private final String bucket;

    public DocumentService(DocumentRepository documents, KnowledgeBaseRepository knowledgeBases,
                           MinioClient minio, @Value("${storage.bucket}") String bucket) {
        this.documents = documents;
        this.knowledgeBases = knowledgeBases;
        this.minio = minio;
        this.bucket = bucket;
    }

    // 对象上传不放在数据库事务内；Repository 负责保存元数据的短事务。
    public UploadResult upload(UUID knowledgeBaseId, MultipartFile file) throws Exception {
        if (!knowledgeBases.existsById(knowledgeBaseId)) {
            throw new BusinessException(ErrorCode.RESOURCE_NOT_FOUND);
        }
        String filename = file.getOriginalFilename();
        if (file.isEmpty() || filename == null || filename.isBlank() || filename.length() > 255) {
            throw new BusinessException(ErrorCode.INVALID_REQUEST);
        }
        if (file.getSize() > 20L * 1024 * 1024) {
            throw new BusinessException(ErrorCode.PAYLOAD_TOO_LARGE);
        }
        String lowerName = filename.toLowerCase(Locale.ROOT);
        if (!lowerName.endsWith(".md") && !lowerName.endsWith(".pdf")) {
            throw new BusinessException(ErrorCode.UNSUPPORTED_FILE_TYPE);
        }

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (var input = new DigestInputStream(file.getInputStream(), digest)) {
            input.transferTo(OutputStream.nullOutputStream());
        }
        String hash = HexFormat.of().formatHex(digest.digest());
        var existing = documents.findByKnowledgeBaseIdAndContentHash(knowledgeBaseId, hash);
        if (existing.isPresent()) {
            return new UploadResult(DocumentResponse.from(existing.get()), false);
        }

        boolean pdf = lowerName.endsWith(".pdf");
        String storageKey = knowledgeBaseId + "/" + UUID.randomUUID() + (pdf ? ".pdf" : ".md");
        try (var input = file.getInputStream()) {
            minio.putObject(PutObjectArgs.builder().bucket(bucket).object(storageKey)
                    .stream(input, file.getSize(), -1)
                    .contentType(pdf ? "application/pdf" : "text/markdown; charset=utf-8")
                    .build());
        }
        Document document = new Document(knowledgeBaseId, filename, storageKey, file.getSize(), hash);
        try {
            Document saved = documents.saveAndFlush(document);
            return new UploadResult(DocumentResponse.from(saved), true);
        } catch (RuntimeException exception) {
            // 数据库保存失败，移除刚上传的对象，避免留下无记录的文件。
            minio.removeObject(RemoveObjectArgs.builder().bucket(bucket).object(storageKey).build());
            throw exception;
        }
    }

    @Transactional(readOnly = true)
    public PageResponse<DocumentResponse> list(UUID knowledgeBaseId, int page, int size) {
        if (!knowledgeBases.existsById(knowledgeBaseId)) {
            throw new BusinessException(ErrorCode.RESOURCE_NOT_FOUND);
        }
        if (page < 0 || size < 1 || size > 100) {
            throw new BusinessException(ErrorCode.INVALID_REQUEST);
        }
        return PageResponse.from(documents
                .findByKnowledgeBaseIdOrderByCreatedAtDescIdDesc(knowledgeBaseId, PageRequest.of(page, size))
                .map(DocumentResponse::from));
    }

    @Transactional(readOnly = true)
    public DocumentResponse getById(UUID id) {
        return documents.findById(id)
                .map(DocumentResponse::from)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND));
    }

    public record UploadResult(DocumentResponse document, boolean created) {
    }
}
