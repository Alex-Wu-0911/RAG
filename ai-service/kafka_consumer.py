"""默认仅预览任务通知；--process 开启真实文档处理并提交消费进度。"""

import argparse
import json
import logging
import os
import socket
import time
from pathlib import Path
from uuid import UUID, uuid4

from confluent_kafka import Consumer, KafkaException
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))


def consume(once: bool = False, timeout: float = 15, process: bool = False) -> int:
    topic = os.getenv("KAFKA_DOCUMENT_TOPIC", "rag.document.process")
    worker_id = f"{socket.gethostname()[:40]}-{os.getpid()}-{uuid4().hex[:8]}"
    consumer = Consumer({
        "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092"),
        # Docker 的开发端口绑定 127.0.0.1，避免 localhost 优先解析成 IPv6。
        "broker.address.family": "v4",
        # 验证使用独立消费组，后续正式 Worker 使用另一个组。
        "group.id": os.getenv("KAFKA_WORKER_GROUP_ID", "rag-document-worker") if process
            else os.getenv("KAFKA_PREVIEW_GROUP_ID", "rag-document-preview"),
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "enable.auto.offset.store": False,
        "allow.auto.create.topics": False,
        "max.poll.interval.ms": 1800000,
    })
    deadline = time.monotonic() + timeout
    try:
        consumer.subscribe([topic])
        mode = "执行任务，持久化结束状态后提交 offset" if process else "仅打印，不处理任务、不提交 offset"
        print(f"正在监听 {topic}（{mode}）", flush=True)
        while True:
            if once and time.monotonic() >= deadline:
                print(f"{timeout:g} 秒内未收到消息，请检查 Kafka、Topic 和 Java 投递日志。", flush=True)
                return 1
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                raise KafkaException(message.error())

            event = json.loads(message.value().decode("utf-8"))
            # 检查消息契约中的三个标识，防止把其他消息当作任务通知。
            ids = {name: str(UUID(event[name])) for name in ("event_id", "task_id", "document_id")}
            print(json.dumps({
                "topic": message.topic(),
                "partition": message.partition(),
                "offset": message.offset(),
                **ids,
            }, ensure_ascii=False, indent=2), flush=True)
            if process:
                # 预览模式不会导入模型/存储模块，更不会调用付费 API。
                from document_worker import process_task
                result = process_task(UUID(ids["task_id"]), UUID(ids["document_id"]), worker_id)
                consumer.commit(message=message, asynchronous=False)
                print(f"任务结果：{result}，消费进度已提交。", flush=True)
            if once:
                return 0
    except KeyboardInterrupt:
        print("消费者已停止。", flush=True)
        return 0
    finally:
        consumer.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="收到一条消息后退出")
    parser.add_argument("--timeout", type=float, default=15, help="单条验证的最长等待秒数")
    parser.add_argument("--process", action="store_true", help="执行真实文档处理，会调用 Embedding API")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    raise SystemExit(consume(args.once, args.timeout, args.process))
