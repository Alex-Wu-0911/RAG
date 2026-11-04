package com.example.knowledgeagent.knowledgebase.service;

import com.example.knowledgeagent.common.error.BusinessException;
import com.example.knowledgeagent.common.error.ErrorCode;
import com.example.knowledgeagent.common.web.PageResponse;
import com.example.knowledgeagent.knowledgebase.dto.KnowledgeBaseResponse;
import com.example.knowledgeagent.knowledgebase.entity.KnowledgeBase;
import com.example.knowledgeagent.knowledgebase.repository.KnowledgeBaseRepository;
import org.springframework.context.annotation.Profile;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
@Profile("db")
@Transactional(readOnly = true)
@SuppressWarnings("all")
public class KnowledgeBaseService {
    private final KnowledgeBaseRepository repository;

    public KnowledgeBaseService(KnowledgeBaseRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public KnowledgeBaseResponse create(String name, String description) {
        KnowledgeBase knowledgeBase = new KnowledgeBase(name, description);
        return KnowledgeBaseResponse.from(repository.save(knowledgeBase));
    }

    public PageResponse<KnowledgeBaseResponse> list(int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new BusinessException(ErrorCode.INVALID_REQUEST);
        }
        return PageResponse.from(repository
                .findAllByOrderByCreatedAtDescIdDesc(PageRequest.of(page, size))
                .map(KnowledgeBaseResponse::from));
    }

    public KnowledgeBaseResponse getById(UUID id) {
        return repository.findById(id)
                .map(KnowledgeBaseResponse::from)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND));
    }
}
