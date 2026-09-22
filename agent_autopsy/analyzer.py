"""Single-trace autopsy: run every detector, rank findings, compute waste."""
from __future__ import annotations

from dataclasses import dataclass, field

from .detectors import DETECTORS, Finding


@dataclass
class Autopsy:
    trace_id: str
    agent: str
    version: str
    status: str
    findings: list = field(default_factory=list)
    total_tokens: int = 0
    duration_ms: float = 0.0
    n_steps: int = 0
    verdict: str = "clean"  # clean | wasteful | failed
    root_cause: Finding | None = None
    wasted_tokens: int = 0

    @property
    def modes(self) -> list:
        return [f.mode for f in self.findings]


def autopsy_trace(trace) -> Autopsy:
    findings = []
    for detector in DETECTORS:
        try:
            found = detector(trace)
        except Exception:
            found = None
        if found:
            findings.append(found)

    # Rank: high severity first, then most wasted tokens.
    findings.sort(key=lambda f: (0 if f.severity == "high" else 1, -f.wasted_tokens))

    wasted = sum(f.wasted_tokens for f in findings)
    if trace.status == "failed" or any(f.severity == "high" for f in findings):
        verdict = "failed"
    elif findings:
        verdict = "wasteful"
    else:
        verdict = "clean"

    return Autopsy(
        trace_id=trace.trace_id,
        agent=trace.agent,
        version=trace.version,
        status=trace.status,
        findings=findings,
        total_tokens=trace.total_tokens,
        duration_ms=trace.duration_ms,
        n_steps=trace.n_steps,
        verdict=verdict,
        root_cause=findings[0] if findings else None,
        wasted_tokens=wasted,
    )
