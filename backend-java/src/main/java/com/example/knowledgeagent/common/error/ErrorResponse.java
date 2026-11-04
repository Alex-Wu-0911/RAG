package com.example.knowledgeagent.common.error;

import java.util.List;

/** 所有 MVC 错误使用同一种响应结构，不包含堆栈或参数原值。 */
public record ErrorResponse(
        String code,
        String message,
        String requestId,
        List<FieldViolation> fieldErrors) {

    public ErrorResponse {
        fieldErrors = List.copyOf(fieldErrors);
    }

    public record FieldViolation(String field, String message) {
    }
}
