# RAG AI Service

当前已实现 Markdown 读取、分块、真实 Embedding、pgvector 入库、相似度检索及基础 RAG 问答。/chat 已替换早期的问题回显实现；以下按学习步骤保留演进说明，当前调用方式见第十步。

## 目录

- main.py：应用、请求/响应模型及接口。
- storage.py：对象存储 SDK 连接及读取。
- text_processing.py：LangChain 文本分块函数。
- embeddings.py：调用真实 OpenAI Embedding API。
- .env：本地对象存储配置，已被 Git 忽略。
- requirements.txt：项目直接依赖。
- requirements.lock.txt：首次安装后的完整固定版本，便于复现。
- .venv：本项目的 Python 虚拟环境，不提交 Git。

## 启动

在 ai-service 目录运行，无需激活虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

- main：main.py 模块名。
- app：main.py 中的 FastAPI 实例变量。
- uvicorn：接收 HTTP 请求、运行 FastAPI 应用的 ASGI 服务程序。
- --reload：修改 Python 文件后自动重启，适用于本地开发。
- Ctrl+C：停止服务。

IDE 中选择 ai-service/.venv/Scripts/python.exe 作为解释器，避免依赖装在一个 Python 中、运行时却使用另一个。

## 第一个接口

打开 http://localhost:8000/health，返回：

```json
{"status":"UP"}
```

阅读 main.py：

1. from fastapi import FastAPI：导入框架。
2. app = FastAPI(...)：创建应用。
3. @app.get('/health')：把 GET /health 映射到下面的函数，类似 Spring 的 @GetMapping。
4. def health()：请求到达时调用函数；现在使用普通 def，后续需要异步 I/O 时再学 async def。
5. return 字典：FastAPI 自动转成 JSON 响应。
6. -> dict[str, str]：Python 返回类型提示，表示键和值都是字符串。

## 自动接口文档

- http://localhost:8000/docs：Swagger UI，展开 GET /health，点击 Try it out，再点击 Execute。
- http://localhost:8000/openapi.json：框架生成的接口描述，包含路径、参数与响应结构。

框架会读取路由和类型信息生成文档，不需要自己写 HTML。

## 重新安装环境

本机已创建 .venv、安装依赖并写入本地对象存储配置。换一台电脑时，先参考 .env.example 创建 .env，再安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

以下是早期 FastAPI 入门阶段的回显示例；当前 /chat 已升级为第十步的 RAG 问答接口。健康检查仍可在 /docs 调用。

## 第二步：POST 请求体与 Pydantic

main.py 中 ChatRequest 继承 BaseModel，相当于 Java 的请求 DTO。

- knowledge_base_id: UUID：JSON 中是 UUID 字符串，解析后变成 Python UUID 对象。
- question: str：必填字符串。
- Field(min_length=1, max_length=4000)：问题长度为 1～4000，类似 @Size。
- @app.post('/chat')：定义 POST 接口。
- request: ChatRequest：FastAPI 从 JSON 请求体创建这个模型对象，并进行校验。
- -> ChatRequest：返回类型声明，FastAPI 据此生成响应文档和序列化结果。
- return request：回显收到的数据，没有检索或模型回答。

在 /docs 中展开 POST /chat，点击 Try it out，提交：

```json
{
  "knowledge_base_id": "550e8400-e29b-41d4-a716-446655440000",
  "question": "服务如何部署？"
}
```

成功返回 200 和相同内容。UUID 只验证格式，不查询知识库是否存在，因此练习时可以使用上面的示例 ID。

把 UUID 改成 abc，或者把 question 改成空字符串，再执行：FastAPI 返回 422，detail 列出错误字段。这是请求校验，没有调用 Java 的异常处理器。

空格组成的问题目前不会被自动去除；本步只学习类型和长度校验。

## 第三步：从对象存储读取 Markdown

新增 POST /documents/read，接收：

```json
{
  "storage_key": "知识库UUID/文件UUID.md"
}
```

在 http://localhost:19001 的 rag-documents bucket 中，找到 Java 上传的 Markdown，复制完整对象 Key。若在子目录里，必须包含目录前缀。不要填写原始文件名或带 http 的下载 URL。

然后打开 http://localhost:8000/docs，选择 POST /documents/read → Try it out → Execute。

响应字段：

- storage_key：请求的对象 Key。
- size_bytes：原文件字节数。
- text_length：解码后的文本字符数。
- preview：前 1000 个字符，尚未分块、检索或生成向量。

