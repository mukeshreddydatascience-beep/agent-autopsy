"""Importers: convert LangSmith / Langfuse exports into autopsy traces.

The core stays vendor-neutral on purpose. These converters sit at the edge:
export a trace from your observability tool, convert it once, then run the
full autopsy on it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .trace import Trace, Span


def _to_ms(value) -> float:
    """ISO timestamp or epoch seconds -> milliseconds."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) * 1000.0
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp() * 1000.0


# ---------------------------------------------------------------- LangSmith

def _langsmith_kind(run: dict, is_root: bool) -> str:
    if is_root:
        return "agent"
    run_type = (run.get("run_type") or "").lower()
    if run_type == "tool":
        return "tool"
    return "llm"  # llm, chain, prompt, retriever: planning/work steps


def _flatten_langsmith(run: dict, spans: list, is_root: bool = False):
    usage = ((run.get("extra") or {}).get("token_usage") or {})
    spans.append(Span(
        span_id=str(run.get("id", f"run-{len(spans)}")),
        parent_id=str(run.get("parent_run_id")) if run.get("parent_run_id") else None,
        name=str(run.get("name", "run")),
        kind=_langsmith_kind(run, is_root),
        start_ms=_to_ms(run.get("start_time")),
        end_ms=_to_ms(run.get("end_time")),
        input=run.get("inputs"),
        output=run.get("outputs"),
        error=run.get("error"),
        tokens_in=int(usage.get("prompt_tokens", 0) or 0),
        tokens_out=int(usage.get("completion_tokens", 0) or 0),
    ))
    for child in run.get("child_runs") or []:
        _flatten_langsmith(child, spans)


def from_langsmith(run: dict, status: str | None = None) -> Trace:
    """Convert a LangSmith run tree (API response or exported JSON) to a Trace.

    Accepts the run dict as returned by the LangSmith API: nested ``child_runs``,
    ``run_type`` per run, token usage under ``extra.token_usage``.
    """
    spans: list = []
    _flatten_langsmith(run, spans, is_root=True)
    tools = sorted({s.name for s in spans if s.kind == "tool"})
    if status is None:
        status = "failed" if any(s.error for s in spans) else "ok"
    return Trace(
        trace_id=str(run.get("id", "langsmith-import")),
        agent=str(run.get("name", "agent")),
        version=str((run.get("extra") or {}).get("version", "unknown")),
        status=status,
        tools=tools,
        spans=spans,
    )


# ---------------------------------------------------------------- Langfuse

def _langfuse_kind(obs: dict, is_root: bool) -> str:
    if is_root:
        return "agent"
    obs_type = (obs.get("type") or "").upper()
    if obs_type == "GENERATION":
        return "llm"
    return "tool"  # SPAN: tool calls, retrievals, sub-steps


def from_langfuse(trace: dict, status: str | None = None) -> Trace:
    """Convert a Langfuse trace export (with ``observations``) to a Trace.

    Observation types: GENERATION -> llm, SPAN -> tool. Observations with
    level ERROR count as errors; a trace with any error defaults to failed.
    """
    observations = trace.get("observations") or []

    spans: list = []
    for i, o in enumerate(observations):
        usage = o.get("usage") or {}
        level = (o.get("level") or "DEFAULT").upper()
        error = o.get("statusMessage") if level == "ERROR" else None
        is_root = not o.get("parentObservationId")
        spans.append(Span(
            span_id=str(o.get("id", f"obs-{i}")),
            parent_id=str(o.get("parentObservationId"))
            if o.get("parentObservationId") else None,
            name=str(o.get("name", "observation")),
            kind=_langfuse_kind(o, is_root),
            start_ms=_to_ms(o.get("startTime")),
            end_ms=_to_ms(o.get("endTime")),
            input=o.get("input"),
            output=o.get("output"),
            error=error,
            tokens_in=int(usage.get("input", 0) or 0),
            tokens_out=int(usage.get("output", 0) or 0),
        ))
    # If several parentless observations exist, none is "the" root: add one.
    if sum(1 for s in spans if s.kind == "agent") != 1:
        for s in spans:
            if s.kind == "agent":
                s.kind = "tool"
        spans.insert(0, Span(
            span_id=str(trace.get("id", "langfuse-import")) + "-root",
            parent_id=None, name=str(trace.get("name", "agent")),
            kind="agent",
            start_ms=min((s.start_ms for s in spans), default=0.0),
            end_ms=max((s.end_ms for s in spans), default=0.0),
        ))
    tools = sorted({s.name for s in spans if s.kind == "tool"})
    if status is None:
        status = "failed" if any(s.error for s in spans) else "ok"
    return Trace(
        trace_id=str(trace.get("id", "langfuse-import")),
        agent=str(trace.get("name", "agent")),
        version=str(trace.get("version", "unknown")),
        status=status,
        tools=tools,
        spans=spans,
    )


IMPORTERS = {"langsmith": from_langsmith, "langfuse": from_langfuse}
