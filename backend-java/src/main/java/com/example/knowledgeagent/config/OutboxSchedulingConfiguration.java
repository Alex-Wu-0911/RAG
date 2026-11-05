package com.example.knowledgeagent.config;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@Profile("db")
@ConditionalOnProperty(name = "outbox.publisher.enabled", havingValue = "true")
@EnableScheduling
@SuppressWarnings("all")
public class OutboxSchedulingConfiguration {
}