### 配置

新增 minio、python-dotenv 两项直接依赖。storage.py 显式读取 ai-service/.env；进程中已有的环境变量优先。

- MINIO_ENDPOINT：完整服务地址，例如 http://localhost:19000。
- MINIO_ACCESS_KEY：deploy/.env 中 MINIO_ROOT_USER 的值。
- MINIO_SECRET_KEY：deploy/.env 中 MINIO_ROOT_PASSWORD 的值。
- MINIO_BUCKET：rag-documents。

本机已配置，密码不写入源码。换环境时复制 .env.example 为 .env 并填写实际值。数据库仍保存文档 ID 与 storage_key，本接口暂不查询数据库。

### 阅读顺序

1. main.py 中 DocumentReadRequest：定义接收的 JSON。
2. @app.post('/documents/read')：声明接口，并用 summary 和函数说明生成文档。
3. read_object(...)：普通 Python 函数调用，跳到 storage.py 看实现。
4. client.get_object(...)：SDK 向对象存储发送请求，返回可读取的二进制响应。
5. response.read()：取得 bytes，finally 中关闭响应并释放 HTTP 连接。
6. content.decode('utf-8-sig')：将字节转换为文本，并兼容 UTF-8 BOM。
7. text[:1000]：Python 切片，取前 1000 个字符。
8. DocumentPreviewResponse：定义响应字段并自动生成响应文档。

此处使用普通 def，因为 SDK 是同步调用；不为了形式改成 async def。

仅接受 UTF-8 Markdown。不存在对象返回 404；扩展名不是 .md 返回 415；不是 UTF-8 文本返回 400。没有把 PDF 当纯文本读取，也没有实现 PDF 解析。

已使用真实对象验证：读取成功、字节数和文本长度、1000 字符预览、UTF-8 BOM、不存在对象与 PDF 拒绝。临时验证对象已清理。

## 第四步：文本分块预览

安装的是 langchain-text-splitters 组件，无需安装完整 LangChain，也不需要 API Key。

在 /docs 调用 POST /documents/chunks：

```json
{
  "storage_key": "知识库UUID/文件UUID.md",
  "chunk_size": 500,
  "chunk_overlap": 50
}
```

后两个参数可省略，使用上面的默认值。chunk_size 为 1～10000，chunk_overlap 必须非负且小于 chunk_size。计数单位是 Python 字符，不是 token 或 UTF-8 字节。

响应含 storage_key、chunk_size、chunk_overlap、total、chunks。每个片段包含：

- index：从 0 开始的片段序号。
- content：实际片段内容。
- length：len(content)，单位为字符。

### 核心代码

text_processing.py 中：

```python
splitter = RecursiveCharacterTextSplitter(
    chunk_size=chunk_size,
    chunk_overlap=chunk_overlap,
    length_function=len,
    separators=["\n\n", "\n", "。", "！", "？", " ", ""],
)
return splitter.split_text(text)
```

它优先尝试段落、换行、中文标点及空格，仍然过长时再按字符切开。chunk_size 是长度上限，不要求每块恰好 500 字符；chunk_overlap 是目标重叠长度，受分隔符边界影响，不保证每两块都刚好重叠 50 字符。

main.py 的 load_markdown 复用已有读取与 UTF-8 解码逻辑，读取预览和分块预览都使用它。分块接口调用 split_text，再通过 enumerate(parts) 为每一块生成序号。

### 动手观察

对同一份较长 Markdown，分别设置 500/50、200/20，比较 total、length 和相邻 content。短于块上限的文档可能只有一个片段，这是正常结果。

已验证真实对象读取后分块、默认与自定义参数、错误重叠参数、空文本处理，并确认原读取接口仍然可用。临时验证对象已清理。

本接口返回全部分块，只用于当前学习预览，不保存分块，不调用模型，不生成或保存向量。下一步才接真实 Embedding 服务，届时再配置所选服务的 API Key。

## 第五步：调用真实 Embedding API

模型调用代码在 embeddings.py，不是一次性验证脚本。它使用官方 openai SDK；LangChain 当前负责文本分块。

本地 .env 配置：

```dotenv
OPENAI_API_KEY=你的实际Key
EMBEDDING_MODEL=text-embedding-3-small
```

.env 已被 Git 忽略，.env.example 只包含占位符。OpenAI SDK 从环境变量读取 Key；修改 .env 后重启服务。

