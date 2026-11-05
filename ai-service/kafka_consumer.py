"""通信验证用消费者：打印任务通知，不执行任务，不提交消费进度。"""

import argparse
import json
import os
import time
from pathlib import Path
from uuid import UUID

from confluent_kafka import Consumer, KafkaException
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))


def consume(once: bool = False, timeout: float = 15) -> int:
    topic = os.getenv("KAFKA_DOCUMENT_TOPIC", "rag.document.process")
    consumer = Consumer({
        "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092"),
        # Docker 的开发端口绑定 127.0.0.1，避免 localhost 优先解析成 IPv6。
        "broker.address.family": "v4",
        # 验证使用独立消费组，后续正式 Worker 使用另一个组。
        "group.id": os.getenv("KAFKA_PREVIEW_GROUP_ID", "rag-document-preview"),
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "enable.auto.offset.store": False,
        "allow.auto.create.topics": False,
    })
    deadline = time.monotonic() + timeout
    try:
        consumer.subscribe([topic])
        print(f"正在监听 {topic}（仅打印，不处理任务、不提交 offset）", flush=True)
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
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    raise SystemExit(consume(args.once, args.timeout))
