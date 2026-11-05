package com.example.knowledgeagent.outbox.service;

import com.example.knowledgeagent.outbox.repository.OutboxRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.concurrent.TimeUnit;

@Service
@Profile("db")
@SuppressWarnings("all")
public class OutboxDispatchService {
    private static final Logger log = LoggerFactory.getLogger(OutboxDispatchService.class);
    private final OutboxRepository outbox;
    private final KafkaTemplate<String, String> kafka;

    public OutboxDispatchService(OutboxRepository outbox, KafkaTemplate<String, String> kafka) {
        this.outbox = outbox;
        this.kafka = kafka;
    }

    // 一条消息一个事务，等待 Kafka 确认期间保持行锁。
    @Transactional
    public boolean dispatchNext() {
        var pending = outbox.lockNextPending();
        if (pending.isEmpty()) {
            return false;
        }
        var event = pending.get();
        try {
            kafka.send(event.topic(), event.messageKey().toString(), event.payload())
                    .get(15, TimeUnit.SECONDS);
        } catch (Exception failure) {
            if (failure instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            // 5、10、20……秒退避，最多 5 分钟；不丢弃消息。
            int delay = (int) Math.min(300L, 5L << Math.min(event.attemptCount(), 6));
            Throwable cause = failure.getCause() == null ? failure : failure.getCause();
            outbox.scheduleRetry(event.id(), delay, cause.toString());
            log.warn("Outbox send failed: eventId={}, retryIn={}s, reason={}", event.id(), delay, cause.toString());
            return true;
        }
        // 数据库写入失败时让整个事务回滚，不把它误判成 Kafka 发送失败。
        outbox.markSent(event.id());
        log.info("Outbox sent: eventId={}, topic={}, key={}", event.id(), event.topic(), event.messageKey());
        return true;
    }
}