核心调用：

```python
response = client.embeddings.create(
    model=EMBEDDING_MODEL,
    input=texts[start:start + 128],
)
vectors.extend(item.embedding for item in response.data)
```

input 是一组片段，response.data 中每项 embedding 是一组浮点数。实现按每批最多 128 个片段请求，返回顺序与片段顺序一致。未启用模拟响应或自动重试。

### 接口

在 /docs 调用 POST /documents/embeddings：

```json
{
  "storage_key": "知识库UUID/文件UUID.md"
}
```

流程：从对象存储读取 Markdown → 用默认 500/50 参数分块 → 调用 embed_texts → 返回向量摘要。

响应包含：

- model：实际配置的模型名。
- chunk_count：片段数量。
- vector_count：返回的向量数量。
- dimensions：单个向量的维度。
- sample_vector：第一个向量的前 8 个数值，用于观察结果；完整向量存在本次函数的内存中，不写数据库。

本步没有向量缓存，每次调用都真实请求 API 并产生对应 API 用量。空白文档没有片段时返回 400，不调用模型。模型服务报错或网络连接失败时返回 502，不用固定数值替代真实结果。

已完成真实端到端验证：2 个片段获得 2 个 1536 维向量，接口返回 200。临时验证对象已清理。

本步只生成向量，没有语义检索和聊天回答；当时的 /chat 为学习用回显，当前已升级为第十步的 RAG 问答接口。下一步再将分块与向量存入数据库。

## 第六步：Python 连接 PostgreSQL

使用 psycopg 驱动，连接与 Java 相同的数据库。连接配置保存在本目录的 .env：

```dotenv
DB_HOST=localhost
DB_PORT=15432
DB_NAME=knowledge_agent
DB_USER=rag
DB_PASSWORD=与deploy/.env中的POSTGRES_PASSWORD一致
```

在 ai-service 目录运行只读检查：

```powershell
.\.venv\Scripts\python.exe database.py
```

脚本输出当前数据库、pgvector 版本，以及 biz.document_chunks 表是否存在。显示 not created 表示还需要使用 db,storage 配置重启 Spring Boot，让 Flyway 执行 V5 迁移；Python 不负责建表。

后续代码通过 get_connection() 获得连接：

```python
from database import get_connection

with get_connection() as connection:
    result = connection.execute("SELECT current_database()").fetchone()
```

with 代码块退出后自动关闭连接；正常退出提交事务，出现异常则回滚。这一步没有连接池，也没有写入文档或向量。

本次验证：连接 knowledge_agent 成功，pgvector 为 0.8.7；分块表尚未创建。依赖检查通过。

驱动文档：https://www.psycopg.org/psycopg3/docs/basic/usage.html

## 第七步：保存文本块和向量

vector_store.py 中的 save_document_chunks(document_id, knowledge_base_id, chunks, vectors) 负责入库，返回保存数量。两个 ID 对应 documents 表中的真实文档及其所属知识库，chunks 和 vectors 按顺序一一对应。

函数先删除该文档的旧分块，再按从 0 开始的序号批量插入新分块。删除与插入使用同一连接、同一事务：全部成功才提交，失败时回滚，因此插入失败不会丢失旧分块。

关键语法：

- %s 是 SQL 参数占位符，实际值单独传递，不使用字符串拼接 SQL。
- %s::public.vector 将传入的向量文本转换成数据库向量类型。这里用 str(vector) 把 Python 浮点列表转成如 [0.1, 0.2] 的文本；当前列要求实际包含 1536 个数字。
- executemany 对多条分块数据执行相同的 INSERT。
- zip(chunks, vectors, strict=True) 按位置配对文本和向量，数量不一致时报错并回滚。

本步只增加可调用的入库函数，没有新增 HTTP 接口，也不会自动调用 Embedding。下一步再通过处理接口串联读取、分块、真实 Embedding 和入库。

## 第八步：按文档 ID 处理并入库

新增同步接口：POST /documents/{document_id}/process，无请求体。在 /docs 填入通过 Java 上传得到的真实文档 ID 后执行。修改代码后需要重启 Uvicorn；若使用 --reload 则自动重载。

处理顺序：

