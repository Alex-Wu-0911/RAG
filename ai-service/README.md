# RAG AI Service

当前已实现 Markdown 读取、分块、真实 Embedding、pgvector 入库、相似度检索、基础 RAG 问答和单轮 Agent 问答。/chat 已替换早期的问题回显实现；以下按学习步骤保留演进说明，当前调用方式见第十步。

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

## 第十一步：把检索封装成 Agent 工具

agent_tools.py 中 create_search_tool(knowledge_base_id) 返回一个 LangChain 工具，名称是 search_knowledge_base。当前仅使用已安装的 langchain-core，已将它显式列为直接依赖；还没有创建 Agent 或新增 HTTP 接口。

@tool 将函数封装为工具对象：函数名是工具名，docstring 是用途说明，类型注解定义模型可传入的参数。query 是检索问题或关键词，top_k 默认 3，取值范围与已有检索接口一致。

知识库 ID 由外层 create_search_tool 固定，内部函数直接使用它。这种写法称为闭包；模型只看到 query 和 top_k，不需要填写知识库 ID。

手动调用方式（knowledge_base_id 是已有的 UUID 对象）：

```python
from agent_tools import create_search_tool

search_tool = create_search_tool(knowledge_base_id)
results = search_tool.invoke({"query": "JVM 内存区域有哪些？", "top_k": 3})
```

这里是程序直接调用工具，不是模型自主选择工具。invoke 会先解析参数，再执行问题 Embedding 和已有 SQL 检索；调用会产生真实 Embedding API 用量。返回的列表包含文档 ID、文件名、分块序号、原文和相似度，UUID 已转为字符串，便于交给模型。

下一步创建 Agent 并注册此工具，让模型根据问题产生 tool call，再由框架执行 Python 函数。

工具文档：https://docs.langchain.com/oss/python/langchain/tools


## 第十二步：由 Agent 自主调用检索工具

新增 agent_service.py，使用 LangChain create_agent，将 ChatOpenAI 和已有的 search_knowledge_base 工具注册在一起。模型仍读取 .env 中的 CHAT_MODEL 和 OPENAI_API_KEY。

核心代码：

```python
agent = create_agent(
    model=model,
    tools=[create_search_tool(knowledge_base_id)],
    system_prompt=...,
    middleware=[ToolCallLimitMiddleware(run_limit=3, exit_behavior="error")],
)
result = agent.invoke({"messages": [{"role": "user", "content": question}]})
```

模型产生 tool call 时，LangChain 执行对应 Python 工具，把结果作为 ToolMessage 交回模型，直到模型输出最终回答。提示词要求知识库问题先检索，普通问候可以直接回复；资料不足时可以更换关键词检索。每个请求独立运行，尚未保存多轮历史。

在 /docs 调用 POST /agent/chat：

```json
{
  "knowledge_base_id": "实际知识库UUID",
  "question": "根据知识库，归档文件需要保留多久？"
}
```

返回字段：

- answer：Agent 最终回答。
- tool_calls：实际调用的工具名、模型传入的 args，以及 result_count。普通问候可能为空。这里没有返回模型内部推理。
- sources：工具实际查到的参考片段，按 source_id 去重。这是全部查到的资料，不代表每个片段都被回答引用。

Agent 的 source_id 使用“文档 UUID:分块序号”，回答中的 [source_id] 对应同一片段，跨多次检索仍可识别来源。原 /chat 的数字编号来源格式保持不变。

每次 Agent 请求最多执行 3 次工具调用；再次请求执行工具会停止并返回 502。另有图执行步数上限，避免持续循环。次数限制只约束单个请求，不是后台任务或服务限流。每次模型判断、生成回答及工具内 Embedding 都会产生实际 API 用量。

对比：/chat 固定检索一次再回答；/agent/chat 让模型选择是否检索及检索关键词，并可继续检索。这一步没有自动把 Java 上传串联到文档处理接口。

