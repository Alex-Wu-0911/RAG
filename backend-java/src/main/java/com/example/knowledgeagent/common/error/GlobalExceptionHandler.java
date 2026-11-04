package com.example.knowledgeagent.common.error;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import com.example.knowledgeagent.common.web.RequestIdFilter;

@RestControllerAdvice
@SuppressWarnings("all")
public class GlobalExceptionHandler extends ResponseEntityExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<Object> handleBusiness(BusinessException exception, WebRequest request) {
        ErrorCode code = exception.getErrorCode();
        return ResponseEntity.status(code.status()).body(error(code, request, List.of()));
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException exception, HttpHeaders headers,
            HttpStatusCode status, WebRequest request) {
        List<ErrorResponse.FieldViolation> violations = exception.getBindingResult().getFieldErrors()
                .stream()
                .map(field -> new ErrorResponse.FieldViolation(field.getField(),
                        field.getDefaultMessage() == null ? "参数不合法" : field.getDefaultMessage()))
                .toList();
        return super.handleExceptionInternal(exception,
                error(ErrorCode.VALIDATION_FAILED, request, violations), headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleExceptionInternal(Exception exception, Object body,
            HttpHeaders headers, HttpStatusCode status, WebRequest request) {
        // 保留框架决定的状态和响应头，例如 405 的 Allow；不将所有异常误报为 500。
        ErrorCode code = switch (status.value()) {
            case 400 -> ErrorCode.INVALID_REQUEST;
            case 404 -> ErrorCode.RESOURCE_NOT_FOUND;
            case 405 -> ErrorCode.METHOD_NOT_ALLOWED;
            case 409 -> ErrorCode.REQUEST_CONFLICT;
            case 413 -> ErrorCode.PAYLOAD_TOO_LARGE;
            case 415 -> ErrorCode.UNSUPPORTED_MEDIA_TYPE;
            default -> null;
        };
        ErrorResponse response;
        if (status.is5xxServerError()) {
            log.error("MVC request failed, requestId={}, exceptionType={}",
                    requestId(request), exception.getClass().getName());
            response = error(ErrorCode.INTERNAL_ERROR, request, List.of());
        } else if (code != null) {
            response = error(code, request, List.of());
        } else {
            response = new ErrorResponse("HTTP_" + status.value(), "请求无法完成",
                    requestId(request), List.of());
        }
        return super.handleExceptionInternal(exception, response, headers, status, request);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Object> handleUnexpected(Exception exception, WebRequest request) {
        // 不向客户端返回底层异常文案，也不把可能包含用户输入的异常文案写入日志。
        log.error("Unexpected request failure, requestId={}, exceptionType={}",
                requestId(request), exception.getClass().getName());
        return ResponseEntity.internalServerError()
                .body(error(ErrorCode.INTERNAL_ERROR, request, List.of()));
    }

    private ErrorResponse error(ErrorCode code, WebRequest request,
                                List<ErrorResponse.FieldViolation> fields) {
        return new ErrorResponse(code.name(), code.message(), requestId(request), fields);
    }

    private String requestId(WebRequest request) {
        Object value = request.getAttribute(RequestIdFilter.ATTRIBUTE, RequestAttributes.SCOPE_REQUEST);
        return value instanceof String id ? id : "unknown";
    }
}
