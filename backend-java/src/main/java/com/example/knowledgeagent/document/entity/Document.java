package com.example.knowledgeagent.document.entity;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

/** 文档元数据，不保存文件正文或向量。 */
@Entity
@Table(name = "documents", schema = "biz")
public class Document {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "knowledge_base_id", nullable = false, updatable = false)
    private UUID knowledgeBaseId;

    @Column(name = "filename", nullable = false, length = 255, updatable = false)
    private String filename;

    @Column(name = "storage_key", nullable = false, length = 255, updatable = false)
    private String storageKey;

    @Column(name = "size_bytes", nullable = false, updatable = false)
    private long sizeBytes;

    @Column(name = "content_hash", nullable = false, length = 64, updatable = false)
    private String contentHash;

    // 存字符串而非枚举序号，和 V4 的状态约束保持一致。
    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private DocumentStatus status;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Document() {
    }

    public Document(UUID knowledgeBaseId, String filename, String storageKey,
                    long sizeBytes, String contentHash) {
        this.knowledgeBaseId = knowledgeBaseId;
        this.filename = filename;
        this.storageKey = storageKey;
        this.sizeBytes = sizeBytes;
        this.contentHash = contentHash;
        this.status = DocumentStatus.PENDING;
    }

    public void changeStatus(DocumentStatus status) {
        this.status = status;
    }

    @PrePersist
    @SuppressWarnings("unused")
    private void onCreate() {
        Instant now = Instant.now();
        this.createdAt = now;
        this.updatedAt = now;
    }

    @PreUpdate
    private void onUpdate() {
        this.updatedAt = Instant.now();
    }

    public UUID getId() {
        return id;
    }

    public UUID getKnowledgeBaseId() {
        return knowledgeBaseId;
    }

    public String getFilename() {
        return filename;
    }

    public String getStorageKey() {
        return storageKey;
    }

    public long getSizeBytes() {
        return sizeBytes;
    }

    public String getContentHash() {
        return contentHash;
    }

    public DocumentStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
