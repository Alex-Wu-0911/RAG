package com.example.knowledgeagent.common.error;

import com.example.knowledgeagent.common.web.RequestIdFilter;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class GlobalExceptionHandlerTest {
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        // 测试控制器仅存在于 test 目录，不开放生产调试接口，也不改变 Security 配置。
        mvc = MockMvcBuilders.standaloneSetup(new TestController())
                .setControllerAdvice(new GlobalExceptionHandler())
                .addFilters(new RequestIdFilter())
                .build();
    }

    @Test
    void businessErrorUsesItsStatusAndStableCode() throws Exception {
        mvc.perform(get("/test/business").header("X-Request-Id", "learning-001"))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(header().string("X-Request-Id", "learning-001"))
                .andExpect(jsonPath("$.code").value("UNSUPPORTED_FILE_TYPE"))
                .andExpect(jsonPath("$.requestId").value("learning-001"))
                .andExpect(jsonPath("$.fieldErrors").isEmpty());
    }

    @Test
    void validationErrorNamesTheFieldWithoutEchoingItsValue() throws Exception {
        mvc.perform(post("/test/validate").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fieldErrors[0].field").value("name"))
                .andExpect(jsonPath("$.fieldErrors[0].message").value("名称不能为空"))
                .andExpect(jsonPath("$.fieldErrors[0].rejectedValue").doesNotExist());
    }

    @Test
    void malformedJsonRemainsBadRequest() throws Exception {
        mvc.perform(post("/test/validate").contentType(MediaType.APPLICATION_JSON).content("{"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
    }

    @Test
    void missingParameterRemainsBadRequest() throws Exception {
        mvc.perform(get("/test/parameter"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
    }

    @Test
    void wrongMethodPreservesAllowHeader() throws Exception {
        mvc.perform(post("/test/business"))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(header().string("Allow", containsString("GET")))
                .andExpect(jsonPath("$.code").value("METHOD_NOT_ALLOWED"));
    }

    @Test
    void unsupportedContentTypeRemains415() throws Exception {
        mvc.perform(post("/test/validate").contentType(MediaType.TEXT_PLAIN).content("text"))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.code").value("UNSUPPORTED_MEDIA_TYPE"));
    }

    @Test
    void unknownFailureDoesNotLeakExceptionDetails() throws Exception {
        mvc.perform(get("/test/unexpected"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.message").value("服务暂时不可用，请稍后重试"))
                .andExpect(content().string(not(containsString("secret-database-password"))))
                .andExpect(jsonPath("$.trace").doesNotExist());
    }

    @Test
    void absentRequestIdIsGeneratedAndMatchesResponseBody() throws Exception {
        var response = mvc.perform(get("/test/business"))
                .andExpect(header().exists("X-Request-Id"))
                .andReturn().getResponse();
        String id = response.getHeader("X-Request-Id");
        assertThat(id).matches("[a-f0-9-]{36}");
        mvc.perform(get("/test/business").header("X-Request-Id", id))
                .andExpect(jsonPath("$.requestId").value(id));
        assertThat(response.getContentAsString()).contains(id);
    }

    @Test
    void invalidRequestIdIsReplacedAndMdcIsRestored() throws Exception {
        String previous = MDC.get("requestId");
        MDC.put("requestId", "outer-context");
        try {
            var response = mvc.perform(get("/test/unexpected")
                            .header("X-Request-Id", "x".repeat(65)))
                    .andReturn().getResponse();
            assertThat(response.getHeader("X-Request-Id")).matches("[a-f0-9-]{36}");
            assertThat(MDC.get("requestId")).isEqualTo("outer-context");
        } finally {
            if (previous == null) MDC.remove("requestId");
            else MDC.put("requestId", previous);
        }
    }

    @RestController
    static class TestController {
        @GetMapping("/test/business")
        void business() {
            throw new BusinessException(ErrorCode.UNSUPPORTED_FILE_TYPE);
        }

        @GetMapping("/test/unexpected")
        void unexpected() {
            throw new IllegalStateException("secret-database-password");
        }

        @PostMapping(value = "/test/validate", consumes = MediaType.APPLICATION_JSON_VALUE)
        void validate(@Valid @RequestBody TestInput input) {
        }

        @GetMapping("/test/parameter")
        void parameter(@RequestParam("name") String name) {
        }
    }

    record TestInput(@NotBlank(message = "名称不能为空") String name) {
    }
}
