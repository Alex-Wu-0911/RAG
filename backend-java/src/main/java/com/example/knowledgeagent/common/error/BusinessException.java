package com.example.knowledgeagent.common.error;

import java.util.Objects;

/** 可预期的业务失败；对外文案统一取自 ErrorCode，避免泄露底层异常。 */
public class BusinessException extends RuntimeException {
    private final ErrorCode errorCode;

    public BusinessException(ErrorCode errorCode) {
        super(Objects.requireNonNull(errorCode, "errorCode").message());
        this.errorCode = errorCode;
    }

    public ErrorCode getErrorCode() {
        return errorCode;
    }
}