依赖已增加 langchain 和 langchain-openai，锁定版本见 requirements.lock.txt。

LangChain 文档：https://docs.langchain.com/oss/python/langchain/agents

本步已通过真实模型和数据库验证：知识库问题自主调用检索工具并引用真实片段；普通问候没有调用工具；空检索明确说明没有资料；参数校验正常。临时验证数据已清理。

## 第十三步：列出知识库的工具（自动选库第 1 步）

新增 knowledge_base_repository.py：find_all_knowledge_bases() 只读查询 biz.knowledge_bases 的 id、name、description，按名称和 ID 排序。

agent_tools.py 新增 @tool 装饰的 list_knowledge_bases()，把数据库 UUID 转为字符串后返回。工具不需要参数，不调用 Embedding 或聊天模型，不修改数据库。

在 ai-service 目录的 PowerShell 中手动验证：

```powershell
.\.venv\Scripts\python.exe -c "import json; from agent_tools import list_knowledge_bases; print(json.dumps(list_knowledge_bases.invoke({}), ensure_ascii=False, indent=2))"
```

预期返回知识库列表，每项包含 id、name 和 description。当前还没有把新工具注册进 Agent，也没有修改检索工具或 /agent/chat 请求格式；这些留到后续步骤。

本步代码已生成；Codex 执行环境无法访问虚拟环境所依赖的基础 Python 安装，尚未完成运行验证，需要在 VS Code Terminal 执行以上命令确认结果。

## 自动选库第 2 步：检索工具接收知识库 ID

agent_tools.py 中新增顶层 search_knowledge_base 工具，参数为 knowledge_base_id、query 和 top_k。knowledge_base_id 是 UUID 类型；后续由模型根据 list_knowledge_bases 的真实结果选择，不能自行编造。

本步只调整工具层。检索仍复用 embed_texts 和 search_chunks，不修改数据库结构和 SQL。create_search_tool 暂时保留，为现有 Agent 固定知识库并调用新工具，因此 /agent/chat 目前仍需要原来的知识库 ID 参数。后续再修改 Agent 注册和请求体。

在 ai-service 目录验证（实际调用 Embedding API）：

```powershell
.\.venv\Scripts\python.exe -c "import json; from agent_tools import search_knowledge_base; result = search_knowledge_base.invoke({'knowledge_base_id':'2dc719cc-a15f-4f9b-9647-ffb80cc7f795','query':'QL-27 最终采用哪个样品组？','top_k':3}); print(json.dumps(result, ensure_ascii=False, indent=2))"
```

## 自动选库第 3 步：注册工具并修改 Agent 接口

当前 POST /agent/chat 只需要 question，不再需要 knowledge_base_id。原 POST /chat 仍保留指定知识库的基础 RAG 用法；前面学习步骤中的旧 /agent/chat 请求示例以本节为准。

```json
{
  "question": "QL-27 最终采用哪个样品组？为什么不选 MSWD 更低的另一组？"
}
```

agent_service.py 注册 list_knowledge_bases 和 search_knowledge_base 两个工具，run_agent 只接收问题。提示词要求知识库问题先查列表，再按名称与简介选择真实 ID 检索；无法确定主题时询问用户。当前是模型按提示词选择工具，没有使用代码硬编码“铷锶”等关键词路由。

解析 ToolMessage 时，两个工具的结果都记录 result_count，但只有 search_knowledge_base 的片段写入 sources，避免把知识库列表当成引用。source_id 仍为“文档 UUID:分块序号”。单次请求最多调用工具 4 次，包含列表查询。普通问候可以不调用工具。

旧的 create_search_tool 固定库封装已移除。接口是单轮执行，不保存追问历史；如果需要澄清，下一次请求应包含完整问题和主题。

验证状态：已从正在运行的 FastAPI OpenAPI 确认 AgentChatRequest 仅含 question；实际模型自动选库结果待在 /docs 手动验证。预期 tool_calls 先出现 list_knowledge_bases，再出现带所选 knowledge_base_id 的 search_knowledge_base。

