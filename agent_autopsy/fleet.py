"""Fleet analysis: one trace tells you what broke, many traces tell you what's broken."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .analyzer import autopsy_trace


@dataclass
class FleetReport:
    n_traces: int = 0
    n_failed: int = 0
    agents: list = field(default_factory=list)
    by_mode: Counter = field(default_factory=Counter)
    by_tool: Counter = field(default_factory=Counter)
    total_tokens: int = 0
    total_wasted_tokens: int = 0
    worst_traces: list = field(default_factory=list)  # (trace_id, wasted, modes)
    autopsies: list = field(default_factory=list)

    @property
    def failure_rate(self) -> float:
        return self.n_failed / self.n_traces if self.n_traces else 0.0

    @property
    def waste_rate(self) -> float:
        return self.total_wasted_tokens / self.total_tokens if self.total_tokens else 0.0


def autopsy_fleet(traces) -> FleetReport:
    report = FleetReport()
    for trace in traces:
        a = autopsy_trace(trace)
        report.autopsies.append(a)
        report.n_traces += 1
        if a.verdict == "failed":
            report.n_failed += 1
        if trace.agent not in report.agents:
            report.agents.append(trace.agent)
        report.by_mode.update(a.modes)
        report.total_tokens += a.total_tokens
        report.total_wasted_tokens += a.wasted_tokens
        for f in a.findings:
            for span_id in f.evidence:
                span = trace.span_by_id(span_id)
                if span and span.kind == "tool":
                    report.by_tool[span.name] += 1
        report.worst_traces.append((a.trace_id, a.wasted_tokens, a.modes))

    report.worst_traces.sort(key=lambda t: -t[1])
    report.worst_traces = report.worst_traces[:10]
    return report
