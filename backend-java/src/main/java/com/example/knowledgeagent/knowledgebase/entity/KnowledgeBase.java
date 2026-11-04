package com.example.knowledgeagent.knowledgebase.entity;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

/** 映射 biz.knowledge_bases，不能直接作为接口响应使用。 */
@Entity
@Table(name = "knowledge_bases", schema = "biz")
@SuppressWarnings("all")
public class KnowledgeBase {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "name", nullable = false, length = 100)
    private String name;

    @Column(name = "description", nullable = false, length = 1000)
    private String description;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    // JPA 加载数据库记录时需要无参构造器。
    protected KnowledgeBase() {
    }

    public KnowledgeBase(String name, String description) {
        updateDetails(name, description);
    }

    /** 保持实体基本约束；接口层后续仍需对输入 DTO 做参数校验。 */
    public void updateDetails(String name, String description) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("知识库名称不能为空");
        }
        String normalizedName = name.strip();
        String normalizedDescription = description == null ? "" : description;
        if (normalizedName.codePointCount(0, normalizedName.length()) > 100) {
            throw new IllegalArgumentException("知识库名称不能超过 100 个字符");
        }
        if (normalizedDescription.codePointCount(0, normalizedDescription.length()) > 1000) {
            throw new IllegalArgumentException("知识库描述不能超过 1000 个字符");
        }
        this.name = normalizedName;
        this.description = normalizedDescription;
    }

    @PrePersist
    private void onCreate() {
        Instant now = Instant.now();
        this.createdAt = now;
        this.updatedAt = now;
    }

    @PreUpdate
    @SuppressWarnings("unused")
    private void onUpdate() {
        this.updatedAt = Instant.now();
    }

    public UUID getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getDescription() {
        return description;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
