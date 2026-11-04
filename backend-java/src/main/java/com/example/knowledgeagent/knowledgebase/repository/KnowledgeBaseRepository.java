package com.example.knowledgeagent.knowledgebase.repository;

import com.example.knowledgeagent.knowledgebase.entity.KnowledgeBase;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface KnowledgeBaseRepository extends JpaRepository<KnowledgeBase, UUID> {
    Page<KnowledgeBase> findAllByOrderByCreatedAtDescIdDesc(Pageable pageable);
}
