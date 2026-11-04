package com.example.knowledgeagent.common.web;

import org.springframework.data.domain.Page;

import java.util.List;

/** 稳定的分页结构，不将 Spring Data Page 的内部结构作为接口协议。 */
@SuppressWarnings("all")
public record PageResponse<T>(List<T> items, int page, int size, long total) {
    public PageResponse {
        items = List.copyOf(items);
    }

    public static <T> PageResponse<T> from(Page<T> result) {
        return new PageResponse<>(result.getContent(), result.getNumber(),
                result.getSize(), result.getTotalElements());
    }
}
