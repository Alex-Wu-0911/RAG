package com.example.knowledgeagent.common.error;

import org.springframework.http.HttpStatus;

/** 错误码保持稳定；HTTP 状态表示类别，错误码表示业务原因。 */
@SuppressWarnings("all")
public enum ErrorCode {
    INVALID_REQUEST(HttpStatus.BAD_REQUEST, "请求格式或参数错误"),
    VALIDATION_FAILED(HttpStatus.BAD_REQUEST, "参数校验失败"),
    RESOURCE_NOT_FOUND(HttpStatus.NOT_FOUND, "资源不存在"),
    METHOD_NOT_ALLOWED(HttpStatus.METHOD_NOT_ALLOWED, "不支持此请求方法"),
    REQUEST_CONFLICT(HttpStatus.CONFLICT, "请求与当前资源状态冲突"),
    PAYLOAD_TOO_LARGE(HttpStatus.PAYLOAD_TOO_LARGE, "上传内容超过大小限制"),
    UNSUPPORTED_FILE_TYPE(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "仅支持 Markdown 和文本型 PDF"),
    UNSUPPORTED_MEDIA_TYPE(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "不支持此请求内容类型"),
    INTERNAL_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "服务暂时不可用，请稍后重试");

    private final HttpStatus status;
    private final String message;

    ErrorCode(HttpStatus status, String message) {
        this.status = status;
        this.message = message;
    }

    public HttpStatus status() {
        return status;
    }

    public String message() {
        return message;
    }
}
