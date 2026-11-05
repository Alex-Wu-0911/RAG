# 本地基础设施

Docker Compose 管理 PostgreSQL（含 pgvector）、MinIO 和 Kafka。Java 与 FastAPI 仍在本机单独启动。

## 文件说明

- compose.yaml：数据库容器、端口、数据卷和健康检查。
- .env.example：可提交的环境变量示例。
- .env：本地实际配置，已加入当前目录的 .gitignore；首次创建时生成随机密码。

## 启动与检查

先启动 Docker Desktop，切换到本目录后运行：

```powershell
docker compose up -d --wait postgres
docker compose ps
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT current_database(), current_user;"'
```

连接地址为 localhost，默认宿主机端口 15432（容器内部仍为 5432），数据库 knowledge_agent，用户 rag，密码查看本机 .env。若端口已被使用，可修改 POSTGRES_PORT 后重试。

## 数据持久化

postgres_data 命名卷保存数据。docker compose stop 或 docker compose down 不删除命名卷，之后重新启动可继续使用。

不要使用 docker compose down -v，除非明确需要删除全部本地数据库数据。

POSTGRES_DB、POSTGRES_USER、POSTGRES_PASSWORD 用于空数据卷的首次初始化。修改 .env 不会自动修改已经创建的数据库账号或密码。

## 当前边界

采用 pgvector/pgvector:0.8.7-pg16-bookworm 镜像，在 PostgreSQL 16 上增加 pgvector 扩展。继续使用 postgres_data 数据卷。镜像包含扩展文件，但每个数据库还需要执行 CREATE EXTENSION 才能启用；具体操作见下文。

下一步才将 Spring Boot 的 db profile 连接到此数据库。Compose 的 .env 不会自动成为 Java 进程的环境变量。

## MinIO 对象存储

Java 后续通过 S3 API 上传原始文件到 MinIO，数据库 storage_key 保存对象 Key。暂不写 Java 本地 storage 文件夹。

### 启动

在 deploy 目录执行：

```powershell
docker compose up -d minio
docker compose run --rm minio-init
docker compose ps
```

minio-init 是一次性 bucket 初始化工具，成功创建后退出；再次执行不会重复创建 bucket。

### 地址与登录

- S3 API：http://localhost:19000，供电脑上运行的 Java/Python 使用。
- 控制台：http://localhost:19001，供浏览器登录查看文件。
- Docker 网络中的服务使用 http://minio:9000，不使用 localhost:19000。
- 用户名、密码分别为本机 .env 的 MINIO_ROOT_USER、MINIO_ROOT_PASSWORD。
- bucket 默认为 rag-documents，可理解为存放文档对象的容器。
- Java 的 MinIO 客户端尚未实现，Compose 环境变量也不会自动进入 Java 进程。

### 持久化

minio_data 命名卷挂载到 /data，容器重建后对象仍保留。数据仍占用本机 Docker 磁盘，由 MinIO 管理，不是云端存储。

不要执行 docker compose down -v，除非明确需要删除 PostgreSQL 和 MinIO 的全部本地数据。

本地开发使用 Silo（PGSTY 维护的 MinIO 社区分支），采用已验证可公开访问的 Docker Hub 版本并固定镜像摘要。保留 minio 服务名、MINIO_* 变量及 S3 接口。初始化工具使用同一镜像内置的 mcli，不再依赖官方 Quay 镜像。原数据库配置与数据卷保留不变。

### 验证

```powershell
Invoke-WebRequest http://localhost:19000/minio/health/live
docker compose run --rm --entrypoint /bin/sh minio-init -c 'mcli alias set storage http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" && mcli ls storage'
```

健康接口应返回 HTTP 200，对象列表中应出现 rag-documents。也可直接在控制台查看 bucket。

### 镜像拉取 401 的处理

原来的 quay.io/minio/minio 与 quay.io/minio/mc 已无法公开拉取，配置现改用 docker.io/pgsty/silo；不是要求用户登录 Quay。

在项目根目录也可以用下面的命令启动，避免找不到 Compose 文件：

```powershell
docker compose -f deploy/compose.yaml pull minio minio-init
docker compose -f deploy/compose.yaml up -d minio
docker compose -f deploy/compose.yaml run --rm minio-init
```

