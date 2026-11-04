# Knowledge Agent Java Backend

当前为 Maven / Spring Boot 工程骨架，尚未实现用户、知识库、文档、问答等业务功能。

## 开发环境

- JDK 21
- Maven 3.6.3 或更新版本（本机已安装 Maven，无需 Wrapper）
- IntelliJ IDEA：打开本目录的 pom.xml，设为 Maven 项目；Project SDK 和 Maven Runner JRE 均选择 JDK 21。

## 启动

在本目录执行 `mvn spring-boot:run`，或运行 `KnowledgeAgentApplication`。
默认 local 配置不连接数据库。访问 `http://localhost:8080/actuator/health` 检查服务状态。
当前仅开放健康检查，业务接口默认拒绝访问。Security 依赖不代表已实现登录或 JWT。

## 数据库模式

创建 PostgreSQL 数据库后，设置 DB_URL、DB_USER、DB_PASSWORD，运行：

`mvn spring-boot:run -Dspring-boot.run.profiles=db`

数据库表和 Flyway 迁移尚未实现，后续迁移文件放在 src/main/resources/db/migration。
不要同时启用 local 和 db：local 会禁用数据库自动配置。

## 模块分工

- auth：用户认证与授权
- knowledgebase：知识库及成员管理
- document：文档元数据与上传
- ingestion：入库任务、重试和幂等
- conversation：会话及消息
- agent：Agent 运行记录（编排逻辑由 Python 负责）
- client：调用内部 Python 服务
- common：统一响应与异常等公共组件
- config：Spring 配置

上述空目录为后续业务实现预留。LangChain、LangGraph 和向量检索在 Python 服务实现，Java 暂不引入 Spring AI。

## 验证

`mvn verify`

当前无业务测试；此命令用于解析依赖、编译和打包。业务实现时再补相应测试。
