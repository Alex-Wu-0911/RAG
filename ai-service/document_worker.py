import logging
from threading import Event, Thread
from uuid import UUID

from document_repository import find_document
from embeddings import embed_texts
from storage import read_object
from task_repository import (
    LeaseLostError, claim_task, complete_task, fail_task, find_task, renew_lease, set_task_stage,
)
from text_processing import split_text

log = logging.getLogger(__name__)


class TaskHeartbeat:
    """主线程处理文档，后台线程每 30 秒向数据库续租。"""

    def __init__(self, task_id: UUID, lease_token: UUID, interval: float = 30):
        self.task_id = task_id
        self.lease_token = lease_token
        self.interval = interval
        self.stop = Event()
        self.lost = Event()
        self.thread = Thread(target=self._run, daemon=True)

    def _run(self):
        while not self.stop.wait(self.interval):
            try:
                if not renew_lease(self.task_id, self.lease_token):
                    self.lost.set()
                    return
            except Exception:
                log.exception("任务续租失败：task_id=%s", self.task_id)
                self.lost.set()
                return

    def check(self):
        if self.lost.is_set():
            raise LeaseLostError("心跳失败，停止本次执行的结果写入")

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join()


def process_task(task_id: UUID, document_id: UUID, worker_id: str) -> str:
    task = claim_task(task_id, document_id, worker_id)
    if task is None:
        existing = find_task(task_id, document_id)
        if existing and existing["status"] in ("SUCCEEDED", "FAILED"):
            log.info("跳过已结束任务：task_id=%s", task_id)
            return "SKIPPED"
        # 不确认正在执行、缺失或错配的任务，退出后保留消息供排查/恢复。
        raise RuntimeError(f"任务未领取，暂不提交消费进度：{task_id}")

    token = task["lease_token"]
    log.info("领取任务：task_id=%s worker_id=%s", task_id, worker_id)
    with TaskHeartbeat(task_id, token) as heartbeat:
        try:
            document = find_document(document_id)
            if document is None:
                raise ValueError("文档不存在")
            if not document["storage_key"].lower().endswith(".md"):
                raise ValueError("当前只支持 UTF-8 Markdown 文件")
            text = read_object(document["storage_key"]).decode("utf-8-sig")
            heartbeat.check()
            set_task_stage(task_id, token, "SPLITTING")
            chunks = split_text(text)
            if not chunks:
                raise ValueError("文档没有可生成向量的文本")
            heartbeat.check()
            set_task_stage(task_id, token, "EMBEDDING")
            vectors = embed_texts(chunks)
            heartbeat.check()
            set_task_stage(task_id, token, "SAVING")
            complete_task(task_id, document_id, token, document["knowledge_base_id"], chunks, vectors)
        except LeaseLostError:
            raise
        except Exception as error:
            heartbeat.check()
            fail_task(task_id, document_id, token, f"{type(error).__name__}: {error}")
            log.exception("文档处理失败，已保存原因：task_id=%s", task_id)
            return "FAILED"
    log.info("任务成功：task_id=%s chunk_count=%s", task_id, len(chunks))
    return "SUCCEEDED"
