package com.example.knowledgeagent.outbox.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@Profile("db")
@ConditionalOnProperty(name = "outbox.publisher.enabled", havingValue = "true")
@SuppressWarnings("all")
public class OutboxPublisher {
    private final OutboxDispatchService dispatcher;
    private final int batchSize;

    public OutboxPublisher(OutboxDispatchService dispatcher,
                           @Value("${outbox.publisher.batch-size:10}") int batchSize) {
        this.dispatcher = dispatcher;
        this.batchSize = batchSize;
    }

    @Scheduled(fixedDelayString = "${outbox.publisher.fixed-delay-ms:2000}", initialDelay = 2000)
    public void publish() {
        for (int index = 0; index < batchSize && !Thread.currentThread().isInterrupted(); index++) {
            if (!dispatcher.dispatchNext()) {
                break;
            }
        }
    }
}