## 知识库语义路由第 1 步：生成主题向量

当前只准备主题向量，还没有替换 Agent 的 list_knowledge_bases 工具。

新增 V6__add_knowledge_base_topic_embedding.sql，为 biz.knowledge_bases 添加可空的 topic_embedding vector(1536)。知识库主题向量与 document_chunks 中的文档片段向量分开保存。现有 Java 实体无需增加向量字段，仍可创建和查询知识库。

操作顺序：

1. 使用 db,storage 配置重新启动 Java，确认 Flyway 成功执行 V6。
2. 在 ai-service 目录运行：

```powershell
.\.venv\Scripts\python.exe knowledge_base_embeddings.py
```

脚本使用“知识库名称＋简介”作为文本，复用 embed_texts 调用真实 Embedding API，并在一个事务内更新知识库主题向量。结束后查询并显示各库实际保存的向量维度，应为 1536。

脚本可重复执行，每次都会重新生成现有知识库的主题向量，产生相应 Embedding 用量。当前新增库或修改名称、简介后，需要手动重跑，不会自动更新。更换 Embedding 模型前也需考虑向量维度和全部重建，不能混用不同模型的向量。

目前简介仍沿用已有内容，因此主题匹配能力受简介质量限制。后续可完善简介覆盖的内容，再重建向量；不能保证一句笼统简介能代表整个知识库。

这里批量读取名称和简介用于离线准备向量，不是每次用户提问时把全部知识库送进聊天模型。下一步才用问题向量搜索少量候选知识库。

代码已生成；迁移执行与实际向量入库结果待按上述步骤验证。

## 知识库语义路由第 2 步：搜索候选知识库

knowledge_base_repository.py 新增 find_similar_knowledge_bases(query_vector, limit)，使用 pgvector 余弦距离查询 topic_embedding；NULL 向量不参与搜索。相似度为 1 - 余弦距离，结果按距离从小到大返回，同分时按 ID 排序。

agent_tools.py 新增 search_knowledge_bases(query, limit=3) 工具，复用 embed_texts 生成查询向量，返回 id、name、description、similarity。limit 范围为 1 到 5。数据库里的完整向量不会返回给模型。

当前还没有相似度阈值，因此返回的是相对最接近的候选，不保证每个结果都与问题相关；即使问题超出所有知识库的主题，也可能得到候选。需要继续核对简介和文档内容，不能把“有返回值”当成“资料足够”。

先在 ai-service 目录单独验证：

```powershell
.\.venv\Scripts\python.exe -c "import json; from agent_tools import search_knowledge_bases; result = search_knowledge_bases.invoke({'query':'铷锶等时线定年和岩石年龄误差分析','limit':2}); print(json.dumps(result, ensure_ascii=False, indent=2))"
```

预期同位素地质年代学排名在 JVM 之前；实际分数由模型与已保存简介决定。查询调用真实 Embedding API，不更新主题向量、不调用聊天模型。

本步暂未替换 Agent 的列表工具，待手动验证语义搜索后再接入。当前 SQL 使用精确向量距离排序；LIMIT 限制返回量，不等于计算时只比较这几个库。更大数据量下可以根据性能测量添加向量索引。

## 知识库语义路由第 3 步：Agent 改用候选搜索

当前 Agent 只注册 search_knowledge_bases 和 search_knowledge_base，不再提供 list_knowledge_bases。此前学习步骤中的全量列表工具已移除；find_all_knowledge_bases 仅由主题向量维护脚本使用。

实际流程：问题 → search_knowledge_bases 生成查询向量并获取候选 → 模型根据名称、简介、相似度选择真实 ID → search_knowledge_base 检索文档片段 → 回答。

/agent/chat 请求仍然只传 question：

```json
{
  "question": "在铷锶等时线定年资料中，QL-27 为什么采用 M-2 而不采用 WR-1？"
}
```