1. document_repository.find_document 从数据库查询知识库 ID 和 storage_key，不由调用方重复填写。
2. 状态更新为 PROCESSING，从 MinIO 读取 UTF-8 Markdown。
3. 默认按 500 字符、50 字符重叠分块，调用真实 Embedding API。
4. save_document_chunks 替换旧分块，并在同一事务内把文档改为 READY。
5. 返回 document_id、status 和 chunk_count。

示例响应结构：

```json
{
  "document_id": "上传接口返回的文档UUID",
  "status": "READY",
  "chunk_count": 3
}
```

接口会等待处理完成才返回，没有后台任务或队列。重复调用会重新产生 Embedding API 用量，并替换分块。不存在的文档返回 404；空白内容返回 400；当前仅支持 .md，其他扩展名返回 415。处理失败时状态记为 FAILED；替换前的分块在新向量成功入库前仍保留。暂不支持并发处理同一文档，请等待上一次处理完成后再重试。

Java 的上传接口仍只保存文件和元数据，尚未自动调用此 Python 接口。/chat 现已在第十步升级为 RAG 问答；文档入库本身只准备了检索数据。

本步已通过真实数据库、MinIO 和 Embedding API 验证：首次处理 READY、重复处理不累积旧分块、向量维度为 1536、空白文档失败后保留旧分块、不存在的文档返回 404。临时验证数据及对象已清理。

## 第九步：相似度检索

接口：POST /knowledge-bases/{knowledge_base_id}/search。在 /docs 填入知识库 ID，并提交：

```json
{
  "question": "JVM 有哪些内存区域？",
  "top_k": 3
}
```

main.py 中 search_knowledge_base 调用同一个 Embedding 模型，把问题转成向量；vector_store.py 中 search_chunks 查询该知识库下 READY 文档的文本块。top_k 默认 3，可取 1 到 20，实际结果数量可能更少。

响应的 items 包含 document_id、filename、chunk_index、content 和 similarity，按相关程度从高到低返回。

SQL 中 <=> 是余弦距离运算符，越小越相近；similarity = 1 - 余弦距离，越大越相似。它不是百分比或正确率，不保证最高分文本一定能回答问题。当前没有设置相似度阈值，也没有添加向量近似索引，使用精确检索。

不存在或没有可检索文本块的知识库返回空 items；PROCESSING、FAILED 和 PENDING 文档不参与检索。每次检索都会真实调用 Embedding API，不调用聊天模型，不生成回答。

重启服务（或使用 --reload 自动重载）后可在 /docs 调用。下一步再把检索到的内容作为上下文交给大模型，完成 RAG 问答。

余弦距离资料：https://github.com/pgvector/pgvector#distances


## 第十步：基础 RAG 问答

/chat 已从回显升级为真实问答。generation.py 中 generate_answer 调用 OpenAI Responses API，CHAT_MODEL 默认 gpt-5.4-mini；Embedding 仍使用 EMBEDDING_MODEL。两个模型复用 .env 中已有的 OPENAI_API_KEY，不需要创建新的 Key。

```dotenv
CHAT_MODEL=gpt-5.4-mini
```

在 /docs 调用 POST /chat：

```json
{
  "knowledge_base_id": "实际知识库UUID",
  "question": "JVM 内存区域有哪些？",
  "top_k": 3
}
```

前提：该知识库中已上传并处理文档，状态为 READY。流程是问题 Embedding → pgvector 检索 → 把问题与参考片段交给聊天模型 → 返回 answer 和 sources。

sources 包含 source_id、document_id、filename、chunk_index、content、similarity。source_id 从 1 开始，供回答中的 [1]、[2] 对照。这是传给模型的全部参考片段，不代表每个片段都被回答引用。

生成提示词要求仅依据资料回答、资料不足时说明，并将文档中的指令视为数据。引用和资料充分性仍由模型判断，当前没有额外的自动事实核验或相似度阈值。没有检索结果时，程序直接说明没有可检索文档，不调用聊天模型；这条提示不是模型生成的回答。

接口同步返回，尚未实现多轮历史、流式输出或 Agent 自主调用工具。请求模型失败返回 502，不使用模拟回答。每次有检索结果的问答会产生一次问题 Embedding 和一次聊天生成的 API 用量。

已通过真实 API 和数据库验证：回答文档特有的“17 天”并标注 [1]；对未记录的 GPU 型号说明无法确定；来源编号对应正确；空检索和参数校验正常。临时数据已清理。

官方文档：https://developers.openai.com/api/docs/quickstart
模型说明：https://developers.openai.com/api/docs/models/gpt-5.4-mini
