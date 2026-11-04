package com.example.knowledgeagent.config;

import io.minio.MinioClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("storage")
@SuppressWarnings("all")
public class MinioConfiguration {
    @Bean
    public MinioClient minioClient(@Value("${storage.endpoint}") String endpoint,
                                   @Value("${storage.access-key}") String accessKey,
                                   @Value("${storage.secret-key}") String secretKey) {
        return MinioClient.builder().endpoint(endpoint).credentials(accessKey, secretKey).build();
    }
}