tool_calls 应先出现复数 search_knowledge_bases（搜索知识库），再出现单数 search_knowledge_base（检索某个库里的文档）。候选库只计入调用记录，sources 仍只包含文档片段。每次请求总工具调用上限仍为 4。

目前不设置统一相似度阈值，模型需核对候选的名称、简介和检索原文；候选返回不保证问题可回答。当前仅限制候选数量，还没有实现整个 Agent 执行的累计上下文 token 预算。

验证状态：先前语义工具已由用户实测，同位素地质年代学相似度约 0.626、JVM 约 0.081。此次注册修改后 /agent/chat 的接口定义仍可读取，仍只要求 question；模型完整调用链待在 /docs 手动验证。

## 开始评测：小型人工标注集

新增 evals/datasets/geochronology_v1.json 和 evals/README.md。数据集包含 10 条问题、目标知识库、相关分块、回答要点与不应编造的结论；当前只准备数据，不运行模型。标注基于现有地质文档与用户此前返回的分块，已核对原文哈希和证据摘录。

下一步再增加逐条调用 /agent/chat 的执行脚本。只有 question 发给模型，其他字段用于评分。具体口径和限制见 evals/README.md。

评测执行脚本已添加：在 ai-service 目录运行 `.\.venv\Scripts\python.exe evals/run_eval.py --limit 1` 可先测试一条；不带 --limit 则运行全部。结果保存在已忽略的 evals/results/独立运行目录，包含逐条 JSONL、统计汇总和人工审阅文档。运行前可执行 evals/test_run_eval.py 的离线测试；详细命令见 evals/README.md。本次尚未执行模型评测。

## 第一次上下文优化：请求内去重与累计工具文本预算

新增 retrieval_budget.py，并在每次 run_agent 调用时创建独立的 RetrievalBudget。Agent 使用 create_agent_tools 创建的包装工具，原来的独立检索工具仍可用于手动测试，返回格式保持列表。

Agent 包装工具返回统一 JSON 文本：status 加 items。候选知识库按 id 去重，文档片段按 source_id（文档 ID:分块序号）去重。重复内容不再发给模型，但仍存在于本次请求之前的工具消息中；去重状态不跨用户请求共享。

默认 AGENT_RETRIEVAL_TOKEN_BUDGET=4000，可在 .env 配置后重启服务。使用 tiktoken 的 o200k_base 编码统计实际工具 JSON 文本，包含条目元数据、状态和 JSON 格式。此口径不是整个模型上下文或 API 账单：不包含系统提示词、用户问题、工具定义、模型消息及协议封装，也不消除历史工具文本在后续模型轮次被再次读取的用量。

工具调用次数仍由 ToolCallLimitMiddleware 限制为最多 4 次。预算计算为剩余调用预留空状态通知的空间，因此这些通知也计入文本预算。tiktoken 已在锁定依赖中，现也显式列为直接依赖；首次初始化编码缓存可能需要下载公开词表，不调用付费模型 API。

按检索排序保留完整条目，不切断原文；首个超预算条目及其后续条目不发送。首次无法继续容纳条目后，标记预算耗尽，后续包装工具直接返回状态，不再请求 Embedding 或查询数据库。这样可能减少证据覆盖，应使用同一评测集确认质量变化，不能只看 token 降低。

状态含义：

- ok：本次返回了新资料。
- no_results：检索没有结果。
- no_new_results：有结果但都已返回过，应参考历史消息，不等于没有资料。
- partial：只发送了部分条目，预算已不足，停止继续检索。
- budget_exhausted：本次不再发送条目，使用已有资料回答或说明不足。

/agent/chat 新增 context_usage：token_budget、used_tokens、duplicate_items_skipped、budget_exhausted。tool_calls 增加 status；result_count 现在表示实际发送给模型的新增条目数，不是数据库原始命中数。sources 仍只包含模型实际收到的文档片段，不包含被预算排除的片段。

