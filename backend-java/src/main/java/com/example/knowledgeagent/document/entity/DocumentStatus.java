package com.example.knowledgeagent.document.entity;

public enum DocumentStatus {
    PENDING,     // 已上传，等待处理
    PROCESSING,  // Python 正在处理
    READY,       // 处理完成，可参与检索
    FAILED       // 处理失败
}
