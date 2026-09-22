"""Importer tests: LangSmith and Langfuse exports must convert cleanly."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_autopsy.importers import from_langsmith, from_langfuse
from agent_autopsy.analyzer import autopsy_trace


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        raise SystemExit(f"FAILED: {name}")


LANGSMITH_RUN = {
    "id": "ls-1", "name": "support-bot", "run_type": "chain",
    "inputs": {"q": "Where is my order?"}, "outputs": None, "error": None,
    "start_time": "2026-09-21T10:00:00Z", "end_time": "2026-09-21T10:01:30Z",
    "parent_run_id": None,
    "extra": {"token_usage": {"prompt_tokens": 500, "completion_tokens": 100}},
    "child_runs": [
        {"id": "ls-2", "name": "search_docs", "run_type": "tool",
         "inputs": {"query": "refund policy"}, "outputs": {"hits": []},
         "error": None, "start_time": "2026-09-21T10:00:05Z",
         "end_time": "2026-09-21T10:00:08Z", "parent_run_id": "ls-1",
         "extra": {"token_usage": {"prompt_tokens": 120, "completion_tokens": 80}},
         "child_runs": []},
        {"id": "ls-3", "name": "search_docs", "run_type": "tool",
         "inputs": {"query": "refund policy"}, "outputs": {"hits": []},
         "error": None, "start_time": "2026-09-21T10:00:10Z",
         "end_time": "2026-09-21T10:00:13Z", "parent_run_id": "ls-1",
         "extra": {"token_usage": {"prompt_tokens": 120, "completion_tokens": 80}},
         "child_runs": []},
        {"id": "ls-4", "name": "search_docs", "run_type": "tool",
         "inputs": {"query": "refund policy"}, "outputs": {"hits": []},
         "error": None, "start_time": "2026-09-21T10:00:15Z",
         "end_time": "2026-09-21T10:00:18Z", "parent_run_id": "ls-1",
         "extra": {"token_usage": {"prompt_tokens": 120, "completion_tokens": 80}},
         "child_runs": []},
    ],
}

LANGFUSE_TRACE = {
    "id": "lf-1", "name": "support-bot",
    "observations": [
        {"id": "o1", "parentObservationId": None, "name": "agent-loop",
         "type": "SPAN", "input": {"q": "Where is my order?"},
         "output": None, "startTime": "2026-09-21T10:00:00Z",
         "endTime": "2026-09-21T10:01:30Z",
         "usage": {"input": 500, "output": 100}, "level": "DEFAULT"},
        {"id": "o2", "parentObservationId": "o1", "name": "get_order",
         "type": "SPAN", "input": {"order_id": "XYZ"}, "output": None,
         "startTime": "2026-09-21T10:00:05Z", "endTime": "2026-09-21T10:00:06Z",
         "usage": {"input": 120, "output": 40}, "level": "ERROR",
         "statusMessage": "OrderNotFound: no order 'XYZ'"},
        {"id": "o3", "parentObservationId": "o1", "name": "get_order",
         "type": "SPAN", "input": {"order_id": "XYZ"}, "output": None,
         "startTime": "2026-09-21T10:00:10Z", "endTime": "2026-09-21T10:00:11Z",
         "usage": {"input": 120, "output": 40}, "level": "ERROR",
         "statusMessage": "OrderNotFound: no order 'XYZ'"},
    ],
}


def test_langsmith_import():
    t = from_langsmith(LANGSMITH_RUN)
    check("langsmith: 4 spans flattened", len(t.spans) == 4)
    check("langsmith: root is agent", t.spans[0].kind == "agent")
    check("langsmith: tools are tool kind",
          all(s.kind == "tool" for s in t.spans[1:]))
    check("langsmith: tokens parsed", t.total_tokens == 600 + 200 * 3)
    a = autopsy_trace(t)
    check("langsmith: loop detected after import", "tool_loop" in a.modes)


def test_langfuse_import():
    t = from_langfuse(LANGFUSE_TRACE)
    check("langfuse: 3 spans", len(t.spans) == 3)
    check("langfuse: root is agent", t.spans[0].kind == "agent")
    check("langfuse: errors carried over",
          sum(1 for s in t.spans if s.error) == 2)
    check("langfuse: error trace defaults to failed", t.status == "failed")
    a = autopsy_trace(t)
    check("langfuse: cascade detected after import", "error_cascade" in a.modes)


if __name__ == "__main__":
    test_langsmith_import()
    test_langfuse_import()
    print("All importer tests passed.")
