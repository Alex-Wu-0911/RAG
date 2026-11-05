"""单次 Agent 请求共享的工具返回预算，不在请求之间共享状态。"""
import json

import tiktoken


class RetrievalBudget:
    def __init__(self, max_tokens: int = 4000, max_calls: int = 4):
        self.encoding = tiktoken.get_encoding("o200k_base")
        self.max_tokens = max_tokens
        self.max_calls = max_calls
        self.used_tokens = 0
        self.calls = 0
        self.seen = set()
        self.duplicate_items_skipped = 0
        self.exhausted = False
        self.statuses = ("ok", "partial", "no_results", "no_new_results", "budget_exhausted")
        self.notice_tokens = max(self.count_tokens(self.serialize(status, [])) for status in self.statuses)
        # 给剩余调用预留空结果通知的空间，通知本身也纳入预算。
        if max_tokens < max_calls * self.notice_tokens:
            raise ValueError("检索预算不足以容纳工具状态通知")

    @staticmethod
    def serialize(status: str, items: list[dict]) -> str:
        return json.dumps({"status": status, "items": items}, ensure_ascii=False, separators=(",", ":"))

    def count_tokens(self, text: str) -> int:
        # 文档里的特殊标记按普通文本计数，不能让其触发特殊 token 错误。
        return len(self.encoding.encode(text, disallowed_special=()))

    def pack(self, items: list[dict], key: str) -> str:
        """按检索顺序保留完整条目，返回可直接作为 ToolMessage 内容的 JSON 文本。"""
        future_calls = max(0, self.max_calls - self.calls - 1)
        available = self.max_tokens - self.used_tokens - future_calls * self.notice_tokens
        selected = []
        selected_keys = set()
        if not self.exhausted:
            for item in items:
                identity = (key, item[key])
                if identity in self.seen or identity in selected_keys:
                    self.duplicate_items_skipped += 1
                    continue
                candidate = selected + [item]
                cost = max(self.count_tokens(self.serialize(status, candidate)) for status in ("ok", "partial"))
                if cost > available:
                    self.exhausted = True
                    break
                selected.append(item)
                selected_keys.add(identity)

        if self.exhausted:
            status = "partial" if selected else "budget_exhausted"
        elif selected:
            status = "ok"
        else:
            status = "no_new_results" if items else "no_results"
        content = self.serialize(status, selected)
        self.used_tokens += self.count_tokens(content)
        self.calls += 1
        self.seen.update(selected_keys)
        return content

    def usage(self) -> dict:
        return {
            "token_budget": self.max_tokens,
            "used_tokens": self.used_tokens,
            "duplicate_items_skipped": self.duplicate_items_skipped,
            "budget_exhausted": self.exhausted,
        }