先运行不调用模型或数据库的测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s evals -p test_retrieval_budget.py
```

再复用同一用例做一次真实回归：

```powershell
.\.venv\Scripts\python.exe evals/run_eval.py --limit 1
```

查看 results.jsonl 中 response.context_usage，人工检查回答和引用。单次调用没有重复片段时，duplicate_items_skipped=0 是正常结果；需要多次检索出现重叠，才能观察去重效果。

本次已从运行中的 OpenAPI 确认新增返回字段，7 项离线测试代码已添加。Codex 执行环境仍不能启动基础 Python，因此离线测试与优化后真实问答尚未运行；不存在已测出的速度或成本提升数据。

## Cohere API 重排（Agent 文档检索）

新增 reranking.py，使用 langchain_cohere.CohereRerank 调用真实 Cohere Rerank API，不是让聊天模型模拟打分。Key 只写入本机已忽略的 .env，.env.example 只有占位符。

```dotenv
COHERE_API_KEY=你的CohereKey
RERANK_MODEL=rerank-v5.0-fast
RERANK_ENABLED=true
```

Agent 的 search_knowledge_base 工具在开启时先用 pgvector 最多召回 20 个候选（不足则返回实际数量），再让 Cohere 根据原问题排序，保留模型指定的 top_k 个，最后才进入现有去重与 token 预算。已有候选知识库的语义搜索不加重排；/chat 和独立 /knowledge-bases/{id}/search 仍使用原始向量检索。

similarity 始终保留原始向量余弦相似度；rerank_score 是重排模型的相关性分数，二者不是同一个量表，也不是回答正确率。Document 的文档 ID、文件名、分块序号与原文在重排后保持对应关系，引用 source_id 不变。原始向量接口的 rerank_score 为 null。

设置 RERANK_ENABLED=false 并重启或重新加载服务，可做纯向量检索对照。修改 .env 一般不会触发 Uvicorn 的 Python 文件重载，需要手动重启。开启时如果重排服务失败，/agent/chat 返回 502，不使用虚构分数或静默假装重排成功。Cohere Key 不会用于 OpenAI 调用。

已安装并锁定 langchain-cohere 与 cohere 依赖，pip check 通过。已运行 16 项离线测试，覆盖重排元数据、关闭开关、空候选和 API 错误，以及原有预算和评测逻辑。

真实调用验证：Agent 自动选库、Embedding、Cohere 重排和引用回答均成功，回答了 QL-27 采用 M-2、批准记录号 QL27-R3。

质量限制：另一个询问仪器型号及空白校正的中文问题，关键的“未提供信息”片段未进入重排前 3 名；因此当前只能确认调用链正确，不能声称召回或回答质量已经提高。该问题以较多候选返回时仍可能取得该片段，需固定 top_k 并使用完整评测集对照。

本次测试中发现 Windows PowerShell 管道会把脚本内中文转成问号，早期受影响的排序结果已排除。若用 here-string 管道向 Python 传脚本，先设置 $OutputEncoding = [System.Text.UTF8Encoding]::new($false)，或把脚本保存为 UTF-8 文件再执行。

试用 Key 的调用频率受服务限制；运行多轮 Agent 或批量评测时要留意 429。现有检索上下文预算只限制给聊天模型的工具结果，不限制发给 Cohere 的候选原文数量；这里通过最多 20 个候选控制单次重排规模。

LangChain 组件：https://docs.langchain.com/oss/python/integrations/retrievers/cohere-reranker
Cohere API：https://docs.cohere.com/reference/rerank

## Kafka 消费者：第 1 步，验证接收通知

新增 kafka_consumer.py，使用 confluent-kafka。它只读取并打印 event_id、task_id、document_id 和 Kafka 分区/offset，不访问数据库、MinIO 或模型 API，不执行文档处理。

在 ai-service 目录执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 kafka_consumer.py
```

持续监听，Ctrl+C 停止。单条验证可用：

```powershell
.\.venv\Scripts\python.exe -X utf8 kafka_consumer.py --once --timeout 15
```

