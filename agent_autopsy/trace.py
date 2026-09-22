"""Trace model: load and navigate agent execution traces."""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class Span:
    span_id: str
    parent_id: str | None
    name: str
    kind: str  # agent | llm | tool
    start_ms: float
    end_ms: float
    input: object = None
    output: object = None
    error: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def duration_ms(self) -> float:
        return self.end_ms - self.start_ms

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out


@dataclass
class Trace:
    trace_id: str
    agent: str
    version: str
    status: str  # ok | failed
    tools: list = field(default_factory=list)
    spans: list = field(default_factory=list)

    def ordered_spans(self) -> list:
        return sorted(self.spans, key=lambda s: s.start_ms)

    def llm_spans(self) -> list:
        return [s for s in self.ordered_spans() if s.kind == "llm"]

    def tool_spans(self) -> list:
        return [s for s in self.ordered_spans() if s.kind == "tool"]

    def span_by_id(self, span_id: str):
        for s in self.spans:
            if s.span_id == span_id:
                return s
        return None

    @property
    def total_tokens(self) -> int:
        return sum(s.tokens for s in self.spans)

    @property
    def duration_ms(self) -> float:
        if not self.spans:
            return 0.0
        return max(s.end_ms for s in self.spans) - min(s.start_ms for s in self.spans)

    @property
    def n_steps(self) -> int:
        return len([s for s in self.spans if s.kind in ("llm", "tool")])


def load_trace(path: str) -> Trace:
    with open(path) as f:
        raw = json.load(f)
    spans = [
        Span(
            span_id=s["span_id"],
            parent_id=s.get("parent_id"),
            name=s["name"],
            kind=s.get("kind", "tool"),
            start_ms=float(s.get("start_ms", 0)),
            end_ms=float(s.get("end_ms", 0)),
            input=s.get("input"),
            output=s.get("output"),
            error=s.get("error"),
            tokens_in=int(s.get("tokens_in", 0)),
            tokens_out=int(s.get("tokens_out", 0)),
        )
        for s in raw.get("spans", [])
    ]
    return Trace(
        trace_id=raw.get("trace_id", path),
        agent=raw.get("agent", "unknown"),
        version=raw.get("version", "unknown"),
        status=raw.get("status", "ok"),
        tools=raw.get("tools", []),
        spans=spans,
    )
