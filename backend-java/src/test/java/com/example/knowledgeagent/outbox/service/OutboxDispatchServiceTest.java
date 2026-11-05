package com.example.knowledgeagent.outbox.service;

import com.example.knowledgeagent.outbox.repository.OutboxRepository;
import org.junit.jupiter.api.Test;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.*;

@SuppressWarnings("all")
class OutboxDispatchServiceTest {
    @Test
    void waitsForAcknowledgementBeforeMarkingSent() throws Exception {
        var outbox = new TestOutbox();
        var kafka = new TestKafka();
        var service = new OutboxDispatchService(outbox, kafka);
        try (var executor = Executors.newSingleThreadExecutor()) {
            var dispatch = executor.submit(service::dispatchNext);
            assertThat(kafka.called.await(3, TimeUnit.SECONDS)).isTrue();
            assertThat(outbox.sent).isFalse();
            kafka.result.complete(null);
            assertThat(dispatch.get(3, TimeUnit.SECONDS)).isTrue();
        } finally {
            kafka.destroy();
        }
        assertThat(outbox.sent).isTrue();
        assertThat(outbox.retryDelay).isZero();
        assertThat(kafka.key).isEqualTo(outbox.event.messageKey().toString());
        assertThat(kafka.payload).isEqualTo(outbox.event.payload());
    }

    @Test
    void failedAcknowledgementSchedulesRetryWithoutMarkingSent() {
        var outbox = new TestOutbox();
        var kafka = new TestKafka();
        kafka.result.completeExceptionally(new IllegalStateException("broker unavailable"));
        try {
            assertThat(new OutboxDispatchService(outbox, kafka).dispatchNext()).isTrue();
        } finally {
            kafka.destroy();
        }
        assertThat(outbox.sent).isFalse();
        assertThat(outbox.retryDelay).isEqualTo(5);
        assertThat(outbox.error).contains("broker unavailable");
    }

    @Test
    void databaseFailureAfterAcknowledgementPropagatesForTransactionRollback() {
        var outbox = new TestOutbox();
        outbox.failOnMarkSent = true;
        var kafka = new TestKafka();
        kafka.result.complete(null);
        try {
            assertThatThrownBy(() -> new OutboxDispatchService(outbox, kafka).dispatchNext())
                    .isInstanceOf(IllegalStateException.class).hasMessage("database unavailable");
        } finally {
            kafka.destroy();
        }
        assertThat(outbox.retryDelay).isZero();
    }

    static class TestOutbox extends OutboxRepository {
        final PendingEvent event = new PendingEvent(UUID.randomUUID(), "rag.document.process",
                UUID.randomUUID(), "{\"task_id\":\"test\"}", 0);
        volatile boolean sent;
        boolean failOnMarkSent;
        int retryDelay;
        String error;

        TestOutbox() { super(null); }

        @Override
        public Optional<PendingEvent> lockNextPending() { return Optional.of(event); }

        @Override
        public void markSent(UUID id) {
            if (failOnMarkSent) { throw new IllegalStateException("database unavailable"); }
            sent = true;
        }

        @Override
        public void scheduleRetry(UUID id, int delay, String reason) {
            retryDelay = delay;
            error = reason;
        }
    }

    // 测试中手动控制确认结果，不连接 Kafka，不依赖 Mockito 动态代理。
    static class TestKafka extends KafkaTemplate<String, String> {
        final CompletableFuture<SendResult<String, String>> result = new CompletableFuture<>();
        final CountDownLatch called = new CountDownLatch(1);
        String key;
        String payload;

        TestKafka() { super(new DefaultKafkaProducerFactory<>(Map.of())); }

        @Override
        public CompletableFuture<SendResult<String, String>> send(String topic, String key, String data) {
            this.key = key;
            this.payload = data;
            called.countDown();
            return result;
        }
    }
}