先确认 Docker Kafka 在运行，然后重启含最新 Outbox 投递逻辑的 Java 服务。已有 PENDING 消息会自动发送；Java 日志应出现 Outbox sent。此后消费者打印对应任务 ID。单条模式若等待 15 秒未收到消息，退出码为 1；不等同于连接一定失败，Topic 为空也会超时。

默认连接 localhost:19092、Topic rag.document.process。配置示例在 .env.example；未设置时使用这些默认值即可。Docker 开发端口绑定 IPv4，消费者显式使用 broker.address.family=v4，避免 localhost 被优先解析成 ::1。

这是预览消费者：独立消费组 rag-document-preview，auto.offset.reset=earliest，关闭自动提交和自动存储 offset，代码也不主动提交。没有已提交进度时，重启会再次读取保留的消息，这是本步骤用于重复验证的预期行为。后续正式 Worker 使用独立消费组，并在任务状态妥善保存后提交进度。

已安装 confluent-kafka 2.16.1 并更新锁定依赖，pip check 通过。实际连接检查确认 Topic 存在，分区 0 的 offset 范围为 (0,0)，当时没有可读取消息；尚未完成 Java 投递到 Python 打印的真实消息联调。
## Kafka Worker：第 2 步，原子领取任务

新增 task_repository.claim_task(task_id, document_id, worker_id)。用一条 UPDATE ... WHERE status='QUEUED' RETURNING 完成状态检查和更新，避免先 SELECT 再 UPDATE 的并发重复领取。额外匹配 document_id，不能用错配的文档通知领取任务。

领取成功时返回字典，包含 RUNNING/READING 状态、执行次数、Worker 标识和本次执行令牌 lease_token；未领取到返回 None。事务正常提交后函数才返回；重复消息、已在执行或已结束的任务不会再次领取。执行次数只在成功领取时增加。

当前同时写入心跳时间及 120 秒租约到期时间，为后续 Worker 心跳及失联恢复预留。此时尚未实现续租、过期任务恢复及令牌校验的结果提交，不能仅靠时间到期自动恢复任务，也不会领取已经 RUNNING 的过期任务。

本步骤只实现数据库方法，kafka_consumer.py 仍保持只打印模式。正式调用领取逻辑要与文档执行、结束状态更新一起接入，避免真实任务被领取后一直停在 RUNNING。

真实数据库测试只创建并清理独立测试记录，不创建 Outbox，不处理原有文档，不调用模型 API。运行：

```powershell
$env:RUN_DB_TESTS = '1'
.\.venv\Scripts\python.exe -X utf8 -m unittest evals.test_task_repository -v
Remove-Item Env:RUN_DB_TESTS
```

覆盖四路并发只有一位领取成功、次数和令牌正确提交、任务/文档 ID 错配、非 QUEUED 状态跳过。
本步骤的 3 项真实 PostgreSQL 测试已全部通过。测试结束后已确认原有任务 eeac38e7-5d67-452b-9629-afbe7db57e7f 仍为 QUEUED，attempt_count=0。

## Kafka Worker：第 3 步，执行文档处理与心跳续租

新增 document_worker.py，kafka_consumer.py 默认仍是只预览模式，显式传 --process 才执行真实任务：

```powershell
# 在 ai-service 目录运行；会修改任务/文档状态、替换该文档分块，并调用付费 Embedding API。
.\.venv\Scripts\python.exe -X utf8 kafka_consumer.py --process --once --timeout 15
```

收到一条消息后，正式消费组 rag-document-worker 领取任务，记录 RUNNING/READING；读取 MinIO 的 UTF-8 Markdown，依次更新 SPLITTING、EMBEDDING、SAVING，复用现有分块和真实 Embedding 函数。成功后任务是 SUCCEEDED/COMPLETED，文档是 READY；失败则任务和文档同时写 FAILED，任务保存 error_message 和 finished_at。当前仍不支持 PDF。

