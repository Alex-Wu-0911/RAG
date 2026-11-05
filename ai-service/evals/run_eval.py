"""顺序调用真实 Agent API，保存评测记录；不把标准答案发给模型。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


ROOT = Path(__file__).resolve().parent


def score_retrieval(case: dict, document_id: str, response: dict) -> dict:
    """统计目标库命中与相关片段覆盖，不判断回答是否正确。"""
    calls = response.get("tool_calls", [])
    searched_ids = {
        call["args"].get("knowledge_base_id")
        for call in calls if call["name"] == "search_knowledge_base"
    }
    retrieved = {
        source["chunk_index"] for source in response.get("sources", [])
        if source["document_id"] == document_id
    }
    relevant = set(case["relevant_chunk_indices"])
    return {
        "knowledge_base_hit": case["expected_knowledge_base_id"] in searched_ids,
        "unexpected_knowledge_base_ids": sorted(searched_ids - {case["expected_knowledge_base_id"]}),
        "retrieved_chunk_indices": sorted(retrieved),
        "evidence_hit_indices": sorted(relevant & retrieved),
        "evidence_coverage": len(relevant & retrieved) / len(relevant),
        "tool_call_count": len(calls),
    }


def summarize(records: list[dict]) -> dict:
    """失败样本保留在分母；耗时分位数只统计有效成功响应。"""
    successes = [record for record in records if record["success"]]
    latencies = sorted(record["elapsed_ms"] for record in successes)
    count = len(records)
    return {
        "attempted_count": count,
        "success_count": len(successes),
        "failure_count": count - len(successes),
        "api_success_rate": len(successes) / count if count else None,
        "knowledge_base_hit_rate": sum(record["metrics"]["knowledge_base_hit"] for record in records) / count if count else None,
        "mean_evidence_coverage": mean(record["metrics"]["evidence_coverage"] for record in records) if count else None,
        "mean_tool_calls_success": mean(record["metrics"]["tool_call_count"] for record in successes) if successes else None,
        "mean_success_latency_ms": round(mean(latencies), 2) if latencies else None,
        "p95_success_latency_ms": latencies[math.ceil(0.95 * len(latencies)) - 1] if latencies else None,
        "answer_quality": "pending_manual_review",
    }


def call_agent(case: dict, document_id: str, url: str, timeout: float) -> dict:
    record = {"case": case, "success": False, "http_status": None, "response": None, "error": None}
    request = Request(
        url,
        data=json.dumps({"question": case["question"]}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            record["http_status"] = response.status
            record["raw_body"] = response.read().decode("utf-8")
        body = json.loads(record["raw_body"])
        record["response"] = body
        if not (isinstance(body, dict) and isinstance(body.get("answer"), str)
                and isinstance(body.get("tool_calls"), list) and isinstance(body.get("sources"), list)):
            raise ValueError("响应不符合 Agent 接口格式")
        record["metrics"] = score_retrieval(case, document_id, body)
        record["success"] = True
    except HTTPError as error:
        record["http_status"] = error.code
        record["raw_body"] = error.read().decode("utf-8", errors="replace")
        record["error"] = str(error)
    except (URLError, OSError, ValueError, KeyError, TypeError) as error:
        record["error"] = f"{type(error).__name__}: {error}"
    record["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    if not record["success"]:
        record["metrics"] = score_retrieval(case, document_id, {})
    return record


def write_review(path: Path, records: list[dict]) -> None:
    lines = ["# 回答人工审阅", "", "自动指标不代表回答正确，请对照预期要点、错误结论和原文检查。", ""]
    for record in records:
        case = record["case"]
        response = record["response"] if isinstance(record["response"], dict) else {}
        lines += [f"## {case['id']}：{case['category']}", "", case["question"], "",
                  f"资料足够回答：{case['answerable']}；请求成功：{record['success']}", "", "预期要点：", ""]
        lines += [f"- {point}" for point in case["expected_points"]]
        lines += ["", "不应出现的结论：", ""]
        lines += [f"- {claim}" for claim in case["forbidden_claims"]]
        lines += ["", "实际回答：", "", response.get("answer", "无有效回答"), "",
                  f"错误：{record['error']}", "", "人工结论：待填写", "", "说明：待填写", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "datasets/geochronology_v1.json")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=300, help="每条请求的网络等待超时秒数")
    parser.add_argument("--limit", type=int, help="只运行前 N 条，省略则运行全部")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit 必须大于 0")
    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    dataset_bytes = args.dataset.read_bytes()
    dataset = json.loads(dataset_bytes.decode("utf-8-sig"))
    cases = dataset["cases"][:args.limit]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    output = ROOT / "results" / run_id
    output.mkdir(parents=True)
    url = args.base_url.rstrip("/") + "/agent/chat"
    records = []
    print(f"将发送 {len(cases)} 条真实请求，不自动重试。结果目录：{output}", flush=True)
    try:
        with (output / "results.jsonl").open("w", encoding="utf-8") as file:
            for index, case in enumerate(cases, start=1):
                print(f"[{index}/{len(cases)}] {case['id']} 请求中…", flush=True)
                record = call_agent(case, dataset["source"]["document_id"], url, args.timeout)
                records.append(record)
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
                file.flush()
                print(f"  HTTP={record['http_status']} success={record['success']} 耗时={record['elapsed_ms']}ms", flush=True)
    finally:
        summary = {
            "run_id": run_id,
            "dataset_id": dataset["dataset_id"],
            "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
            "url": url,
            "timeout_seconds": args.timeout,
            "selected_count": len(cases),
            "uncompleted_count": len(cases) - len(records),
            **summarize(records),
        }
        (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        write_review(output / "review.md", records)
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