在 deploy 目录执行时省略 -f deploy/compose.yaml 即可。凭证、端口、bucket 和数据卷不变，无需删除现有卷。

镜像资料：https://github.com/pgsty/silo

## 启用 pgvector

在项目根目录的 PowerShell 执行：

```powershell
docker compose -f deploy/compose.yaml pull postgres
docker compose -f deploy/compose.yaml up -d --wait postgres
docker compose -f deploy/compose.yaml exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /opt/rag/enable-pgvector.sql'
```

第二条命令会重建 PostgreSQL 容器，期间数据库短暂断开；原数据卷、业务表和连接端口继续使用，不要删除数据卷。

最后一条执行本目录的 enable-pgvector.sql，应该返回扩展版本 0.8.7 和 dimensions = 3。脚本可以重复执行，适用于已经存在的数据库；不依赖只在空数据卷上运行的初始化脚本。

当前只准备向量存储能力，还没有创建文本块表或写入 Embedding。后续再由 Python 保存文本块和对应向量。

资料：https://github.com/pgvector/pgvector#docker
## Kafka：异步文档处理第 1 步

采用官方 apache/kafka:4.4.0 JVM 镜像并固定已验证的镜像摘要。单节点 KRaft，broker 和 controller 在同一容器内，不需要 ZooKeeper。此配置用于本地开发，单副本不提供节点级高可用。

### 地址和数据

- 本机 Java/Python 使用 localhost:19092。
- Compose 内其他容器使用 kafka:29092。
- 9092 是 Kafka 容器内的外部监听端口，映射到本机 19092；controller 的 29093 不暴露到本机。
- 可用 deploy/.env 中的 KAFKA_PORT 修改本机端口，默认值已在 Compose 中提供，不必新增真实 .env 项也能启动。
- kafka_data 命名卷保存消息日志和 KRaft 元数据；重建容器继续使用原卷。CLUSTER_ID 与该卷保持一致，不要随意修改。

### 启动并创建 Topic

在项目根目录执行：

```powershell
docker compose -f deploy/compose.yaml up -d --wait kafka
docker compose -f deploy/compose.yaml run --rm kafka-init
docker compose -f deploy/compose.yaml ps
```

kafka 应显示 healthy。kafka-init 等待 broker 健康，然后创建 rag.document.process；采用 1 个分区、1 个副本，先供单 Worker 顺序处理。重复运行初始化不会清空 Topic。kafka-init 正常完成后退出。

查看 Topic：

```powershell
docker compose -f deploy/compose.yaml exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:29092 --describe --topic rag.document.process
```

预期包含 PartitionCount: 1、ReplicationFactor: 1，以及已选出的 Leader。

### 验证真实消息收发

在项目根目录执行：

```powershell
.\deploy\test-kafka.ps1
```

脚本创建名称带随机编号的临时 rag.smoke.* Topic，用 console producer 发送一条唯一的 ASCII 测试消息，再用 console consumer 读取并核对，最后删除自己创建的临时 Topic。成功输出 PASS: produced and consumed ...。这只验证 Kafka 基础消息收发，不会生成 Embedding 或更改文档状态。

### 常用检查

```powershell
docker compose -f deploy/compose.yaml logs --tail 80 kafka
Test-NetConnection localhost -Port 19092
```

如果端口冲突或被 Windows 保留，修改 KAFKA_PORT 后重新创建 Kafka；本机客户端连接端口也要一起更新。TCP 检查只表示端口可连接，不能代替 Kafka 消息收发验证。

### 当前进度

本步只添加 Kafka、Topic 初始化和烟雾测试脚本。下一步再增加任务表和 Outbox 表；Java 生产者与 Python 消费者尚未接入。

已验证：官方镜像标签和摘要在 Docker Hub Registry 可访问、Compose 解析与监听地址配置、原 PostgreSQL/MinIO 服务保留，以及 PowerShell 验证脚本语法。

待验证：实际容器启动、Topic 创建和真实收发。Codex 命令环境无法访问 Docker 引擎命名管道，因此需要在 VS Code Terminal 执行上述命令，不能把配置校验当成运行成功。

官方资料：https://kafka.apache.org/44/getting-started/docker/