TaskHeartbeat 在独立线程每 30 秒向 PostgreSQL 续租一次，将有效期延长至数据库当前时间后 120 秒。只允许当前 lease_token、RUNNING 且尚未到期的执行续租，不能复活过期执行。续租失败会阻止后续阶段和结果写入；已经发出的模型请求不能强制撤回，返回后仍会检查执行资格。

complete_task 在同一数据库事务中锁定文档与任务、校验令牌及租约、替换向量、更新文档 READY 和任务 SUCCEEDED。入库过程中再次检查租约，过期则整个事务回滚；旧 Worker 也不能在成功后把任务改为失败。write_document_chunks 仅复用 SQL，不自行提交事务。

为了避免旧同步入口与 Worker 互相覆盖，只要文档已有异步任务历史，旧 POST /documents/{id}/process 就返回 409。重新处理请提交新的 Java 任务。没有异步任务历史的文档仍可使用旧同步入口。

Kafka 手动提交规则：

- SUCCEEDED：结果与成功状态已提交，再提交 offset。
- FAILED：失败原因已可靠保存，再提交 offset。当前不自动重试业务失败，重试通过 Java 创建新任务。
- 已 SUCCEEDED/FAILED 的重复通知：跳过处理并提交 offset。
- 正在执行、任务缺失/文档错配、租约丢失或数据库写入失败：不提交 offset，消费者退出，保留进度供排查及恢复。

预览组与正式处理组隔离，预览消息不会推进正式消费进度。正式组没有进度时从最早保留消息开始，--once 处理最早的一条，不是按指定任务 ID 选消息。取消 --once 可持续运行，Ctrl+C 停止；单个消费者串行处理。

max.poll.interval.ms 设置为 30 分钟：单次处理超过该时间可能导致分区重新分配和提交失败，不意味着支持无限长的任务。Worker 退出时，未正常结束的任务可能保持 RUNNING。租约到期后的自动重新入队、重新投递和恢复程序尚未实现；不会仅靠租约到期自动开始重试。

本次已通过 26 项测试：包含 6 项真实 PostgreSQL 任务测试、4 项 Worker/消费进度测试及原有 16 项离线测试。数据库测试使用自建文档与固定测试向量，结束后清理，只用于验证事务和令牌，不代表模型检索效果；不调用真实 Embedding API。真实模型与 MinIO 的完整 Worker 联调待用户确认后执行。

```powershell
# 仅当前终端使用 IPv4，避免 localhost 的 IPv6 连接等待，不修改 .env。
$env:DB_HOST = '127.0.0.1'
$env:RUN_DB_TESTS = '1'
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s evals -p 'test_*.py'
Remove-Item Env:RUN_DB_TESTS
Remove-Item Env:DB_HOST
```
## Agent 流式输出：第 1 步，Python 事件流

agent_service.py 新增 async stream_agent(question)，使用当前安装的 LangChain astream_events(version="v2") 获取真实执行事件。这里只产生 Python 字典，尚未新增 HTTP 接口或 SSE 编码。run_agent 及原 /agent/chat 保留，两个入口共用 Agent 创建配置和最终结果汇总。

| event | data | 含义 |
| --- | --- | --- |
| tool_start | id、name、args | Agent 开始执行一个工具 |
| tool_end | id、name、args、status、result_count | 包装工具执行结束；同一个 id 与开始事件对应 |
| answer_delta | message_id、text | 一段模型可见文本，message_id 为本次模型调用 run_id |
| done | answer、tool_calls、sources、context_usage | 根 Agent 执行结束后的完整、权威结果 |

保留原有每次请求独立的检索预算、去重、Cohere 重排、最多 4 次工具调用及递归上限。工具内部的原始检索调用不重复显示为外层工具事件，也不把候选库当作文档来源。

模型流只提取文本块，不转发 reasoning、工具调用参数或其他原始模型事件。模型可能在调用工具前输出简短可见说明，因此不要将不同 message_id 的文本简单拼接后当作最终答案；done.answer 是最终完整回答，前面的 answer_delta 是过程中的可见文本。错误或不完整结果会抛出异常，不伪造 done；下一步由 SSE 层转换为 error 事件。

流正常结束、调用方取消或显式 aclose 时关闭上游异步事件流。同步工具在线程池中已经发出的网络请求不保证能被强制中止；本步测试的是事件流关闭和取消传播，HTTP 客户端断连检测留给下一步。

新增 evals/test_agent_stream.py 的 7 项离线测试已通过。其中使用本地测试模型运行真实 LangChain Agent 图，覆盖选库、检索、文本分段、嵌套工具过滤、最终来源和预算；另外检查推理/参数过滤、根状态选择、不完整结果、异常、提前关闭与取消。模型、数据库和重排调用在测试中被替换，不消耗付费 API。

本轮全部离线测试：33 项中 27 项通过，6 项真实数据库任务测试按开关跳过。没有运行真实模型流式联调。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest evals.test_agent_stream -v
```

下一步再增加 POST /agent/chat/stream，将这里的事件编码为 SSE；当前不能通过 curl 请求新路径。
## Agent 流式输出：第 2 步，FastAPI SSE 接口

新增 POST /agent/chat/stream。请求体与 /agent/chat 相同，{"question":"问题"}。响应 Content-Type 为 text/event-stream; charset=utf-8，每个 Python 事件编码为 event 行和单行 JSON data，最后以空行分隔。原有同步 /agent/chat 保留，不需要 Java 转发或新增中间件。

agent_sse.py 负责事件编码、错误消息和断连清理；main.py 注册接口并设置 Cache-Control: no-cache、X-Accel-Buffering: no。响应生成器直接发送上游事件，不先收齐答案。

- tool_start / tool_end：工具执行进展。
- answer_delta：模型可见文本片段，按 message_id 区分模型调用；done.answer 为最终答案。
- done：成功结束，包含完整答案、引用来源、调用记录和检索预算统计。
- error：流内失败，包含 code 和简短 message；不向客户端返回原始异常或堆栈，之后关闭连接。

请求参数错误在开始响应前返回 HTTP 422。流建立后响应头已发送，即使模型执行失败，HTTP 状态也通常仍是 200，所以客户端必须检查 done/error，不能只看 HTTP 状态码。收到部分文本后遇到 error，部分文本不表示完整成功答案。当前没有断线自动续传。

客户端等待模型或工具时也会每 250 毫秒检查断连；断连会取消正在读取的异步任务并关闭上游事件流。响应写入失败或服务器取消响应时也清理生成器。已在线程池中发出的同步检索/API 请求不能保证立刻中断，不能将连接取消等同于已撤回所有付费调用。

### 手动联调（会调用真实模型 API）

重启 FastAPI，确认 http://127.0.0.1:8000/health 可访问。在 ai-service 目录执行：

```powershell
curl.exe -N -X POST "http://127.0.0.1:8000/agent/chat/stream" -H "Content-Type: application/json" --data-binary "@requests/agent-chat.json"
```

-N 关闭 curl 的输出缓冲；UTF-8 请求正文放在 JSON 文件里，避免 Windows PowerShell 的中文管道或 JSON 引号转义问题。应陆续看到 event: tool_start、tool_end、answer_delta，最后 done；实际工具顺序和片段数量由 Agent 执行决定，日常问候可能没有工具调用。Ctrl+C 可中断请求。不要用 Invoke-RestMethod 是否一次性显示来判断服务器是否流式。

本轮没有运行真实模型联调，也没有花费模型 API 额度。新增 8 项 SSE 离线测试通过，覆盖事件编码、响应头、请求校验、错误清理、真实 ASGI 分块发送（首段先于执行完成）、等待期间断连以及写响应失败时的上游关闭。完整离线回归共 41 项：35 项通过，6 项数据库任务测试因未开启而跳过。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest evals.test_agent_sse -v
```